"""Render SDK entry point; task inputs/outputs never contain casting contacts."""
from render import Retry, TaskContext, Workflows

from . import jobs
from .db import make_engine

app = Workflows(default_retry=Retry(max_retries=3, wait_duration_ms=1000), default_timeout=300, default_plan="flex")


def execute(name, value=None):
    engine = make_engine()
    try:
        function = getattr(jobs, name)
        return function(engine=engine) if value is None else function(value, engine=engine)
    finally:
        engine.dispose()


@app.task
def rotate_daily_missions(ctx: TaskContext, date: str | None = None) -> str:
    return execute("rotate_daily_missions", date)


@app.task
def close_due_missions(ctx: TaskContext, now: float | None = None) -> int:
    return execute("close_due_missions", now)


@app.task
def purge_expired_applications(ctx: TaskContext, now: float | None = None) -> int:
    return execute("purge_expired_applications", now)


@app.task
def build_sponsor_report(ctx: TaskContext, mission_id: str) -> dict:
    return execute("build_sponsor_report", mission_id)


if __name__ == "__main__":
    app.start()
