"""Real browser journeys against an isolated, synthetic local fixture.

No production DB, fixed passwords, external browsers or network mocks.
"""
import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright

from app.db import make_engine, initialize
from app.engine import WORDS, has_rieul
from app.security import password_hash
from app.seed import seed


def main():
    os.chdir(ROOT)
    out = ROOT / '_workspace/shots'
    out.mkdir(parents=True, exist_ok=True)
    checker_path = Path.home() / '.codex/skills/arka-design/scripts/check.py'
    spec = importlib.util.spec_from_file_location('arka_check', checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    password = secrets.token_urlsafe(30)
    failures, records = [], []
    with tempfile.TemporaryDirectory(prefix='ui-check-', dir=ROOT/'data') as temporary:
        url = 'sqlite:///' + str(Path(temporary)/'synthetic.sqlite')
        engine = make_engine(url)
        initialize(engine)
        seed(engine)
        engine.dispose()
        sock = None
        for port in range(8900,9000):
            candidate = socket.socket()
            try:
                candidate.bind(('127.0.0.1',port))
                candidate.listen(128)
                sock = candidate
                break
            except OSError:
                candidate.close()
        if sock is None:
            raise RuntimeError('No free local port')
        base = 'http://127.0.0.1:' + str(port)
        env = {**os.environ,'DATABASE_URL':url,'REDIS_URL':'','SESSION_SECRET':secrets.token_hex(32),'STUDIO_PASSWORD_HASH':password_hash(password)}
        with (ROOT/'_workspace/browser-server.log').open('w') as log:
            process = subprocess.Popen([sys.executable,'-m','uvicorn','app.main:create_app','--factory','--fd',str(sock.fileno()),'--no-access-log','--log-level','warning'],env=env,pass_fds=(sock.fileno(),),stdout=log,stderr=log)
            try:
                import httpx
                for _ in range(100):
                    try:
                        if httpx.get(base+'/healthz').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError('Fixture did not start')
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True,args=['--no-sandbox'])
                    try:
                        for width in (390,1280):
                            context = browser.new_context(viewport={'width':width,'height':844 if width==390 else 900},locale='ko-KR')
                            last_request = [0]
                            def throttle(route):
                                # Stay within the real 30 requests / 10 s limit.
                                time.sleep(max(0,.46-(time.monotonic()-last_request[0])))
                                last_request[0] = time.monotonic()
                                route.continue_()
                            context.route('**/api/**',throttle)
                            page = context.new_page()
                            page.on('pageerror',lambda error: failures.append(str(error)))
                            def goto(path):
                                page.goto(base+path)
                                expect(page.locator('main')).to_have_attribute('aria-busy','false')
                                expect(page.locator('main [role=alert]')).to_have_count(0)
                            def shot(name, full=True):
                                path = out/(str(width)+'-'+name+'.png')
                                page.evaluate("Promise.all(document.getAnimations().filter(a => a.effect.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => null)))")  # settle one-shot entrance motion
                                page.screenshot(path=str(path),full_page=full)
                                defects = page.evaluate(checker.JS,False)
                                failures.extend([name+': '+str(item) for item in defects])
                                records.append({'width':width,'screen':name,'path':str(path.relative_to(ROOT)),'defects':defects})
                            goto('/')
                            shot('home')
                            data = page.evaluate('async () => (await fetch("/api/missions")).json()')['missions']
                            for template in ('no-rieul','telepathy','ore-hunt'):
                                m = next(m for m in data if m['template']==template and not m['is_sponsored'])
                                goto('/missions/'+m['id'])
                                shot(template+'-start')
                                page.locator('#nickname').fill('Screen test '+str(width))
                                page.locator('#start').click()
                                expect(page.locator('#timer')).to_be_visible()
                                if template=='no-rieul':
                                    ko = json.loads((ROOT/'app/static/i18n/ko.json').read_text())
                                    category = next(k for k in WORDS if ko['category_'+k]==page.locator('.prompt').inner_text())
                                    word = next(w for w in WORDS[category] if not has_rieul(w))
                                    page.locator('#word').fill(word)
                                    page.locator('#answer button').click()
                                    expect(page.locator('.progress').filter(has_text='2 / 8')).to_be_visible()
                                    shot(template+'-mid')
                                    page.locator('#word').fill('not-a-word')
                                    page.locator('#answer button').click()
                                elif template=='telepathy':
                                    page.locator('[data-option="0"]').click()
                                    expect(page.locator('.progress').filter(has_text='2 / 10')).to_be_visible()
                                    shot(template+'-mid')
                                    for n in range(2,11):
                                        page.locator('[data-option="0"]').click()
                                        if n<10:
                                            expect(page.locator('.progress').filter(has_text=str(n+1)+' / 10')).to_be_visible()
                                else:
                                    for n in range(25):
                                        page.locator('[data-cell]:not(:disabled)').first.click()
                                        expect(page.locator('.ore-grid .dug')).to_have_count(n+1)
                                        if n==4:
                                            shot(template+'-mid')
                                expect(page.locator('.result-score')).to_be_visible()
                                shot(template+'-result')
                            sponsored = next(m for m in data if m['is_sponsored'])
                            goto('/missions/'+sponsored['id'])
                            expect(page.locator('.sponsor-label')).to_contain_text('광고 · Sponsored by Demo Games')
                            page.evaluate('window.scrollTo(0,400)')
                            assert abs(page.locator('.sponsor-label').bounding_box()['y']) < 2
                            page.evaluate('window.scrollTo(0,0)')
                            shot('sponsored-mission')
                            goto('/leaderboard')
                            expect(page.locator('.demo-note')).to_be_visible()
                            shot('leaderboard',False)
                            goto('/casting')
                            expect(page.locator('#casting-form button')).to_be_enabled()
                            shot('casting')
                            page.locator('#birth_year').fill('2000')
                            page.locator('#contact').fill('screen-test')
                            page.locator('#intro').fill('Synthetic screen verification')
                            page.locator('[name=consent]').check()
                            page.locator('#casting-form button').click()
                            expect(page.locator('.success-box')).to_be_visible()
                            shot('casting-sent')
                            goto('/studio')
                            shot('studio-login')
                            page.locator('#password').fill(password)
                            page.locator('#login button').click()
                            expect(page.locator('.application')).to_have_count(1 if width==390 else 2)
                            shot('studio')
                            page.locator('.application').first.locator('select').select_option('invited')
                            page.locator('.application').first.locator('button').click()
                            expect(page.locator('.application').first.locator('.application-head strong')).to_have_text('초대함')
                            goto('/studio?view=builder')
                            shot('studio-builder')
                            page.locator('#title').fill('Screen mission '+str(width))
                            page.locator('#sponsor_name').fill('Demo Games')
                            page.locator('#template').select_option('telepathy')
                            page.locator('#builder button').click()
                            page.wait_for_url('**/missions/**')
                            expect(page.locator('#start')).to_be_visible()
                            expect(page.locator('.sponsor-label')).to_contain_text('Sponsored by Demo Games')
                            goto('/studio?view=links')
                            page.locator('#link-builder button').click()
                            expect(page.locator('tbody tr')).to_have_count(5 if width==390 else 6)
                            shot('studio-links')
                            goto('/studio/reports/'+sponsored['id'])
                            expect(page.locator('.stat')).to_have_count(6)
                            shot('sponsor-report')
                            with page.expect_download() as download:
                                page.get_by_role('link',name='CSV 내려받기').click()
                            assert download.value.suggested_filename.endswith('.csv')
                            goto('/sponsor')
                            shot('sponsor')
                            goto('/faq')
                            shot('faq')
                            goto('/')
                            page.locator('#language').click()
                            expect(page.locator('html')).to_have_attribute('lang','en')
                            expect(page.locator('main')).to_have_attribute('aria-busy','false')
                            expect(page.locator('h1')).to_contain_text('starts with you')
                            shot('home-en')
                            context.close()
                            print('Browser journeys complete at '+str(width)+' px',flush=True)
                    finally:
                        browser.close()
                (ROOT/'_workspace/browser-results.json').write_text(json.dumps({'screens':records,'failures':failures},ensure_ascii=False,indent=2))
                if failures:
                    raise AssertionError(json.dumps(failures,ensure_ascii=False))
                print(str(len(records))+' screenshots; zero layout/page errors.',flush=True)
            finally:
                process.terminate()  # Only the fixture process created above.
                process.wait(timeout=10)
                sock.close()


if __name__=='__main__':
    main()
