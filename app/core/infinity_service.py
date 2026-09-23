from contextlib import contextmanager

from app.constants import GAME_ROUND_COUNT as ROUND_COUNT
from app.core.db import get_conn
from app.core.logging import get_logger, timing_scope
from app.core.game_mappers import map_completed_rounds, map_square
from app.core.game_queries import (
    find_exact_city_in_expansions,
    get_base_square_id_for_round,
    get_completed_round_rows,
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
    get_infinity_session_by_id,
    get_infinity_guess_city_ids,
    insert_infinity_guesses,
    update_current_round,
)
from app.core.guess_resolution import resolve_city_guess
from app.core.scoring import compute_score
from app.core.session_service import get_current_session
from app.core.side_missions.queries import get_side_mission_round
from app.core.side_missions.service import (
    ensure_side_mission_assignments,
    get_original_answer_city_id,
    load_side_mission_state,
)


_logger = get_logger('geosquare.infinity')


def _format_log_fields(fields: dict) -> str:
    return ' '.join(
        f'{key}={value}'
        for key, value in sorted(fields.items())
    )


@contextmanager
def _logged_step(
    operation: str,
    step: str,
    *,
    session_id: int | None = None,
    **fields,
):
    details = {}
    _logger.info('%s: %s started %s', operation, step, _format_log_fields(fields))
    timing_details = dict(fields)
    if session_id is not None:
        timing_details['session_id'] = session_id
    with timing_scope(
        f'{operation}: {step} completed',
        details=timing_details,
        session_id=session_id,
    ) as timing_node:
        try:
            yield details
        except Exception:
            timing_node.event_name = f'{operation}: {step} failed'
            _logger.exception(
                '%s: %s failed %s',
                operation,
                step,
                _format_log_fields(fields),
            )
            raise
        timing_details.update(details)


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


def _resolve_infinity_session(
    cur,
    user_id: int,
    session_id: int | None,
    infinity_pool_session_id: int | None,
):
    if infinity_pool_session_id is not None:
        infinity_session = get_infinity_session_by_id(
            cur,
            user_id,
            infinity_pool_session_id,
        )
        if infinity_session is None:
            raise LookupError('Infinity Pool not found.')
        return infinity_session

    daily_session = _require_completed_daily_session(cur, user_id, session_id)
    return _get_or_create_infinity_session(cur, user_id, int(daily_session.GameId))


def _map_guess(row) -> dict:
    return {
        'round_number': int(row.RoundNumber),
        'city_id': int(row.CityId),
        'city_name': row.CityName,
        'population': int(row.Population),
        'score': int(row.Score),
        'latitude': float(row.Latitude),
        'longitude': float(row.Longitude),
    }


def _map_incorrect_city(row) -> dict:
    return {
        'city_name': row.CityName,
        'country_code': row.CountryCode,
        'latitude': float(row.Latitude),
        'longitude': float(row.Longitude),
        'population': int(row.Population),
    }


def _load_guesses(cur, infinity_session_id: int) -> list[dict]:
    return [
        _map_guess(row)
        for row in get_infinity_guesses(cur, infinity_session_id)
    ]


def _load_daily_answers(cur, daily_session_id: int) -> list[dict]:
    completed_rounds = map_completed_rounds(
        get_completed_round_rows(cur, daily_session_id)
    )
    return [
        {
            'round_number': int(round_data['round_number']),
            'city_id': int(round_data['guesses'][0]['city_id']),
            'city_name': round_data['guesses'][0]['city_name'],
            'population': int(round_data['guesses'][0]['population']),
            'score': int(round_data['score']),
            'latitude': float(round_data['guesses'][0]['latitude']),
            'longitude': float(round_data['guesses'][0]['longitude']),
        }
        for round_data in completed_rounds
        if round_data['guesses']
    ]


def _map_scores(score_rows) -> dict[int, int]:
    scores = {round_number: 0 for round_number in range(1, ROUND_COUNT + 1)}
    for row in score_rows:
        scores[int(row.RoundNumber)] = int(row.RoundScore)
    return scores


def _add_daily_scores(scores: dict[int, int], daily_answers: list[dict]) -> None:
    for answer in daily_answers:
        scores[answer['round_number']] += answer['score']


def _load_base_square(cur, game_id: int, round_number: int) -> dict:
    square_id = get_base_square_id_for_round(cur, game_id, round_number)
    if square_id is None:
        raise LookupError(f'No base square found for round {round_number}.')
    square_row = get_square_by_id(cur, square_id)
    city_rows = get_square_cities(cur, square_id)
    city_count_row = get_square_city_count(cur, square_id)
    return map_square(square_row, city_rows, city_count_row, False)


