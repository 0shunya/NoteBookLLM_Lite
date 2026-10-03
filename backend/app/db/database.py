from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# PostgreSQL connection string.
#
# Later we'll move these credentials into environment variables.
DATABASE_URL = (
    "postgresql+psycopg://"
    "postgres:postgres@localhost:5432/notebooklm"
)


# Creates the connection between our Python application
# and PostgreSQL.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# Creates database sessions.
# A session is how our application reads/writes database data.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


# Every database model will inherit from this Base class.
class Base(DeclarativeBase):
    pass


def get_db():
    """
    Provide a database session to an API request
    and close it when the request finishes.
    """

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()