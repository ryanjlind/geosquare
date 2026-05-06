# core/game_service.py

from time import perf_counter

from app.core.db import get_conn
from app.core.game_queries import (
    complete_session,
    get_completed_round_rows,
    get_session_round,
    get_ranked_square_cities,
    get_session_total_score,
    get_square_cities,
    get_square_city_count,
    get_square_for_round,
    get_square_id_for_round,
    increment_session_total_score,
    insert_correct_guess,
    find_city_anywhere,
    get_best_guess_for_user,
    get_completed_sessions_for_user,
    get_round_stats_for_sessions,
    get_game_id_by_date,
    has_next_expansion_level,
    get_active_session_square,
    get_next_expansion_square,
    upsert_session_round_expand,
    get_square_by_id,
    set_round_completed,
    set_round_passed,
    
)
from app.core.matching import find_matching_city
from app.core.scoring import compute_score
from app.core.session_service import get_current_session
from app.core.game_mappers import (
    map_completed_rounds,
    map_square,
    map_game_state,
    map_player_stats,
)
from app.helpers.date import get_effective_game_date

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

def _resolve_square(cur, session_id, game_id, round_number):
    square = get_active_session_square(cur, session_id, round_number)
    
    if square is not None:
        square_id = square.SquareId
        expansion_level = square.ExpansionLevel
        return int(square_id), int(expansion_level)            

    row = get_square_id_for_round(cur, game_id, round_number)
    if not row:
        return None

    return int(row.SquareId), int(row.ExpansionLevel)

def get_daily_square_data(user_id: int, session_id: int | None, round_number: int) -> dict:
    with get_conn() as conn:
        cur = conn.cursor()

        session = get_current_session(cur, user_id, session_id)
        if not session:
            raise Exception("No session")

        game_id = int(session.GameId)
        session_id = int(session.SessionId)

        square_id, expansion_level = _resolve_square(cur, session_id, game_id, round_number)
        row = get_square_by_id(cur, square_id)
        cities_rows = get_square_cities(cur, square_id)
        city_count_row = get_square_city_count(cur, square_id)

        has_next = has_next_expansion_level(cur, game_id, round_number, square_id)

        return map_square(row, cities_rows, city_count_row, has_next)


def submit_guess(payload: dict, user_id: int, session_id: int | None):
    t0 = perf_counter()

    guess_text = (payload.get("guess") or "").strip()
    round_number = int(payload.get("round_number", 1))

    if not guess_text:
        return {"error": "Guess is required."}, 400

    with get_conn() as conn:
        cur = conn.cursor()

        session = get_current_session(cur, user_id, session_id)
        if not session:
            return {"error": "No game found for today."}, 404

        session_id = int(session.SessionId)
        game_id = int(session.GameId)

        existing_round = get_session_round(cur, session_id, round_number)
        if existing_round and existing_round.RoundStatus == "Completed":
            return {
                "ok": True,
                "noop": True,
                "total_score": int(session.TotalScore),
            }, 200

        square_id, expansion_level = _resolve_square(cur, session_id, game_id, round_number)
        if square_id is None:
            return {"error": "No square found for that round."}, 404

        rows = get_ranked_square_cities(cur, square_id)
        matched = find_matching_city(rows, guess_text)

        if matched:
            population = int(matched.Population)
            score = compute_score(rows, population)
            expansion_level = int(expansion_level)
            score = int(score * (1 - (expansion_level * 0.2)))

            set_round_completed(cur, session_id, round_number, square_id, score)

            session_round = get_session_round(cur, session_id, round_number)
            session_round_id = int(session_round.SessionRoundId)

            insert_correct_guess(
                cur,
                session_round_id,
                matched.CityName,
                population,
                score,
            )

            increment_session_total_score(cur, session_id, score)

            updated = get_session_total_score(cur, session_id)

            if round_number == 5:
                complete_session(cur, session_id)

            conn.commit()

            return {
                "ok": True,
                "correct": True,
                "city": matched.CityName,
                "country_code": matched.CountryCode,
                "latitude": float(matched.Latitude),
                "longitude": float(matched.Longitude),
                "population": population,
                "score": score,
                "rank": int(matched.PopRank),
                "total_score": int(updated.TotalScore),                
                "expansion_level": expansion_level,
            }, 200

        nearby = find_city_anywhere(cur, guess_text)
        conn.commit()

        return {
            "ok": True,
            "correct": False,
            "city": guess_text,
            "score": 0,
            "total_score": int(session.TotalScore),
            "matched_city": {
                "city_name": nearby.CityName,
                "country_code": nearby.CountryCode,
                "latitude": float(nearby.Latitude),
                "longitude": float(nearby.Longitude),
                "population": int(nearby.Population),
            } if nearby else None,
        }, 200


