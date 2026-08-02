def get_infinity_session(cur, user_id: int, game_id: int):
    cur.execute(
        """
        SELECT
            InfinityPoolSessionId,
            GameId,
            UserId,
            CurrentRoundNumber,
            StartedAt,
            UpdatedAt
        FROM dbo.InfinityPoolSessions
        WHERE UserId = ?
          AND GameId = ?
        """,
        (user_id, game_id),
    )
    return cur.fetchone()


def create_infinity_session(cur, user_id: int, game_id: int):
    cur.execute(
        """
        INSERT INTO dbo.InfinityPoolSessions (
            GameId,
            UserId,
            CurrentRoundNumber,
            StartedAt,
            UpdatedAt
        )
        OUTPUT
            inserted.InfinityPoolSessionId,
            inserted.GameId,
            inserted.UserId,
            inserted.CurrentRoundNumber,
            inserted.StartedAt,
            inserted.UpdatedAt
        VALUES (?, ?, 1, SYSUTCDATETIME(), SYSUTCDATETIME())
        """,
        (game_id, user_id),
    )
    return cur.fetchone()


def update_current_round(cur, infinity_session_id: int, round_number: int) -> None:
    cur.execute(
        """
        UPDATE dbo.InfinityPoolSessions
        SET CurrentRoundNumber = ?,
            UpdatedAt = SYSUTCDATETIME()
        WHERE InfinityPoolSessionId = ?
        """,
        (round_number, infinity_session_id),
    )


def get_infinity_guesses(cur, infinity_session_id: int):
    cur.execute(
        """
        SELECT
            guess.RoundNumber,
            guess.CityName,
            guess.Score,
            city.Latitude,
            city.Longitude
        FROM dbo.InfinityPoolGuesses guess
        INNER JOIN dbo.GameSquareCities city
            ON city.SquareId = guess.SquareId
            AND city.CityId = guess.CityId
        WHERE guess.InfinityPoolSessionId = ?
        ORDER BY guess.RoundNumber, guess.GuessedAt, guess.InfinityPoolGuessId
        """,
        (infinity_session_id,),
    )
    return cur.fetchall()


def infinity_guess_exists(
    cur,
    infinity_session_id: int,
    round_number: int,
    city_id: int,
) -> bool:
    cur.execute(
        """
        SELECT TOP 1 1
        FROM dbo.InfinityPoolGuesses
        WHERE InfinityPoolSessionId = ?
          AND RoundNumber = ?
          AND CityId = ?
        """,
        (infinity_session_id, round_number, city_id),
    )
    return cur.fetchone() is not None


def insert_infinity_guess(
    cur,
    infinity_session_id: int,
    round_number: int,
    square_id: int,
    city_id: int,
    city_name: str,
    population: int,
    score: int,
) -> None:
    cur.execute(
        """
        INSERT INTO dbo.InfinityPoolGuesses (
            InfinityPoolSessionId,
            RoundNumber,
            SquareId,
            CityId,
            CityName,
            Population,
            Score,
            GuessedAt
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME())
        """,
        (
            infinity_session_id,
            round_number,
            square_id,
            city_id,
            city_name,
            population,
            score,
        ),
    )


def get_infinity_scores(cur, infinity_session_id: int):
    cur.execute(
        """
        SELECT
            RoundNumber,
            SUM(Score) AS RoundScore
        FROM dbo.InfinityPoolGuesses
        WHERE InfinityPoolSessionId = ?
        GROUP BY RoundNumber
        ORDER BY RoundNumber
        """,
        (infinity_session_id,),
    )
    return cur.fetchall()