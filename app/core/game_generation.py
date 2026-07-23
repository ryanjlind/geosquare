

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


def persist_square(cur, square, is_active: int = 1) -> int:
    cur.execute(
        "SELECT dbo.ComputeLocationKey(?, ?)",
        square["seed_lat"],
        square["seed_lon"],
    )
    location_key = int(cur.fetchone()[0])

    cur.execute(
        """
        INSERT INTO dbo.GameSquares (
            SeedLat,
            SeedLon,
            MinLat,
            MinLon,
            MaxLat,
            MaxLon,
            WidthDegrees,
            HeightDegrees,
            IsActive,
            LocationKey
        )
        OUTPUT INSERTED.SquareId
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            square["seed_lat"],
            square["seed_lon"],
            square["min_lat"],
            square["min_lon"],
            square["max_lat"],
            square["max_lon"],
            square["width_degrees"],
            square["height_degrees"],
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

