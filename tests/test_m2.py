from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select, text
from fastapi.testclient import TestClient

from app import jobs
from app.db import Run, Mission, OptionCount, transaction, initialize, make_engine
from app.services import add_vote
from conftest import start, mission, finish


def require_postgres(rig):
    if rig[1].dialect.name != 'postgresql':
        pytest.skip('PostgreSQL row-lock/concurrency integration test')


def parallel(function, count):
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(function, range(count)))


def test_ten_starts_exactly_three(rig):
    require_postgres(rig)
    client, engine, clock, _ = rig
    identifier = mission(client, 'telepathy')['id']
    def send(_):
        return client.post('/api/runs', json={'mission_id': identifier}).status_code
    results = parallel(send, 10)
    assert results.count(200) == 3 and results.count(409) == 7
    with transaction(engine) as db:
        assert sorted(db.scalars(select(Run.attempt_no))) == [1, 2, 3]


def test_fifty_atomic_votes(rig):
    require_postgres(rig)
    client, engine, _, _ = rig
    identifier = mission(client, 'telepathy')['id']
    peers = [TestClient(client.app) for _ in range(50)]
    try:
        runs = [peer.post('/api/runs', json={'mission_id': identifier}).json()['id'] for peer in peers]
        results = parallel(lambda i: peers[i].post('/api/runs/' + runs[i] + '/answer', json={'text': 2, 'index': 0}).status_code, 50)
        assert results == [200] * 50
        with transaction(engine) as db:
            assert db.get(OptionCount, (identifier, 0, 2)).count == 50
        jobs.close_due_missions(rig[2][0] + 86400, engine=engine)
        with transaction(engine) as db:
            assert list(db.scalars(select(Run.score))) == [100] * 50
    finally:
        for peer in peers:
            peer.close()


def test_concurrent_rotations_and_closers(rig):
    require_postgres(rig)
    client, engine, clock, _ = rig
    parallel(lambda _: jobs.rotate_daily_missions('2026-11-07', engine=engine), 2)
    with transaction(engine) as db:
        assert db.scalar(select(func.count()).select_from(Mission).where(Mission.id.like('2026-11-07-%'))) == 3
    run = start(client, 'telepathy')
    # Same instant: answers and two closers race for the mission/run locks.
    clock[0] += 86400
    def action(i):
        if i < 2:
            return jobs.close_due_missions(clock[0], engine=engine)
        return client.post('/api/runs/' + run['id'] + '/answer', json={'text': 2, 'index': 0}).status_code
    outcomes = parallel(action, 4)
    assert outcomes[2:] == [200, 200]
    assert jobs.close_due_missions(clock[0], engine=engine) == 0
    with transaction(engine) as db:
        assert db.get(Mission, run['mission_id']).closed
        assert db.get(Run, run['id']).finished_at is not None
        assert db.scalar(select(func.count()).select_from(OptionCount)) == 0


