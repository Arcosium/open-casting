const main = document.querySelector('#main');
const sponsorship = document.querySelector('#sponsorship');
const dictionaries = await Promise.all(['ko', 'en'].map(async lang => [lang, await fetch('/static/i18n/' + lang + '.json').then(r => r.json())]));
const messages = Object.fromEntries(dictionaries);
let lang = localStorage.getItem('oc_language') === 'en' ? 'en' : 'ko';
let interval, run, currentMission, noticeTimeout, busy = false;
const t = (key, values = {}) => Object.entries(values).reduce((s, [k, v]) => s.replaceAll('{' + k + '}', String(v)), messages[lang][key] ?? key);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const tr = (key, values) => esc(t(key, values));
const button = (key, href, secondary = false) => '<a class="button' + (secondary ? ' secondary' : '') + '" href="' + esc(href) + '">' + tr(key) + '</a>';
const pageTop = (title, description = '') => '<div class="page-top bleed"><div class="markers" aria-hidden="true"><i></i><i></i><i></i></div><h1>' + tr(title) + '</h1>' + (description ? '<p class="description">' + tr(description) + '</p>' : '') + '</div>';
const field = (name, label, type = 'text', extra = '', hint = '') => '<div class="field"><label for="' + name + '">' + tr(label) + '</label><input id="' + name + '" name="' + name + '" type="' + type + '" ' + extra + (hint ? ' aria-describedby="' + name + '-hint"' : '') + '>' + (hint ? '<small id="' + name + '-hint">' + tr(hint) + '</small>' : '') + '</div>';
const title = m => m.title || t(m.template);
const glyph = template => '<span class="glyph ' + esc(template) + '" aria-hidden="true">' + ({'no-rieul': '<b>ㄹ</b>', telepathy: '<i></i><i></i>', 'ore-hunt': '<i></i>'.repeat(9)}[template] || '') + '</span>';
const LIMITS = {'no-rieul': 7, telepathy: 5, 'ore-hunt': 60};
const calm = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const displayDate = stamp => new Date(stamp * 1000).toLocaleDateString(lang === 'ko' ? 'ko-KR' : 'en-US', {timeZone: 'Asia/Seoul'});
const inputDate = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

