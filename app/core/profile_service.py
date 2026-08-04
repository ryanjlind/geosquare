from collections import defaultdict
from contextlib import contextmanager
from datetime import date, timedelta
from time import perf_counter

from app.core.db import get_conn
from app.core.infinity_queries import get_started_infinity_pools
from app.helpers.logging import info as log_info

REGION_ORDER = [
    'Nordic Europe',
    'Mainland Europe',
    'European Russia',
    'Asian Steppe',
    'China',
    'Japan / Korea',
    'South Asia',
    'Southeast Asia',
    'West Asia',
    'North Africa',
    'West Africa',
    'Sub-Saharan Africa',
    'Caribbean / Central America',
    'US / Canada',
    'Mexico',
    'South America',
    'Oceania',
    'Other',
]
HISTORY_PAGE_SIZE = 20


def _log_profile_duration(label: str, start: float):
    log_info(f'[profile] {label} took {perf_counter() - start:.3f}s')


@contextmanager
def _profile_stage(label: str):
    start = perf_counter()
    log_info(f'[profile] {label} started')
    try:
        yield
    except Exception as error:
        log_info(
            f'[profile] {label} failed after {perf_counter() - start:.3f}s: '
            f'{type(error).__name__}: {error}'
        )
        raise
    log_info(f'[profile] {label} completed in {perf_counter() - start:.3f}s')


def _fetchone_with_timing(cur, label: str):
    start = perf_counter()
    row = cur.fetchone()
    log_info(f'[profile] {label}.fetchone completed in {perf_counter() - start:.3f}s')
    return row


def _fetchall_with_timing(cur, label: str):
    start = perf_counter()
    rows = cur.fetchall()
    log_info(
        f'[profile] {label}.fetchall completed in {perf_counter() - start:.3f}s '
        f'row_count={len(rows)}'
    )
    return rows

def get_profile_payload(user_id: int | None) -> tuple[dict, int]:
    start = perf_counter()
    log_info(f"fetching profile for user_id={user_id}")
    if user_id is None:
        _log_profile_duration('get_profile_payload', start)
        return {
            'profile_found': False,
            'message': 'No profile found.',
        }, 200

    connection_start = perf_counter()
    log_info('[profile] database connection started')
    with get_conn() as conn:
        log_info(
            f'[profile] database connection completed in '
            f'{perf_counter() - connection_start:.3f}s'
        )
        cursor_start = perf_counter()
        cur = conn.cursor()
        log_info(f'[profile] cursor creation completed in {perf_counter() - cursor_start:.3f}s')

        log_info(f'[profile] user_id={user_id}')

        user_row = _get_user_row(cur, user_id)
        log_info(
            f'[profile] user_row_exists={user_row is not None} '
            f'username={user_row.Username if user_row else None}'
        )

        lifetime_games = _get_lifetime_games(cur, user_id)
        sessions = _get_completed_sessions(cur, user_id, offset=0)
        log_info(f'[profile] completed_session_count={len(sessions)}')
        if not lifetime_games:
            _log_profile_duration('get_profile_payload', start)
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

        history = _load_history(cur, sessions[:HISTORY_PAGE_SIZE])

        most_obscure_city = _get_most_obscure_city(cur, user_id)
        most_used_city = _get_most_used_city(cur, user_id)
        strongest_country = _get_strongest_country(cur, user_id)
        region_performance, region_classification_details = _get_region_performance(cur, user_id)

        summary = _build_summary(
            lifetime_games,
            most_obscure_city,
            most_used_city,
            strongest_country,
        )

        commit_start = perf_counter()
        log_info('[profile] commit started')
        conn.commit()
        log_info(f'[profile] commit completed in {perf_counter() - commit_start:.3f}s')

    _log_profile_duration('get_profile_payload', start)
    return {
        'profile_found': True,
        'user': {
            'user_id': int(user_row.UserId),
            'username': user_row.Username,
            'is_authenticated': bool(user_row.AuthProviderSubject),
        },
        'summary': summary,
        'region_performance': region_performance,
        'region_classification_details': region_classification_details,
        'history': history,
        'history_pagination': {
            'offset': 0,
            'page_size': HISTORY_PAGE_SIZE,
            'has_more': len(sessions) > HISTORY_PAGE_SIZE,
        },
    }, 200