def submit_pass(payload: dict, user_id: int, session_id: int | None):
    round_number = int(payload.get("round_number", 1))

    with get_conn() as conn:
        cur = conn.cursor()

        session = get_current_session(cur, user_id, session_id)
        if not session:
            return {"error": "No game found for today."}, 404

        session_id = int(session.SessionId)
        game_id = int(session.GameId)

        square_row = get_square_id_for_round(cur, game_id, round_number)
        if not square_row:
            return {"error": "No square found for that round."}, 404

        square_id = int(square_row.SquareId)

        set_round_passed(cur, session_id, round_number, square_id)

        rows = get_ranked_square_cities(cur, square_id)
        largest = rows[0] if rows else None

        if round_number == 5:
            complete_session(cur, session_id)

        conn.commit()

        return {
            "ok": True,
            "passed": True,
            "round_number": round_number,
            "score": 0,
            "largest_city": {
                "city_name": largest.CityName,
                "country_code": largest.CountryCode,
                "latitude": float(largest.Latitude),
                "longitude": float(largest.Longitude),
                "population": int(largest.Population),
                "rank": int(largest.PopRank),
            } if largest else None,
        }, 200


def get_game_state_payload(user_id: int, session_id: int | None):
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

        session = get_current_session(cur, user_id, session_id)
        if session is None:
            return {"error": "No game found for today."}, 404

        completed = map_completed_rounds(
            get_completed_round_rows(cur, int(session.SessionId))
        )

        conn.commit()

        return map_game_state(session, completed, is_authenticated, username), 200


def get_player_stats_payload(user_id: int):
    through = get_effective_game_date()

    with get_conn() as conn:
        cur = conn.cursor()

        sessions = get_completed_sessions_for_user(cur, user_id, through)
        best_guess = get_best_guess_for_user(cur, user_id, through)

        if not sessions:
            conn.commit()
            return {
                "games_played": 0,
                "current_streak": 0,
                "longest_streak": 0,
                "perfect_days": 0,
                "perfect_streak": 0,
                "average_score": 0,
                "best_score": 0,
                "best_score_game_date": None,
                "last_score": 0,
                "last_game_date": None,
                "graph_points": [],
                "best_guess": None,
            }, 200

        session_ids = [int(s.SessionId) for s in sessions]
        round_stats = get_round_stats_for_sessions(cur, session_ids)

        game_dates = [s.GameDate for s in sessions]
        current_streak, longest_streak = _compute_streaks(game_dates)

        conn.commit()

        return map_player_stats(
            sessions,
            round_stats,
            best_guess,
            current_streak,
            longest_streak,
        ), 200


def _compute_streaks(game_dates):
    if not game_dates:
        return 0, 0

    unique = sorted(set(game_dates))

    longest = 1
    current = 1

    for i in range(1, len(unique)):
        if (unique[i] - unique[i - 1]).days == 1:
            current += 1
        else:
            longest = max(longest, current)
            current = 1

    longest = max(longest, current)

    current_streak = 1
    for i in range(len(unique) - 1, 0, -1):
        if (unique[i] - unique[i - 1]).days == 1:
            current_streak += 1
        else:
            break

    return current_streak, longest


