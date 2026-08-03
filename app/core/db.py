import os

import pyodbc

PRODUCTION_DATABASE_NAME = 'GeoSquare'


def _required_environment_value(name: str) -> str:
    value = os.environ[name].strip()
    if not value:
        raise RuntimeError(f'{name} must not be empty.')
    return value


def _e2e_database_name() -> str:
    database = _required_environment_value('E2E_DATABASE')
    if database.casefold() == PRODUCTION_DATABASE_NAME.casefold():
        raise RuntimeError('E2E_DATABASE must not reference the production database.')
    return database


def _connect(database: str, *, environment_prefix: str = 'SQL'):
    server = _required_environment_value(f'{environment_prefix}_SERVER')
    username = _required_environment_value(f'{environment_prefix}_USERNAME')
    password = _required_environment_value(f'{environment_prefix}_PASSWORD')
    driver = os.getenv('SQL_DRIVER', 'ODBC Driver 18 for SQL Server')

    conn_str = (
        f'DRIVER={{{driver}}};'
        f'SERVER={server};'
        f'DATABASE={database};'
        f'UID={username};'
        f'PWD={password};'
        'Encrypt=yes;'
        'TrustServerCertificate=yes;'
    )
    return pyodbc.connect(conn_str)


def get_conn(*, e2e: bool = False):
    database_target = os.getenv('DATABASE_TARGET')
    if e2e or database_target == 'e2e':
        return _connect(_e2e_database_name(), environment_prefix='E2E_SQL')
    if database_target not in (None, 'sql'):
        raise RuntimeError("DATABASE_TARGET must be 'sql' or 'e2e'.")
    return _connect(_required_environment_value('SQL_DATABASE'))
