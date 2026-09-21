import os
from dotenv import load_dotenv
import psycopg

load_dotenv()

def test_connection():
    conn = psycopg.connect(os.getenv("DATABASE_URL"))
    print("連線成功:", conn.info.dbname)
    conn.close()

if __name__ == "__main__":
    test_connection()