from datetime import date
from time import perf_counter

from app.core.db import get_conn
from app.core.game_queries import (
    complete_session,
    create_session,
    get_completed_round_rows,
    get_session_round,
    create_session_round,
    get_ranked_square_cities,    
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
    get_round_stats_for_sessions,
    get_game_id_by_date,
    has_next_expansion_level
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

    # 1. If cookie session_id exists and is valid, use it
    if session_id is not None:
        cur.execute(
            """
            SELECT SessionId, GameId, UserId, CompletedAt, TotalScore
            FROM GameSessions
            WHERE SessionId = ?
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if row and int(row.UserId) == user_id and int(row.GameId) == game_id:
            return row

    # 2. Otherwise: find the single best existing session for this user/game
    cur.execute(
        """
        SELECT SessionId, GameId, UserId, CompletedAt, TotalScore
        FROM GameSessions
        WHERE UserId = ? AND GameId = ?
        ORDER BY
            CASE WHEN CompletedAt IS NOT NULL THEN 0 ELSE 1 END,
            StartedAt DESC
        """,
        (user_id, game_id),
    )
    rows = cur.fetchall()

    if rows:
        # pick the best one (completed first, else latest in-progress)
        return rows[0]

    # 3. Only create if NONE exist
    cur.execute(
        """
        INSERT INTO GameSessions (UserId, GameId)
        OUTPUT INSERTED.SessionId, INSERTED.GameId, INSERTED.UserId, INSERTED.CompletedAt, INSERTED.TotalScore
        VALUES (?, ?)
        """,
        (user_id, game_id),
    )
    return cur.fetchone()

def resolve_request_identity() -> dict:
    with get_conn() as conn:
        cur = conn.cursor()
        
        cookie_user_id = get_user_id_from_cookie()
        cookie_session_id = get_session_id_from_cookie()

        user = None
        print(f"user={user}")        
        if cookie_user_id is not None:
            user = get_user_by_id(cur, cookie_user_id)

        print(f"user={user}")
        if user is None:
            user = create_user(cur)
            print(f'[DEBUG] identity created_user_id={int(user.UserId)}', flush=True)

        user_id = int(user.UserId)
        game_id = _require_today_game(cur)
        print(f"user_id={user_id}, game_id={game_id}")
        session = None

        if game_id is not None and session is None:
            # NEW: if authenticated, try to recover existing session
            cur.execute(
                """
                SELECT TOP 1 SessionId, GameId, UserId, CompletedAt, TotalScore
                FROM GameSessions
                WHERE UserId = ? AND GameId = ?
                ORDER BY
                    CASE WHEN CompletedAt IS NOT NULL THEN 0 ELSE 1 END,
                    StartedAt DESC
                """,
                (user_id, game_id),
            )
            existing = cur.fetchone()

            if existing:
                session = existing
            else:
                session = create_session(cur, user_id, game_id)

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
                'city_id': int(row.CityId) if row.CityId is not None else None,
                'city_name': row.CityName,
                'latitude': float(row.Latitude),
                'longitude': float(row.Longitude),
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
        has_next_expansion = has_next_expansion_level(cur, game_id, round_number)

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
            'expansion_level': int(row.ExpansionLevel),
            'has_next_expansion': has_next_expansion,
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
    
def get_daily_square_data_for_game(round_number: int, game_id: int) -> dict:
    with get_conn() as conn:
        cur = conn.cursor()

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
    t0 = perf_counter()

    def log_stage(stage: str, started_at: float) -> float:
        now = perf_counter()
        print(f"[submit_guess] {stage}: {(now - started_at) * 1000:.1f} ms")
        return now

    guess_text = (payload.get('guess') or '').strip()
    round_number = int(payload.get('round_number', 1))
    t = log_stage("parse_input", t0)

    if not guess_text:
        print(f"[submit_guess] total: {(perf_counter() - t0) * 1000:.1f} ms")
        return {'error': 'Guess is required.'}, 400

    with get_conn() as conn:
        t = log_stage("get_conn", t)
        cur = conn.cursor()
        t = log_stage("create_cursor", t)

        session = _get_current_session(cur, user_id, session_id)
        t = log_stage("_get_current_session", t)

        if not session:
            print(f"[submit_guess] total: {(perf_counter() - t0) * 1000:.1f} ms")
            return {'error': 'No game found for today.'}, 404

        session_id = int(session.SessionId)

        existing_round = get_session_round(cur, session_id, round_number)
        t = log_stage("get_session_round", t)

        if existing_round:
            print(f"[submit_guess] total: {(perf_counter() - t0) * 1000:.1f} ms")
            return {
                'ok': True,
                'noop': True,
                'total_score': int(session.TotalScore),
            }, 200

        game_id = int(session.GameId)
        square_row = get_square_id_for_round(cur, game_id, round_number)
        t = log_stage("get_square_id_for_round", t)

        if not square_row:
            print(f"[submit_guess] total: {(perf_counter() - t0) * 1000:.1f} ms")
            return {'error': 'No square found for that round.'}, 404

        square_id = int(square_row.SquareId)

        print(f"Square={square_id}")
        rows = get_ranked_square_cities(cur, square_id)
        t = log_stage("get_ranked_square_cities", t)

        matched_city = find_matching_city(rows, guess_text)
        t = log_stage("find_matching_city", t)

        if matched_city:
            session_round = create_session_round(cur, session_id, round_number, square_id)
            t = log_stage("create_session_round", t)

            session_round_id = int(session_round.SessionRoundId)

            city_name = matched_city.CityName
            population = int(matched_city.Population)
            score = compute_score(rows, population)
            t = log_stage("compute_score", t)

            insert_correct_guess(cur, session_round_id, city_name, population, score)
            t = log_stage("insert_correct_guess", t)

            increment_session_round_score(cur, session_round_id, score)
            t = log_stage("increment_session_round_score", t)

            increment_session_total_score(cur, session_id, score)
            t = log_stage("increment_session_total_score", t)

            updated_session = get_session_total_score(cur, session_id)
            t = log_stage("get_session_total_score", t)

            if round_number == 5:
                complete_session(cur, session_id)
                t = log_stage("complete_session", t)

            conn.commit()
            t = log_stage("commit", t)

            print(f"[submit_guess] total: {(perf_counter() - t0) * 1000:.1f} ms")
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
        t = log_stage("find_city_anywhere", t)

        conn.commit()
        t = log_stage("commit", t)

        print(f"[submit_guess] total: {(perf_counter() - t0) * 1000:.1f} ms")
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

        create_session_round(cur, session_id, round_number, square_id)
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

        cur.execute(
            """
            SELECT AuthProviderSubject, Username
            FROM Users
            WHERE UserId = ?
            """,
            (user_id,),
        )
        user_row = cur.fetchone()
        is_authenticated = bool(user_row and user_row.AuthProviderSubject)
        username = user_row.Username if user_row else None

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
        is_perfect = all(r['score'] > 0 for r in completed_rounds)
        print(f"is_perfect: {is_perfect}")

        base_payload = {
            'session_id': int(session.SessionId),
            'user_id': int(session.UserId),
            'game_id': int(session.GameId),
            'total_score': int(session.TotalScore),
            'is_authenticated': is_authenticated,
            'username': username,
        }

        if session.CompletedAt is not None:
            latest_round_number = completed_rounds[-1]['round_number'] if completed_rounds else 1
            conn.commit()

            return {
                'state': 'completed',
                'round_number': latest_round_number,
                'completed_at': session.CompletedAt.isoformat(),
                'completed_rounds': completed_rounds,
                'is_perfect': is_perfect,
                **base_payload,
            }, 200

        if len(completed_rounds) == 0:
            conn.commit()

            return {
                'state': 'not_started',
                'round_number': 1,
                'completed_at': None,
                'completed_rounds': [],
                'is_perfect': True,
                **base_payload,
            }, 200

        next_round = completed_rounds[-1]['round_number'] + 1
        conn.commit()

        return {
            'state': 'in_progress',
            'round_number': next_round,
            'completed_at': None,
            'completed_rounds': completed_rounds,
            'is_perfect': is_perfect,
            **base_payload,
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
    
def get_reveal_cities_for_square(square_id: int, excluded_city: dict | None = None) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()

        params = [square_id]
        sql = """
            SELECT TOP 5
                gsc.CityName,
                gsc.CountryCode,
                gsc.Latitude,
                gsc.Longitude,
                gsc.Population
            FROM dbo.GameSquareCities gsc
            JOIN dbo.GeoCities gc
                ON gc.CityId = gsc.CityId
            WHERE gsc.SquareId = ?
        """

        if excluded_city:
            sql += " AND gsc.CityId <> ? AND gsc.Population < ?"
            params.append(excluded_city['city_id'])
            params.append(excluded_city['population'])

        sql += " ORDER BY gc.NotorietyScore DESC, gsc.Population DESC"

        cur.execute(sql, params)
        rows = cur.fetchall()

        return [
            {
                'city_name': row.CityName,
                'country_code': row.CountryCode,
                'latitude': float(row.Latitude),
                'longitude': float(row.Longitude),
                'population': int(row.Population),
            }
            for row in rows
        ]


def get_all_daily_square_data(user_id: int, session_id: int | None) -> tuple[dict, int]:
    with get_conn() as conn:
        cur = conn.cursor()

        session = _get_current_session(cur, user_id, session_id)
        if session is None:
            return {'error': 'No game found for today.'}, 404

        completed_rounds = _build_completed_rounds(
            get_completed_round_rows(cur, int(session.SessionId))
        )

        completed_by_round = {
            int(r['round_number']): r for r in completed_rounds
        }

    rounds = []

    for round_number in range(1, 6):
        base = get_daily_square_data(round_number)

        completed = completed_by_round.get(round_number)
        guess = None

        if completed and completed.get('guesses'):
            guess = completed['guesses'][0]

        excluded_city = None
        if guess:
            excluded_city = {
                'city_id': guess['city_id'],
                'population': guess['population'],
            }

        reveal_cities = get_reveal_cities_for_square(
            base['square_id'],
            excluded_city=excluded_city
        )

        rounds.append({
            **base,
            'expansion_level': base.get('expansion_level', 0),
            'player_guess': guess,
            'reveal_cities': reveal_cities
        })

    return {'rounds': rounds}, 200

def get_all_daily_square_data_preview(game_date: str) -> tuple[dict, int]:
    with get_conn() as conn:
        cur = conn.cursor()

        game_id = get_game_id_by_date(cur, game_date)
        print(f"game_id={game_id}", flush=True)

        if game_id is None:
            return {'error': 'No game found for date.'}, 404

        cur.execute("""
            SELECT
                r.RoundNumber,
                r.ExpansionLevel,
                s.SquareId,
                s.SeedLat,
                s.SeedLon,
                s.MinLat,
                s.MinLon,
                s.MaxLat,
                s.MaxLon
            FROM GeoSquare.dbo.GameRounds r
            JOIN GeoSquare.dbo.GameSquares s
                ON s.SquareId = r.SquareId
            WHERE r.GameId = ?
            ORDER BY r.RoundNumber, r.ExpansionLevel
        """, (game_id,))

        rows = cur.fetchall()

        rounds_map = {}

        for r in rows:
            round_num = int(r.RoundNumber)
            level = int(r.ExpansionLevel)

            rounds_map.setdefault(round_num, []).append({
                'square_id': int(r.SquareId),
                'round_number': round_num,
                'expansion_level': level,
                'seed': {
                    'lat': float(r.SeedLat),
                    'lon': float(r.SeedLon),
                },
                'bounds': {
                    'min_lat': float(r.MinLat),
                    'min_lon': float(r.MinLon),
                    'max_lat': float(r.MaxLat),
                    'max_lon': float(r.MaxLon),
                },
                'player_guess': None,
                'label': f"Round {round_num} Level {level}"
            })

        rounds = [
            {
                'round_number': r,
                'levels': rounds_map[r]
            }
            for r in sorted(rounds_map.keys())
        ]

        return {'rounds': rounds}, 200