import logging
from types import SimpleNamespace

from app.helpers.date import get_effective_game_date
from app.helpers.text import strip_accents

_logger = logging.getLogger('geosquare')

def get_base_square_id_for_round(cur, game_id: int, round_number: int):
    cur.execute("""
        SELECT TOP 1 SquareId
        FROM dbo.GameRounds
        WHERE GameId = ?
          AND RoundNumber = ?
          AND ExpansionLevel = 0
    """, game_id, round_number)
    row = cur.fetchone()
    return int(row.SquareId) if row else None

def get_today_game(cur):
    game_date = get_effective_game_date()    
    cur.execute("""
        SELECT TOP 1 GameId
        FROM dbo.Games
        WHERE GameDate = ?
    """, game_date)

    return cur.fetchone()


def get_square_cities(cur, square_id: int):
    cur.execute("""
        SELECT CityName, CountryCode, Latitude, Longitude, Population
        FROM dbo.GameSquareCities
        WHERE SquareId = ?
        ORDER BY Population DESC, CityName ASC
    """, square_id)
    return cur.fetchall()


def get_square_city_count(cur, square_id: int):
    cur.execute("""
        SELECT COUNT(*) AS TotalCityCount
        FROM dbo.GameSquareCities
        WHERE SquareId = ?
    """, square_id)
    return cur.fetchone()


def create_session(cur, user_id: int, game_id: int):
    cur.execute("""
        INSERT INTO dbo.GameSessions
            (GameId, UserId, StartedAt, CompletedAt, TotalScore)
        OUTPUT
            inserted.SessionId,
            inserted.GameId,
            inserted.UserId,
            inserted.StartedAt,
            inserted.CompletedAt,
            inserted.TotalScore
        VALUES
            (?, ?, SYSUTCDATETIME(), NULL, 0)
    """, game_id, user_id)
    return cur.fetchone()


def get_square_id_for_round(cur, game_id: int, round_number: int):
    cur.execute("""
       SELECT TOP 1
            gs.SquareId,
            gr.ExpansionLevel
        FROM dbo.GameRounds gr
        INNER JOIN dbo.GameSquares gs ON gr.SquareId = gs.SquareId
        WHERE gr.GameId = ?
        AND gr.RoundNumber = ?
    """, game_id, round_number)
    return cur.fetchone()

def get_ranked_square_cities(cur, square_id: int):
    cur.execute("""
        SELECT
            c.CityId,
            c.CityName,
            c.CountryCode,
            c.Latitude,
            c.Longitude,
            c.Population,
            ROW_NUMBER() OVER (ORDER BY c.Population DESC) AS PopRank,
            gc.AltNames AS AlternateNames,
            gc.ProvinceCodes
        FROM dbo.GameSquareCities c
        LEFT JOIN dbo.GeoCities gc
            ON gc.CityId = c.CityId
        WHERE c.SquareId = ?
            AND gc.FeatureCode <> 'PPLX'
        ORDER BY c.Population DESC
    """, square_id)
    return cur.fetchall()

def get_session_round(cur, session_id: int, round_number: int):
    cur.execute("""
        SELECT TOP 1
            SessionRoundId,
            SessionId,
            RoundNumber,
            SquareId,
            Score,
            RoundStatus
        FROM dbo.GameSessionRounds
        WHERE SessionId = ?
          AND RoundNumber = ?
        ORDER BY SessionRoundId DESC
    """, session_id, round_number)
    return cur.fetchone()

def insert_correct_guess(cur, session_round_id: int, city_name: str, population: int, score: int):
    cur.execute("""
        INSERT INTO dbo.GameGuesses
            (SessionRoundId, CityName, IsCorrect, Population, Score, GuessedAt)
        VALUES
            (?, ?, 1, ?, ?, SYSUTCDATETIME())
    """, session_round_id, city_name, population, score)


