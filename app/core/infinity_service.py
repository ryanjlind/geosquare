from contextlib import contextmanager
import logging
from time import perf_counter

from app.core.db import get_conn
from app.core.game_mappers import map_square
from app.core.game_queries import (
    get_base_square_id_for_round,
    get_ranked_square_cities,
    get_square_by_id,
    get_square_cities,
    get_square_city_count,
)
from app.core.infinity_queries import (
    create_infinity_session,
    get_infinity_guesses,
    get_infinity_scores,
    get_infinity_session,
    infinity_guess_exists,
    insert_infinity_guess,
    update_current_round,
)
from app.core.matching import find_matching_city
from app.core.scoring import compute_score
from app.core.session_service import get_current_session


ROUND_COUNT = 5

_logger = logging.getLogger('geosquare.infinity')


def _format_log_fields(fields: dict) -> str:
    return ' '.join(
        f'{key}={value}'
        for key, value in sorted(fields.items())
    )


@contextmanager
def _logged_step(operation: str, step: str, **fields):
    started_at = perf_counter()
    details = {}
    _logger.info('%s: %s started %s', operation, step, _format_log_fields(fields))
    try:
        yield details
    except Exception:
        _logger.exception(
            '%s: %s failed elapsed_ms=%.1f %s',
            operation,
            step,
            (perf_counter() - started_at) * 1000.0,
            _format_log_fields(fields),
        )
        raise
    completed_fields = {**fields, **details}
    _logger.info(
        '%s: %s completed elapsed_ms=%.1f %s',
        operation,
        step,
        (perf_counter() - started_at) * 1000.0,
        _format_log_fields(completed_fields),
    )


def _require_round_number(round_number: int) -> None:
    if not 1 <= round_number <= ROUND_COUNT:
        raise ValueError(f'round_number must be between 1 and {ROUND_COUNT}.')


def _require_completed_daily_session(cur, user_id: int, session_id: int | None):
    daily_session = get_current_session(cur, user_id, session_id)
    if daily_session is None:
        raise LookupError('No game found for today.')
    if daily_session.CompletedAt is None:
        raise PermissionError('Complete the Daily game to unlock Infinity Pool.')
    return daily_session


def _get_or_create_infinity_session(cur, user_id: int, game_id: int):
    infinity_session = get_infinity_session(cur, user_id, game_id)
    if infinity_session is not None:
        return infinity_session
    return create_infinity_session(cur, user_id, game_id)


def _map_guess(row) -> dict:
    return {
        'round_number': int(row.RoundNumber),
        'city_name': row.CityName,
        'score': int(row.Score),
        'latitude': float(row.Latitude),
        'longitude': float(row.Longitude),
    }


def _load_guesses(cur, infinity_session_id: int) -> list[dict]:
    return [
        _map_guess(row)
        for row in get_infinity_guesses(cur, infinity_session_id)
    ]


def _map_scores(score_rows) -> dict[int, int]:
    scores = {round_number: 0 for round_number in range(1, ROUND_COUNT + 1)}
    for row in score_rows:
        scores[int(row.RoundNumber)] = int(row.RoundScore)
    return scores


def _load_base_square(cur, game_id: int, round_number: int) -> dict:
    square_id = get_base_square_id_for_round(cur, game_id, round_number)
    if square_id is None:
        raise LookupError(f'No base square found for round {round_number}.')
    square_row = get_square_by_id(cur, square_id)
    city_rows = get_square_cities(cur, square_id)
    city_count_row = get_square_city_count(cur, square_id)
    return map_square(square_row, city_rows, city_count_row, False)