def get_infinity_state(
    user_id: int,
    session_id: int | None,
    infinity_pool_session_id: int | None = None,
) -> tuple[dict, int]:
    operation = 'get_infinity_state'
    _logger.info('%s: started', operation)
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            with _logged_step(operation, 'load_infinity_session'):
                infinity_session = _resolve_infinity_session(
                    cur,
                    user_id,
                    session_id,
                    infinity_pool_session_id,
                )
        except LookupError as error:
            return {'error': str(error)}, 404
        except PermissionError as error:
            return {'error': str(error), 'unlocked': False}, 403

        game_id = int(infinity_session.GameId)
        infinity_session_id = int(infinity_session.InfinityPoolSessionId)
        daily_session = _require_completed_daily_session(cur, user_id, session_id)
        ensure_side_mission_assignments(cur, daily_session, infinity_session)
        infinity_session = get_infinity_session_by_id(
            cur,
            user_id,
            infinity_session_id,
        )
        round_number = int(infinity_session.CurrentRoundNumber)
        with _logged_step(
            operation,
            'load_guesses_and_daily_answers',
            infinity_session_id=infinity_session_id,
        ) as details:
            daily_answers = _load_daily_answers(cur, int(daily_session.SessionId))
            guesses = daily_answers + _load_guesses(cur, infinity_session_id)
            details['guess_count'] = len(guesses)
            details['daily_answer_count'] = len(daily_answers)
        with _logged_step(
            operation,
            'load_scores',
            infinity_session_id=infinity_session_id,
        ) as details:
            score_rows = get_infinity_scores(cur, infinity_session_id)
            details['score_row_count'] = len(score_rows)
            scores = _map_scores(score_rows)
            _add_daily_scores(scores, daily_answers)
        with _logged_step(
            operation,
            'load_square',
            game_id=game_id,
            round_number=round_number,
        ):
            square = _load_base_square(cur, game_id, round_number)
        with _logged_step(
            operation,
            'load_side_missions',
            infinity_session_id=infinity_session_id,
        ):
            side_missions = load_side_mission_state(cur, daily_session, infinity_session)
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
        'infinity_pool_session_id': infinity_session_id,
        'current_round': int(infinity_session.CurrentRoundNumber),
        'round_count': ROUND_COUNT,
        'round_scores': scores,
        'total_score': sum(scores.values()),
        'guesses': guesses,
        'square': square,
        'side_missions': side_missions,
    }, 200