def increment_session_total_score(cur, session_id: int, score: int):
    cur.execute("""
        UPDATE dbo.GameSessions
        SET TotalScore = TotalScore + ?
        WHERE SessionId = ?
    """, score, session_id)


def get_session_total_score(cur, session_id: int):
    cur.execute("""
        SELECT TotalScore
        FROM dbo.GameSessions
        WHERE SessionId = ?
    """, session_id)
    return cur.fetchone()


def complete_session(cur, session_id: int):
    cur.execute("""
        UPDATE dbo.GameSessions
        SET CompletedAt = SYSUTCDATETIME()
        WHERE SessionId = ?
    """, session_id)

def find_city_anywhere(cur, guess_text: str):
    normalized_guess = strip_accents(guess_text).lower().strip()

    cur.execute("""
        SELECT TOP 1
            CityId,
            CityName,
            CountryCode,
            Latitude,
            Longitude,
            Population
        FROM dbo.GeoCities
        WHERE IsActive = 1
          AND CityNameLower = ?
          AND FeatureCode <> 'PPLX'
        ORDER BY Population DESC, CityId ASC
    """, normalized_guess)
    return cur.fetchone()

def get_completed_round_rows(cur, session_id: int):
    cur.execute("""
        SELECT
            gsr.SessionRoundId,
            gsr.RoundNumber,
            gsr.SquareId,
            gsr.RoundStatus,
            gsr.Score,
            gr.ExpansionLevel
        FROM dbo.GameSessionRounds gsr
        INNER JOIN dbo.GameSessions gs
            ON gs.SessionId = gsr.SessionId
        INNER JOIN dbo.GameRounds gr
            ON gr.GameId = gs.GameId
            AND gr.RoundNumber = gsr.RoundNumber
            AND gr.SquareId = gsr.SquareId
        WHERE gsr.SessionId = ?
          AND gsr.RoundStatus IN ('Completed', 'Passed')
        ORDER BY gsr.RoundNumber ASC, gsr.SessionRoundId ASC
    """, session_id)

    completed_rounds = []

    for round_row in cur.fetchall():
        _logger.debug('get_completed_round_rows: processing session_round_id=%s', round_row.SessionRoundId)
        cur.execute("""
            SELECT
                gg.CityName,
                gg.Population,
                gg.GuessedAt
            FROM dbo.GameGuesses gg
            WHERE gg.SessionRoundId = ?
              AND gg.IsCorrect = 1
            ORDER BY gg.GuessedAt ASC
        """, int(round_row.SessionRoundId))
        guess_rows = cur.fetchall()

        cur.execute("""
            SELECT
                c.CityId,
                c.CityName,
                c.Latitude,
                c.Longitude,
                c.Population
            FROM dbo.GameSquareCities c
            WHERE c.SquareId = ?
            ORDER BY c.Population DESC, c.CityName ASC
        """, int(round_row.SquareId))
        ranked_city_rows = cur.fetchall()

        rank_map = {
            (row.CityName, int(row.Population)): {
                'city_id': int(row.CityId),
                'rank': index + 1,
                'latitude': float(row.Latitude),
                'longitude': float(row.Longitude),
                'population': int(row.Population),
            }
            for index, row in enumerate(ranked_city_rows)
        }

        base_row = SimpleNamespace(
            SessionRoundId=round_row.SessionRoundId,
            RoundNumber=round_row.RoundNumber,
            SquareId=round_row.SquareId,
            RoundStatus=round_row.RoundStatus,
            Score=round_row.Score,
            ExpansionLevel=round_row.ExpansionLevel,
            CityName=None,
            CityId=None,
            Population=None,
            GuessedAt=None,
            PopRank=None,
            Latitude=None,
            Longitude=None,
        )
        completed_rounds.append(base_row)

        for guess_row in guess_rows:
            matched = rank_map.get((guess_row.CityName, int(guess_row.Population)))
            if not matched:
                continue

            completed_rounds.append(SimpleNamespace(
                SessionRoundId=round_row.SessionRoundId,
                RoundNumber=round_row.RoundNumber,
                SquareId=round_row.SquareId,
                RoundStatus=round_row.RoundStatus,
                Score=round_row.Score,
                ExpansionLevel=round_row.ExpansionLevel,
                CityName=guess_row.CityName,
                CityId=matched['city_id'],
                Population=matched['population'],
                GuessedAt=guess_row.GuessedAt,
                PopRank=matched['rank'],
                Latitude=matched['latitude'],
                Longitude=matched['longitude'],
            ))

    return completed_rounds

