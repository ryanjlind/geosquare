# Geo Daily v0

Flask + SQL Server + Azure App Service scaffold for a daily geography game.

## Chosen stack

- Flask app served by Gunicorn
- Azure App Service on Linux
- SQL Server for config, city data, land polygons, and precomputed squares
- CesiumJS for a true globe renderer
- GeoNames for global city population data
- Precomputed square generation stored in SQL Server

## v0 rule set

The generator uses one active config row in `dbo.GameConfig`.

Default seed values:
- minimum total population inside square: 1,000,000
- minimum qualifying city count: 3
- minimum qualifying city population: 100,000
- maximum square width/height: 10 degrees
- square growth step: 0.25 degrees

## Request flow

1. Browser loads `/`
2. Frontend requests `/api/daily-square`
3. API returns the current active square plus its qualifying cities
4. Cesium renders the rectangle and city markers on a globe

## Database objects

Run `sql/schema.sql`.

Main tables:
- `dbo.GeoCities`: imported GeoNames city records
- `dbo.LandPolygons`: land geometry used for random land seed checks
- `dbo.GameConfig`: active generator configuration
- `dbo.GameSquares`: precomputed valid squares
- `dbo.GameSquareCities`: qualifying cities stored with each square

## Data load

### GeoNames

Expected input is a GeoNames zip such as `cities15000.zip`.

Example:

```bash
python scripts/load_geonames.py
```

Required env vars:
- `SQL_SERVER`
- `SQL_DATABASE`
- `SQL_USERNAME`
- `SQL_PASSWORD`
- optional `SQL_DRIVER`
- optional `GEONAMES_ZIP_PATH`
- optional `GEONAMES_TXT_NAME`
- optional `MIN_GEONAMES_POPULATION`

### Land polygons

This scaffold expects you to load simplified land polygons into `dbo.LandPolygons` as WKT. I did not invent a custom importer because that depends on the exact source file you want to use.

## Square generation

Example:

```bash
python scripts/generate_square.py
```

Generation algorithm:
1. Load active config
2. Pick a random land seed from lat/lon space
3. Start with a square centered on the seed
4. Expand by `StepDegrees`
5. Sum enclosed city populations
6. Count enclosed cities with population >= `MinCityPopulation`
7. Accept when both thresholds are met
8. Reject when max size is exceeded and start over
9. Persist accepted square and qualifying city rows

## Azure App Service

Startup command:

```bash
bash startup.sh
```

App settings:
- `SQL_SERVER`
- `SQL_DATABASE`
- `SQL_USERNAME`
- `SQL_PASSWORD`
- `SECRET_KEY`
- optional `CESIUM_ION_TOKEN`
- optional `SQL_DRIVER`

## Missing pieces by design

Two pieces still need exact source files:
- the GeoNames zip you want to import
- the land polygon source you want to use for `dbo.LandPolygons`

Once you give me the exact land polygon file choice, I can add that importer too.
