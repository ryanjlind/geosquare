from datetime import date

from app.core.db import get_conn
from app.core.game_queries import (
    complete_session,
    create_session,
    get_completed_round_rows,
    get_or_create_session_round,
    get_ranked_square_cities,
    get_session_by_id,
    get_session_total_score,
    get_square_cities,
    get_square_city_count,
    get_square_for_round,
    get_square_id_for_round,
    get_today_game,
    increment_session_round_score,
    increment_session_total_score,
    insert_correct_guess,    
    find_city_anywhere,
    get_best_guess_for_user,
    get_completed_sessions_for_user,
    get_round_stats_for_sessions
)
from app.core.matching import find_matching_city
from app.core.scoring import compute_score
from app.core.user_queries import create_user, get_user_by_id
from app.helpers.date import get_effective_game_date
from app.helpers.session import get_session_id_from_cookie, get_user_id_from_cookie


def _require_today_game(cur):
    today_game = get_today_game(cur)
    if today_game is None:
        return None
    return int(today_game.GameId)


def _get_current_session(cur, user_id: int, session_id: int | None):
    game_id = _require_today_game(cur)
    if game_id is None:
        return None

    if session_id is None:
        return None

    session = get_session_by_id(cur, session_id)
    if session is None:
        return None

    if int(session.UserId) != user_id:
        return None

    if int(session.GameId) != game_id:
        return None

    return session


def resolve_request_identity() -> dict:
    with get_conn() as conn:
        cur = conn.cursor()

        cookie_user_id = get_user_id_from_cookie()
        cookie_session_id = get_session_id_from_cookie()

        user = None
        if cookie_user_id is not None:
            user = get_user_by_id(cur, cookie_user_id)

        if user is None:
            user = create_user(cur)
            print(f'[DEBUG] identity created_user_id={int(user.UserId)}', flush=True)

        user_id = int(user.UserId)
        game_id = _require_today_game(cur)

        session = None

        if game_id is not None and cookie_session_id is not None:
            session = get_session_by_id(cur, cookie_session_id)

            if session is not None:
                if int(session.UserId) != user_id:
                    session = None
                elif int(session.GameId) != game_id:
                    session = None

        if game_id is not None and session is None:
            session = create_session(cur, user_id, game_id)
            print(f'[DEBUG] identity created_session_id={int(session.SessionId)} user_id={user_id} game_id={game_id}', flush=True)

        conn.commit()

        return {
            'user_id': user_id,
            'session_id': int(session.SessionId) if session is not None else None,
        }


def _build_completed_rounds(rows):
    completed_rounds_by_number = {}

    for row in rows:
        round_number = int(row.RoundNumber)

        if round_number not in completed_rounds_by_number:
            completed_rounds_by_number[round_number] = {
                'session_round_id': int(row.SessionRoundId),
                'round_number': round_number,
                'square_id': int(row.SquareId),
                'score': int(row.Score),
                'guesses': [],
            }

        if row.CityName is not None:
            completed_rounds_by_number[round_number]['guesses'].append({
                'city_name': row.CityName,                
                'population': int(row.Population) if row.Population is not None else None,
                'score': int(row.GuessScore),
                'rank': int(row.PopRank) if row.PopRank is not None else None,
                'guessed_at': row.GuessedAt.isoformat(),
            })

    return list(completed_rounds_by_number.values())


def get_daily_square_data(round_number: int) -> dict:
    with get_conn() as conn:
        cur = conn.cursor()

        game_id = _require_today_game(cur)
        row = get_square_for_round(cur, game_id, round_number)
        cities_rows = get_square_cities(cur, int(row.SquareId))
        city_count_row = get_square_city_count(cur, int(row.SquareId))

        cities = [
            {
                'city_name': city.CityName,
                'country_code': city.CountryCode,
                'latitude': float(city.Latitude),
                'longitude': float(city.Longitude),
                'population': int(city.Population),
            }
            for city in cities_rows
        ]

        return {
            'square_id': int(row.SquareId),
            'config_key': row.ConfigKey,
            'seed': {'lat': float(row.SeedLat), 'lon': float(row.SeedLon)},
            'bounds': {
                'min_lat': float(row.MinLat),
                'min_lon': float(row.MinLon),
                'max_lat': float(row.MaxLat),
                'max_lon': float(row.MaxLon),
            },
            'total_population': int(row.TotalPopulation),
            'qualifying_city_count': int(row.QualifyingCityCount),
            'width_degrees': float(row.WidthDegrees),
            'height_degrees': float(row.HeightDegrees),
            'generated_at': row.GeneratedAt.isoformat(),
            'rules': {
                'min_total_population': int(row.MinTotalPopulation),
                'min_city_count': int(row.MinCityCount),
                'min_city_population': int(row.MinCityPopulation),
                'max_square_width_degrees': float(row.MaxSquareWidthDegrees),
                'max_square_height_degrees': float(row.MaxSquareHeightDegrees),
                'step_degrees': float(row.StepDegrees),
            },
            'cities': cities,
            'total_city_count': int(city_count_row.TotalCityCount),
            'largest_city': cities[0],
            'round_number': int(row.RoundNumber),
            'game_id': int(row.GameId),
        }


