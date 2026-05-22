import os
import logging
import asyncio
from dotenv import load_dotenv
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, BigInteger
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    role = Column(String(20), nullable=False)       # user / assistant
    message_type = Column(String(20), nullable=False)  # text / voice / image
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    _db_available = True
except Exception as e:
    logging.warning(f"DB engine init failed: {e}")
    engine = None
    SessionLocal = None
    _db_available = False

def _ensure_db_exists():
    """Create the database if it doesn't exist yet."""
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT,
            user=DB_USER, password=DB_PASSWORD,
            database="postgres",
            options="-c client_encoding=UTF8",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{DB_NAME}"')
            logging.info(f"Database '{DB_NAME}' created.")
        cur.close()
        conn.close()
    except Exception as e:
        try:
            msg = str(e)
        except Exception:
            msg = repr(e.args)
        logging.warning(f"Could not ensure DB exists (check DB_USER/DB_PASSWORD in .env): {msg}")

def create_tables():
    if not _db_available:
        return
    try:
        _ensure_db_exists()
        Base.metadata.create_all(bind=engine)
        logging.info("DB tables created/verified.")
    except Exception as e:
        logging.warning(f"create_tables failed (DB unavailable?): {e}")

def _sync_save(user_id, chat_id, role, message_type, content):
    db = SessionLocal()
    try:
        db.add(Message(
            user_id=user_id,
            chat_id=chat_id,
            role=role,
            message_type=message_type,
            content=content,
        ))
        db.commit()
    finally:
        db.close()

async def save_message(user_id: int, chat_id: int, role: str, message_type: str, content: str):
    if not _db_available or SessionLocal is None:
        return
    try:
        await asyncio.to_thread(_sync_save, user_id, chat_id, role, message_type, content)
    except Exception as e:
        logging.warning(f"save_message failed: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