def expand_square(user_id: int, session_id: int, round_number: int):
    with get_conn() as conn:
        cur = conn.cursor()

        session = get_current_session(cur, user_id, session_id)
        if not session:
            return {"error": "No session"}, 404

        session_id = int(session.SessionId)
        game_id = int(session.GameId)

        current_square_id, expansion_level = _resolve_square(cur, session_id, game_id, round_number)

        next_square = get_next_expansion_square(
            cur, game_id, round_number, current_square_id
        )

        if not next_square:
            conn.commit()
            return {"ok": True, "has_next_expansion": False}, 200

        next_id = int(next_square.SquareId)

        upsert_session_round_expand(cur, session_id, round_number, next_id)
        bounds = get_square_by_id(cur, next_id)

        conn.commit()

        return {
            "ok": True,
            "square_id": next_id,
            "expansion_level": int(next_square.ExpansionLevel),
            "has_next_expansion": has_next_expansion_level(
                cur, game_id, round_number, next_id
            ),
            "bounds": {
                "min_lat": float(bounds.MinLat),
                "min_lon": float(bounds.MinLon),
                "max_lat": float(bounds.MaxLat),
                "max_lon": float(bounds.MaxLon),
            },
        }, 200
    
def get_all_daily_square_data(user_id: int, session_id: int | None):
    with get_conn() as conn:
        cur = conn.cursor()

        session = get_current_session(cur, user_id, session_id)
        if session is None:
            return {"error": "No game found for today."}, 404

        completed = map_completed_rounds(
            get_completed_round_rows(cur, int(session.SessionId))
        )

        completed_by_round = {
            int(r["round_number"]): r for r in completed
        }

    rounds = []

    for round_number in range(1, 6):
        base = get_daily_square_data(user_id, session_id, round_number)

        completed_round = completed_by_round.get(round_number)
        guess = None

        if completed_round and completed_round.get("guesses"):
            guess = completed_round["guesses"][0]

        excluded_city = None
        if guess:
            excluded_city = {
                "city_id": guess["city_id"],
                "population": guess["population"],
            }

        reveal_cities = get_reveal_cities_for_square(
            base["square_id"],
            excluded_city=excluded_city,
        )

        rounds.append({
            **base,
            "levels": [{
                "bounds": base["bounds"],
                "expansion_level": base.get("expansion_level", 0),
                "seed": base["seed"],
            }],
            "player_guess": guess,
            "reveal_cities": reveal_cities,
        })

    return {"rounds": rounds}, 200

def get_all_daily_square_data_preview(game_date: str):
    with get_conn() as conn:
        cur = conn.cursor()

        game_id = get_game_id_by_date(cur, game_date)
        if game_id is None:
            return {"error": "No game found for date."}, 404

        cur.execute(
            """
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
            """,
            (game_id,),
        )

        rows = cur.fetchall()

        rounds_map = {}

        for r in rows:
            round_num = int(r.RoundNumber)
            level = int(r.ExpansionLevel)

            rounds_map.setdefault(round_num, []).append({
                "square_id": int(r.SquareId),
                "round_number": round_num,
                "expansion_level": level,
                "seed": {
                    "lat": float(r.SeedLat),
                    "lon": float(r.SeedLon),
                },
                "bounds": {
                    "min_lat": float(r.MinLat),
                    "min_lon": float(r.MinLon),
                    "max_lat": float(r.MaxLat),
                    "max_lon": float(r.MaxLon),
                },
                "player_guess": None,
                "label": f"Round {round_num} Level {level}",
            })

        rounds = [
            {
                "round_number": rn,
                "levels": rounds_map[rn],
            }
            for rn in sorted(rounds_map.keys())
        ]

        return {"rounds": rounds}, 200