def get_infinity_state(user_id: int, session_id: int | None) -> tuple[dict, int]:
    operation = 'get_infinity_state'
    _logger.info('%s: started', operation)
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            with _logged_step(operation, 'load_completed_daily_session'):
                daily_session = _require_completed_daily_session(cur, user_id, session_id)
        except LookupError as error:
            return {'error': str(error)}, 404
        except PermissionError as error:
            return {'error': str(error), 'unlocked': False}, 403

        game_id = int(daily_session.GameId)
        with _logged_step(operation, 'load_infinity_session', game_id=game_id):
            infinity_session = _get_or_create_infinity_session(cur, user_id, game_id)
        infinity_session_id = int(infinity_session.InfinityPoolSessionId)
        round_number = int(infinity_session.CurrentRoundNumber)
        with _logged_step(
            operation,
            'load_guesses',
            infinity_session_id=infinity_session_id,
        ) as details:
            guesses = _load_guesses(cur, infinity_session_id)
            details['guess_count'] = len(guesses)
        with _logged_step(
            operation,
            'load_scores',
            infinity_session_id=infinity_session_id,
        ) as details:
            score_rows = get_infinity_scores(cur, infinity_session_id)
            details['score_row_count'] = len(score_rows)
            scores = _map_scores(score_rows)
        with _logged_step(
            operation,
            'load_square',
            game_id=game_id,
            round_number=round_number,
        ):
            square = _load_base_square(cur, game_id, round_number)
        with _logged_step(operation, 'commit', infinity_session_id=infinity_session_id):
            conn.commit()

    _logger.info(
        '%s: completed infinity_session_id=%s guess_count=%s',
        operation,
        infinity_session_id,
        len(guesses),
    )

    return {
        'unlocked': True,
        'current_round': int(infinity_session.CurrentRoundNumber),
        'round_count': ROUND_COUNT,
        'round_scores': scores,
        'total_score': sum(scores.values()),
        'guesses': guesses,
        'square': square,
    }, 200


def select_infinity_round(
    user_id: int,
    session_id: int | None,
    round_number: int,
) -> tuple[dict, int]:
    operation = 'select_infinity_round'
    _logger.info('%s: started round_number=%s', operation, round_number)
    try:
        _require_round_number(round_number)
    except ValueError as error:
        return {'error': str(error)}, 400
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            with _logged_step(operation, 'load_completed_daily_session', round_number=round_number):
                daily_session = _require_completed_daily_session(cur, user_id, session_id)
        except LookupError as error:
            return {'error': str(error)}, 404
        except PermissionError as error:
            return {'error': str(error), 'unlocked': False}, 403

        game_id = int(daily_session.GameId)
        with _logged_step(operation, 'load_infinity_session', game_id=game_id):
            infinity_session = _get_or_create_infinity_session(cur, user_id, game_id)
        infinity_session_id = int(infinity_session.InfinityPoolSessionId)
        with _logged_step(
            operation,
            'update_current_round',
            infinity_session_id=infinity_session_id,
            round_number=round_number,
        ):
            update_current_round(cur, infinity_session_id, round_number)
        with _logged_step(
            operation,
            'load_square',
            game_id=game_id,
            round_number=round_number,
        ):
            square = _load_base_square(cur, game_id, round_number)
        with _logged_step(operation, 'commit', infinity_session_id=infinity_session_id):
            conn.commit()

    _logger.info(
        '%s: completed infinity_session_id=%s round_number=%s',
        operation,
        infinity_session_id,
        round_number,
    )

    return {'current_round': round_number, 'square': square}, 200