function notice(message) {
  clearTimeout(noticeTimeout);
  document.querySelector('#notice').textContent = message;
  noticeTimeout = setTimeout(() => document.querySelector('#notice').textContent = '', 7000);
}
async function api(path, data, method = 'POST') {
  const response = await fetch(path, data === undefined ? {} : {method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(t('error_' + body.error) === 'error_' + body.error ? t('error_generic') : t('error_' + body.error));
    error.status = response.status;
    throw error;
  }
  return body;
}
function action(selector, callback, event = 'click') {
  document.querySelector(selector)?.addEventListener(event, async e => {
    e.preventDefault();
    if (busy) return;
    busy = true;
    const target = event === 'submit' ? e.target.querySelector('[type=submit]') : e.currentTarget;
    if (target?.tagName === 'BUTTON') target.disabled = true;
    try { await callback(e); }
    catch (error) { notice(error.message); }
    finally { busy = false; if (target?.isConnected && target.tagName === 'BUTTON') target.disabled = false; }
  });
}
function ad(m) {
  sponsorship.innerHTML = m?.is_sponsored ? '<div class="sponsor-label">' + (m.has_logo ? '<img src="/api/missions/' + esc(m.id) + '/logo" alt="">' : '') + '광고 · Sponsored by ' + esc(m.sponsor_name) + '</div>' : '';
  if (m) {
    document.documentElement.style.setProperty('--mission-accent', m.accent_color);
    const rgb = m.accent_color.slice(1).match(/../g).map(v => parseInt(v, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    document.documentElement.style.setProperty('--mission-ink', rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722 > .179 ? '#000000' : '#ffffff');
  } else {
    document.documentElement.style.removeProperty('--mission-accent');
    document.documentElement.style.removeProperty('--mission-ink');
  }
}
function rulesAside(template) {
  return '<aside><h2 class="aside-title">' + tr('how_to') + '</h2><ol class="rules-list">' + [1, 2, 3].map(n => '<li>' + tr('rule_' + template + '_' + n) + '</li>').join('') + '</ol><p class="hint">' + tr('free_only') + '</p><p class="hint">' + tr('footer_guard') + '</p></aside>';
}

async function home() {
  const {missions} = await api('/api/missions');
  main.innerHTML = '<section class="stage bleed"><div class="markers" aria-hidden="true"><i></i><i></i><i></i><i></i></div><div class="stage-copy"><p class="eyebrow">' + tr('hero_kicker') + '</p><h1><span>' + tr('hero_a') + '</span><span>' + tr('hero_b') + '</span></h1><p class="description">' + tr('hero_desc') + '</p><div class="actions">' + button('hero_cta', '#missions') + '</div></div><div class="viewfinder" aria-hidden="true"><div class="vf-top"><span class="vf-rec"><i></i>REC</span><span id="timecode">00:00:00:00</span></div><b>' + tr('art_title').replace('\n', '<br>') + '</b><p>' + tr('art_caption') + '</p></div><div class="stage-mark" aria-hidden="true">OPEN CASTING</div></section><section id="missions" class="missions"><div class="section-heading"><h2>' + tr('missions_today') + '</h2><p>' + tr('daily_limit') + '</p></div><div class="mission-list">' + missions.map(m => '<article class="mission-row">' + glyph(m.template) + '<div class="mission-copy">' + (m.is_sponsored ? '<div class="ad-inline">광고 · Sponsored by ' + esc(m.sponsor_name) + '</div>' : '') + '<h3><a href="/missions/' + esc(m.id) + '">' + esc(title(m)) + '</a></h3><p>' + tr('desc_' + m.template) + '</p><div class="meta"><span>' + tr('meta_' + m.template) + '</span></div></div>' + button(m.active ? 'play' : 'closed', '/missions/' + m.id, true) + '</article>').join('') + '</div></section><section class="casting-call bleed"><h2>' + tr('casting_cta_title') + '</h2><p>' + tr('casting_cta_desc') + '</p>' + button('nav_casting', '/casting') + '</section>';
  const timecode = document.querySelector('#timecode'), start = performance.now();
  clearInterval(interval);
  if (!calm()) interval = setInterval(() => {
    const frames = Math.floor((performance.now() - start) * .03);
    timecode.textContent = [frames / 108000, frames / 1800 % 60, frames / 30 % 60, frames % 30].map(v => String(Math.floor(v)).padStart(2, '0')).join(':');
  }, 1000 / 30);
}

async function missionPage(id) {
  const detail = await api('/api/missions/' + encodeURIComponent(id));
  currentMission = detail.mission;
  run = detail.recent_run;
  ad(currentMission);
  const head = '<div class="mission-top bleed"><a class="back" href="/">' + tr('back_missions') + '</a><div class="mission-title">' + glyph(currentMission.template) + '<h1>' + esc(title(currentMission)) + '</h1></div></div>';
  const intro = () => {
    clearInterval(interval);
    main.innerHTML = head + '<div class="game-layout"><section class="game-panel monitor enter"><div class="monitor-bar"><span class="vf-rec standby"><i></i>STANDBY</span><span>' + tr('meta_' + currentMission.template) + '</span></div><p class="game-intro">' + tr('desc_' + currentMission.template) + '</p>' + field('nickname', 'nickname', 'text', 'maxlength="24" autocomplete="off" value="' + esc(localStorage.getItem('oc_nickname') || '') + '"', 'nickname_hint') + '<div class="actions"><button id="start"' + (!currentMission.active || detail.attempts_left === 0 ? ' disabled' : '') + '>' + tr('start_run') + '</button>' + (run ? '<button id="resume" class="secondary">' + tr(run.finished ? 'view_record' : 'resume') + '</button>' : '') + '</div><p class="hint">' + tr('attempts_left', {n: detail.attempts_left}) + '</p>' + (!currentMission.active ? '<p class="hint">' + tr('closed') + '</p>' : '') + '</section>' + rulesAside(currentMission.template) + '</div>';
    action('#start', async () => {
      const nickname = document.querySelector('#nickname').value.trim();
      if (nickname) localStorage.setItem('oc_nickname', nickname);
      run = await api('/api/runs', {mission_id: id, nickname});
      detail.attempts_left--;
      game();
    });
    action('#resume', async () => { run = await api('/api/runs/' + run.id); game(); });
  };
  const game = () => {
    clearInterval(interval);
    const template = currentMission.template;
    if (run.finished) {
      main.innerHTML = head + '<div class="game-layout"><section class="game-panel monitor result enter"><div class="cut-stamp" aria-hidden="true">' + tr('cut_stamp') + '</div><h2 class="result-title">' + tr('result_title') + '</h2><div class="result-score">' + run.score + '</div><p>' + tr(run.final ? 'final_score' : 'provisional') + '</p><p class="result-message">' + tr(run.reason === 'timeout' ? 'result_timeout' : run.reason === 'invalid_word' ? 'result_invalid' : 'result_complete') + '</p><p class="hint">' + tr('record_badge') + ' · ' + tr('display_only') + '</p><div class="actions section-gap">' + (detail.attempts_left > 0 && currentMission.active ? '<button id="again">' + tr('try_again') + '</button>' : '') + button('to_leaderboard', '/leaderboard?mission=' + id, true) + button('nav_casting', '/casting', true) + '</div>' + (template === 'ore-hunt' ? gridHtml(true) : '') + '</section>' + rulesAside(template) + '</div>';
      action('#again', async () => intro());
      const score = document.querySelector('.result-score'), begin = performance.now();
      if (!calm() && run.score > 0) requestAnimationFrame(function count(now) {
        const p = Math.min(1, (now - begin) / 700);
        score.textContent = Math.round(run.score * (1 - (1 - p) ** 3));
        if (p < 1) requestAnimationFrame(count);
      });
      return;
    }
    let content = '';
    if (template === 'no-rieul') content = '<p class="progress">' + tr('round', {n:run.index + 1,total:8}) + '</p><div class="prompt">' + tr('category_' + run.category) + '</div><form id="answer" class="game-form"><label class="sr-only" for="word">' + tr('answer_label') + '</label><input id="word" name="word" maxlength="100" required autocomplete="off"><button type="submit">' + tr('answer_submit') + '</button></form><p class="hint">' + tr('word_hint') + '</p><p class="hint">' + tr('used_words') + ': ' + run.used.map(esc).join(', ') + '</p>';
    if (template === 'telepathy') content = '<p class="progress">' + tr('round', {n:run.index + 1,total:10}) + '</p><div class="prompt">' + tr('question_' + run.index) + '</div><div class="answer-options">' + [0,1,2,3].map(n => '<button data-option="' + n + '">' + tr('option_' + run.index + '_' + n) + '</button>').join('') + '</div><p class="hint">' + tr('provisional') + '</p>';
    if (template === 'ore-hunt') content = '<p class="progress">' + tr('digs_left', {n:25 - Object.keys(run.digs).length}) + '</p>' + gridHtml(false) + '<p class="hint">' + tr('ore_legend') + '</p>';
    main.innerHTML = head + '<div class="game-layout"><section class="game-panel monitor live"><div class="monitor-bar"><span class="vf-rec"><i></i>REC</span><span>' + esc(title(currentMission)) + '</span></div><div class="game-head"><div><div class="timer" id="timer" aria-label="' + tr('time_left') + '"></div><span class="progress">' + tr('time_left') + '</span></div><div class="score"><strong>' + (run.score ?? '–') + '</strong><span>' + tr('score') + '</span></div></div><div class="time-bar" aria-hidden="true"><i id="timebar"></i></div>' + content + '</section>' + rulesAside(template) + '</div>';
    action('#answer', async () => { run = await api('/api/runs/' + run.id + '/answer', {text:document.querySelector('#word').value,index:run.index}); game(); }, 'submit');
    for (const element of document.querySelectorAll('[data-option]')) action('[data-option="' + element.dataset.option + '"]', async () => { run = await api('/api/runs/' + run.id + '/answer', {text:Number(element.dataset.option),index:run.index}); game(); });
    for (const element of document.querySelectorAll('[data-cell]:not(:disabled)')) action('[data-cell="' + element.dataset.cell + '"]', async () => { const cell = Number(element.dataset.cell); run = await api('/api/runs/' + run.id + '/dig', {x:cell % 10,y:Math.floor(cell / 10)}); game(); });
    const localStart = performance.now();
    const snapshot = run;
    let checking = false;
    const tick = async () => {
      const serverNow = snapshot.server_now + (performance.now() - localStart) / 1000;
      const displayDeadline = snapshot.deadline - (template === 'ore-hunt' ? 0 : 1.5);
      const timer = document.querySelector('#timer'), bar = document.querySelector('#timebar');
      const left = Math.max(0, displayDeadline - serverNow);
      if (timer) { timer.textContent = left.toFixed(1); timer.classList.toggle('low', left < LIMITS[template] * .3); }
      if (bar) bar.style.transform = 'scaleX(' + Math.min(1, left / LIMITS[template]) + ')';
      if (serverNow >= snapshot.deadline && !checking && !busy) {
        checking = true;
        try { run = await api('/api/runs/' + snapshot.id); game(); }
        catch (error) { notice(error.message); setTimeout(() => checking = false, 1000); }
      }
    };
    tick();
    interval = setInterval(tick, 100);
    if (template === 'no-rieul' && matchMedia('(min-width:761px)').matches) document.querySelector('#word').focus();
  };
  function gridHtml(reveal) {
    return '<div class="ore-grid" role="group" aria-label="' + tr('ore-hunt') + '">' + Array.from({length:100}, (_, i) => {
      const cell = run.digs[i];
      const ore = cell?.ore || (reveal && run.board?.[i]);
      const label = t('cell', {x:i % 10 + 1,y:Math.floor(i / 10) + 1}) + (ore ? ', ' + t(ore) : cell ? ', ' + t('distance', {n:cell.distance}) : '');
      return '<button type="button" data-cell="' + i + '" aria-label="' + esc(label) + '" class="' + (cell ? 'dug ' : '') + (ore ? cell ? 'found' : 'revealed' : '') + '"' + (cell || reveal ? ' disabled' : '') + '>' + (ore ? rulesOre(ore) : cell ? cell.distance : '<span aria-hidden="true">·</span>') + '</button>';
    }).join('') + '</div>';
  }
  intro();
}
function rulesOre(ore) { return ({iron:'10',gold:'30',gem:'100'})[ore]; }

async function leaderboardPage() {
  const missions = (await api('/api/missions')).missions;
  const selected = new URLSearchParams(location.search).get('mission') || 'weekly';
  const result = await api('/api/leaderboards/' + encodeURIComponent(selected));
  ad(missions.find(m => m.id === selected));
  main.innerHTML = pageTop('leaderboard_title','leaderboard_desc') + '<label for="scope">' + tr('choose_mission') + '</label><select id="scope"><option value="weekly">' + tr('weekly') + '</option>' + missions.map(m => '<option value="' + esc(m.id) + '"' + (selected === m.id ? ' selected' : '') + '>' + esc(title(m)) + (m.is_sponsored ? ' · ' + esc(m.sponsor_name) : '') + '</option>').join('') + '</select>' + (result.has_demo ? '<div class="demo-note">' + tr('demo_badge') + '</div>' : '') + (result.provisional ? '<p class="hint">' + tr('provisional') + '</p>' : '') + '<div class="table-wrap"><table class="rank-table"><thead><tr><th>' + tr('rank') + '</th><th>' + tr('player') + '</th><th>' + tr('score') + '</th></tr></thead><tbody>' + result.rows.map(r => '<tr' + (r.rank <= 3 ? ' class="top"' : '') + '><td>' + r.rank + '</td><td>' + esc(r.nickname) + (r.is_demo ? '<small>' + tr('demo_row') + '</small>' : '') + '</td><td>' + r.score + '</td></tr>').join('') + '</tbody></table></div>' + (!result.rows.length ? '<p class="empty">' + tr('no_records') + '</p>' : '') + '<div class="my-rank"><strong>' + tr('my_rank') + '</strong><span>' + (result.mine ? result.mine.rank + ' · ' + esc(result.mine.nickname) + ' · ' + result.mine.score : tr('no_my_rank')) + '</span></div><p class="hint">' + tr('display_only') + '</p>';
  document.querySelector('#scope').addEventListener('change', e => location.href = '/leaderboard?mission=' + encodeURIComponent(e.target.value));
}

async function castingPage() {
  const eligibility = await api('/api/casting/eligibility');
  main.innerHTML = pageTop('casting_title','casting_desc') + '<div class="form-layout"><section><div class="notice-box">' + tr(eligibility.eligible ? 'eligible' : 'not_eligible_msg') + (eligibility.eligible ? '<p class="hint">' + eligibility.records.map(r => tr(r.template) + ' ' + r.score).join(' · ') + '</p>' : '<div class="actions section-gap">' + button('nav_missions','/') + '</div>') + '</div><form id="casting-form">' + field('nickname','nickname','text','required maxlength="24" value="' + esc(localStorage.getItem('oc_nickname') || '') + '"','nickname_hint') + field('birth_year','birth_year','number','required min="1900" max="2200" inputmode="numeric"','age_hint') + field('contact','contact','text','required maxlength="120" autocomplete="off"','contact_hint') + '<div class="field"><label for="intro">' + tr('intro') + '</label><textarea name="intro" id="intro" maxlength="100" required aria-describedby="intro-hint"></textarea><small id="intro-hint">' + tr('intro_hint') + '</small></div><div class="field"><label class="checkbox"><input type="checkbox" name="consent" required><span>' + tr('consent') + '</span></label></div><button type="submit"' + (!eligibility.eligible ? ' disabled' : '') + '>' + tr('apply') + '</button></form></section><aside class="form-aside"><h2>' + tr('casting_steps_title') + '</h2><ol>' + [1,2,3].map(i => '<li>' + tr('casting_step' + i) + '</li>').join('') + '</ol><p class="hint">' + tr('footer_guard') + '</p></aside></div>';
  action('#casting-form', async e => {
    const data = new FormData(e.target);
    const result = await api('/api/casting', {nickname:data.get('nickname'),birth_year:Number(data.get('birth_year')),contact:data.get('contact'),intro:data.get('intro'),consent:data.get('consent') === 'on'});
    main.innerHTML = '<section class="success-box"><h1>' + tr('casting_sent') + '</h1><p class="description">' + tr('casting_sent_desc') + '</p><p class="hint">' + tr('retention_until',{date:displayDate(result.expires_at)}) + '</p><div class="actions section-gap">' + button('nav_missions','/') + '</div></section>';
  }, 'submit');
}

function studioLogin() {
  main.innerHTML = '<section class="studio-login">' + pageTop('studio_title','studio_desc') + '<form id="login">' + field('password','studio_password','password','required maxlength="200" autocomplete="current-password"') + '<button type="submit">' + tr('login') + '</button></form></section>';
  action('#login', async e => { await api('/api/studio/login',{password:new FormData(e.target).get('password')}); await render(); }, 'submit');
}
function studioNav() {
  return '<div class="studio-tabs">' + [['applications','/studio'],['stats','/studio?view=stats'],['builder','/studio?view=builder'],['short_links','/studio?view=links']].map(([label,href]) => '<a href="' + href + '">' + tr(label) + '</a>').join('') + '<button class="secondary" id="logout">' + tr('logout') + '</button></div>';
}
async function studioPage() {
  if (!(await api('/api/studio/session')).authenticated) return studioLogin();
  const view = new URLSearchParams(location.search).get('view') || 'applications';
  let missions;
  try { missions = (await api('/api/studio/missions')).missions; }
  catch (error) { if (error.status === 401) return studioLogin(); throw error; }
  main.innerHTML = pageTop('studio_title','studio_desc') + studioNav() + '<section id="studio-content"></section>';
  action('#logout',async () => { await api('/api/studio/logout',{}); studioLogin(); });
  const content = document.querySelector('#studio-content');
  if (view === 'applications') {
    const query = new URLSearchParams(location.search);
    const status = query.get('status') || 'all', sort = query.get('sort') || 'newest';
    const rows = (await api('/api/studio/applications?status=' + encodeURIComponent(status) + '&sort=' + encodeURIComponent(sort))).applications;
    content.innerHTML = '<h2>' + tr('applications') + '</h2><div class="studio-toolbar"><label class="sr-only" for="status-filter">' + tr('status') + '</label><select id="status-filter">' + ['all','submitted','shortlisted','invited','declined'].map(s => '<option value="' + s + '"' + (s === status ? ' selected' : '') + '>' + tr(s === 'all' ? 'all_status' : s) + '</option>').join('') + '</select><label class="sr-only" for="sort-filter">' + tr('records') + '</label><select id="sort-filter">' + ['newest','score'].map(s => '<option value="' + s + '"' + (s === sort ? ' selected' : '') + '>' + tr('sort_' + s) + '</option>').join('') + '</select>' + button('export_csv','/api/studio/applications?format=csv&status=' + status + '&sort=' + sort,true) + '</div>' + rows.map(row => '<article class="application"><div class="application-head"><h3>' + esc(row.nickname) + '</h3><strong>' + tr(row.status) + '</strong></div><p>' + esc(row.intro) + '</p><p class="hint">' + tr('age_ok') + ' · ' + displayDate(row.submitted_at) + '</p><p>' + esc(row.contact) + '</p><p class="hint">' + tr('records') + ': ' + row.records.map(r => tr(r.template) + ' ' + r.score).join(' · ') + '</p><label for="status-' + row.id + '">' + tr('status') + '</label><div class="actions"><select id="status-' + row.id + '">' + ['shortlisted','invited','declined'].map(s => '<option value="' + s + '"' + (s === row.status ? ' selected' : '') + '>' + tr(s) + '</option>').join('') + '</select><button class="secondary" data-save="' + row.id + '">' + tr('save_status') + '</button></div></article>').join('') + (!rows.length ? '<p class="empty">' + tr('no_applications') + '</p>' : '');
    for (const id of ['#status-filter','#sort-filter']) document.querySelector(id).addEventListener('change', () => location.href = '/studio?status=' + document.querySelector('#status-filter').value + '&sort=' + document.querySelector('#sort-filter').value);
    for (const row of rows) action('[data-save="' + row.id + '"]',async () => { await api('/api/studio/applications/' + row.id,{status:document.querySelector('#status-' + row.id).value},'PATCH'); await studioPage(); notice(t('saved')); });
  } else if (view === 'builder') {
    content.innerHTML = '<div class="builder"><h2>' + tr('builder') + '</h2><p class="notice-box section-gap">' + tr('ad_required') + '</p><form id="builder">' + field('title','mission_title','text','required maxlength="100"') + '<div class="field"><label for="template">' + tr('mission_template') + '</label><select id="template" name="template">' + ['no-rieul','telepathy','ore-hunt'].map(template => '<option value="' + template + '">' + tr(template) + '</option>').join('') + '</select></div>' + field('sponsor_name','sponsor_name','text','required maxlength="60"') + field('accent_color','accent_color','color','value="#d5ef45" required') + field('logo','logo','file','accept="image/png,image/jpeg"','logo_hint') + '<div class="field-pair">' + field('starts_at','starts_at','datetime-local','required value="' + inputDate(new Date()) + '"') + field('ends_at','ends_at','datetime-local','required value="' + inputDate(new Date(Date.now() + 86400000)) + '"') + '</div><button type="submit">' + tr('create_mission') + '</button></form></div>';
    action('#builder',async e => {
      const form = new FormData(e.target), file = form.get('logo');
      let logo = null;
      if (file?.size) {
        if (file.size > 200 * 1024) throw new Error(t('error_invalid_logo'));
        logo = await new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = reject; reader.readAsDataURL(file); });
      }
      const result = await api('/api/studio/missions',{template:form.get('template'),title:form.get('title'),sponsor_name:form.get('sponsor_name'),accent_color:form.get('accent_color'),logo,starts_at:new Date(form.get('starts_at')).getTime()/1000,ends_at:new Date(form.get('ends_at')).getTime()/1000});
      location.href = '/missions/' + result.id;
    }, 'submit');
  } else if (view === 'links') {
    const links = (await api('/api/studio/links')).links;
    content.innerHTML = '<h2>' + tr('short_links') + '</h2><form id="link-builder" class="studio-toolbar"><label class="sr-only" for="link-mission">' + tr('mission_title') + '</label><select id="link-mission" name="mission_id">' + missions.map(m => '<option value="' + esc(m.id) + '">' + esc(title(m)) + ' · ' + displayDate(m.starts_at) + '</option>').join('') + '</select><button type="submit">' + tr('new_link') + '</button></form><div class="table-wrap"><table><thead><tr><th>' + tr('link') + '</th><th>' + tr('visits') + '</th></tr></thead><tbody>' + links.map(link => '<tr><td><a href="/v/' + esc(link.code) + '">/v/' + esc(link.code) + '</a><small>' + esc(title(missions.find(m => m.id === link.mission_id) || {template:'ore-hunt'})) + '</small></td><td>' + link.visits + '</td></tr>').join('') + '</tbody></table></div>';
    action('#link-builder',async e => { await api('/api/studio/links',{mission_id:new FormData(e.target).get('mission_id')}); await studioPage(); },'submit');
  } else {
    content.innerHTML = '<h2>' + tr('stats') + '</h2><div class="table-wrap"><table><thead><tr><th>' + tr('mission_title') + '</th><th>' + tr('date') + '</th><th>' + tr('report') + '</th></tr></thead><tbody>' + missions.map(m => '<tr><td><a href="/missions/' + esc(m.id) + '">' + esc(title(m)) + '</a>' + (m.is_sponsored ? '<small>광고 · Sponsored by ' + esc(m.sponsor_name) + '</small>' : '') + '</td><td>' + displayDate(m.starts_at) + '</td><td><a href="/studio/reports/' + esc(m.id) + '">' + tr('report') + ' →</a></td></tr>').join('') + '</tbody></table></div>';
  }
}

async function reportPage(id) {
  if (!(await api('/api/studio/session')).authenticated) return studioLogin();
  let report;
  try { report = await api('/api/studio/reports/' + encodeURIComponent(id)); }
  catch (error) { if (error.status === 401) return studioLogin(); throw error; }
  const m = (await api('/api/studio/missions')).missions.find(m => m.id === id);
  ad(m);
  const stats = ['unique_players','runs','completion_rate','average_score','average_session_time','short_link_visits'];
  const value = (key, row) => key === 'completion_rate' ? (row[key] * 100).toFixed(1) + '%' : key === 'average_session_time' ? t('seconds',{n:row[key]}) : row[key];
  main.innerHTML = '<a class="back" href="/studio?view=stats">← ' + tr('nav_studio') + '</a>' + pageTop('report_title') + '<h2>' + esc(title(m)) + '</h2>' + (report.totals.has_demo ? '<div class="demo-note">' + tr('demo_badge') + '</div>' : '') + (report.provisional ? '<p class="hint">' + tr('provisional') + '</p>' : '') + '<div class="stat-grid">' + stats.map(key => '<div class="stat"><b>' + esc(value(key,report.totals)) + '</b><span>' + tr(key) + '</span></div>').join('') + '</div><p class="hint">' + tr('report_note') + '</p><div class="section-heading section-gap"><h2>' + tr('daily_report') + '</h2>' + button('export_csv','/api/studio/reports/' + id + '?format=csv',true) + '</div><p class="table-hint hint">' + tr('table_scroll') + '</p><div class="table-wrap"><table class="report-table"><thead><tr><th>' + tr('date') + '</th>' + stats.map(key => '<th>' + tr(key) + '</th>').join('') + '</tr></thead><tbody>' + report.days.map(row => '<tr><td>' + esc(row.date) + '</td>' + stats.map(key => '<td>' + esc(value(key,row)) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>' + (!report.days.length ? '<p class="empty">' + tr('no_report') + '</p>' : '');
}
async function sponsorPage() {
  const config = await api('/api/config');
  main.innerHTML = '<section class="sponsor-hero"><h1>' + tr('sponsor_title').replace('\n','<br>') + '</h1><p>' + tr('sponsor_desc') + '</p></section><div class="steps">' + [1,2].map(i => '<section><h2>' + tr('sponsor_step' + i + '_title') + '</h2><p>' + tr('sponsor_step' + i + '_desc') + '</p></section>').join('') + '</div><section class="section-gap"><h2>' + tr('sample_report') + '</h2><p class="hint">' + tr('sample_note') + '</p><div class="stat-grid">' + ['unique_players','runs','completion_rate','average_score','average_session_time','short_link_visits'].map(key => '<div class="stat"><strong>' + tr(key) + '</strong></div>').join('') + '</div></section><section class="section-gap"><h2>' + tr('sponsor_contact_title') + '</h2><p class="description">' + (config.sponsor_contact ? esc(config.sponsor_contact) : tr('sponsor_contact_empty')) + '</p></section>';
}
function faqPage() {
  main.innerHTML = pageTop('faq_title') + '<div class="faq-list">' + [0,1,2,3,4,5].map(i => '<details' + (i === 0 ? ' open' : '') + '><summary>' + tr('faq_' + i + '_q') + '</summary><p>' + tr('faq_' + i + '_a') + '</p></details>').join('') + '</div>';
}
async function render() {
  clearInterval(interval);
  ad(null);
  document.documentElement.lang = lang;
  document.querySelector('#language').textContent = lang === 'ko' ? 'English' : '한국어';
  document.querySelector('#ticker').innerHTML = ['missions_today', 'daily_limit', 'free_only', 'ticker_pick'].map(key => '<span>' + tr(key) + '</span>').join('');
  document.querySelectorAll('[data-i18n]').forEach(el => el.textContent = t(el.dataset.i18n));
  document.querySelectorAll('[data-i18n-label]').forEach(el => el.setAttribute('aria-label',t(el.dataset.i18nLabel)));
  main.setAttribute('aria-busy','true');
  try {
    const path = location.pathname.split('/').filter(Boolean);
    if (!path.length) await home();
    else if (path[0] === 'missions') await missionPage(decodeURIComponent(path[1]));
    else if (path[0] === 'leaderboard') await leaderboardPage();
    else if (path[0] === 'casting') await castingPage();
    else if (path[0] === 'studio' && path[1] === 'reports') await reportPage(decodeURIComponent(path[2]));
    else if (path[0] === 'studio') await studioPage();
    else if (path[0] === 'sponsor') await sponsorPage();
    else faqPage();
  } catch (error) {
    main.innerHTML = '<p class="notice-box" role="alert">' + esc(error.message) + '</p><a class="back" href="/">' + tr('back_missions') + '</a>';
  } finally { main.setAttribute('aria-busy','false'); }
}
document.querySelector('#language').addEventListener('click',async () => {
  if (busy) return;
  busy = true;
  lang = lang === 'ko' ? 'en' : 'ko';
  localStorage.setItem('oc_language',lang);
  try { await render(); } finally { busy = false; }
});
await render();
