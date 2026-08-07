import json
import os
import random
from datetime import date
from pathlib import Path

from app.core.db import get_conn
from app.core.game_generation import fetch_cities_in_bounds, persist_square
from e2e_tests.setup_game import delete_existing_game, expansion_bounds


PLAYABILITY_THRESHOLD = 80.0
ROUND_COUNT = 5
EXPANSION_LEVEL_COUNT = 5
FIXTURE_PATH = Path('e2e_tests/artifacts/weekly_fixture.json')


def required_environment_value(name: str) -> str:
    value = os.environ[name].strip()
    if not value:
        raise ValueError(f'{name} must not be empty.')
    return value


def select_random_squares(cur, square_pool_id: int) -> list[dict]:
    cur.execute("""
        SELECT
            sp.SquareId,
            sp.CenterLat,
            sp.CenterLng,
            sp.SquareLength
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
    """, square_pool_id, PLAYABILITY_THRESHOLD)

    candidates = [
        {
            'square_id': int(row.SquareId),
            'center_lat': float(row.CenterLat),
            'center_lon': float(row.CenterLng),
            'square_length': float(row.SquareLength),
        }
        for row in cur.fetchall()
    ]
    if len(candidates) < ROUND_COUNT:
        raise ValueError(
            f'Pool {square_pool_id} has {len(candidates)} playable squares; '
            f'{ROUND_COUNT} are required.'
        )

    return random.SystemRandom().sample(candidates, ROUND_COUNT)


def create_weekly_game(cur, game_date: date, selected_squares: list[dict]) -> tuple[int, list[dict]]:
    cur.execute("""
        INSERT INTO dbo.Games (GameDate)
        OUTPUT INSERTED.GameId
        VALUES (?)
    """, game_date)
    game_id = int(cur.fetchone()[0])
    rounds = []

    for round_number, selected_square in enumerate(selected_squares, start=1):
        print(
            f'Creating round {round_number} from pool square '
            f'{selected_square["square_id"]}...',
            flush=True,
        )
        round_guess = None
        for expansion_level in range(EXPANSION_LEVEL_COUNT):
            bounds = expansion_bounds(selected_square, expansion_level)
            cities = fetch_cities_in_bounds(
                cur,
                bounds['min_lat'],
                bounds['min_lon'],
                bounds['max_lat'],
                bounds['max_lon'],
            )
            if expansion_level == 0:
                if not cities:
                    raise ValueError(
                        f'Pool square {selected_square["square_id"]} has no cities.'
                    )
                round_guess = max(cities, key=lambda city: city['population'])

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

        rounds.append({
            'round_number': round_number,
            'pool_square_id': selected_square['square_id'],
            'city_id': round_guess['city_id'],
            'city_name': round_guess['city_name'],
            'country_code': round_guess['country_code'],
        })

    return game_id, rounds


def main() -> None:
    game_date = date.fromisoformat(required_environment_value('E2E_GAME_DATE'))
    square_pool_id = int(required_environment_value('E2E_SQUARE_POOL_ID'))

    with get_conn(e2e=True) as conn:
        cur = conn.cursor()
        print(f'Rebuilding weekly E2E game for {game_date.isoformat()}...', flush=True)
        delete_existing_game(cur, game_date)
        selected_squares = select_random_squares(cur, square_pool_id)
        print(
            'Selected pool squares: '
            + ', '.join(str(square['square_id']) for square in selected_squares),
            flush=True,
        )
        game_id, rounds = create_weekly_game(cur, game_date, selected_squares)
        conn.commit()

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps({'game_id': game_id, 'rounds': rounds}, indent=2) + '\n',
        encoding='utf-8',
    )
    for round_fixture in rounds:
        print(
            f'Round {round_fixture["round_number"]} guess: '
            f'{round_fixture["city_name"]} '
            f'(city {round_fixture["city_id"]})',
            flush=True,
        )
    print(f'Created weekly E2E game {game_id}.', flush=True)


if __name__ == '__main__':
    main()