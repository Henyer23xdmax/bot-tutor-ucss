import os
from sqlalchemy import create_engine, Column, Integer, BigInteger, String
from sqlalchemy.orm import declarative_base, sessionmaker

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

# Leer base de datos de variable de entorno (con fallback a SQLite local)
db_url = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
# Ajuste por compatibilidad con cadenas antiguas 'postgres://' (ej. Render/Heroku)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Si se usa SQLite local (sin DATABASE_URL de nube), en entornos serverless como
# Vercel el escritorio es efímero, así que guardamos el archivo en /tmp por velocidad
# y ponemos un timeout amplio para evitar errores de "database is locked" con
# invocaciones concurrentes. NOTA: en Vercel /tmp NO persiste entre ejecuciones.
if db_url.startswith("sqlite"):
    import tempfile
    if ":///" not in db_url or db_url == "sqlite:///bot_database.db":
        db_path = os.path.join(tempfile.gettempdir(), "bot_database.db")
        db_url = f"sqlite:///{db_path}"

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
else:
    # Compatibilidad con PostgreSQL (Supabase) en entornos serverless:
    # 'creator' permite usar un pool por invocación y evita conexiones colgadas
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

