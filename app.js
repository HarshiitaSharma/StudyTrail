// Frontend for StudyTrail. All user-provided text is inserted with textContent (never innerHTML).
(() => {
  const $ = id => document.getElementById(id);
  let csrf = null, me = null, subjects = [];

  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => k === 'class' ? e.className = v : k.startsWith('on') ? e.addEventListener(k.slice(2), v) : e.setAttribute(k, v));
    kids.flat().forEach(c => { if (c != null) e.append(c); });
    return e;
  };
  const svgEl = (tag, attrs = {}, text) => {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    if (text != null) e.textContent = text;
    return e;
  };
  const fmt = m => m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m` : `${m}m`;
  const todayKey = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

  async function api(path, { method = 'GET', body } = {}) {
    const opts = { method, headers: {}, credentials: 'same-origin' };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    if (method !== 'GET' && csrf) opts.headers['X-CSRF-Token'] = csrf;
    const r = await fetch('/api' + path, opts);
    if (r.status === 204) return null;
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      if (r.status === 401 && !['/login', '/register'].includes(path)) leave();
      const err = new Error(data.error || 'Something went wrong'); err.status = r.status; throw err;
    }
    return data;
  }
  const say = (id, text, ok) => { const el = $(id); el.textContent = text || ''; el.className = 'msg ' + (ok ? 'ok' : 'err'); };
  const guard = (msgId, fn) => async e => { e.preventDefault(); say(msgId, ''); try { await fn(); } catch (err) { say(msgId, err.message); } };

  function leave() { csrf = null; me = null; $('appView').hidden = true; $('who').hidden = true; $('authView').hidden = false; }
  function enter(d) {
    csrf = d.csrf; me = d.user;
    $('authView').hidden = true; $('appView').hidden = false; $('who').hidden = false;
    $('hello').textContent = `Hi, ${me.name}`; $('goalInput').value = me.weekly_goal_min; $('logDay').value = todayKey();
    return refresh();
  }

  // ---------- auth ----------
  const tab = which => {
    $('loginForm').hidden = which !== 'login'; $('registerForm').hidden = which !== 'register';
    $('tabLogin').setAttribute('aria-selected', which === 'login'); $('tabRegister').setAttribute('aria-selected', which === 'register'); say('authMsg', '');
  };
  $('tabLogin').onclick = () => tab('login'); $('tabRegister').onclick = () => tab('register');
  $('loginForm').addEventListener('submit', guard('authMsg', async () => {
    await enter(await api('/login', { method: 'POST', body: { email: $('loginEmail').value, password: $('loginPassword').value } }));
    $('loginPassword').value = '';
  }));
  $('registerForm').addEventListener('submit', guard('authMsg', async () => {
    await enter(await api('/register', { method: 'POST', body: { name: $('regName').value, email: $('regEmail').value, password: $('regPassword').value } }));
    $('regPassword').value = '';
  }));
  $('logoutBtn').onclick = async () => { try { await api('/logout', { method: 'POST' }); } catch {} leave(); };

  // ---------- data ----------
  async function refresh() {
    const [subs, st, sess] = await Promise.all([api('/subjects'), api('/stats'), api('/sessions?limit=30')]);
    subjects = subs; renderSubjects(); renderStats(st); renderSessions(sess);
  }

  function renderStats(s) {
    $('sToday').textContent = fmt(s.today); $('sWeek').textContent = fmt(s.week); $('sStreak').textContent = String(s.streak);
    $('goalBar').style.width = s.goal_pct + '%'; $('goalTxt').textContent = s.goal ? `${s.goal_pct}% of ${fmt(s.goal)} goal` : 'No goal set';
    const svg = $('chart'); svg.replaceChildren();
    const max = Math.max(60, ...s.daily.map(d => d.minutes)), bw = 560 / s.daily.length, base = 120;
    s.daily.forEach((d, i) => {
      const hgt = Math.round((d.minutes / max) * 100);
      const r = svgEl('rect', { x: i * bw + 4, y: base - hgt, width: bw - 8, height: Math.max(hgt, d.minutes ? 2 : 0), rx: 3, fill: '#2F7D6B' });
      r.append(svgEl('title', {}, `${d.day}: ${fmt(d.minutes)}`));
      svg.append(r, svgEl('text', { x: i * bw + bw / 2, y: 135, 'text-anchor': 'middle' }, d.day.slice(8)));
    });
    $('breakdown').replaceChildren(...s.by_subject.map(b => { const dot = h('span', { class: 'dot' }); dot.style.background = b.color; return h('li', {}, dot, ` ${b.name} ${fmt(b.minutes)}`); }));
  }

  function renderSubjects() {
    $('logSubject').replaceChildren(...subjects.map(s => h('option', { value: s.id }, s.name)));
    $('subjectList').replaceChildren(...subjects.map(s => {
      const dot = h('span', { class: 'dot' }); dot.style.background = s.color;
      return h('li', {}, dot, s.name, h('button', { 'aria-label': `Delete ${s.name}`, onclick: () => removeSubject(s) }, '✕'));
    }));
    say('logMsg', subjects.length ? '' : 'Add a subject below first.');
  }
  function renderSessions(list) {
    $('sessionList').replaceChildren(...(list.length ? list.map(s => {
      const dot = h('span', { class: 'dot' }); dot.style.background = s.color;
      return h('li', {}, h('small', {}, s.day), dot, h('span', { class: 'grow' }, `${s.subject}${s.note ? ' · ' + s.note : ''}`),
        h('span', { class: 'm' }, fmt(s.minutes)),
        h('button', { 'aria-label': 'Delete session', onclick: async () => { await api('/sessions/' + s.id, { method: 'DELETE' }); refresh(); } }, '✕'));
    }) : [h('li', {}, 'No sessions yet.')]));
  }
  async function removeSubject(s) {
    if (!confirm(`Delete "${s.name}" and all its sessions?`)) return;
    await api('/subjects/' + s.id, { method: 'DELETE' }); refresh();
  }

  // ---------- forms ----------
  $('subjectForm').addEventListener('submit', guard('logMsg', async () => {
    await api('/subjects', { method: 'POST', body: { name: $('subName').value, color: $('subColor').value } });
    $('subName').value = ''; await refresh();
  }));
  $('logForm').addEventListener('submit', guard('logMsg', async () => {
    await api('/sessions', { method: 'POST', body: { subject_id: Number($('logSubject').value), minutes: Number($('logMinutes').value), day: $('logDay').value || undefined, note: $('logNote').value } });
    $('logNote').value = ''; await refresh(); say('logMsg', 'Session added.', true);
  }));
  $('goalForm').addEventListener('submit', guard('setMsg', async () => {
    await api('/goal', { method: 'PUT', body: { weekly_goal_min: Number($('goalInput').value) } });
    await refresh(); say('setMsg', 'Goal saved.', true);
  }));
  $('pwForm').addEventListener('submit', guard('setMsg', async () => {
    csrf = (await api('/password', { method: 'POST', body: { current: $('pwCur').value, new: $('pwNew').value } })).csrf;
    $('pwCur').value = $('pwNew').value = ''; say('setMsg', 'Password changed.', true);
  }));
  $('delForm').addEventListener('submit', guard('setMsg', async () => {
    if (!confirm('Permanently delete your account and all data?')) return;
    await api('/account', { method: 'DELETE', body: { password: $('delPw').value } });
    $('delPw').value = ''; leave();
  }));

  // ---------- start ----------
  api('/me').then(enter).catch(leave);
})();