def get_profile_history_payload(user_id: int | None, offset: int) -> tuple[dict, int]:
    if user_id is None:
        return {'error': 'No profile found.'}, 404
    if offset < 0:
        return {'error': 'offset must be non-negative.'}, 400

    with _profile_stage('get_profile_history_payload'):
        connection_start = perf_counter()
        log_info('[profile] history database connection started')
        with get_conn() as conn:
            log_info(
                f'[profile] history database connection completed in '
                f'{perf_counter() - connection_start:.3f}s'
            )
            cur = conn.cursor()
            sessions = _get_completed_sessions(cur, user_id, offset=offset)
            history = _load_history(cur, sessions[:HISTORY_PAGE_SIZE])

    return {
        'history': history,
        'history_pagination': {
            'offset': offset,
            'page_size': HISTORY_PAGE_SIZE,
            'has_more': len(sessions) > HISTORY_PAGE_SIZE,
        },
    }, 200


def get_infinity_pools_payload(user_id: int | None) -> tuple[dict, int]:
    if user_id is None:
        return {'pools': []}, 200

    with get_conn() as conn:
        cur = conn.cursor()
        rows = get_started_infinity_pools(cur, user_id)

    pools_by_id = {}
    for row in rows:
        infinity_session_id = int(row.InfinityPoolSessionId)
        pool = pools_by_id.setdefault(infinity_session_id, {
            'infinity_pool_session_id': infinity_session_id,
            'game_date': row.GameDate.isoformat(),
            'current_round': int(row.CurrentRoundNumber),
            'started_at': row.StartedAt.isoformat(),
            'updated_at': row.UpdatedAt.isoformat(),
            'total_score': 0,
            'squares': [],
        })
        round_score = int(row.RoundScore)
        pool['total_score'] += round_score
        pool['squares'].append({
            'round_number': int(row.RoundNumber),
            'score': round_score,
            'city_count': int(row.CityCount),
        })

    return {'pools': list(pools_by_id.values())}, 200

def _get_user_row(cur, user_id: int):
    with _profile_stage('_get_user_row'):
        execute_start = perf_counter()
        cur.execute(
            """
            SELECT UserId, AuthProviderSubject, Username
            FROM dbo.Users
            WHERE UserId = ?
            """,
            (user_id,),
        )
        log_info(f'[profile] _get_user_row.execute completed in {perf_counter() - execute_start:.3f}s')
        return _fetchone_with_timing(cur, '_get_user_row')

def _get_lifetime_games(cur, user_id: int) -> list[dict]:
    with _profile_stage('_get_lifetime_games'):
        execute_start = perf_counter()
        cur.execute(
            """
            SELECT
                gs.SessionId,
                g.GameDate,
                gs.TotalScore,
                COUNT(gsr.SessionRoundId) AS RoundCount,
                SUM(CASE WHEN gsr.Score > 0 THEN 1 ELSE 0 END) AS SolvedCount
            FROM dbo.GameSessions gs
            INNER JOIN dbo.Games g
                ON g.GameId = gs.GameId
            LEFT JOIN dbo.GameSessionRounds gsr
                ON gsr.SessionId = gs.SessionId
                AND gsr.RoundStatus IN ('Completed', 'Passed')
            WHERE gs.UserId = ?
              AND gs.CompletedAt IS NOT NULL
            GROUP BY gs.SessionId, g.GameDate, gs.TotalScore
            ORDER BY g.GameDate DESC, gs.SessionId DESC
            """,
            (user_id,),
        )
        log_info(
            f'[profile] _get_lifetime_games.execute completed in '
            f'{perf_counter() - execute_start:.3f}s'
        )
        rows = _fetchall_with_timing(cur, '_get_lifetime_games')
        return [
            {
                'game_date': row.GameDate.isoformat(),
                'total_score': int(row.TotalScore),
                'solved_count': int(row.SolvedCount),
                'is_perfect': int(row.RoundCount) == 5 and int(row.SolvedCount) == 5,
            }
            for row in rows
        ]


