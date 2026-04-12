from collections import defaultdict
from datetime import date, timedelta

from app.core.db import get_conn


def get_profile_payload(user_id: int | None) -> tuple[dict, int]:
    print(f"fetching profile for user_id={user_id}")
    if user_id is None:
        return {
            'profile_found': False,
            'message': 'No profile found.',
        }, 200

    with get_conn() as conn:
        cur = conn.cursor()

        print(f'[profile] user_id={user_id}', flush=True)

        user_row = _get_user_row(cur, user_id)
        print(
            f'[profile] user_row_exists={user_row is not None} '
            f'username={user_row.Username if user_row else None}',
            flush=True,
        )

        sessions = _get_completed_sessions(cur, user_id)
        print(f'[profile] completed_session_count={len(sessions)}', flush=True)
        if sessions:
            print(f'[profile] first_session={sessions[0]}', flush=True)
        if not sessions:
            return {
                'profile_found': False,
                'message': 'No profile found.',
                'user': {
                    'user_id': int(user_id),
                    'username': user_row.Username if user_row else None,
                    'is_authenticated': bool(user_row and user_row.AuthProviderSubject),
                },
                'history': [],
            }, 200

        completed_round_rows = _get_completed_round_rows_for_sessions(
            cur,
            [session['session_id'] for session in sessions],
        )
        completed_rounds_by_session = _build_completed_rounds_by_session(completed_round_rows)

        history = []
        for session in sessions:
            completed_rounds = completed_rounds_by_session.get(session['session_id'], [])
            solved_count = sum(1 for round_data in completed_rounds if int(round_data['score']) > 0)
            is_perfect = len(completed_rounds) == 5 and all(int(round_data['score']) > 0 for round_data in completed_rounds)
            best_round = _get_best_round(completed_rounds)

            history.append({
                'session_id': int(session['session_id']),
                'game_id': int(session['game_id']),
                'game_date': session['game_date'].isoformat(),
                'completed_at': session['completed_at'].isoformat() if session['completed_at'] else None,
                'total_score': int(session['total_score']),
                'solved_count': int(solved_count),
                'is_perfect': bool(is_perfect),
                'best_round': best_round,
                'completed_rounds': completed_rounds,
            })

        most_obscure_city = _get_most_obscure_city(cur, user_id)
        most_used_city = _get_most_used_city(cur, user_id)

        summary = _build_summary(history, most_obscure_city, most_used_city)

        conn.commit()

    return {
        'profile_found': True,
        'user': {
            'user_id': int(user_id),
            'username': user_row.Username if user_row else None,
            'is_authenticated': bool(user_row and user_row.AuthProviderSubject),
        },
        'summary': summary,
        'history': history,
    }, 200


def _get_user_row(cur, user_id: int):
    cur.execute(
        """
        SELECT UserId, AuthProviderSubject, Username
        FROM dbo.Users
        WHERE UserId = ?
        """,
        (user_id,),
    )
    return cur.fetchone()


def _get_completed_sessions(cur, user_id: int) -> list[dict]:
    cur.execute(
        """
        SELECT
            gs.SessionId,
            gs.GameId,
            g.GameDate,
            gs.CompletedAt,
            gs.TotalScore
        FROM dbo.GameSessions gs
        INNER JOIN dbo.Games g
            ON g.GameId = gs.GameId
        WHERE gs.UserId = ?
          AND gs.CompletedAt IS NOT NULL
        ORDER BY g.GameDate DESC, gs.CompletedAt DESC, gs.SessionId DESC
        """,
        (user_id,),
    )

    return [
        {
            'session_id': int(row.SessionId),
            'game_id': int(row.GameId),
            'game_date': row.GameDate,
            'completed_at': row.CompletedAt,
            'total_score': int(row.TotalScore),
        }
        for row in cur.fetchall()
    ]


