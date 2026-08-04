import time

import pyodbc

from app.core.db import get_conn

RETRY_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 120


def main() -> None:
    started_at = time.monotonic()
    deadline = started_at + TIMEOUT_SECONDS
    attempt = 0

    while True:
        attempt += 1
        elapsed = time.monotonic() - started_at
        print(
            f'Checking E2E database readiness (attempt {attempt}, '
            f'elapsed {elapsed:.1f}s)...',
            flush=True,
        )

        try:
            with get_conn(e2e=True) as conn:
                cur = conn.cursor()
                cur.execute('SELECT 1')
                cur.fetchone()
        except pyodbc.Error as error:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f'E2E database was not ready after {TIMEOUT_SECONDS} seconds.'
                ) from error

            print(
                f'E2E database is unavailable: {error}. Retrying in '
                f'{min(RETRY_INTERVAL_SECONDS, remaining):.1f}s...',
                flush=True,
            )
            time.sleep(min(RETRY_INTERVAL_SECONDS, remaining))
            continue

        elapsed = time.monotonic() - started_at
        print(f'E2E database is ready after {elapsed:.1f}s.', flush=True)
        return


if __name__ == '__main__':
    main()