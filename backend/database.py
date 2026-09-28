import os

from dotenv import load_dotenv
import mysql.connector
from mysql.connector import pooling

load_dotenv()

db_pool = pooling.MySQLConnectionPool(
    pool_name="monitoring_pool",
    pool_size=5,
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)


def get_connection():
    return db_pool.get_connection()