def test_close_waits_for_inflight_answer(rig):
    require_postgres(rig)
    import threading
    client, engine, clock, _ = rig
    identifier = mission(client, 'telepathy')['id']
    in_flight, closing = threading.Event(), threading.Event()
    def answer():
        with transaction(engine) as db:
            db.scalar(select(Mission).where(Mission.id == identifier).with_for_update(read=True))
            in_flight.set()
            assert closing.wait(5)
            add_vote(db, identifier, 0, 1)
    def close():
        assert in_flight.wait(5)
        closing.set()
        jobs.close_due_missions(clock[0] + 86400, engine=engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(answer); b = pool.submit(close)
        a.result(timeout=15); b.result(timeout=15)
    with transaction(engine) as db:
        assert db.get(Mission, identifier).closed
        assert db.get(OptionCount, (identifier, 0, 1)).count == 1


def test_shared_leaderboard_cache_no_owner_leak(rig, monkeypatch):
    client, engine, clock, _ = rig
    run = finish(client)
    import app.main as main
    original = main.leaderboard_snapshot
    build = Mock(side_effect=original)
    monkeypatch.setattr(main, 'leaderboard_snapshot', build)
    first = client.get('/api/leaderboards/' + run['mission_id']).json()
    client.cookies.clear()
    second = client.get('/api/leaderboards/' + run['mission_id']).json()
    assert first['mine'] is not None and second['mine'] is None
    assert first['rows'] == second['rows'] and 'owners' not in second
    assert build.call_count == 1


def test_metrics_bearer_and_configurable_ip(rig, monkeypatch):
    client = rig[0]
    monkeypatch.setenv('METRICS_TOKEN', 'test-metrics')
    assert client.get('/metrics').status_code == 401
    assert client.get('/metrics', headers={'Authorization': 'Bearer test-metrics'}).status_code == 200
    monkeypatch.setenv('RATE_LIMIT_IP', '2')
    assert client.get('/api/config').status_code == 200
    client.cookies.clear()
    assert client.get('/api/config').status_code == 200
    client.cookies.clear()
    assert client.get('/api/config').status_code == 429


def test_mission_get_timeout_view_does_not_write(rig):
    client, engine, clock, _ = rig
    run = start(client, 'ore-hunt')
    clock[0] += 61
    assert client.get('/api/missions/' + run['mission_id']).json()['recent_run']['finished']
    with transaction(engine) as db:
        assert db.get(Run, run['id']).finished_at is None


def test_workflow_registration_and_trigger():
    from app.workflows import app
    from app.trigger_workflows import trigger
    # Use the real installed SDK, then mock only its network-facing client.
    assert len(app._registry.get_task_names()) == 4
    client = Mock()
    trigger(client, 'test-workflow', 'maintenance')
    assert client.workflows.start_task.call_count == 3
    trigger(client, 'test-workflow', 'build_sponsor_report', 'synthetic-mission')
    client.workflows.start_task.assert_called_with('test-workflow/build_sponsor_report', ['synthetic-mission'])


def test_prelaunch_upgrade_keeps_runs(tmp_path):
    engine = make_engine('sqlite:///' + str(tmp_path / 'old.sqlite'))
    with engine.begin() as c:
        c.execute(text('CREATE TABLE runs (id TEXT PRIMARY KEY, token TEXT, mission_id TEXT, started_at FLOAT)'))
        c.execute(text("INSERT INTO runs VALUES ('b','t','m',2),('a','t','m',1)"))
    initialize(engine)
    initialize(engine)
    with engine.connect() as c:
        assert c.execute(text('SELECT id, attempt_no FROM runs ORDER BY id')).all() == [('a', 1), ('b', 2)]
    engine.dispose()


def test_concurrent_casting_unique(rig):
    require_postgres(rig)
    client = rig[0]
    finish(client)
    payload = dict(nickname='Load applicant', birth_year=2000, contact='synthetic-contact', intro='', consent=True)
    results = parallel(lambda _: client.post('/api/casting', json=payload).status_code, 5)
    assert results.count(200) == 1 and results.count(409) == 4


def test_workflow_executes_real_jobs_offline(rig, monkeypatch):
    from app import workflows
    client, engine, clock, _ = rig
    monkeypatch.setattr(workflows, 'make_engine', lambda: engine)
    assert workflows.rotate_daily_missions.func(None, '2026-11-07') == '2026-11-07'
    assert workflows.close_due_missions.func(None, clock[0]) == 0
    assert workflows.purge_expired_applications.func(None, clock[0]) == 0
    identifier = mission(client, 'ore-hunt')['id']
    assert workflows.build_sponsor_report.func(None, identifier)['totals']['runs'] == 0


def test_workflow_trigger_cli_timestamp(monkeypatch):
    import runpy
    import sys
    import render
    import app.trigger_workflows as module
    client = Mock()
    monkeypatch.setattr(render, 'Render', lambda: client)
    monkeypatch.setenv('RENDER_WORKFLOW_SLUG', 'test-workflow')
    monkeypatch.setattr(sys, 'argv', ['trigger_workflows', 'close_due_missions', '123.5'])
    runpy.run_path(module.__file__, run_name='__main__')
    client.workflows.start_task.assert_called_once_with('test-workflow/close_due_missions', [123.5])


def test_ip_limit_ignores_forged_forwarded_for(rig, monkeypatch):
    import yaml
    client = rig[0]
    monkeypatch.setenv('CLIENT_IP_HEADER', 'True-Client-IP')
    monkeypatch.setenv('RATE_LIMIT_IP', '2')
    def call(real, forged):
        client.cookies.clear()  # fresh device each time, so only the IP limit can trip
        return client.get('/api/missions', headers={'True-Client-IP': real, 'X-Forwarded-For': forged}).status_code
    assert [call('203.0.113.9', f'6.6.6.{i}') for i in range(3)] == [200, 200, 429]
    assert call('198.51.100.7', '6.6.6.9') == 200  # keyed on the edge header, not one shared socket peer
    web = next(s for s in yaml.safe_load(open('render.yaml'))['services'] if s['type'] == 'web')
    env = {e['key']: e.get('value') for e in web['envVars']}
    assert env['CLIENT_IP_HEADER'] == 'True-Client-IP' and env.get('FORWARDED_ALLOW_IPS') != '*'
