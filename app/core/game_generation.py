from dataclasses import dataclass
from datetime import date
import math
import random


@dataclass
class Config:
    config_id: int
    config_key: str
    min_total_population: int
    min_city_count: int
    min_city_population: int
    max_square_width_degrees: float
    max_square_height_degrees: float
    step_degrees: float
    max_attempts_per_square: int


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return r * c


def load_config(cur) -> Config:
    cur.execute(
        """
        SELECT TOP 1
            ConfigId,
            ConfigKey,
            MinTotalPopulation,
            MinCityCount,
            MinCityPopulation,
            MaxSquareWidthDegrees,
            MaxSquareHeightDegrees,
            StepDegrees,
            MaxAttemptsPerSquare
        FROM dbo.GameConfig
        WHERE IsActive = 1
        ORDER BY ConfigId DESC
    """
    )
    row = cur.fetchone()

    if not row:
        raise RuntimeError("No active config found.")

    return Config(
        config_id=int(row.ConfigId),
        config_key=row.ConfigKey,
        min_total_population=int(row.MinTotalPopulation),
        min_city_count=int(row.MinCityCount),
        min_city_population=int(row.MinCityPopulation),
        max_square_width_degrees=float(row.MaxSquareWidthDegrees),
        max_square_height_degrees=float(row.MaxSquareHeightDegrees),
        step_degrees=float(row.StepDegrees),
        max_attempts_per_square=int(row.MaxAttemptsPerSquare),
    )


def load_land_polygons(cur):
    cur.execute(
        """
        SELECT MinLat, MinLon, MaxLat, MaxLon
        FROM dbo.LandPolygons
    """
    )
    rows = cur.fetchall()

    if not rows:
        raise RuntimeError("No land polygons loaded.")

    return [
        {
            "min_lat": float(row.MinLat),
            "min_lon": float(row.MinLon),
            "max_lat": float(row.MaxLat),
            "max_lon": float(row.MaxLon),
        }
        for row in rows
    ]


def fetch_cities_in_bounds(cur, min_lat, min_lon, max_lat, max_lon):
    buffer = 0.01

    cur.execute(
        """
        SELECT
            CityId,
            CityName,
            CountryCode,
            Latitude,
            Longitude,
            Population
        FROM dbo.GeoCities
        WHERE IsActive = 1
          AND Latitude BETWEEN ? AND ?
          AND Longitude BETWEEN ? AND ?
          AND FeatureCode <> 'PPLX'
          AND FeatureCode <> 'PPLQ'
          AND FeatureCode <> 'PPLH'
    """,
        min_lat - buffer,
        max_lat + buffer,
        min_lon - buffer,
        max_lon + buffer,
    )

    rows = cur.fetchall()

    return [
        {
            "city_id": int(r.CityId),
            "city_name": r.CityName,
            "country_code": r.CountryCode,
            "latitude": float(r.Latitude),
            "longitude": float(r.Longitude),
            "population": int(r.Population),
        }
        for r in rows
    ]


def get_square_side_limit(config: Config) -> float:
    return min(
        float(config.max_square_width_degrees),
        float(config.max_square_height_degrees),
    )


def build_candidate(seed_lat, seed_lon, width_deg, height_deg):
    half_height = height_deg / 2.0
    half_width = width_deg / 2.0

    min_lat = max(-89.0, seed_lat - half_height)
    max_lat = min(89.0, seed_lat + half_height)
    min_lon = max(-179.0, seed_lon - half_width)
    max_lon = min(179.0, seed_lon + half_width)

    return min_lat, min_lon, max_lat, max_lon


def choose_seed(use_continent_weights: bool = True):
    _ = use_continent_weights

    seed_lat = random.uniform(-58.0, 75.0)
    seed_lon = random.uniform(-179.0, 179.0)

    return None, seed_lat, seed_lon


def try_generate(
    cur,
    config: Config,
    polygons,
    square_attempt_number: int,
    on_progress=None,
    use_continent_weights: bool = True,
):
    _ = polygons

    max_square_side = get_square_side_limit(config)

    if config.step_degrees <= 0:
        raise RuntimeError("Config StepDegrees must be greater than 0.")

    if max_square_side <= 0:
        raise RuntimeError("Config max square dimensions must be greater than 0.")

    _, seed_lat, seed_lon = choose_seed(use_continent_weights=use_continent_weights)

    size = min(config.step_degrees, max_square_side)

    if on_progress is not None:
        on_progress(
            {
                "type": "candidate_started",
                "attempt_number": square_attempt_number,
                "continent": None,
                "seed_lat": seed_lat,
                "seed_lon": seed_lon,
            }
        )

    prev_cities = None
    prev_qual = None
    prev_pop = None

    while size <= max_square_side + 1e-9:
        min_lat, min_lon, max_lat, max_lon = build_candidate(
            seed_lat,
            seed_lon,
            size,
            size,
        )

        cities = fetch_cities_in_bounds(cur, min_lat, min_lon, max_lat, max_lon)
        total_population = sum(c["population"] for c in cities)
        qualifying_city_count = sum(
            1 for c in cities if c["population"] >= config.min_city_population
        )

        if (
            len(cities) != prev_cities
            or qualifying_city_count != prev_qual
            or total_population != prev_pop
        ):
            if on_progress is not None:
                on_progress(
                    {
                        "type": "candidate_progress",
                        "attempt_number": square_attempt_number,
                        "seed_lat": seed_lat,
                        "seed_lon": seed_lon,
                        "bounds": {
                            "min_lat": min_lat,
                            "min_lon": min_lon,
                            "max_lat": max_lat,
                            "max_lon": max_lon,
                        },
                        "size": size,
                        "total_city_count": len(cities),
                        "qualifying_city_count": qualifying_city_count,
                        "total_population": total_population,
                    }
                )

            prev_cities = len(cities)
            prev_qual = qualifying_city_count
            prev_pop = total_population

        if (
            total_population >= config.min_total_population
            and qualifying_city_count >= config.min_city_count
        ):
            square = {
                "seed_lat": seed_lat,
                "seed_lon": seed_lon,
                "min_lat": min_lat,
                "min_lon": min_lon,
                "max_lat": max_lat,
                "max_lon": max_lon,
                "width_degrees": size,
                "height_degrees": size,
                "total_population": total_population,
                "qualifying_city_count": qualifying_city_count,
                "cities": cities,
            }

            if on_progress is not None:
                on_progress(
                    {
                        "type": "candidate_accepted",
                        "attempt_number": square_attempt_number,
                        "square": square,
                    }
                )

            return square

        size += config.step_degrees

    if on_progress is not None:
        on_progress(
            {
                "type": "candidate_rejected",
                "attempt_number": square_attempt_number,
            }
        )

    return None


