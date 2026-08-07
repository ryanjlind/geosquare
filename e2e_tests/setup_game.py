import os
import random
from datetime import date

from app.core.db import get_conn
from app.core.game_generation import fetch_cities_in_bounds, persist_square

PLAYABILITY_THRESHOLD = 80.0
ROUND_COUNT = 5
EXPANSION_LEVEL_COUNT = 5
EXPANSION_SCALE = 1.5
MIN_LATITUDE = -56.0
MAX_LATITUDE = 78.0
MIN_LONGITUDE = -180.0
MAX_LONGITUDE = 180.0


def required_environment_value(name: str) -> str:
    value = os.environ[name].strip()
    if not value:
        raise ValueError(f'{name} must not be empty.')
    return value


def delete_existing_game(cur, game_date: date) -> None:
    cur.execute('SELECT GameId FROM dbo.Games WHERE GameDate = ?', game_date)
    row = cur.fetchone()
    if row is None:
        return

    game_id = int(row.GameId)
    cur.execute(
        'SELECT SquareId FROM dbo.GameRounds WHERE GameId = ?',
        game_id,
    )
    square_ids = [int(square.SquareId) for square in cur.fetchall()]

    cur.execute("""
        DELETE gg
        FROM dbo.GameGuesses gg
        INNER JOIN dbo.GameSessionRounds gsr
            ON gsr.SessionRoundId = gg.SessionRoundId
        INNER JOIN dbo.GameSessions gs
            ON gs.SessionId = gsr.SessionId
        WHERE gs.GameId = ?
    """, game_id)
    cur.execute("""
        DELETE gsr
        FROM dbo.GameSessionRounds gsr
        INNER JOIN dbo.GameSessions gs
            ON gs.SessionId = gsr.SessionId
        WHERE gs.GameId = ?
    """, game_id)
    cur.execute('DELETE FROM dbo.GameSessions WHERE GameId = ?', game_id)
    cur.execute('DELETE FROM dbo.GameRounds WHERE GameId = ?', game_id)
    cur.execute('DELETE FROM dbo.Games WHERE GameId = ?', game_id)

    if square_ids:
        placeholders = ', '.join('?' for _ in square_ids)
        cur.execute(
            f'DELETE FROM dbo.GameSquareCities WHERE SquareId IN ({placeholders})',
            *square_ids,
        )
        cur.execute(
            f'DELETE FROM dbo.GameSquares WHERE SquareId IN ({placeholders})',
            *square_ids,
        )


def select_playable_squares(cur, square_pool_id: int, random_seed: int) -> list[dict]:
    cur.execute("""
        SELECT
            sp.SquareId,
            sp.CenterLat,
            sp.CenterLng,
            sp.SquareLength,
            grade.PlayabilityScore
        FROM dbo.SquarePool sp
        INNER JOIN (
            SELECT g.SquarePoolId, g.SquareId, g.PlayabilityScore
            FROM dbo.SquarePoolGrades g
            INNER JOIN (
                SELECT SquarePoolId, SquareId, MAX(SquarePoolGradeId) AS GradeId
                FROM dbo.SquarePoolGrades
                GROUP BY SquarePoolId, SquareId
            ) latest
                ON latest.GradeId = g.SquarePoolGradeId
        ) grade
            ON grade.SquarePoolId = sp.SquarePoolId
            AND grade.SquareId = sp.SquareId
        WHERE sp.SquarePoolId = ?
          AND grade.PlayabilityScore > ?
        ORDER BY sp.SquareId
    """, square_pool_id, PLAYABILITY_THRESHOLD)

    candidates = [
        {
            'square_id': int(row.SquareId),
            'center_lat': float(row.CenterLat),
            'center_lon': float(row.CenterLng),
            'square_length': float(row.SquareLength),
            'playability_score': float(row.PlayabilityScore),
        }
        for row in cur.fetchall()
    ]

    if len(candidates) < ROUND_COUNT:
        raise ValueError(
            f'Pool {square_pool_id} has {len(candidates)} playable squares; '
            f'{ROUND_COUNT} are required.'
        )

    return random.Random(random_seed).sample(candidates, ROUND_COUNT)


def expansion_bounds(square: dict, expansion_level: int) -> dict:
    half = square['square_length'] / 2.0
    base_min_lat = max(MIN_LATITUDE, square['center_lat'] - half)
    base_max_lat = min(MAX_LATITUDE, square['center_lat'] + half)
    base_min_lon = max(MIN_LONGITUDE, square['center_lon'] - half)
    base_max_lon = min(MAX_LONGITUDE, square['center_lon'] + half)
    scale = EXPANSION_SCALE ** expansion_level
    height = (base_max_lat - base_min_lat) * scale
    width = (base_max_lon - base_min_lon) * scale
    center_lat = (base_min_lat + base_max_lat) / 2.0
    center_lon = (base_min_lon + base_max_lon) / 2.0

    return {
        'min_lat': center_lat - (height / 2.0),
        'min_lon': center_lon - (width / 2.0),
        'max_lat': center_lat + (height / 2.0),
        'max_lon': center_lon + (width / 2.0),
    }


def create_test_game(cur, game_date: date, selected_squares: list[dict]) -> int:
    cur.execute("""
        INSERT INTO dbo.Games (GameDate)
        OUTPUT INSERTED.GameId
        VALUES (?)
    """, game_date)
    game_id = int(cur.fetchone()[0])

    for round_number, selected_square in enumerate(selected_squares, start=1):
        print(
            f'Creating round {round_number} from pool square '
            f'{selected_square["square_id"]}...',
            flush=True,
        )
        for expansion_level in range(EXPANSION_LEVEL_COUNT):
            bounds = expansion_bounds(selected_square, expansion_level)
            cities = fetch_cities_in_bounds(
                cur,
                bounds['min_lat'],
                bounds['min_lon'],
                bounds['max_lat'],
                bounds['max_lon'],
            )
            square_id = persist_square(cur, {
                'seed_lat': selected_square['center_lat'],
                'seed_lon': selected_square['center_lon'],
                'min_lat': bounds['min_lat'],
                'min_lon': bounds['min_lon'],
                'max_lat': bounds['max_lat'],
                'max_lon': bounds['max_lon'],
                'width_degrees': bounds['max_lon'] - bounds['min_lon'],
                'height_degrees': bounds['max_lat'] - bounds['min_lat'],
                'cities': cities,
            })
            cur.execute("""
                INSERT INTO dbo.GameRounds (
                    GameId,
                    RoundNumber,
                    SquareId,
                    ExpansionLevel
                ) VALUES (?, ?, ?, ?)
            """, game_id, round_number, square_id, expansion_level)

    return game_id


def main() -> None:
    game_date = date.fromisoformat(required_environment_value('E2E_GAME_DATE'))
    square_pool_id = int(required_environment_value('E2E_SQUARE_POOL_ID'))
    random_seed = int(required_environment_value('E2E_RANDOM_SEED'))

    with get_conn(e2e=True) as conn:
        cur = conn.cursor()
        print(f'Rebuilding E2E game for {game_date.isoformat()}...', flush=True)
        delete_existing_game(cur, game_date)
        selected_squares = select_playable_squares(cur, square_pool_id, random_seed)
        print(
            'Selected pool squares: '
            + ', '.join(str(square['square_id']) for square in selected_squares),
            flush=True,
        )
        game_id = create_test_game(cur, game_date, selected_squares)
        conn.commit()

    print(f'Created E2E game {game_id}.', flush=True)


if __name__ == '__main__':
    main()