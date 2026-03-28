import os

import pyodbc


def get_conn():
    server = os.environ['SQL_SERVER']
    database = os.environ['SQL_DATABASE']
    username = os.environ['SQL_USERNAME']
    password = os.environ['SQL_PASSWORD']
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
