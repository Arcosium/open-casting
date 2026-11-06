import http from 'k6/http';
import { sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
const bad = new Rate('unexpected_error');
const latency = new Trend('step_latency', true);
const requests = new Counter('step_requests');
const base = __ENV.BASE_URL || 'http://app:10000';
const steps = [50, 100, 200, 400, 800];
const scenarios = {};
const thresholds = {};
for (let i = 0; i < steps.length; i++) {
  const step = String(steps[i]);
  scenarios['vu_' + step] = { executor: 'constant-vus', vus: steps[i], duration: '45s', startTime: (i * 45) + 's', gracefulStop: '0s', tags: { step } };
  thresholds['step_latency{step:' + step + '}'] = ['p(95)<500'];
  thresholds['unexpected_error{step:' + step + '}'] = ['rate<0.01'];
  thresholds['step_requests{step:' + step + '}'] = ['count>0'];
}
export const options = { scenarios, thresholds, summaryTrendStats: ['med', 'p(95)', 'p(99)'], systemTags: ['status', 'method', 'name', 'scenario'], discardResponseBodies: false };
const words = { fruit: '사과', animal: '개', country: '한국', color: '주황', food: '김치', job: '의사', vehicle: '버스', sport: '축구' };
function request(method, path, body, allowed = [200]) {
  const r = http.request(method, base + path, body === undefined ? null : JSON.stringify(body), { headers: { 'Content-Type': 'application/json' }, timeout: '5s', tags: { name: path.replace(/\/api\/runs\/[^/]+/, '/api/runs/:id').replace(/\d{4}-\d{2}-\d{2}/g, ':date') } });
  bad.add(!allowed.includes(r.status));
  latency.add(r.timings.duration);
  requests.add(1);
  return r;
}
export default function () {
  // k6 resets the per-VU cookie jar each iteration: each journey is a new arriving viewer.
  request('GET', '/');
  const response = request('GET', '/api/missions');
  if (response.status !== 200) { sleep(1); return; }
  const missions = response.json('missions').filter(m => m.active && !m.is_sponsored);
  if (!missions.length) return;
  const mission = missions[Math.floor(Math.random() * missions.length)];
  let responseRun = request('POST', '/api/runs', { mission_id: mission.id, nickname: 'Load viewer' });
  if (responseRun.status !== 200) { sleep(1); return; }
  let run = responseRun.json();
  const used = new Set();
  for (let i = 0; i < (mission.template === 'ore-hunt' ? 25 : 10) && !run.finished; i++) {
    sleep(1 + Math.random() * 2);
    if (mission.template === 'ore-hunt') {
      let cell;
      do { cell = Math.floor(Math.random() * 100); } while (used.has(cell));
      used.add(cell);
      responseRun = request('POST', '/api/runs/' + run.id + '/dig', { x: cell % 10, y: Math.floor(cell / 10) });
    } else {
      responseRun = request('POST', '/api/runs/' + run.id + '/answer', { text: mission.template === 'telepathy' ? Math.floor(Math.random() * 4) : words[run.category], index: run.index });
    }
    if (responseRun.status !== 200) break;
    run = responseRun.json();
  }
  request('GET', '/api/leaderboards/' + mission.id);
  if (Math.random() < 0.1) request('GET', '/casting');
}
export function handleSummary(data) {
  return { '/results/summary.json': JSON.stringify(data, null, 2) };
}
