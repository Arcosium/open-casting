from unittest.mock import patch

from sqlalchemy import func, select

from app import jobs
from app.cache import Cache
from app.db import Mission, Run, transaction
from app.engine import ore_board
from app.seed import seed
from app.services import leaderboard, week_bounds
from conftest import mission, start


def test_telepathy_grace_and_hidden_majority(rig):
    client, _, clock, _ = rig
    run = start(client, 'telepathy')
    path = '/api/runs/'+run['id']+'/answer'
    assert 'counts' not in run and run['score'] is None
    clock[0] += 6
    late = client.post(path,json={'text':0,'index':0}).json()
    assert not late['finished'] and late['score'] is None and 'counts' not in late
    clock[0] += 6.5
    result = client.post(path,json={'text':0,'index':1}).json()
    assert result['finished'] and result['reason'] == 'timeout' and result['score'] == 100
    assert 'counts' not in result


def test_close_job_expires_abandoned_runs_and_leaves_open_missions(rig):
    client, engine, clock, _ = rig
    run = start(client, 'ore-hunt')
    clock[0] += 61
    assert jobs.close_due_missions(clock[0],engine=engine) == 0
    with transaction(engine) as db:
        row = db.get(Run,run['id'])
        assert row.finished_at == run['deadline'] and row.state['reason'] == 'timeout'
        assert not db.get(Mission,run['mission_id']).closed


def test_ore_twenty_five_dig_limit(rig):
    client, engine, clock, _ = rig
    run = start(client,'ore-hunt')
    with transaction(engine) as db:
        board = ore_board(db.get(Mission,run['mission_id']).seed)
    empty = [i for i in range(100) if i not in board]
    for cell in empty[:25]:
        result = client.post('/api/runs/'+run['id']+'/dig',json={'x':cell%10,'y':cell//10})
        assert result.status_code == 200
    body = result.json()
    assert body['finished'] and len(body['digs']) == 25 and body['score'] == 0
    # No further score or state changes after completion.
    client.app.state.cache.items.clear()
    cell = next(iter(board))
    body = client.post('/api/runs/'+run['id']+'/dig',json={'x':cell%10,'y':cell//10}).json()
    assert body['score'] == 0 and len(body['digs']) == 25


def test_weekly_best_only_and_week_boundary(rig):
    client, engine, clock, _ = rig
    first = start(client,'no-rieul')
    second = start(client,'no-rieul')
    third = start(client,'ore-hunt')
    week, begin, end = week_bounds(clock[0])
    assert week == '2026-W45' and end-begin == 7*86400
    with transaction(engine) as db:
        token = db.get(Run,first['id']).token
        for identifier,score in [(first['id'],100),(second['id'],300),(third['id'],80)]:
            row = db.get(Run,identifier)
            row.finished_at, row.score = clock[0],score
        db.flush()
        assert leaderboard(db,'weekly',token,clock[0])['mine']['score'] == 380
        assert leaderboard(db,'weekly',token,end)['mine'] is None


def test_seed_demo_flag_and_idempotence(rig):
    _, engine, _, _ = rig
    seed(engine)
    seed(engine)
    with transaction(engine) as db:
        demo = db.scalars(select(Run).where(Run.is_demo.is_(True))).all()
        assert len(demo) == 200
        assert all(r.nickname.startswith('Demo ') for r in demo)
        assert db.scalar(select(func.count()).select_from(Mission).where(Mission.is_sponsored.is_(True))) == 1


def test_cache_limit_expiration_and_read_interface():
    cache = Cache()
    with patch('app.cache.time.monotonic',return_value=100):
        assert cache.hit('a',2,10) and cache.hit('a',2,10)
        assert not cache.hit('a',2,10)
        cache.set('sample',{'value':1},2)
        assert cache.get('sample') == {'value':1}
    with patch('app.cache.time.monotonic',return_value=111):
        assert cache.hit('a',2,10)
        assert cache.get('sample') is None


def test_no_payment_or_reward_routes(rig):
    client, _, _, _ = rig
    for path in ('/api/payments','/api/rewards','/api/paid-retry'):
        assert client.post(path,json={}).status_code == 404
    assert 'microphone=()' in client.get('/').headers['permissions-policy']


def test_runtime_files_stay_private(tmp_path, monkeypatch):
    from app.runtime import runtime_directory
    from app.db import make_engine
    monkeypatch.chdir(tmp_path)
    target = tmp_path/'private-runtime'
    monkeypatch.setenv('OPEN_CASTING_RUNTIME_DIR',str(target))
    engine = make_engine('sqlite:///data/test.sqlite')
    assert runtime_directory().is_symlink()
    from app.db import initialize
    initialize(engine)
    assert (target/'test.sqlite').exists()
    assert (target/'test.sqlite').stat().st_mode & 0o777 == 0o600
    engine.dispose()
