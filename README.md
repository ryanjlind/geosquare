# GeoSquare

Flask + SQL Server + Azure App Service for a daily geography game.

## Tech Stack

- Flask app served by Gunicorn
- Azure App Service on Linux
- SQL Server for config, city data, land polygons, and precomputed squares
- CesiumJS for a true globe renderer
- GeoNames for global city population data
- Precomputed square generation stored in SQL Server

## Rule Set

The generator uses one active config row in `GameConfig`.

- minimum total population inside square
- minimum qualifying city count
- minimum qualifying city population
- maximum square width/height
- square growth step

Squares are drawn by choosing a seed that has to be on land. The square then expands until the above criteria are met.

## Database

- `GeoCities`: imported GeoNames city records
- `LandPolygons`: land geometry used for random seed
- `GameConfig`: active generator configuration
- `GameSquares`: precomputed valid squares
- `GameSquareCities`: qualifying cities stored with each square

Required env vars:
- `SQL_SERVER`
- `SQL_DATABASE`
- `SQL_USERNAME`
- `SQL_PASSWORD`