def get_completed_sessions_for_user(cur, user_id: int, through_game_date: str):
    cur.execute("""
        SELECT
            gs.SessionId,
            gs.TotalScore,
            gs.CompletedAt,
            g.GameDate
        FROM dbo.GameSessions gs
        INNER JOIN dbo.Games g
            ON g.GameId = gs.GameId
        WHERE gs.UserId = ?
          AND gs.CompletedAt IS NOT NULL
          AND g.GameDate <= ?
        ORDER BY g.GameDate ASC, gs.SessionId ASC
    """, user_id, through_game_date)
    return cur.fetchall()


def get_best_guess_for_user(cur, user_id: int, through_game_date: str):
    cur.execute("""
        SELECT TOP 1
            gg.CityName,
            gg.Population,
            gg.Score,
            g.GameDate,
            gsr.RoundNumber
        FROM dbo.GameGuesses gg
        INNER JOIN dbo.GameSessionRounds gsr
            ON gsr.SessionRoundId = gg.SessionRoundId
        INNER JOIN dbo.GameSessions gs
            ON gs.SessionId = gsr.SessionId
        INNER JOIN dbo.Games g
            ON g.GameId = gs.GameId
        WHERE gs.UserId = ?
          AND gs.CompletedAt IS NOT NULL
          AND g.GameDate <= ?
        ORDER BY gg.Score DESC, g.GameDate DESC, gg.GuessId DESC
    """, user_id, through_game_date)
    return cur.fetchone()

def get_round_stats_for_sessions(cur, session_ids: list[int]) -> dict[int, dict]:
    if not session_ids:
        return {}

    placeholders = ','.join(['?'] * len(session_ids))

    cur.execute(f"""
        SELECT
            SessionId,
            COUNT(*) AS TotalRounds,
            SUM(CASE WHEN RoundStatus = 'Completed' THEN 1 ELSE 0 END) AS SolvedRounds
        FROM dbo.GameSessionRounds
        WHERE SessionId IN ({placeholders})
        GROUP BY SessionId
    """, *session_ids)

    return {
        int(row.SessionId): {
            'total_rounds': int(row.TotalRounds),
            'solved_rounds': int(row.SolvedRounds),
        }
        for row in cur.fetchall()
    }

def get_game_id_by_date(cur, game_date: str):
    cur.execute(
        """
        SELECT GameId
        FROM Games
        WHERE GameDate = ?
        """,
        (game_date,)
    )
    row = cur.fetchone()
    return int(row.GameId) if row else None

def has_next_expansion_level(cur, game_id: int, round_number: int, square_id: int) -> bool:
    cur.execute("""
        SELECT TOP 1 1
        FROM dbo.GameRounds
        WHERE GameId = ?
          AND RoundNumber = ?
          AND SquareId = ?
    """, (game_id, round_number, square_id))

    row = cur.fetchone()
    if not row:
        return False

    cur.execute("""
        SELECT TOP 1 1
        FROM dbo.GameRounds
        WHERE GameId = ?
          AND RoundNumber = ?
          AND ExpansionLevel >
              (SELECT ExpansionLevel
               FROM dbo.GameRounds
               WHERE GameId = ?
                 AND RoundNumber = ?
                 AND SquareId = ?)
        ORDER BY ExpansionLevel ASC
    """, (game_id, round_number, game_id, round_number, square_id))

    return cur.fetchone() is not None

