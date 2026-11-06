import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .runtime import runtime_directory


class Base(DeclarativeBase):
    pass


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    template: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(100), default="")
    seed: Mapped[str] = mapped_column(String(80))
    starts_at: Mapped[float] = mapped_column(Float, index=True)
    ends_at: Mapped[float] = mapped_column(Float, index=True)
    is_sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    sponsor_name: Mapped[str] = mapped_column(String(60), default="")
    accent_color: Mapped[str] = mapped_column(String(7), default="#d5ef45")
    logo: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("token", "mission_id", "attempt_no", name="uq_runs_attempt"),)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: uuid.uuid4().hex)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), index=True)
    nickname: Mapped[str] = mapped_column(String(24), default="")
    started_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class OptionCount(Base):
    __tablename__ = "option_counts"
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), primary_key=True)
    question: Mapped[int] = mapped_column(Integer, primary_key=True)
    option: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("token", "week"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: uuid.uuid4().hex)
    token: Mapped[str] = mapped_column(String(64))
    week: Mapped[str] = mapped_column(String(10))
    nickname: Mapped[str] = mapped_column(String(24))
    age_ok: Mapped[bool] = mapped_column(Boolean)
    contact: Mapped[str] = mapped_column(String(120))
    intro: Mapped[str] = mapped_column(String(100))
    records: Mapped[list] = mapped_column(JSON)
    submitted_at: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(16), default="submitted")


class ShortLink(Base):
    __tablename__ = "short_links"
    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"))


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(ForeignKey("short_links.code"))
    visited_at: Mapped[float] = mapped_column(Float, index=True)


def make_engine(url=None):
    url = url or os.getenv("DATABASE_URL", "sqlite:///data/open-casting.sqlite")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite:///"):
        path = Path(url.removeprefix("sqlite:///"))
        if path.parts and path.parts[0] == "data":
            runtime_directory()
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **({"connect_args": {"check_same_thread": False, "timeout": 20}} if url.startswith("sqlite") else {"pool_size": int(os.getenv("DB_POOL_SIZE", "5")), "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "5")), "pool_pre_ping": True}))
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
    if url.startswith("sqlite:///") and path.exists():
        path.chmod(0o600)
    return engine


@contextmanager
def transaction(engine):
    with sessionmaker(engine, expire_on_commit=False)() as db:
        try:
            # SQLite has no row locks; serialize writes before reading attempt/state counters.
            if engine.dialect.name == "sqlite":
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def insert_for(db, model):
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


def initialize(engine):
    # ponytail: add Alembic with the first post-launch schema change; create_all never upgrades existing tables.
    Base.metadata.create_all(engine)
    # Upgrade the pre-launch M1 table in place without discarding records.
    if "attempt_no" not in {column["name"] for column in inspect(engine).get_columns("runs")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE runs ADD COLUMN attempt_no INTEGER DEFAULT 1 NOT NULL"))
            connection.execute(text("""UPDATE runs SET attempt_no = numbered.attempt_no FROM
                (SELECT id, ROW_NUMBER() OVER (PARTITION BY token, mission_id ORDER BY started_at, id) AS attempt_no FROM runs) AS numbered
                WHERE runs.id = numbered.id"""))
            connection.execute(text("CREATE UNIQUE INDEX uq_runs_attempt ON runs(token, mission_id, attempt_no)"))
    if engine.dialect.name == "sqlite" and engine.url.database != ":memory:":
        Path(engine.url.database).chmod(0o600)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init"])
    parser.parse_args()
    database = make_engine()
    initialize(database)
    if os.getenv("SEED_DEMO", "false").lower() == "true":
        from .seed import seed
        seed(database)
    database.dispose()
