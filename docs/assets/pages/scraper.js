/**
 * Scraper page — password-gated, with a LIVE control panel that drives the
 * local scraper engine.
 *
 * How it works:
 *   - GitHub Pages is a public static host, so the password check runs in the
 *     browser. It's a *soft* gate (keeps casual eyes out, not unbreakable).
 *   - A web page can't launch a program on a PC. So the user runs
 *     "Start Hygiene App.bat" once (downloaded below); that boots the local
 *     engine at http://localhost:8765 with CORS enabled.
 *   - This page then DETECTS that engine and drives it: Run / Run all / Stop
 *     with live progress — no need to open the localhost tab.
 *
 * The downloadable zip is CODE ONLY — no service_account.json. Whoever runs it
 * adds their own Google key locally. Never put the key in this public zip.
 *
 * Change the password: compute SHA-256 of the new password and replace PW_HASH.
 */

(function () {

  // SHA-256 of the access password. Default password is "fabhotels2026".
  const PW_HASH = '09e0ba824b8bdf58703de93588ccf6311dd7f08a54375d71f868a179e3f48c33';
  const ZIP_URL = 'downloads/bdc-hygiene-app.zip';
  const LOCAL   = 'http://localhost:8765';
  const LAUNCH_URL = 'bdchygiene://start';   // custom protocol (registered once locally)

  let unlocked = false;   // in-memory only — re-locks on every browser refresh
  let pollTimer = null;
  let scrapersLoaded = false;
  let SCRAPERS = [];
  let CATEGORIES = [];
  let connected = false;
  let loggedIn = false;
  let running = false;

  async function sha256Hex(str) {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
    return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function lget(path)        { return fetch(LOCAL + path, { method: 'GET' }).then(r => r.json()); }
  function lpost(path, body) {
    return fetch(LOCAL + path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }).then(r => r.json());
  }

  // ── Unlocked view: control panel + collapsible download ──────────────────────
  function unlockedView(target) {
    const el = UI.el;

    // Connection banner
    const connDot  = el('span', { id: 'sc-conn-dot', style: 'width:10px;height:10px;border-radius:50%;display:inline-block;background:#cbd5e1' });
    const connText = el('span', { id: 'sc-conn-text', style: 'font-size:13px;color:#52525b' }, 'Looking for the local engine…');
    const startBtn = el('button', {
      id: 'sc-start', style: 'display:none;background:#16a34a;color:#fff;border:none;border-radius:8px;'
        + 'padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer',
    }, '▶ Start engine');
    startBtn.addEventListener('click', () => {
      window.location.href = LAUNCH_URL;
      UI.toast('Launching… click "Open" if your browser asks. Give it a few seconds.');
    });
    const banner = el('div', {
      style: 'display:flex;align-items:center;gap:10px;border:1px solid #e4e4e7;'
           + 'border-radius:10px;padding:12px 16px;background:#fff;margin-bottom:14px',
    }, [connDot, connText, el('span', { style: 'flex:1' }), startBtn]);
    target.appendChild(banner);

    // ── Control card (shown when connected) ───────────────────────────────────
    const sessRow = el('div', { style: 'display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px' }, [
      el('span', { id: 'sc-sess-dot', style: 'width:10px;height:10px;border-radius:50%;display:inline-block;background:#cbd5e1' }),
      el('span', { id: 'sc-sess-text', style: 'font-size:13px;color:#3f3f46' }, 'Session: —'),
      el('span', { style: 'flex:1' }),
    ]);
    const openBtn = el('button', {
      style: 'background:#fff;color:#2563eb;border:1px solid #2563eb;border-radius:8px;'
           + 'padding:8px 14px;font-size:13px;font-weight:600;cursor:pointer',
    }, 'Open Booking & log in');
    openBtn.addEventListener('click', async () => {
      try { await lpost('/api/open-chrome'); UI.toast('Opening Chrome — log into Booking.com there.'); }
      catch (_) { UI.toast('Could not reach the local engine.', true); }
    });
    sessRow.appendChild(openBtn);

    const limitWrap = el('div', { style: 'display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:12px;color:#71717a' }, [
      el('span', null, 'Test limit (blank = all):'),
      el('input', { id: 'sc-limit', type: 'text', inputmode: 'numeric', placeholder: 'e.g. 50',
        style: 'border:1px solid #d4d4d8;border-radius:6px;padding:5px 8px;font-size:12px;width:110px' }),
      el('span', null, 'IDs (optional, space/comma):'),
      el('input', { id: 'sc-ids', type: 'text', placeholder: 'e.g. 16600534 12345678',
        style: 'border:1px solid #d4d4d8;border-radius:6px;padding:5px 8px;font-size:12px;flex:1;min-width:160px' }),
    ]);

    const listHost = el('div', { id: 'sc-list' });
    const progWrap = el('div', { id: 'sc-prog-wrap', style: 'display:none;height:10px;background:#eef2f6;border-radius:6px;overflow:hidden;margin-top:12px' },
                        [el('div', { id: 'sc-bar', style: 'height:100%;width:0;background:#2563eb;transition:width .3s' })]);
    const msgRow = el('div', { style: 'display:flex;align-items:center;gap:10px;margin-top:10px' }, [
      el('div', { id: 'sc-msg', style: 'flex:1;font-size:12.5px;color:#71717a' }, ''),
      (() => {
        const b = el('button', { id: 'sc-stop', style: 'display:none;background:#b91c1c;color:#fff;border:none;'
          + 'border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer' }, 'Stop');
        b.addEventListener('click', async () => {
          b.disabled = true; b.textContent = 'Stopping…';
          try { await lpost('/api/stop'); } catch (_) {}
        });
        return b;
      })(),
    ]);

    const controlCard = el('div', {
      id: 'sc-control',
      style: 'border:1px solid #e4e4e7;border-radius:10px;padding:18px 20px;background:#fff;'
           + 'margin-bottom:14px;display:none',
    }, [sessRow, limitWrap, listHost, progWrap, msgRow]);
    target.appendChild(controlCard);

    // ── Download & setup (collapsible) ────────────────────────────────────────
    const details = document.createElement('details');
    details.style.cssText = 'border:1px solid #e4e4e7;border-radius:10px;background:#fff;padding:4px 20px';
    const summary = document.createElement('summary');
    summary.style.cssText = 'cursor:pointer;font-weight:600;font-size:14px;color:#18181b;padding:14px 0';
    summary.textContent = 'First time? Download & set up the engine';
    details.appendChild(summary);
    const dl = el('a', {
      href: ZIP_URL, download: 'bdc-hygiene-app.zip',
      style: 'display:inline-block;background:#18181b;color:#fff;text-decoration:none;font-weight:600;'
           + 'font-size:14px;padding:11px 22px;border-radius:8px;margin-bottom:6px',
    }, '⬇️  Download scraper (.zip)');
    details.appendChild(dl);
    const ol = document.createElement('ol');
    ol.style.cssText = 'font-size:13px;color:#3f3f46;line-height:1.7;padding-left:20px;margin:14px 0 4px';
    [
      'Unzip the folder anywhere (e.g. your Desktop).',
      'Make sure <b>Python</b> and <b>Chrome</b> are installed (the launcher needs Python — Anaconda or python.org).',
      'Place your <b>service_account.json</b> (the Google key — shared privately) next to <code>app.py</code>.',
      'Double-click <b>Start Hygiene App.bat</b> <u>once</u> to set up. (The app self-registers so the green <b>▶ Start engine</b> button works from then on.)',
      'After that first run, you can boot it straight from here — just click <b>▶ Start engine</b> above (allow the browser "Open?" prompt) and the controls turn on.',
    ].forEach(t => { const li = document.createElement('li'); li.innerHTML = t; ol.appendChild(li); });
    details.appendChild(ol);
    const warn = el('div', {
      style: 'margin:10px 0 14px;padding:11px 14px;background:#fef9c3;border:1px solid #fde047;'
           + 'border-radius:7px;font-size:12px;color:#854d0e',
    }, '⚠️ The Google key (service_account.json) is NOT in this download. Get it privately from your admin — never share it publicly.');
    details.appendChild(warn);
    target.appendChild(details);

    startPolling();
  }

  function renderList() {
    const host = document.getElementById('sc-list');
    if (!host) return;
    host.innerHTML = '';
    CATEGORIES.forEach(c => {
      const members = SCRAPERS.filter(s => s.cat === c.key);
      if (!members.length) return;
      const liveCount = members.filter(s => s.status === 'live').length;

      const head = UI.el('div', { style: 'display:flex;align-items:center;justify-content:space-between;'
        + 'background:#f8fafc;padding:9px 14px;border-bottom:1px solid #e4e4e7' }, [
        UI.el('div', null, [
          UI.el('span', { style: 'font-weight:700;font-size:13px' }, c.label),
          UI.el('span', { style: 'color:#71717a;font-size:11px;margin-left:8px' }, c.hint || ''),
        ]),
        (() => {
          const b = UI.el('button', { class: 'sc-cat-run', style: 'background:#0f172a;color:#fff;border:none;'
            + 'border-radius:8px;padding:7px 14px;font-size:12px;font-weight:600;cursor:pointer' },
            'Run all (' + liveCount + ')');
          b.disabled = !liveCount || running || !loggedIn;
          b.addEventListener('click', () => runCategory(c.key));
          return b;
        })(),
      ]);

      const rows = members.map(s => {
        const btn = UI.el('button', { class: 'sc-run', style: 'background:#2563eb;color:#fff;border:none;'
          + 'border-radius:8px;padding:7px 14px;font-size:12px;font-weight:600;cursor:pointer' }, 'Run');
        btn.disabled = (s.status !== 'live') || running || !loggedIn;
        btn.addEventListener('click', () => runOne(s.id));
        return UI.el('div', { style: 'display:flex;align-items:center;justify-content:space-between;gap:12px;'
          + 'padding:11px 14px;border-bottom:1px solid #f1f3f5' }, [
          UI.el('div', null, [
            UI.el('span', { style: 'font-weight:600;font-size:14px' }, s.label),
            UI.el('span', { style: 'font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px;'
              + 'text-transform:uppercase;' + (s.status === 'live' ? 'background:#dcfce7;color:#15803d' : 'background:#f1f5f9;color:#71717a') },
              s.status === 'live' ? 'live' : 'soon'),
            UI.el('div', { style: 'color:#71717a;font-size:12px;margin-top:2px' }, s.desc || ''),
          ]),
          btn,
        ]);
      });

      const wrap = UI.el('div', { style: 'border:1px solid #e4e4e7;border-radius:10px;overflow:hidden;margin-top:12px' }, [head, ...rows]);
      host.appendChild(wrap);
    });
  }

  function readOpts() {
    const limit = parseInt((document.getElementById('sc-limit') || {}).value) || 0;
    const ids = ((document.getElementById('sc-ids') || {}).value || '').trim();
    return { limit, ids };
  }
  async function runOne(id) {
    const { limit, ids } = readOpts();
    try { const r = await lpost('/api/run', { id, limit, ids }); if (!r.ok) setMsg(r.error, true); }
    catch (_) { UI.toast('Lost connection to the local engine.', true); }
  }
  async function runCategory(cat) {
    const { limit, ids } = readOpts();
    try { const r = await lpost('/api/run-category', { cat, limit, ids }); if (!r.ok) setMsg(r.error, true); }
    catch (_) { UI.toast('Lost connection to the local engine.', true); }
  }
  function setMsg(t, isErr) {
    const m = document.getElementById('sc-msg');
    if (m) { m.textContent = t || ''; m.style.color = isErr ? '#b91c1c' : '#71717a'; }
  }

  async function poll() {
    let st = null;
    try { st = await lget('/api/status'); } catch (_) { st = null; }

    const connDot = document.getElementById('sc-conn-dot');
    const connText = document.getElementById('sc-conn-text');
    const control = document.getElementById('sc-control');
    if (!connDot) { stopPolling(); return; }   // navigated away — stop the timer

    const startBtn = document.getElementById('sc-start');
    connected = !!st;
    if (!connected) {
      connDot.style.background = '#cbd5e1';
      connText.innerHTML = 'Local engine not detected — click <b>Start engine</b> (or run <b>Start Hygiene App.bat</b> from the setup section below).';
      if (control) control.style.display = 'none';
      if (startBtn) startBtn.style.display = 'inline-block';
      scrapersLoaded = false;
      return;
    }

    connDot.style.background = '#16a34a';
    connText.innerHTML = 'Local engine connected ✓';
    if (control) control.style.display = 'block';
    if (startBtn) startBtn.style.display = 'none';

    if (!scrapersLoaded) {
      try {
        const data = await lget('/api/scrapers');
        SCRAPERS = data.scrapers || []; CATEGORIES = data.categories || [];
        scrapersLoaded = true; renderList();
      } catch (_) {}
    }

    loggedIn = !!st.logged_in;
    const sd = document.getElementById('sc-sess-dot'), stx = document.getElementById('sc-sess-text');
    if (!st.chrome) { sd.style.background = '#cbd5e1'; stx.textContent = 'Chrome not open — click “Open Booking & log in”.'; }
    else if (!st.logged_in) { sd.style.background = '#b45309'; stx.textContent = 'Chrome open — log into Booking.com in that window.'; }
    else { sd.style.background = '#16a34a'; stx.textContent = 'Booking session ready ✓'; }

    const r = st.run || {};
    running = !!r.running;
    const pw = document.getElementById('sc-prog-wrap'), bar = document.getElementById('sc-bar'), stop = document.getElementById('sc-stop');
    stop.style.display = running ? 'inline-block' : 'none';
    if (running && r.stage !== 'stopping') { stop.disabled = false; stop.textContent = 'Stop'; }
    if (running) {
      pw.style.display = 'block';
      const pct = r.total ? Math.round((r.done / r.total) * 100) : 5;
      bar.style.width = pct + '%';
      const paused = r.stage === 'paused';
      bar.style.background = paused ? '#b45309' : '#2563eb';
      setMsg((r.batch ? '[batch ' + r.batch + '] ' : '') + (r.message || (paused ? 'Paused — verify in Chrome…' : 'Working…')), paused);
    } else {
      if (r.error) { setMsg(r.error, true); pw.style.display = 'none'; }
      else if (r.result) { bar.style.width = '100%'; setMsg(r.message || ('Done — ' + r.result.filled + '/' + r.result.total + ' filled.'), false); }
    }
    // refresh button enabled/disabled state
    document.querySelectorAll('.sc-run, .sc-cat-run').forEach(b => { /* re-render is cheap enough */ });
    if (scrapersLoaded) renderList();
  }

  function startPolling() {
    stopPolling();
    poll();
    pollTimer = setInterval(poll, 2000);
  }
  function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

  // ── Locked view ──────────────────────────────────────────────────────────────
  function lockedView(target) {
    const wrap = UI.el('div', {
      style: 'max-width:420px;border:1px solid #e4e4e7;border-radius:10px;padding:28px 26px;background:#fff',
    });
    wrap.appendChild(UI.el('div', { style: 'font-size:26px;margin-bottom:6px' }, '🔒'));
    wrap.appendChild(UI.el('div', { style: 'font-size:15px;font-weight:600;color:#18181b;margin-bottom:4px' }, 'Protected'));
    wrap.appendChild(UI.el('div', { style: 'font-size:13px;color:#52525b;margin-bottom:18px' },
      'Enter the access password to open the scraper controls.'));
    const input = UI.el('input', { type: 'password', placeholder: 'Password',
      style: 'width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #d4d4d8;border-radius:8px;font-size:14px;margin-bottom:12px' });
    const btn = UI.el('button', { style: 'width:100%;background:#18181b;color:#fff;border:none;font-weight:600;'
      + 'font-size:14px;padding:11px;border-radius:8px;cursor:pointer' }, 'Unlock');
    const msg = UI.el('div', { style: 'font-size:12px;color:#dc2626;margin-top:10px;min-height:16px' }, '');
    async function tryUnlock() {
      if (await sha256Hex(input.value) === PW_HASH) {
        unlocked = true;
        const t = document.getElementById('content'); t.innerHTML = '';
        t.appendChild(UI.pageHeader({ title: 'Scraper', subtitle: 'Run the Booking.com hygiene scraper' }));
        unlockedView(t);
      } else { msg.textContent = 'Incorrect password.'; input.value = ''; input.focus(); }
    }
    btn.addEventListener('click', tryUnlock);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') tryUnlock(); });
    wrap.appendChild(input); wrap.appendChild(btn); wrap.appendChild(msg);
    target.appendChild(wrap);
    setTimeout(() => input.focus(), 50);
  }

  async function render(target) {
    stopPolling();
    scrapersLoaded = false;
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({ title: 'Scraper', subtitle: 'Run the Booking.com hygiene scraper' }));
    if (unlocked) unlockedView(target);
    else lockedView(target);
  }

  window.PAGE_SCRAPER = { id: 'scraper', label: 'Scraper', render: render };

})();
