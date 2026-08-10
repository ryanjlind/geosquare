import json
import os
import random
from datetime import date
from pathlib import Path

from app.core.db import get_conn
from app.core.game_generation import fetch_cities_in_bounds, persist_square
from app.helpers.text import normalize_place_name
from e2e_tests.setup_game import delete_existing_game, expansion_bounds


PLAYABILITY_THRESHOLD = 80.0
ROUND_COUNT = 5
EXPANSION_LEVEL_COUNT = 5
FIXTURE_PATH = Path('e2e_tests/artifacts/weekly_fixture.json')
GUESS_MAX_ROLL = 70
EXPAND_MAX_ROLL = 95


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


def random_round_action(random_source) -> str:
    roll = random_source.randrange(100)
    if roll < GUESS_MAX_ROLL:
        return 'guess'
    if roll < EXPAND_MAX_ROLL:
        return 'expand'
    return 'pass'


def city_fixture(city: dict) -> dict:
    return {
        'city_id': city['city_id'],
        'city_name': city['city_name'],
        'country_code': city['country_code'],
        'latitude': city['latitude'],
        'longitude': city['longitude'],
    }


def create_weekly_game(cur, game_date: date, selected_squares: list[dict]) -> tuple[int, list[dict]]:
    cur.execute("""
        INSERT INTO dbo.Games (GameDate)
        OUTPUT INSERTED.GameId
        VALUES (?)
    """, game_date)
    game_id = int(cur.fetchone()[0])
    rounds = []
    random_source = random.SystemRandom()

    for round_number, selected_square in enumerate(selected_squares, start=1):
        print(
            f'Creating round {round_number} from pool square '
            f'{selected_square["square_id"]}...',
            flush=True,
        )
        cities_by_expansion = []
        bounds_by_expansion = []
        for expansion_level in range(EXPANSION_LEVEL_COUNT):
            bounds = expansion_bounds(selected_square, expansion_level)
            cities = fetch_cities_in_bounds(
                cur,
                bounds['min_lat'],
                bounds['min_lon'],
                bounds['max_lat'],
                bounds['max_lon'],
            )
            cities_by_expansion.append(cities)
            bounds_by_expansion.append(bounds)

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

        if not cities_by_expansion[0]:
            raise ValueError(
                f'Pool square {selected_square["square_id"]} has no cities.'
            )

        action = random_round_action(random_source)
        round_fixture = {
            'round_number': round_number,
            'pool_square_id': selected_square['square_id'],
            'action': action,
            'base_bounds': bounds_by_expansion[0],
        }

        if action == 'guess':
            round_fixture['correct_city'] = city_fixture(
                random_source.choice(cities_by_expansion[0])
            )

        if action == 'expand':
            round_fixture['correct_city'] = city_fixture(
                random_source.choice(cities_by_expansion[1])
            )
            base_city_ids = {
                city['city_id']
                for city in cities_by_expansion[0]
            }
            base_city_names = {
                normalize_place_name(city['city_name'])
                for city in cities_by_expansion[0]
            }
            base_bounds = bounds_by_expansion[0]
            nearby_candidates = [
                city
                for city in cities_by_expansion[1]
                if city['city_id'] not in base_city_ids
                and normalize_place_name(city['city_name']) not in base_city_names
                and (
                    city['latitude'] < base_bounds['min_lat']
                    or city['latitude'] > base_bounds['max_lat']
                    or city['longitude'] < base_bounds['min_lon']
                    or city['longitude'] > base_bounds['max_lon']
                )
            ]
            round_fixture['incorrect_city'] = (
                city_fixture(random_source.choice(nearby_candidates))
                if nearby_candidates
                else None
            )

        rounds.append(round_fixture)

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
        description = (
            f'Round {round_fixture["round_number"]}: pool square '
            f'{round_fixture["pool_square_id"]}; action {round_fixture["action"]}'
        )
        if round_fixture['action'] != 'pass':
            correct_city = round_fixture['correct_city']
            description += (
                f'; correct guess {correct_city["city_name"]} '
                f'(city {correct_city["city_id"]}, {correct_city["country_code"]})'
            )
        incorrect_city = round_fixture.get('incorrect_city')
        if incorrect_city is not None:
            description += (
                f'; incorrect next-ring guess {incorrect_city["city_name"]} '
                f'(city {incorrect_city["city_id"]}, {incorrect_city["country_code"]})'
            )
        print(description, flush=True)
    print(f'Created weekly E2E game {game_id}.', flush=True)


if __name__ == '__main__':
    main()