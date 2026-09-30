# GeoSquare

Flask + SQL Server + Azure App Service for a daily geography game.

## Tech Stack

- Flask app served by Gunicorn
- Azure App Service on Linux
- SQL Server for city data, generated games, player sessions, and profiles
- CesiumJS for a true globe renderer
- GeoNames for global city population data
- Persisted square bounds and city membership for each game round

## Game Structure

Each daily game contains five rounds. A round starts with a square on the globe, and the player attempts to identify a city inside it. The square can expand through four additional levels, with each expansion reducing the round score.

Correct guesses are scored from the guessed city's population relative to the other cities in the square. Completing the daily game unlocks its Infinity Pool, which reuses the game's squares in a continuing mode.

## Database

- `GeoCities`: imported GeoNames city records
- `Games`: one dated daily game
- `GameRounds`: round and expansion-level assignments for each game
- `GameSquares`: persisted geographic bounds for game rounds
- `GameSquareCities`: cities captured within each persisted square
- `GameSessions`, `GameSessionRounds`, and `GameGuesses`: daily player progress and scoring
- `Users`: anonymous and authenticated player records
- `InfinityPoolSessions` and `InfinityPoolGuesses`: post-game Infinity Pool progress

## Environment Variables

Required env vars:
- `SQL_SERVER`
- `SQL_DATABASE`
- `SQL_USERNAME`
- `SQL_PASSWORD`
- `SECRET_KEY`
- `CSRF_ORIGIN`

Optional env vars:
- `SQL_DRIVER` (defaults to `ODBC Driver 18 for SQL Server`)
- `LOCAL_AUTH_BYPASS=true` to use the local authentication path
- `GAME_DATE_OVERRIDE` to run the application against a specific game date
- `CESIUM_ION_TOKEN` for Cesium configuration
- `LASTLOGIN_CLIENT_ID` for LastLogin authentication

## Application Structure

The backend follows a `routes -> core -> helpers` dependency direction.

- `app/routes/` handles HTTP input and response serialization.
- `app/core/` contains game behavior, database queries, matching, scoring, authentication, profiles, and Infinity Pool logic.
- `app/helpers/` contains small shared utilities.
- `app/templates/` contains the Flask page templates.
- `app/static/` contains the browser JavaScript, CSS, and image assets.
- `tests/` contains Python unit tests.
- `e2e_tests/` contains Playwright tests and their database setup utilities.

## Testing

Run the Python unit tests from the repository root:

```bash
python -m pytest tests
```

## Deployment

Pushes to `main` run the Python tests and deterministic browser tests before deployment to Azure App Service. Production starts through Gunicorn using `main:app` and binds to the configured `PORT`.

## LICENSE

This project uses CesiumJS (https://cesium.com/), 
Copyright 2011–2025 CesiumJS Contributors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this software except in compliance with the License.
You may obtain a copy of the License at:

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.