def _get_completed_round_rows_for_sessions(cur, session_ids: list[int]):
    if not session_ids:
        return []

    placeholders = ', '.join('?' for _ in session_ids)

    cur.execute(
        f"""
        SELECT
            gsr.SessionId,
            gsr.SessionRoundId,
            gsr.RoundNumber,
            gsr.SquareId,
            gsr.Score,
            gg.CityName,
            gg.Population,
            gg.Score AS GuessScore,
            gg.GuessedAt,
            ranked.CityId,
            ranked.PopRank,
            ranked.Latitude,
            ranked.Longitude
        FROM dbo.GameSessionRounds gsr
        LEFT JOIN dbo.GameGuesses gg
            ON gg.SessionRoundId = gsr.SessionRoundId
        LEFT JOIN (
            SELECT
                SquareId,
                CityId,
                CityName,
                Population,
                Latitude,
                Longitude,
                ROW_NUMBER() OVER (
                    PARTITION BY SquareId
                    ORDER BY Population DESC, CityName ASC
                ) AS PopRank
            FROM dbo.GameSquareCities
        ) ranked
            ON ranked.SquareId = gsr.SquareId
            AND ranked.CityName = gg.CityName
            AND ranked.Population = gg.Population
        WHERE gsr.SessionId IN ({placeholders})
        ORDER BY gsr.SessionId ASC, gsr.RoundNumber ASC, gg.GuessedAt ASC, gg.GuessId ASC
        """,
        session_ids,
    )

    return cur.fetchall()


def _build_completed_rounds_by_session(rows) -> dict[int, list[dict]]:
    rounds_by_session = defaultdict(dict)

    for row in rows:
        session_id = int(row.SessionId)
        round_number = int(row.RoundNumber)

        if round_number not in rounds_by_session[session_id]:
            rounds_by_session[session_id][round_number] = {
                'session_round_id': int(row.SessionRoundId),
                'round_number': round_number,
                'square_id': int(row.SquareId),
                'score': int(row.Score),
                'guesses': [],
            }

        if row.CityName is not None:
            rounds_by_session[session_id][round_number]['guesses'].append({
                'city_id': int(row.CityId) if row.CityId is not None else None,
                'city_name': row.CityName,
                'latitude': float(row.Latitude) if row.Latitude is not None else None,
                'longitude': float(row.Longitude) if row.Longitude is not None else None,
                'population': int(row.Population) if row.Population is not None else None,
                'score': int(row.GuessScore),
                'rank': int(row.PopRank) if row.PopRank is not None else None,
                'guessed_at': row.GuessedAt.isoformat() if row.GuessedAt is not None else None,
            })

    result = {}

    for session_id, round_map in rounds_by_session.items():
        result[session_id] = [round_map[round_number] for round_number in sorted(round_map.keys())]

    return result


def _get_best_round(completed_rounds: list[dict]) -> dict | None:
    scored_rounds = [round_data for round_data in completed_rounds if int(round_data['score']) > 0]
    if not scored_rounds:
        return None

    best_round = max(
        scored_rounds,
        key=lambda round_data: (
            int(round_data['score']),
            -int(round_data['round_number']),
        ),
    )

    best_guess = best_round['guesses'][-1] if best_round['guesses'] else None

    return {
        'round_number': int(best_round['round_number']),
        'score': int(best_round['score']),
        'city_name': best_guess['city_name'] if best_guess else None,
        'population': int(best_guess['population']) if best_guess and best_guess['population'] is not None else None,
        'rank': int(best_guess['rank']) if best_guess and best_guess['rank'] is not None else None,
    }


def _get_most_obscure_city(cur, user_id: int) -> dict | None:
    cur.execute(
        """
        WITH RankedGuesses AS (
            SELECT
                gsr.SessionId,
                gsr.SquareId,
                gg.CityName,
                gg.Population,
                gsc.CityId,
                gc.NotorietyScore,
                ROW_NUMBER() OVER (
                    PARTITION BY gsr.SessionId, gsr.SquareId, gg.CityName, gg.Population
                    ORDER BY gsc.CityId ASC
                ) AS rn
            FROM dbo.GameSessions gs
            INNER JOIN dbo.GameSessionRounds gsr
                ON gsr.SessionId = gs.SessionId
            INNER JOIN dbo.GameGuesses gg
                ON gg.SessionRoundId = gsr.SessionRoundId
            INNER JOIN dbo.GameSquareCities gsc
                ON gsc.SquareId = gsr.SquareId
                AND gsc.CityName = gg.CityName
                AND gsc.Population = gg.Population
            INNER JOIN dbo.GeoCities gc
                ON gc.CityId = gsc.CityId
            WHERE gs.UserId = ?
              AND gs.CompletedAt IS NOT NULL
              AND gc.NotorietyScore IS NOT NULL
        )
        SELECT TOP 1
            CityId,
            CityName,
            Population,
            NotorietyScore
        FROM RankedGuesses
        WHERE rn = 1
        ORDER BY NotorietyScore ASC, Population ASC, CityName ASC
        """,
        (user_id,),
    )
    row = cur.fetchone()

    if not row:
        return None

    return {
        'city_id': int(row.CityId),
        'city_name': row.CityName,
        'population': int(row.Population),
        'notoriety_score': float(row.NotorietyScore),
    }


