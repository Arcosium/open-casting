import datetime as dt
import secrets
import os
import uuid
from sqlalchemy import event, text

import pytest
from fastapi.testclient import TestClient

from app.cache import Cache
from app.db import make_engine, initialize
from app.main import create_app
from app.security import password_hash
from app.services import KST


@pytest.fixture
def rig(tmp_path):
    url = os.getenv("TEST_DATABASE_URL", 'sqlite:///' + str(tmp_path / 'test.sqlite'))
    engine = make_engine(url)
    schema = "test_" + uuid.uuid4().hex if engine.dialect.name == "postgresql" else None
    if schema:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine.dispose()
        @event.listens_for(engine, "connect")
        def search_path(connection, _):
            with connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()
    initialize(engine)
    timestamp = [dt.datetime(2026, 11, 6, 12, tzinfo=KST).timestamp()]
    password = secrets.token_urlsafe(24)
    app = create_app(engine=engine, secret=secrets.token_hex(32), password_hash=password_hash(password), clock=lambda: timestamp[0], background=False, cache=Cache(os.getenv("TEST_REDIS_URL"), namespace="test:" + uuid.uuid4().hex))
    with TestClient(app) as client:
        yield client, engine, timestamp, password
    if schema:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


def mission(client, template):
    return next(m for m in client.get('/api/missions').json()['missions'] if m['template'] == template)


def start(client, template='no-rieul'):
    result = client.post('/api/runs', json={'mission_id': mission(client, template)['id'], 'nickname': 'Test player'})
    assert result.status_code == 200, result.text
    return result.json()


def login(rig):
    client, _, _, password = rig
    assert client.post('/api/studio/login', json={'password': password}).status_code == 200


def finish(client):
    run = start(client)
    result = client.post('/api/runs/' + run['id'] + '/answer', json={'text': 'not-a-word'})
    assert result.json()['finished']
    return run