def submit_infinity_guess(
    payload: dict,
    user_id: int,
    session_id: int | None,
) -> tuple[dict, int]:
    operation = 'submit_infinity_guess'
    if 'guess' not in payload:
        return {'error': 'Guess is required.'}, 400
    if 'round_number' not in payload:
        return {'error': 'round_number is required.'}, 400

    guess_text = payload['guess'].strip()
    round_number = int(payload['round_number'])
    if not guess_text:
        return {'error': 'Guess is required.'}, 400
    try:
        _require_round_number(round_number)
    except ValueError as error:
        return {'error': str(error)}, 400

    _logger.info('%s: started round_number=%s', operation, round_number)
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            with _logged_step(operation, 'load_completed_daily_session', round_number=round_number):
                daily_session = _require_completed_daily_session(cur, user_id, session_id)
        except LookupError as error:
            return {'error': str(error)}, 404
        except PermissionError as error:
            return {'error': str(error), 'unlocked': False}, 403

        game_id = int(daily_session.GameId)
        with _logged_step(operation, 'load_infinity_session', game_id=game_id):
            infinity_session = _get_or_create_infinity_session(cur, user_id, game_id)
        infinity_session_id = int(infinity_session.InfinityPoolSessionId)
        with _logged_step(
            operation,
            'load_base_square_id',
            game_id=game_id,
            round_number=round_number,
        ):
            square_id = get_base_square_id_for_round(cur, game_id, round_number)
        if square_id is None:
            return {'error': f'No base square found for round {round_number}.'}, 404
        with _logged_step(
            operation,
            'load_ranked_cities',
            square_id=square_id,
        ) as details:
            ranked_cities = get_ranked_square_cities(cur, square_id)
            details['city_count'] = len(ranked_cities)

        with _logged_step(
            operation,
            'match_guess',
            infinity_session_id=infinity_session_id,
            round_number=round_number,
        ) as details:
            result = find_matching_city(
                ranked_cities,
                guess_text,
                nearby_exact_match=None,
                current_expansion_level=0,
            )
            details['result_type'] = result.get('type')
        result_type = result.get('type')
        if result_type == 'no_match':
            return {'ok': True, 'correct': False, 'score': 0}, 200
        if result_type == 'match':
            matched_rows = [result['row']]
        elif result_type == 'confirmation_required':
            rows_by_city_id = {
                int(row.CityId): row
                for row in ranked_cities
            }
            matched_rows = [
                rows_by_city_id[int(suggestion['city_id'])]
                for suggestion in result['suggestions']
            ]
        else:
            return {'error': 'Invalid match result.'}, 500
        _logger.info(
            '%s: accepting candidates candidate_count=%s infinity_session_id=%s round_number=%s',
            operation,
            len(matched_rows),
            infinity_session_id,
            round_number,
        )

        added_guesses = []
        duplicate_cities = []
        for matched in matched_rows:
            city_id = int(matched.CityId)
            with _logged_step(
                operation,
                'check_duplicate',
                city_id=city_id,
                infinity_session_id=infinity_session_id,
                round_number=round_number,
            ):
                duplicate = infinity_guess_exists(
                    cur,
                    infinity_session_id,
                    round_number,
                    city_id,
                )
            if duplicate:
                duplicate_cities.append(matched.CityName)
                continue

            score = compute_score(ranked_cities, int(matched.Population))
            with _logged_step(
                operation,
                'insert_guess',
                city_id=city_id,
                infinity_session_id=infinity_session_id,
                round_number=round_number,
            ):
                insert_infinity_guess(
                    cur,
                    infinity_session_id,
                    round_number,
                    square_id,
                    city_id,
                    matched.CityName,
                    int(matched.Population),
                    score,
                )
            added_guesses.append({
                'city': matched.CityName,
                'city_id': city_id,
                'country_code': matched.CountryCode,
                'latitude': float(matched.Latitude),
                'longitude': float(matched.Longitude),
                'population': int(matched.Population),
                'rank': int(matched.PopRank),
                'score': score,
            })

        if not added_guesses:
            return {
                'ok': True,
                'correct': True,
                'duplicate': True,
                'duplicates': duplicate_cities,
            }, 200

        with _logged_step(
            operation,
            'update_current_round',
            infinity_session_id=infinity_session_id,
            round_number=round_number,
        ):
            update_current_round(cur, infinity_session_id, round_number)
        with _logged_step(
            operation,
            'load_scores',
            infinity_session_id=infinity_session_id,
        ) as details:
            score_rows = get_infinity_scores(cur, infinity_session_id)
            details['score_row_count'] = len(score_rows)
            scores = _map_scores(score_rows)
        with _logged_step(operation, 'commit', infinity_session_id=infinity_session_id):
            conn.commit()

    _logger.info(
        '%s: completed added_count=%s duplicate_count=%s infinity_session_id=%s round_number=%s',
        operation,
        len(added_guesses),
        len(duplicate_cities),
        infinity_session_id,
        round_number,
    )

    return {
        'ok': True,
        'correct': True,
        'duplicate': False,
        'guesses': added_guesses,
        'duplicates': duplicate_cities,
        'round_score': scores[round_number],
        'total_score': sum(scores.values()),
    }, 200