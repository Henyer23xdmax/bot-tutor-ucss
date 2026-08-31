import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    telegram_id = Column(Integer, primary_key=True)
    first_name = Column(String)
    correct_answers = Column(Integer, default=0)
    wrong_answers = Column(Integer, default=0)
    last_context = Column(String, nullable=True)

class ActivePoll(Base):
    __tablename__ = 'active_polls'
    poll_id = Column(String, primary_key=True)
    correct_option_id = Column(Integer)

# Leer base de datos de variable de entorno (con fallback a SQLite local)
db_url = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
# Ajuste por compatibilidad con cadenas antiguas 'postgres://' (ej. Render/Heroku)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(db_url)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

