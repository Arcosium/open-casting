import base64
import concurrent.futures
import io

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app import engine as rules, jobs
from app.db import Application, Mission, OptionCount, Run, transaction
from app.main import clean_logo
from app.security import sign, unsign, verify_password
from app.services import counts
from conftest import finish, login, mission, start


def test_health_metrics_and_no_secrets(rig):
    client, _, _, _ = rig
    assert client.get('/healthz').json()['ok']
    metrics = client.get('/metrics').text
    assert 'oc_request_duration_seconds_bucket' in metrics
    assert 'oc_runs_started_total{template="no-rieul"}' in metrics
    missions = client.get('/api/missions').json()['missions']
    assert len(missions) == 3 and all('seed' not in m and 'board' not in m for m in missions)


def test_timing_and_input_cannot_spoof_score(rig):
    client, _, clock, _ = rig
    run = start(client)
    path = '/api/runs/' + run['id'] + '/answer'
    assert client.post(path,json={'text':'사과','score':99999}).status_code == 422
    clock[0] += 8.6
    result = client.post(path,json={'text':'사과'}).json()
    assert result['finished'] and result['score'] == 0 and result['reason'] == 'timeout'
    assert client.post(path,json={'text':'사과'}).json()['score'] == 0


def test_attempt_cap_is_atomic(rig):
    client, engine, _, _ = rig
    identifier = mission(client,'ore-hunt')['id']
    client.get('/healthz')
    cookie = client.cookies.get('oc_device')
    def attempt(_):
        with TestClient(client.app, raise_server_exceptions=True) as peer:
            peer.cookies.set('oc_device',cookie)
            return peer.post('/api/runs',json={'mission_id':identifier}).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(attempt,range(5)))
    assert results.count(200) == 3 and results.count(409) == 2
    with transaction(engine) as db:
        assert db.scalar(select(func.count()).select_from(Run)) == 3


def test_cookie_ownership_tamper_and_csrf(rig):
    client, _, _, _ = rig
    run = start(client)
    with TestClient(client.app) as other:
        assert other.get('/api/runs/' + run['id']).status_code == 404
        other.cookies.set('oc_device','forged.payload')
        assert other.get('/api/runs/' + run['id']).status_code == 404
    assert client.post('/api/runs',json={'mission_id':run['mission_id']},headers={'Origin':'https://untrusted.invalid'}).status_code == 403
    assert client.post('/api/runs',content='{}').status_code == 415