def _get_most_used_city(cur, user_id: int) -> dict | None:
    cur.execute(
        """
        WITH RankedGuesses AS (
            SELECT
                gsr.SessionId,
                gsr.SquareId,
                gg.CityName,
                gg.Population,
                gsc.CityId,
                ROW_NUMBER() OVER (
                    PARTITION BY gsr.SessionId, gsr.SquareId, gg.CityName, gg.Population
                    ORDER BY gsc.CityId ASC
                ) AS rn
            FROM dbo.GameSessions gs
            INNER JOIN dbo.GameSessionRounds gsr
                ON gsr.SessionId = gs.SessionId
            INNER JOIN dbo.GameGuesses gg
                ON gg.SessionRoundId = gsr.SessionRoundId
            INNER JOIN dbo.GameSquareCities gsc
                ON gsc.SquareId = gsr.SquareId
                AND gsc.CityName = gg.CityName
                AND gsc.Population = gg.Population
            WHERE gs.UserId = ?
              AND gs.CompletedAt IS NOT NULL
        )
        SELECT TOP 1
            CityId,
            CityName,
            Population,
            COUNT(*) AS TimesUsed
        FROM RankedGuesses
        WHERE rn = 1
        GROUP BY CityId, CityName, Population
        ORDER BY COUNT(*) DESC, Population ASC, CityName ASC
        """,
        (user_id,),
    )
    row = cur.fetchone()

    if not row:
        return None

    return {
        'city_id': int(row.CityId),
        'city_name': row.CityName,
        'population': int(row.Population),
        'times_used': int(row.TimesUsed),
    }


def _build_summary(history: list[dict], most_obscure_city: dict | None, most_used_city: dict | None) -> dict:
    games_played = len(history)
    perfect_games_played = sum(1 for game in history if game['is_perfect'])
    total_points = sum(int(game['total_score']) for game in history)
    average_points = round(total_points / games_played, 2) if games_played else 0.0
    total_squares_solved = sum(int(game['solved_count']) for game in history)
    average_squares_solved = round(total_squares_solved / games_played, 2) if games_played else 0.0

    best_game = max(
        history,
        key=lambda game: (
            int(game['total_score']),
            game['game_date'],
        ),
    ) if history else None

    current_game_streak = _calculate_game_streak(history)
    current_perfect_streak = _calculate_perfect_streak(history)

    return {
        'games_played': int(games_played),
        'perfect_games_played': int(perfect_games_played),
        'best_score': int(best_game['total_score']) if best_game else 0,
        'best_score_date': best_game['game_date'] if best_game else None,
        'total_points': int(total_points),
        'average_points': average_points,
        'total_squares_solved': int(total_squares_solved),
        'average_squares_solved': average_squares_solved,
        'current_game_streak': int(current_game_streak),
        'current_perfect_streak': int(current_perfect_streak),
        'most_obscure_city': most_obscure_city,
        'most_used_city': most_used_city,
    }


def _calculate_game_streak(history: list[dict]) -> int:
    if not history:
        return 0

    ordered_dates = []
    seen = set()

    for game in history:
        game_date = date.fromisoformat(game['game_date'])
        if game_date not in seen:
            seen.add(game_date)
            ordered_dates.append(game_date)

    ordered_dates.sort(reverse=True)

    streak = 0
    previous_date = None

    for game_date in ordered_dates:
        if previous_date is None:
            streak = 1
            previous_date = game_date
            continue

        if game_date == previous_date - timedelta(days=1):
            streak += 1
            previous_date = game_date
            continue

        break

    return streak


def _calculate_perfect_streak(history: list[dict]) -> int:
    if not history:
        return 0

    streak = 0
    previous_date = None

    for game in history:
        if not game['is_perfect']:
            break

        game_date = date.fromisoformat(game['game_date'])

        if previous_date is None:
            streak = 1
            previous_date = game_date
            continue

        if game_date == previous_date - timedelta(days=1):
            streak += 1
            previous_date = game_date
            continue

        break

    return streak