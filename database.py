import os
import logging
from sqlalchemy import create_engine, Column, Integer, BigInteger, String
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    telegram_id = Column(BigInteger, primary_key=True)
    first_name = Column(String)
    correct_answers = Column(Integer, default=0)
    wrong_answers = Column(Integer, default=0)
    last_context = Column(String, nullable=True)

class ActivePoll(Base):
    __tablename__ = 'active_polls'
    poll_id = Column(String, primary_key=True)
    correct_option_id = Column(Integer)

_engine = None
_SessionLocal = None


def _build_engine():
    """Crea y devuelve el engine de la base de datos (forma perezosa para serverless)."""
    global _engine
    if _engine is not None:
        return _engine

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        db_url = "sqlite:///bot_database.db"

    # Compatibilidad con cadenas antiguas 'postgres://'
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        if db_url.startswith("sqlite"):
            # SQLite local: en serverless (Vercel) el disco es efímero, usamos /tmp.
            # NOTA: los datos NO persisten entre invocaciones en Vercel.
            import tempfile
            db_path = os.path.join(tempfile.gettempdir(), "bot_database.db")
            engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False, "timeout": 30},
            )
        else:
            # PostgreSQL / Supabase: usar SSL y configurar timeout para serverless.
            # connect_timeout corto para que el failover a SQLite sea rápido si Supabase no responde.
            engine = create_engine(
                db_url,
                pool_pre_ping=True,
                pool_recycle=1800,
                connect_args={"sslmode": "require", "connect_timeout": 3},
            )
        Base.metadata.create_all(engine)
        _engine = engine
        return engine
    except Exception as e:
        logger.error(f"Error inicializando base de datos: {e}")
        _engine = None
        raise


def _get_session_local():
    global _SessionLocal
    if _SessionLocal is None and _engine is not None:
        _SessionLocal = sessionmaker(bind=_engine)
    return _SessionLocal


def SessionLocal():
    """Devuelve una sesión de SQLAlchemy. Inicializa la DB de forma perezosa si hace falta.
    Si la base de datos principal (ej. Supabase) falla, cae a SQLite en /tmp para no romper el bot."""
    global _engine, _SessionLocal
    if _engine is None:
        try:
            _build_engine()
        except Exception as e:
            logger.error(f"Failover a SQLite porque fallo la DB principal: {e}")
            import tempfile
            db_path = os.path.join(tempfile.gettempdir(), "bot_database.db")
            _engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            Base.metadata.create_all(_engine)
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_engine)
    return _SessionLocal()
