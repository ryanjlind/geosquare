import os
from datetime import date

from app.core.db import get_conn
from app.core.game_generation import fetch_cities_in_bounds, persist_square

FIXED_POOL_SQUARE_IDS = (242, 301, 289, 171, 236)
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


def load_fixed_squares(cur, square_pool_id: int) -> list[dict]:
    placeholders = ', '.join('?' for _ in FIXED_POOL_SQUARE_IDS)
    cur.execute(f"""
        SELECT
            sp.SquareId,
            sp.CenterLat,
            sp.CenterLng,
            sp.SquareLength
        FROM dbo.SquarePool sp
        WHERE sp.SquarePoolId = ?
          AND sp.SquareId IN ({placeholders})
    """, square_pool_id, *FIXED_POOL_SQUARE_IDS)

    squares_by_id = {
        int(row.SquareId): {
            'square_id': int(row.SquareId),
            'center_lat': float(row.CenterLat),
            'center_lon': float(row.CenterLng),
            'square_length': float(row.SquareLength),
        }
        for row in cur.fetchall()
    }

    missing_square_ids = [
        square_id
        for square_id in FIXED_POOL_SQUARE_IDS
        if square_id not in squares_by_id
    ]
    if missing_square_ids:
        raise ValueError(
            f'Pool {square_pool_id} is missing required E2E square IDs: '
            + ', '.join(str(square_id) for square_id in missing_square_ids)
        )

    return [squares_by_id[square_id] for square_id in FIXED_POOL_SQUARE_IDS]


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

    with get_conn(e2e=True) as conn:
        cur = conn.cursor()
        print(f'Rebuilding E2E game for {game_date.isoformat()}...', flush=True)
        delete_existing_game(cur, game_date)
        selected_squares = load_fixed_squares(cur, square_pool_id)
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