def select_infinity_round(
    user_id: int,
    session_id: int | None,
    round_number: int,
    infinity_pool_session_id: int | None = None,
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
            with _logged_step(operation, 'load_infinity_session', round_number=round_number):
                infinity_session = _resolve_infinity_session(
                    cur,
                    user_id,
                    session_id,
                    infinity_pool_session_id,
                )
        except LookupError as error:
            return {'error': str(error)}, 404
        except PermissionError as error:
            return {'error': str(error), 'unlocked': False}, 403

        game_id = int(infinity_session.GameId)
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

    return {
        'infinity_pool_session_id': infinity_session_id,
        'current_round': round_number,
        'square': square,
    }, 200


def submit_infinity_guess(
    payload: dict,
    user_id: int,
    session_id: int | None,
    mode: str,
) -> tuple[dict, int]:
    operation = 'submit_infinity_guess'
    is_reveal = 'reveal_city_id' in payload
    if 'round_number' not in payload:
        return {'error': 'round_number is required.'}, 400

    if is_reveal:
        guess_text = None
    else:
        if 'guess' not in payload:
            return {'error': 'Guess is required.'}, 400
        guess_text = payload['guess'].strip()
        if not guess_text:
            return {'error': 'Guess is required.'}, 400
    round_number = int(payload['round_number'])
    if mode not in {'infinity', 'side_missions'}:
        return {'error': 'Invalid game mode.'}, 400
    confirmed_city_id = payload.get('confirmed_city_id')
    infinity_pool_session_id = payload.get('infinity_pool_session_id')
    if infinity_pool_session_id is not None:
        infinity_pool_session_id = int(infinity_pool_session_id)
    try:
        _require_round_number(round_number)
    except ValueError as error:
        return {'error': str(error)}, 400

    _logger.info('%s: started round_number=%s', operation, round_number)
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            with _logged_step(operation, 'load_infinity_session', round_number=round_number):
                infinity_session = _resolve_infinity_session(
                    cur,
                    user_id,
                    session_id,
                    infinity_pool_session_id,
                )
        except LookupError as error:
            return {'error': str(error)}, 404
        except PermissionError as error:
            return {'error': str(error), 'unlocked': False}, 403

        game_id = int(infinity_session.GameId)
        infinity_session_id = int(infinity_session.InfinityPoolSessionId)
        daily_session = _require_completed_daily_session(cur, user_id, session_id)
        if mode == 'side_missions':
            mission_round = get_side_mission_round(cur, infinity_session_id, round_number)
            if mission_round is None:
                return {'error': 'Side missions have not been started.'}, 409
            if mission_round.CompletedAt is not None:
                return {'error': 'This side mission is complete.'}, 409
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

        if is_reveal:
            reveal_city_id = int(payload['reveal_city_id'])
            guessed_city_ids = {
                int(guess.CityId)
                for guess in get_infinity_guesses(cur, infinity_session_id)
                if int(guess.RoundNumber) == round_number
            }
            unnamed_cities = [
                city for city in ranked_cities
                if int(city.CityId) not in guessed_city_ids
            ]
            matched_rows = [
                city for city in unnamed_cities
                if int(city.CityId) == reveal_city_id
            ]
            if (
                not matched_rows
                or int(matched_rows[0].Population) != int(unnamed_cities[0].Population)
            ):
                return {'error': 'Reveal city must be the largest unnamed city.'}, 409
        else:
            with _logged_step(
                operation,
                'load_nearby_exact_match',
                game_id=game_id,
                round_number=round_number,
            ):
                nearby_exact_match = find_exact_city_in_expansions(
                    cur,
                    game_id,
                    round_number,
                    0,
                    guess_text,
                )
            with _logged_step(
                operation,
                'match_guess',
                session_id=int(daily_session.SessionId),
                infinity_session_id=infinity_session_id,
                round_number=round_number,
                guess_text=guess_text,
                ranked_city_count=len(ranked_cities),
                confirmed_city_id=confirmed_city_id,
                has_nearby_exact_match=nearby_exact_match is not None,
            ) as details:
                result = resolve_city_guess(
                    ranked_cities,
                    guess_text=guess_text,
                    confirmed_city_id=confirmed_city_id,
                    nearby_exact_match=nearby_exact_match,
                    expansion_level=0,
                )
                details['result_type'] = result.get('type')
            result_type = result.get('type')
            if result_type == 'invalid_confirmation':
                return {'error': 'Invalid confirmation selection.'}, 400
            if result_type == 'no_match':
                response = {'ok': True, 'correct': False, 'score': 0}
                if 'nearby_exact_match' in result:
                    response['matched_city'] = _map_incorrect_city(
                        result['nearby_exact_match']
                    )
                return response, 200
            if result_type == 'match':
                matched_rows = [result['row']]
            elif result_type == 'confirmation_required':
                response = {
                    'ok': True,
                    'requires_confirmation': True,
                    'candidates': result['suggestions'],
                    'guess': guess_text,
                }
                if 'nearby_exact_match' in result:
                    response['nearby_city'] = _map_incorrect_city(result['nearby_exact_match'])
                return response, 200
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
        original_answer_city_id = get_original_answer_city_id(
            cur,
            daily_session,
            infinity_session_id,
            round_number,
        )
        with _logged_step(
            operation,
            'check_duplicates',
            candidate_count=len(matched_rows),
            infinity_session_id=infinity_session_id,
            round_number=round_number,
        ):
            duplicate_city_ids = get_infinity_guess_city_ids(
                cur,
                infinity_session_id,
                round_number,
            )
        guesses_to_insert = []
        for matched in matched_rows:
            city_id = int(matched.CityId)
            if city_id == original_answer_city_id:
                duplicate_cities.append(matched.CityName)
                continue
            if city_id in duplicate_city_ids:
                duplicate_cities.append(matched.CityName)
                continue

            score = 0 if is_reveal else compute_score(
                ranked_cities,
                int(matched.Population),
            )
            guesses_to_insert.append((
                infinity_session_id,
                round_number,
                square_id,
                city_id,
                matched.CityName,
                int(matched.Population),
                score,
            ))
            duplicate_city_ids.add(city_id)
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
        if guesses_to_insert:
            with _logged_step(
                operation,
                'insert_guesses',
                guess_count=len(guesses_to_insert),
                infinity_session_id=infinity_session_id,
                round_number=round_number,
            ):
                insert_infinity_guesses(cur, guesses_to_insert)

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
            daily_answers = _load_daily_answers(cur, int(daily_session.SessionId))
            _add_daily_scores(scores, daily_answers)
        with _logged_step(
            operation,
            'update_side_mission_progress',
            infinity_session_id=infinity_session_id,
            round_number=round_number,
        ):
            side_missions = load_side_mission_state(cur, daily_session, infinity_session)
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
                'side_missions': side_missions,
    }, 200