def submit_guess(payload: dict, user_id: int, session_id: int | None) -> tuple[dict, int]:
    guess_text = (payload.get('guess') or '').strip()
    round_number = int(payload.get('round_number', 1))

    if not guess_text:
        return {'error': 'Guess is required.'}, 400

    with get_conn() as conn:
        cur = conn.cursor()

        session = _get_current_session(cur, user_id, session_id)
        if not session:
            return {'error': 'No game found for today.'}, 404

        game_id = int(session.GameId)
        square_row = get_square_id_for_round(cur, game_id, round_number)

        if not square_row:
            return {'error': 'No square found for that round.'}, 404

        square_id = int(square_row.SquareId)

        rows = get_ranked_square_cities(cur, square_id)
        matched_city = find_matching_city(rows, guess_text)

        if matched_city:
            session_id = int(session.SessionId)
            session_round = get_or_create_session_round(cur, session_id, round_number, square_id)
            session_round_id = int(session_round.SessionRoundId)

            city_name = matched_city.CityName
            population = int(matched_city.Population)
            score = compute_score(rows, population)

            insert_correct_guess(cur, session_round_id, city_name, population, score)
            increment_session_round_score(cur, session_round_id, score)
            increment_session_total_score(cur, session_id, score)

            updated_session = get_session_total_score(cur, session_id)

            if round_number == 5:
                complete_session(cur, session_id)

            conn.commit()

            return {
                'ok': True,
                'correct': True,
                'city': matched_city.CityName,
                'country_code': matched_city.CountryCode,
                'latitude': float(matched_city.Latitude),
                'longitude': float(matched_city.Longitude),
                'population': population,
                'score': score,
                'rank': int(matched_city.PopRank),
                'total_score': int(updated_session.TotalScore),
            }, 200

        nearby_city = find_city_anywhere(cur, guess_text)
        conn.commit()

        return {
            'ok': True,
            'correct': False,
            'city': guess_text,
            'score': 0,
            'total_score': int(session.TotalScore),
            'matched_city': {
                'city_name': nearby_city.CityName,
                'country_code': nearby_city.CountryCode,
                'latitude': float(nearby_city.Latitude),
                'longitude': float(nearby_city.Longitude),
                'population': int(nearby_city.Population),
            } if nearby_city else None,
        }, 200
    
def submit_pass(payload: dict, user_id: int, session_id: int | None) -> tuple[dict, int]:
    round_number = int(payload.get('round_number', 1))

    with get_conn() as conn:
        cur = conn.cursor()

        session = _get_current_session(cur, user_id, session_id)
        if not session:
            return {'error': 'No game found for today.'}, 404

        game_id = int(session.GameId)
        square_row = get_square_id_for_round(cur, game_id, round_number)

        if not square_row:
            return {'error': 'No square found for that round.'}, 404

        square_id = int(square_row.SquareId)
        session_id = int(session.SessionId)

        get_or_create_session_round(cur, session_id, round_number, square_id)
        rows = get_ranked_square_cities(cur, square_id)
        largest_city = rows[0] if rows else None

        if round_number == 5:
            complete_session(cur, session_id)

        conn.commit()

        return {
            'ok': True,
            'passed': True,
            'round_number': round_number,
            'score': 0,
            'largest_city': {
                'city_name': largest_city.CityName,
                'country_code': largest_city.CountryCode,
                'latitude': float(largest_city.Latitude),
                'longitude': float(largest_city.Longitude),
                'population': int(largest_city.Population),
                'rank': int(largest_city.PopRank),
            } if largest_city else None,
        }, 200


def get_game_state_payload(user_id: int, session_id: int | None) -> tuple[dict, int]:
    with get_conn() as conn:
        cur = conn.cursor()

        game_id = _require_today_game(cur)
        if game_id is None:
            return {'error': 'No game found for today.'}, 404

        print(f'[DEBUG] game_state game_id={game_id}', flush=True)

        session = _get_current_session(cur, user_id, session_id)
        print(
            f'[DEBUG] game_state session_id={int(session.SessionId) if session else None} '
            f'session_game_id={int(session.GameId) if session else None} '
            f'completed_at={session.CompletedAt if session else None}',
            flush=True,
        )

        if session is None:
            return {'error': 'No game found for today.'}, 404

        completed_rounds = _build_completed_rounds(get_completed_round_rows(cur, int(session.SessionId)))

        print(
            f'[DEBUG] game_state completed_round_count={len(completed_rounds)} '
            f'completed_round_numbers={[round_data["round_number"] for round_data in completed_rounds]}',
            flush=True,
        )

        print(completed_rounds)
        is_perfect = len(completed_rounds) == all(r.get('city_name') is not None for r in completed_rounds)

        if session.CompletedAt is not None:
            latest_round_number = completed_rounds[-1]['round_number'] if completed_rounds else 1
            conn.commit()
            
            return {
                'state': 'completed',
                'session_id': int(session.SessionId),
                'user_id': int(session.UserId),
                'game_id': int(session.GameId),
                'round_number': latest_round_number,
                'total_score': int(session.TotalScore),
                'completed_at': session.CompletedAt.isoformat(),
                'completed_rounds': completed_rounds,
                'is_perfect': is_perfect,
            }, 200

        if len(completed_rounds) == 0:
            conn.commit()

            return {
                'state': 'not_started',
                'session_id': int(session.SessionId),
                'user_id': int(session.UserId),
                'game_id': int(session.GameId),
                'round_number': 1,
                'total_score': int(session.TotalScore),
                'completed_at': None,
                'completed_rounds': [],
                'is_perfect': False,
            }, 200

        next_round = completed_rounds[-1]['round_number'] + 1
        conn.commit()

        return {
            'state': 'in_progress',
            'session_id': int(session.SessionId),
            'user_id': int(session.UserId),
            'game_id': int(session.GameId),
            'round_number': next_round,
            'total_score': int(session.TotalScore),
            'completed_at': None,
            'completed_rounds': completed_rounds,
            'is_perfect': is_perfect,
        }, 200
    