def get_active_session_square(cur, session_id: int, round_number: int):
    cur.execute("""
        SELECT TOP 1 gsr.SquareId, gr.ExpansionLevel
        FROM dbo.GameSessionRounds gsr
            INNER JOIN dbo.GameSessions gs
                ON gsr.SessionId = gs.SessionId
            INNER JOIN dbo.GameRounds gr 
                ON gsr.SquareId = gr.SquareId 
                AND gs.GameId = gr.GameId
                AND gsr.RoundNumber = gr.RoundNumber
        WHERE gsr.SessionId = ?
          AND gsr.RoundNumber = ?
        ORDER BY gsr.SessionRoundId DESC
    """, (session_id, round_number))

    return cur.fetchone()    

def get_next_expansion_square(cur, game_id: int, round_number: int, current_square_id: int):
    cur.execute("""
        SELECT TOP 1
            gs.SquareId,
            gr.ExpansionLevel
        FROM dbo.GameRounds gr
        INNER JOIN dbo.GameSquares gs
            ON gs.SquareId = gr.SquareId
        WHERE gr.GameId = ?
          AND gr.RoundNumber = ?
          AND gr.ExpansionLevel >
              (SELECT ExpansionLevel
               FROM dbo.GameRounds
               WHERE GameId = ?
                 AND RoundNumber = ?
                 AND SquareId = ?)
        ORDER BY gr.ExpansionLevel ASC
    """, (game_id, round_number, game_id, round_number, current_square_id))

    return cur.fetchone()

# Shared square column selection for get_square_by_id
_SQUARE_SELECT_COLUMNS = """
    gr.GameId,
    gr.RoundNumber,
    gr.ExpansionLevel,
    gs.SquareId,
    gs.SeedLat,
    gs.SeedLon,
    gs.MinLat,
    gs.MinLon,
    gs.MaxLat,
    gs.MaxLon,
    gs.WidthDegrees,
    gs.HeightDegrees,
    gs.GeneratedAt
"""

def get_square_by_id(cur, square_id: int):
    cur.execute(f"""
        SELECT TOP 1 {_SQUARE_SELECT_COLUMNS}
        FROM dbo.GameRounds gr
        INNER JOIN dbo.GameSquares gs
            ON gs.SquareId = gr.SquareId
        WHERE gs.SquareId = ?
        ORDER BY gr.RoundNumber DESC, gr.ExpansionLevel DESC
    """, square_id)

    return cur.fetchone()

def _upsert_session_round(cur, session_id: int, round_number: int, square_id: int, round_status: str, score: int = 0):
    """Helper to upsert session rounds with MERGE pattern."""
    cur.execute("""
        MERGE dbo.GameSessionRounds AS target
        USING (SELECT ? AS SessionId, ? AS RoundNumber) AS src
        ON target.SessionId = src.SessionId AND target.RoundNumber = src.RoundNumber
        WHEN MATCHED THEN
            UPDATE SET SquareId = ?, RoundStatus = ?, Score = ?
        WHEN NOT MATCHED THEN
            INSERT (SessionId, RoundNumber, SquareId, RoundStatus, Score)
            VALUES (?, ?, ?, ?, ?);
    """, session_id, round_number, square_id, round_status, score, session_id, round_number, square_id, round_status, score)

def upsert_session_round_expand(cur, session_id: int, round_number: int, square_id: int):
    _upsert_session_round(cur, session_id, round_number, square_id, 'Expanded', 0)

def set_round_completed(cur, session_id: int, round_number: int, square_id: int, score: int):
    _upsert_session_round(cur, session_id, round_number, square_id, 'Completed', score)

def set_round_passed(cur, session_id: int, round_number: int, square_id: int):
    _upsert_session_round(cur, session_id, round_number, square_id, 'Passed', 0)