def test_ore_hides_board_and_cell_scoring(rig):
    client, engine, clock, _ = rig
    run = start(client,'ore-hunt')
    assert 'board' not in run and 'seed' not in run
    with transaction(engine) as db:
        m = db.get(Mission,run['mission_id'])
        board = rules.ore_board(m.seed)
    cell = next(i for i, ore in board.items() if ore == 'gem')
    result = client.post('/api/runs/' + run['id'] + '/dig',json={'x':cell%10,'y':cell//10}).json()
    assert result['score'] == 100 and result['cell'] == {'ore':'gem','points':100} and 'board' not in result
    assert client.post('/api/runs/' + run['id'] + '/dig',json={'x':cell%10,'y':cell//10}).status_code == 400
    assert client.post('/api/runs/' + run['id'] + '/dig',json={'x':-1,'y':0}).status_code == 422
    clock[0] += 61
    result = client.get('/api/runs/' + run['id']).json()
    assert result['finished'] and len(result['board']) == 12


def test_telepathy_votes_idempotent_final_and_ties(rig):
    client, engine, clock, _ = rig
    run = start(client,'telepathy')
    path = '/api/runs/' + run['id'] + '/answer'
    result = client.post(path,json={'text':1,'index':0}).json()
    assert result['score'] is None and 'counts' not in result and not result['final']
    assert client.post(path,json={'text':1,'index':0}).status_code == 409
    with transaction(engine) as db:
        db.add(OptionCount(mission_id=run['mission_id'],question=0,option=2,count=1))
        assert counts(db,run['mission_id'])[0][1] == 1
        m = db.get(Mission,run['mission_id'])
        m.ends_at = clock[0] + 1
    clock[0] += 2
    assert jobs.close_due_missions(clock[0],engine=engine) == 1
    assert jobs.close_due_missions(clock[0],engine=engine) == 0
    result = client.get('/api/runs/' + run['id']).json()
    assert result['finished'] and result['final'] and result['score'] == 100
    assert result['counts'][0] == [0,1,1,0]
    assert client.get('/api/leaderboards/' + run['mission_id']).json()['mine']['score'] == 100


def test_rate_limit_returns_429(rig):
    client, _, _, _ = rig
    statuses = [client.get('/api/missions').status_code for _ in range(31)]
    assert statuses[:30] == [200]*30 and statuses[-1] == 429
    assert client.get('/api/missions').headers['Retry-After'] == '10'
    with TestClient(client.app) as neighbour:
        # Same address (carrier NAT, school Wi-Fi), different device: not blocked.
        assert neighbour.get('/api/missions').status_code == 200


def test_casting_gate_consent_retention_and_no_birth_year(rig):
    client, engine, clock, _ = rig
    data = {'nickname':'Synthetic player','birth_year':2000,'contact':'test-player','intro':'Synthetic application','consent':True}
    assert client.post('/api/casting',json=data).status_code == 403
    finish(client)
    assert client.get('/api/casting/eligibility').json()['eligible']
    assert client.post('/api/casting',json=data | {'birth_year':2012}).json()['error'] == 'age_gate'
    assert client.post('/api/casting',json=data | {'consent':False}).json()['error'] == 'consent_required'
    assert client.post('/api/casting',json=data | {'contact':'000-0000-0000'}).json()['error'] == 'invalid_contact'
    result = client.post('/api/casting',json=data | {'birth_year':2011})
    assert result.status_code == 200
    assert client.post('/api/casting',json=data).status_code == 409
    assert 'birth_year' not in Application.__table__.columns
    with transaction(engine) as db:
        row = db.scalar(select(Application))
        assert row.age_ok and len(row.records) == 1
    assert jobs.purge_expired_applications(clock[0]+30*86400-1,engine=engine) == 0
    assert jobs.purge_expired_applications(clock[0]+30*86400,engine=engine) == 1
    assert jobs.purge_expired_applications(clock[0]+31*86400,engine=engine) == 0


def test_studio_auth_login_limit_and_signed_sessions(rig):
    client, _, _, password = rig
    assert client.get('/api/studio/applications').status_code == 401
    assert client.get('/api/studio/session').json() == {'authenticated':False}
    assert client.get('/api/studio/missions').status_code == 401
    assert client.get('/api/studio/links').status_code == 401
    for _ in range(5):
        assert client.post('/api/studio/login',json={'password':'wrong'}).status_code == 401
    assert client.post('/api/studio/login',json={'password':password}).status_code == 429
    assert unsign(sign({'exp':1},'key'),'key') is None
    assert not verify_password('anything','invalid')


def test_studio_status_and_csv_formula_escape(rig):
    client, _, _, _ = rig
    finish(client)
    result = client.post('/api/casting',json={'nickname':'=TEST()','birth_year':2000,'contact':'test-player','intro':'+formula','consent':True})
    identifier = result.json()['id']
    login(rig)
    assert client.get('/api/studio/session').json() == {'authenticated':True}
    assert client.get('/api/studio/applications').status_code == 200
    assert client.post('/api/studio/logout',json={}).status_code == 200
    assert client.get('/api/studio/applications').status_code == 401
    login(rig)
    assert client.patch('/api/studio/applications/' + identifier,json={'status':'invited'}).status_code == 200
    rows = client.get('/api/studio/applications?status=invited&sort=score').json()['applications']
    assert len(rows) == 1 and rows[0]['status'] == 'invited'
    export = client.get('/api/studio/applications?format=csv').text
    assert 'birth_year' not in export and 'age_ok' in export and "'=TEST()" in export


def test_sponsor_builder_label_logo_report_and_link(rig):
    client, _, clock, _ = rig
    login(rig)
    image = io.BytesIO()
    Image.new('RGB',(12,12),'green').save(image,format='PNG')
    data = {'template':'ore-hunt','title':'Synthetic mission','sponsor_name':'Demo Games <safe>','accent_color':'#abcd12','starts_at':clock[0]-1,'ends_at':clock[0]+3600,'logo':base64.b64encode(image.getvalue()).decode()}
    result = client.post('/api/studio/missions',json=data)
    assert result.status_code == 200, result.text
    m = result.json()
    assert m['is_sponsored'] and 'seed' not in m
    page = client.get('/missions/' + m['id']).text
    assert '광고 · Sponsored by Demo Games &lt;safe&gt;' in page and '<safe>' not in page
    assert client.get('/api/missions/' + m['id'] + '/logo').headers['content-type'] == 'image/png'
    for bad in [{'accent_color':'url(evil)'},{'starts_at':clock[0]+4000},{'logo':'not-base64'}]:
        assert client.post('/api/studio/missions',json=data|bad).status_code == 400
    assert client.post('/api/studio/missions',json=data|{'entry_fee':10}).status_code == 422
    link = client.post('/api/studio/links',json={'mission_id':m['id']}).json()
    response = client.get(link['url'],follow_redirects=False)
    assert response.status_code == 302 and response.headers['location'] == '/missions/' + m['id']
    r = client.post('/api/runs',json={'mission_id':m['id']}).json()
    clock[0] += 61
    client.get('/api/runs/' + r['id'])
    report = client.get('/api/studio/reports/' + m['id']).json()
    assert report['totals']['runs'] == 1 and report['totals']['unique_players'] == 1
    assert report['totals']['completion_rate'] == 1 and report['totals']['short_link_visits'] == 1
    assert report['days'][0]['average_session_time'] == 60
    assert client.get('/api/studio/reports/' + m['id'] + '?format=csv').status_code == 200


def test_rotation_and_seed_are_idempotent(rig):
    client, engine, _, _ = rig
    jobs.rotate_daily_missions('2026-11-06',engine=engine)
    jobs.rotate_daily_missions('2026-11-06',engine=engine)
    assert len(client.get('/api/missions').json()['missions']) == 3


def test_body_and_wrong_mission_action(rig):
    client, _, _, _ = rig
    assert client.post('/api/runs',content='x'*300001,headers={'content-type':'application/json'}).status_code == 413
    run = start(client,'telepathy')
    assert client.post('/api/runs/' + run['id'] + '/dig',json={'x':0,'y':0}).status_code == 400
    assert client.post('/api/runs/' + run['id'] + '/answer',json={'text':4}).status_code == 400