def persist_square(cur, config: Config, square, is_active: int = 1) -> int:
    cur.execute(
        "SELECT dbo.ComputeLocationKey(?, ?)",
        square["seed_lat"],
        square["seed_lon"],
    )
    location_key = int(cur.fetchone()[0])

    cur.execute(
        """
        INSERT INTO dbo.GameSquares (
            ConfigId,
            SeedLat,
            SeedLon,
            MinLat,
            MinLon,
            MaxLat,
            MaxLon,
            WidthDegrees,
            HeightDegrees,
            TotalPopulation,
            QualifyingCityCount,
            IsActive,
            LocationKey
        )
        OUTPUT INSERTED.SquareId
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            config.config_id,
            square["seed_lat"],
            square["seed_lon"],
            square["min_lat"],
            square["min_lon"],
            square["max_lat"],
            square["max_lon"],
            square["width_degrees"],
            square["height_degrees"],
            square["total_population"],
            square["qualifying_city_count"],
            is_active,
            location_key,
        ),
    )

    square_id = int(cur.fetchone()[0])

    rows = [
        (
            square_id,
            city["city_id"],
            city["city_name"],
            city["country_code"],
            city["latitude"],
            city["longitude"],
            city["population"],
        )
        for city in square["cities"]
    ]

    if rows:
        cur.fast_executemany = True
        cur.executemany(
            """
            INSERT INTO dbo.GameSquareCities (
                SquareId,
                CityId,
                CityName,
                CountryCode,
                Latitude,
                Longitude,
                Population
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            rows,
        )

    return square_id


def _delete_square_ids(cur, square_ids):
    if not square_ids:
        return

    placeholders = ", ".join("?" for _ in square_ids)

    cur.execute(
        f"DELETE FROM dbo.GameSquareCities WHERE SquareId IN ({placeholders})",
        tuple(square_ids),
    )

    cur.execute(
        f"DELETE FROM dbo.GameSquares WHERE SquareId IN ({placeholders})",
        tuple(square_ids),
    )


def delete_game_squares(cur, game_id: int):
    cur.execute(
        """
        SELECT SquareId
        FROM dbo.GameRounds
        WHERE GameId = ?
        ORDER BY RoundNumber
    """,
        game_id,
    )
    square_ids = [int(row.SquareId) for row in cur.fetchall()]

    cur.execute(
        """
        DELETE FROM dbo.GameRounds
        WHERE GameId = ?
    """,
        game_id,
    )

    _delete_square_ids(cur, square_ids)


def generate_game_for_date(cur, config: Config, polygons, game_date: date):
    _ = polygons

    cur.execute(
        """
        SELECT TOP 1 GameId
        FROM dbo.Games
        WHERE GameDate = ?
    """,
        game_date,
    )
    existing_game = cur.fetchone()

    if existing_game:
        game_id = int(existing_game.GameId)

        cur.execute(
            """
            DELETE gg
            FROM dbo.GameGuesses gg
            INNER JOIN dbo.GameSessionRounds gsr ON gg.SessionRoundId = gsr.SessionRoundId
            INNER JOIN dbo.GameSessions gsess ON gsr.SessionId = gsess.SessionId
            WHERE gsess.GameId = ?
        """,
            game_id,
        )

        cur.execute(
            """
            DELETE gsr
            FROM dbo.GameSessionRounds gsr
            INNER JOIN dbo.GameSessions gsess ON gsr.SessionId = gsess.SessionId
            WHERE gsess.GameId = ?
        """,
            game_id,
        )

        cur.execute(
            """
            DELETE FROM dbo.GameSessions
            WHERE GameId = ?
        """,
            game_id,
        )

        delete_game_squares(cur, game_id)
    else:
        cur.execute(
            """
            INSERT INTO dbo.Games (GameDate)
            OUTPUT INSERTED.GameId
            VALUES (?)
        """,
            game_date,
        )
        game_id = int(cur.fetchone()[0])

    for round_number in range(1, 6):
        square = None

        for square_attempt_number in range(1, config.max_attempts_per_square + 1):
            candidate = try_generate(cur, config, polygons, square_attempt_number)

            if candidate is None:
                continue

            square = candidate
            break

        if square is None:
            raise Exception(f"Failed to generate square for round {round_number}")

        square_id = persist_square(cur, config, square)

        cur.execute(
            """
            INSERT INTO dbo.GameRounds (GameId, RoundNumber, SquareId)
            VALUES (?, ?, ?)
        """,
            game_id,
            round_number,
            square_id,
        )

    return game_id
