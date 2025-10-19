import os
from sqlalchemy import create_engine, text

def pg_engine():
    dsn = f"postgresql+psycopg2://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}@{os.getenv('PGHOST')}:{os.getenv('PGPORT','5432')}/{os.getenv('PGDATABASE')}?sslmode={os.getenv('PGSSLMODE','require')}"
    return create_engine(dsn, pool_pre_ping=True, pool_size=5, max_overflow=5)

def insert_trade(engine, payload: dict):
    cols = ",".join(payload.keys())
    vals = ",".join([f":{k}" for k in payload.keys()])
    sql = text(f"INSERT INTO trades ({cols}) VALUES ({vals})")
    with engine.begin() as cx:
        cx.execute(sql, payload)