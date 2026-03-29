from app.helpers.date import get_effective_game_date

def get_today_game(cur):
    game_date = get_effective_game_date()
    print(game_date)
    cur.execute("""
        SELECT TOP 1 GameId
        FROM dbo.Games
        WHERE GameDate = ?
    """, game_date)

    return cur.fetchone()

def get_square_for_round(cur, game_id: int, round_number: int):
    cur.execute("""
        SELECT TOP 1
            g.GameId,
            gr.RoundNumber,
            gs.SquareId,
            gs.SeedLat,
            gs.SeedLon,
            gs.MinLat,
            gs.MinLon,
            gs.MaxLat,
            gs.MaxLon,
            gs.TotalPopulation,
            gs.QualifyingCityCount,
            gs.WidthDegrees,
            gs.HeightDegrees,
            gs.GeneratedAt,
            c.ConfigKey,
            c.MinTotalPopulation,
            c.MinCityCount,
            c.MinCityPopulation,
            c.MaxSquareWidthDegrees,
            c.MaxSquareHeightDegrees,
            c.StepDegrees
        FROM dbo.Games g
        INNER JOIN dbo.GameRounds gr ON g.GameId = gr.GameId
        INNER JOIN dbo.GameSquares gs ON gr.SquareId = gs.SquareId
        INNER JOIN dbo.GameConfig c ON gs.ConfigId = c.ConfigId
        WHERE g.GameId = ?
          AND gr.RoundNumber = ?
    """, game_id, round_number)
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


def get_session_by_id(cur, session_id: int):
    cur.execute("""
        SELECT TOP 1
            SessionId,
            GameId,
            UserId,
            StartedAt,
            CompletedAt,
            TotalScore
        FROM dbo.GameSessions
        WHERE SessionId = ?
    """, session_id)
    return cur.fetchone()


def get_latest_session_round(cur, session_id: int):
    cur.execute("""
        SELECT TOP 1
            SessionRoundId,
            SessionId,
            RoundNumber,
            SquareId,
            Score
        FROM dbo.GameSessionRounds
        WHERE SessionId = ?
        ORDER BY RoundNumber DESC, SessionRoundId DESC
    """, session_id)
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
            gs.SquareId
        FROM dbo.GameRounds gr
        INNER JOIN dbo.GameSquares gs ON gr.SquareId = gs.SquareId
        WHERE gr.GameId = ?
          AND gr.RoundNumber = ?
    """, game_id, round_number)
    return cur.fetchone()


def get_ranked_square_cities(cur, square_id: int):
    cur.execute("""
        SELECT
            CityName,
            CountryCode,
            Latitude,
            Longitude,
            Population,
            ROW_NUMBER() OVER (ORDER BY Population DESC) AS PopRank
        FROM dbo.GameSquareCities
        WHERE SquareId = ?
    """, square_id)
    return cur.fetchall()


def get_or_create_session_round(cur, session_id: int, round_number: int, square_id: int):
    cur.execute("""
        SELECT TOP 1
            SessionRoundId,
            SessionId,
            RoundNumber,
            SquareId,
            Score
        FROM dbo.GameSessionRounds
        WHERE SessionId = ?
          AND RoundNumber = ?
        ORDER BY SessionRoundId DESC
    """, session_id, round_number)
    existing = cur.fetchone()

    if existing is not None:
        return existing

    cur.execute("""
        INSERT INTO dbo.GameSessionRounds
            (SessionId, RoundNumber, SquareId, Score)
        OUTPUT
            inserted.SessionRoundId,
            inserted.SessionId,
            inserted.RoundNumber,
            inserted.SquareId,
            inserted.Score
        VALUES
            (?, ?, ?, 0)
    """, session_id, round_number, square_id)
    return cur.fetchone()


def insert_correct_guess(cur, session_round_id: int, city_name: str, population: int, score: int):
    cur.execute("""
        INSERT INTO dbo.GameGuesses
            (SessionRoundId, CityName, IsCorrect, Population, Score, GuessedAt)
        VALUES
            (?, ?, 1, ?, ?, SYSUTCDATETIME())
    """, session_round_id, city_name, population, score)


def increment_session_round_score(cur, session_round_id: int, score: int):
    cur.execute("""
        UPDATE dbo.GameSessionRounds
        SET Score = Score + ?
        WHERE SessionRoundId = ?
    """, score, session_round_id)


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
          AND LOWER(CityName) = LOWER(?)
        ORDER BY Population DESC, CityId ASC
    """, guess_text)
    return cur.fetchone()

def get_completed_round_rows(cur, session_id: int):
    cur.execute("""
        SELECT
            gsr.SessionRoundId,
            gsr.RoundNumber,
            gsr.SquareId,
            gsr.Score,
            gg.CityName,            
            gg.Population,
            gg.Score AS GuessScore,
            gg.GuessedAt,
            ranked.PopRank
        FROM dbo.GameSessionRounds gsr
        LEFT JOIN dbo.GameGuesses gg
            ON gg.SessionRoundId = gsr.SessionRoundId
            AND gg.IsCorrect = 1
        LEFT JOIN (
            SELECT
                SquareId,
                CityName,
                Population,
                ROW_NUMBER() OVER (
                    PARTITION BY SquareId
                    ORDER BY Population DESC, CityName ASC
                ) AS PopRank
            FROM dbo.GameSquareCities
        ) ranked
            ON ranked.SquareId = gsr.SquareId
            AND ranked.CityName = gg.CityName
            AND ranked.Population = gg.Population
        WHERE gsr.SessionId = ?
        ORDER BY gsr.RoundNumber ASC, gg.GuessedAt ASC, gg.GuessId ASC
    """, session_id)
    return cur.fetchall()

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
            gsr.SessionId,
            COUNT(*) AS TotalRounds,
            SUM(CASE WHEN gsr.Score > 0 THEN 1 ELSE 0 END) AS SolvedRounds
        FROM dbo.GameSessionRounds gsr
        WHERE gsr.SessionId IN ({placeholders})
        GROUP BY gsr.SessionId
    """, *session_ids)

    return {
        int(row.SessionId): {
            'total_rounds': int(row.TotalRounds),
            'solved_rounds': int(row.SolvedRounds),
        }
        for row in cur.fetchall()
    }