def _get_completed_sessions(cur, user_id: int, offset: int) -> list[dict]:
    with _profile_stage('_get_completed_sessions'):
        execute_start = perf_counter()
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
                        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
                        (user_id, offset, HISTORY_PAGE_SIZE + 1),
        )
        log_info(
            f'[profile] _get_completed_sessions.execute completed in '
            f'{perf_counter() - execute_start:.3f}s'
        )
        rows = _fetchall_with_timing(cur, '_get_completed_sessions')
        map_start = perf_counter()
        result = [
            {
                'session_id': int(row.SessionId),
                'game_id': int(row.GameId),
                'game_date': row.GameDate,
                'completed_at': row.CompletedAt,
                'total_score': int(row.TotalScore),
            }
            for row in rows
        ]
        log_info(
            f'[profile] _get_completed_sessions.map completed in '
            f'{perf_counter() - map_start:.3f}s'
        )
        return result


def _load_history(cur, sessions: list[dict]) -> list[dict]:
    completed_round_rows = _get_completed_round_rows_for_sessions(
        cur,
        [session['session_id'] for session in sessions],
    )
    completed_rounds_by_session = _build_completed_rounds_by_session(completed_round_rows)

    with _profile_stage('build_history'):
        history = []
        for session in sessions:
            session_id = session['session_id']
            if session_id not in completed_rounds_by_session:
                raise RuntimeError(f'Completed session {session_id} has no completed round data.')
            completed_rounds = completed_rounds_by_session[session_id]
            solved_count = sum(1 for round_data in completed_rounds if int(round_data['score']) > 0)
            is_perfect = len(completed_rounds) == 5 and all(
                int(round_data['score']) > 0 for round_data in completed_rounds
            )
            history.append({
                'session_id': int(session['session_id']),
                'game_id': int(session['game_id']),
                'game_date': session['game_date'].isoformat(),
                'completed_at': session['completed_at'].isoformat() if session['completed_at'] else None,
                'total_score': int(session['total_score']),
                'solved_count': int(solved_count),
                'is_perfect': bool(is_perfect),
                'best_round': _get_best_round(completed_rounds),
                'completed_rounds': completed_rounds,
            })
        log_info(f'[profile] build_history session_count={len(history)}')
        return history

def _get_completed_round_rows_for_sessions(cur, session_ids: list[int]):
    start = perf_counter()
    if not session_ids:
        _log_profile_duration('_get_completed_round_rows_for_sessions', start)
        return []

    placeholders = ', '.join('?' for _ in session_ids)

    log_info(
        f'[profile] _get_completed_round_rows_for_sessions.execute started '
        f'session_count={len(session_ids)}'
    )
    execute_start = perf_counter()
    cur.execute(
        f"""
        WITH TargetRounds AS (
            SELECT
                gsr.SessionId,
                gsr.SessionRoundId,
                gsr.RoundNumber,
                gsr.SquareId,
                gsr.Score,
                gr.ExpansionLevel
            FROM dbo.GameSessionRounds gsr
            INNER JOIN dbo.GameSessions gs
                ON gs.SessionId = gsr.SessionId
            INNER JOIN dbo.GameRounds gr
                ON gr.GameId = gs.GameId
                AND gr.SquareId = gsr.SquareId
            WHERE gsr.SessionId IN ({placeholders})
        )
        SELECT
            gsr.SessionId,
            gsr.SessionRoundId,
            gsr.RoundNumber,
            gsr.SquareId,
            gsr.Score,
            gsr.ExpansionLevel,
            gg.CityName,
            gg.Population,
            gg.Score AS GuessScore,
            gg.GuessedAt,
            matched.CityId,
            CASE
                WHEN matched.CityId IS NULL THEN NULL
                ELSE higher_ranked.CityCount + 1
            END AS PopRank,
            matched.Latitude,
            matched.Longitude
        FROM TargetRounds gsr
        LEFT JOIN dbo.GameGuesses gg
            ON gg.SessionRoundId = gsr.SessionRoundId
        OUTER APPLY (
            SELECT TOP 1
                city.CityId,
                city.Latitude,
                city.Longitude
            FROM dbo.GameSquareCities city
            WHERE city.SquareId = gsr.SquareId
              AND city.CityName = gg.CityName
              AND city.Population = gg.Population
            ORDER BY city.CityId ASC
        ) matched
        OUTER APPLY (
            SELECT COUNT(*) AS CityCount
            FROM dbo.GameSquareCities city
            WHERE city.SquareId = gsr.SquareId
              AND (
                  city.Population > gg.Population
                  OR (
                      city.Population = gg.Population
                      AND city.CityName < gg.CityName
                  )
                  OR (
                      city.Population = gg.Population
                      AND city.CityName = gg.CityName
                      AND city.CityId < matched.CityId
                  )
              )
        ) higher_ranked
        ORDER BY gsr.SessionId ASC, gsr.RoundNumber ASC, gg.GuessedAt ASC, gg.GuessId ASC
        """,
        session_ids,
    )

    log_info(
        f'[profile] _get_completed_round_rows_for_sessions.execute completed in '
        f'{perf_counter() - execute_start:.3f}s'
    )
    rows = _fetchall_with_timing(cur, '_get_completed_round_rows_for_sessions')
    _log_profile_duration('_get_completed_round_rows_for_sessions', start)
    return rows