def _compute_streaks(game_dates):
    if not game_dates:
        return 0, 0

    unique_dates = sorted(set(game_dates))

    longest_streak = 1
    current_run = 1

    for i in range(1, len(unique_dates)):
        if (unique_dates[i] - unique_dates[i - 1]).days == 1:
            current_run += 1
        else:
            if current_run > longest_streak:
                longest_streak = current_run
            current_run = 1

    if current_run > longest_streak:
        longest_streak = current_run

    current_streak = 1
    for i in range(len(unique_dates) - 1, 0, -1):
        if (unique_dates[i] - unique_dates[i - 1]).days == 1:
            current_streak += 1
        else:
            break

    return current_streak, longest_streak


def get_player_stats_payload(user_id: int) -> tuple[dict, int]:
    through_game_date = get_effective_game_date()

    with get_conn() as conn:
        cur = conn.cursor()

        sessions = get_completed_sessions_for_user(cur, user_id, through_game_date)
        best_guess = get_best_guess_for_user(cur, user_id, through_game_date)

        if not sessions:
            conn.commit()
            return {
                'games_played': 0,
                'current_streak': 0,
                'longest_streak': 0,
                'perfect_days': 0,
                'perfect_streak': 0,
                'average_score': 0,
                'best_score': 0,
                'best_score_game_date': None,
                'last_score': 0,
                'last_game_date': None,
                'graph_points': [],
                'best_guess': None,
            }, 200

        session_ids = [int(row.SessionId) for row in sessions]
        round_stats = get_round_stats_for_sessions(cur, session_ids)

        scores = [int(row.TotalScore) for row in sessions]
        game_dates = [row.GameDate for row in sessions]

        games_played = len(scores)
        average_score = round(sum(scores) / games_played)

        current_streak, longest_streak = _compute_streaks(game_dates)

        perfect_days = 0
        perfect_streak = 0
        solved_counts_by_session_id = {}
        perfect_flags = []

        for row in sessions:
            round_stat = round_stats.get(int(row.SessionId))
            solved_rounds = int(round_stat['solved_rounds']) if round_stat else 0
            total_rounds = int(round_stat['total_rounds']) if round_stat else 0

            solved_counts_by_session_id[int(row.SessionId)] = solved_rounds

            is_perfect = total_rounds > 0 and solved_rounds == total_rounds
            perfect_flags.append(is_perfect)

            if is_perfect:
                perfect_days += 1

        for is_perfect in reversed(perfect_flags):
            if not is_perfect:
                break
            perfect_streak += 1

        best_score_index = max(range(len(sessions)), key=lambda i: int(sessions[i].TotalScore))
        best_score = int(sessions[best_score_index].TotalScore)
        best_score_game_date = sessions[best_score_index].GameDate.isoformat()
        last_score = int(sessions[-1].TotalScore)
        last_game_date = sessions[-1].GameDate.isoformat()

        graph_points = []

        for row in sessions[-20:]:
            rs = round_stats.get(row.SessionId)

            solved = int(rs['solved_rounds']) if rs else 0
            total = int(rs['total_rounds']) if rs else 0

            graph_points.append({
                'game_date': row.GameDate.isoformat(),
                'solved': solved,
                'points': int(row.TotalScore),
                'is_perfect': solved == total
            })

        conn.commit()

        return {
            'games_played': games_played,
            'current_streak': current_streak,
            'longest_streak': longest_streak,
            'perfect_days': perfect_days,
            'perfect_streak': perfect_streak,
            'average_score': average_score,
            'best_score': best_score,
            'best_score_game_date': best_score_game_date,
            'last_score': last_score,
            'last_game_date': last_game_date,
            'graph_points': graph_points,
            'best_guess': {
                'city_name': best_guess.CityName,
                'population': int(best_guess.Population) if best_guess.Population is not None else None,
                'score': int(best_guess.Score),
                'game_date': best_guess.GameDate.isoformat(),
                'round_number': int(best_guess.RoundNumber),
            } if best_guess else None,
        }, 200