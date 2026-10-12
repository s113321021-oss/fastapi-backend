import os

import psycopg


def get_db_connection() -> psycopg.Connection:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg.connect(database_url)