def _build_completed_rounds_by_session(rows) -> dict[int, list[dict]]:
    start = perf_counter()
    rounds_by_session = defaultdict(dict)

    for row in rows:
        session_id = int(row.SessionId)
        round_number = int(row.RoundNumber)

        if round_number not in rounds_by_session[session_id]:
            rounds_by_session[session_id][round_number] = {
                'session_round_id': int(row.SessionRoundId),
                'round_number': round_number,
                'square_id': int(row.SquareId),
                'expansion_level': int(row.ExpansionLevel),
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

    _log_profile_duration('_build_completed_rounds_by_session', start)
    return result

def _get_best_round(completed_rounds: list[dict]) -> dict | None:
    start = perf_counter()
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

    result = {
        'round_number': int(best_round['round_number']),
        'score': int(best_round['score']),
        'expansion_level': int(best_round['expansion_level']),
        'city_name': best_guess['city_name'] if best_guess else None,
        'population': int(best_guess['population']) if best_guess and best_guess['population'] is not None else None,
        'rank': int(best_guess['rank']) if best_guess and best_guess['rank'] is not None else None,
    }
    _log_profile_duration('_get_best_round', start)
    return result

def _get_strongest_country(cur, user_id: int) -> dict | None:
    start = perf_counter()
    log_info('[profile] _get_strongest_country.execute started')
    execute_start = perf_counter()
    cur.execute(
        """
        WITH ResolvedGuesses AS (
            SELECT
                gg.Score AS GuessScore,
                matched.CountryCode
            FROM dbo.GameSessions gs
            INNER JOIN dbo.GameSessionRounds gsr
                ON gsr.SessionId = gs.SessionId
            INNER JOIN dbo.GameGuesses gg
                ON gg.SessionRoundId = gsr.SessionRoundId
            CROSS APPLY (
                SELECT TOP 1
                    gsc.CountryCode
                FROM dbo.GameSquareCities gsc
                WHERE gsc.SquareId = gsr.SquareId
                  AND gsc.CityName = gg.CityName
                  AND gsc.Population = gg.Population
                ORDER BY gsc.CityId ASC
            ) matched
            WHERE gs.UserId = ?
              AND gs.CompletedAt IS NOT NULL
        )
        SELECT TOP 1
            CountryCode,
            COUNT(*) AS GuessCount,
            AVG(CAST(GuessScore AS float)) AS AverageScore,
            SUM(GuessScore) AS TotalScore
        FROM ResolvedGuesses
        GROUP BY CountryCode
        ORDER BY AVG(CAST(GuessScore AS float)) DESC, COUNT(*) DESC, CountryCode ASC
        """,
        (user_id,),
    )
    log_info(
        f'[profile] _get_strongest_country.execute completed in '
        f'{perf_counter() - execute_start:.3f}s'
    )
    row = _fetchone_with_timing(cur, '_get_strongest_country')

    if not row:
        _log_profile_duration('_get_strongest_country', start)
        return None

    result = {
        'country_code': row.CountryCode,
        'guess_count': int(row.GuessCount),
        'average_score': round(float(row.AverageScore), 2),
        'total_score': int(row.TotalScore),
    }
    _log_profile_duration('_get_strongest_country', start)
    return result

def _get_most_obscure_city(cur, user_id: int) -> dict | None:
    start = perf_counter()
    log_info('[profile] _get_most_obscure_city.execute started')
    execute_start = perf_counter()
    cur.execute(
        """
        SELECT TOP 1
            matched.CityId,
            gg.CityName,
            matched.CountryCode,
            gg.Population,
            matched.NotorietyScore
        FROM dbo.GameSessions gs
        INNER JOIN dbo.GameSessionRounds gsr
            ON gsr.SessionId = gs.SessionId
        INNER JOIN dbo.GameGuesses gg
            ON gg.SessionRoundId = gsr.SessionRoundId
        CROSS APPLY (
            SELECT TOP 1
                gsc.CityId,
                gsc.CountryCode,
                gc.NotorietyScore
            FROM dbo.GameSquareCities gsc
            INNER JOIN dbo.GeoCities gc
                ON gc.CityId = gsc.CityId
            WHERE gsc.SquareId = gsr.SquareId
              AND gsc.CityName = gg.CityName
              AND gsc.Population = gg.Population
              AND gc.NotorietyScore IS NOT NULL
              AND gc.FeatureCode <> 'PPLX'
            ORDER BY gsc.CityId ASC
        ) matched
        WHERE gs.UserId = ?
          AND gs.CompletedAt IS NOT NULL
        ORDER BY matched.NotorietyScore ASC, gg.Population ASC, gg.CityName ASC
        """,
        (user_id,),
    )
    log_info(
        f'[profile] _get_most_obscure_city.execute completed in '
        f'{perf_counter() - execute_start:.3f}s'
    )
    row = _fetchone_with_timing(cur, '_get_most_obscure_city')

    if not row:
        _log_profile_duration('_get_most_obscure_city', start)
        return None

    result = {
        'city_id': int(row.CityId),
        'city_name': row.CityName,
        'country_code': row.CountryCode,
        'population': int(row.Population),
        'notoriety_score': float(row.NotorietyScore),
    }
    _log_profile_duration('_get_most_obscure_city', start)
    return result


def _get_most_used_city(cur, user_id: int) -> dict | None:
    start = perf_counter()
    log_info('[profile] _get_most_used_city.execute started')
    execute_start = perf_counter()
    cur.execute(
        """
        WITH ResolvedGuesses AS (
            SELECT
                gg.CityName,
                gg.Population,
                matched.CityId,
                matched.CountryCode
            FROM dbo.GameSessions gs
            INNER JOIN dbo.GameSessionRounds gsr
                ON gsr.SessionId = gs.SessionId
            INNER JOIN dbo.GameGuesses gg
                ON gg.SessionRoundId = gsr.SessionRoundId
            CROSS APPLY (
                SELECT TOP 1
                    gsc.CityId,
                    gsc.CountryCode
                FROM dbo.GameSquareCities gsc
                WHERE gsc.SquareId = gsr.SquareId
                  AND gsc.CityName = gg.CityName
                  AND gsc.Population = gg.Population
                ORDER BY gsc.CityId ASC
            ) matched
            WHERE gs.UserId = ?
              AND gs.CompletedAt IS NOT NULL
        )
        SELECT TOP 1
            CityId,
            CityName,
            CountryCode,
            Population,
            COUNT(*) AS TimesUsed
        FROM ResolvedGuesses
        GROUP BY CityId, CityName, CountryCode, Population
        ORDER BY COUNT(*) DESC, Population ASC, CityName ASC
        """,
        (user_id,),
    )
    log_info(
        f'[profile] _get_most_used_city.execute completed in '
        f'{perf_counter() - execute_start:.3f}s'
    )
    row = _fetchone_with_timing(cur, '_get_most_used_city')

    if not row:
        _log_profile_duration('_get_most_used_city', start)
        return None

    result = {
        'city_id': int(row.CityId),
        'city_name': row.CityName,
        'country_code': row.CountryCode,
        'population': int(row.Population),
        'times_used': int(row.TimesUsed),
    }
    _log_profile_duration('_get_most_used_city', start)
    return result


def _classify_region(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> str:
    start = perf_counter()
    try:
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        if 54 <= center_lat <= 72 and -25 <= center_lon <= 40:
            return 'Nordic Europe'

        if 43 <= center_lat < 54 and -11 <= center_lon <= 30:
            return 'Mainland Europe'

        if 50 <= center_lat <= 72 and 30 < center_lon <= 60:
            return 'European Russia'

        if 35 <= center_lat <= 55 and 60 <= center_lon <= 95:
            return 'Asian Steppe'

        if 18 <= center_lat <= 50 and 95 < center_lon <= 125:
            return 'China'

        if 30 <= center_lat <= 46 and 125 < center_lon <= 146:
            return 'Japan / Korea'

        if 5 <= center_lat <= 35 and 60 <= center_lon < 95:
            return 'South Asia'

        if -10 <= center_lat <= 25 and 95 <= center_lon <= 135:
            return 'Southeast Asia'

        if 20 <= center_lat <= 45 and 30 <= center_lon < 60:
            return 'West Asia'

        if 20 <= center_lat <= 37 and -17 <= center_lon <= 35:
            return 'North Africa'

        if 4 <= center_lat < 20 and -20 <= center_lon <= 15:
            return 'West Africa'

        if -35 <= center_lat < 20 and -20 <= center_lon <= 52:
            return 'Sub-Saharan Africa'

        if 5 <= center_lat <= 28 and -92 <= center_lon <= -58:
            return 'Caribbean / Central America'

        if 14 <= center_lat <= 33 and -118 <= center_lon < -86:
            return 'Mexico'

        if 25 <= center_lat <= 72 and -170 <= center_lon <= -52:
            return 'US / Canada'

        if -56 <= center_lat <= 13 and -82 <= center_lon <= -34:
            return 'South America'

        if -47 <= center_lat <= 0 and 110 <= center_lon <= 179:
            return 'Oceania'

        return 'Other'
    finally:
        pass


def _get_region_performance(cur, user_id: int) -> tuple[list[dict], list[dict]]:
    start = perf_counter()
    log_info(f'[profile] _get_region_performance user_id={user_id}')
    log_info('[profile] _get_region_performance.execute started')
    execute_start = perf_counter()
    cur.execute(
        """
        SELECT
            g.GameDate,
            gsr.RoundNumber,
            gsr.Score,
            gg.CityName AS GuessedCity,
            gg.Population AS GuessedPopulation,
            topcity.CityName AS TopCityName,
            topcity.Population AS TopCityPopulation,
            gsq.MinLat,
            gsq.MinLon,
            gsq.MaxLat,
            gsq.MaxLon
        FROM dbo.GameSessions gs
        INNER JOIN dbo.Games g
            ON g.GameId = gs.GameId
        INNER JOIN dbo.GameSessionRounds gsr
            ON gsr.SessionId = gs.SessionId
        LEFT JOIN dbo.GameGuesses gg
            ON gg.SessionRoundId = gsr.SessionRoundId
        INNER JOIN dbo.GameSquares gsq
            ON gsq.SquareId = gsr.SquareId
        OUTER APPLY (
            SELECT TOP 1
                gsc.CityName,
                gsc.Population
            FROM dbo.GameSquareCities gsc
            WHERE gsc.SquareId = gsr.SquareId
            ORDER BY gsc.Population DESC, gsc.CityName ASC
        ) topcity
        WHERE gs.UserId = ?
            AND gs.CompletedAt IS NOT NULL
        ORDER BY g.GameDate DESC, gsr.RoundNumber ASC
        """,
        (user_id,),
    )
    log_info(
        f'[profile] _get_region_performance.execute completed in '
        f'{perf_counter() - execute_start:.3f}s'
    )
    rows = _fetchall_with_timing(cur, '_get_region_performance')

    process_start = perf_counter()
    buckets = {
        region: {
            'region': region,
            'square_count': 0,
            'solved_count': 0,
            'total_points': 0,
        }
        for region in REGION_ORDER
    }

    details = []

    for row in rows:
        min_lat = float(row.MinLat)
        min_lon = float(row.MinLon)
        max_lat = float(row.MaxLat)
        max_lon = float(row.MaxLon)
        score = int(row.Score)

        region = _classify_region(min_lat, min_lon, max_lat, max_lon)

        if region not in buckets:
            buckets[region] = {
                'region': region,
                'square_count': 0,
                'solved_count': 0,
                'total_points': 0,
            }

        buckets[region]['square_count'] += 1
        buckets[region]['total_points'] += score

        if score > 0:
            buckets[region]['solved_count'] += 1

        details.append({
            'game_date': row.GameDate.isoformat(),
            'round_number': int(row.RoundNumber),
            'region': region,
            'score': score,
            'solved': score > 0,
            'guessed_city': row.GuessedCity,
            'guessed_population': int(row.GuessedPopulation) if row.GuessedPopulation is not None else None,
            'top_city_name': row.TopCityName,
            'top_city_population': int(row.TopCityPopulation) if row.TopCityPopulation is not None else None,
        })

    summary = []
    for region in REGION_ORDER:
        region_data = buckets[region]
        square_count = int(region_data['square_count'])
        solved_count = int(region_data['solved_count'])
        total_points = int(region_data['total_points'])

        summary.append({
            'region': region,
            'square_count': square_count,
            'solved_count': solved_count,
            'completion_rate': round((solved_count / square_count) * 100, 2) if square_count else 0.0,
            'average_points': round(total_points / square_count, 2) if square_count else 0.0,
        })

    log_info(
        f'[profile] _get_region_performance.process completed in '
        f'{perf_counter() - process_start:.3f}s row_count={len(rows)}'
    )

    _log_profile_duration('_get_region_performance', start)
    return summary, details
    return summary, details


def _build_summary(
    history: list[dict],
    most_obscure_city: dict | None,
    most_used_city: dict | None,
    strongest_country: dict | None,
) -> dict:
    start = perf_counter()
    games_played = len(history)
    perfect_games_played = sum(1 for game in history if game['is_perfect'])
    total_points = sum(int(game['total_score']) for game in history)
    total_squares_solved = sum(int(game['solved_count']) for game in history)
    average_points = round(total_points / games_played, 2) if games_played else 0.0
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

    result = {
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
        'strongest_country': strongest_country,
    }
    _log_profile_duration('_build_summary', start)
    return result

def _calculate_game_streak(history: list[dict]) -> int:
    start = perf_counter()
    if not history:
        _log_profile_duration('_calculate_game_streak', start)
        return 0

    ordered_dates = []
    seen = set()

    for game in history:
        game_date = date.fromisoformat(game['game_date'])
        if game_date not in seen:
            seen.add(game_date)
            ordered_dates.append(game_date)

    ordered_dates.sort(reverse=True)

    streak = 1
    previous_date = ordered_dates[0]

    for game_date in ordered_dates[1:]:
        if game_date == previous_date - timedelta(days=1):
            streak += 1
            previous_date = game_date
            continue
        break

    _log_profile_duration('_calculate_game_streak', start)
    return streak

def _calculate_perfect_streak(history: list[dict]) -> int:
    start = perf_counter()
    if not history:
        _log_profile_duration('_calculate_perfect_streak', start)
        return 0

    perfect_dates = []
    for game in history:
        if not game['is_perfect']:
            break
        perfect_dates.append(date.fromisoformat(game['game_date']))

    if not perfect_dates:
        _log_profile_duration('_calculate_perfect_streak', start)
        return 0

    streak = 1
    previous_date = perfect_dates[0]

    for game_date in perfect_dates[1:]:
        if game_date == previous_date - timedelta(days=1):
            streak += 1
            previous_date = game_date
            continue
        break

    _log_profile_duration('_calculate_perfect_streak', start)
    return streak