/**
 * Scraper page — password-gated download of the Booking.com hygiene scraper.
 *
 * IMPORTANT — this is a *soft* gate. GitHub Pages is a public static host, so
 * the check runs in the browser and a determined person could bypass it. It
 * exists to keep the tool away from casual eyes, not to be unbreakable.
 *
 * The downloadable zip contains CODE ONLY — no service_account.json. Whoever
 * runs it locally must drop their own Google key in beside the files (see the
 * on-screen instructions). Never put the key in this public zip.
 *
 * Change the password:
 *   1. Pick a new password.
 *   2. Compute its SHA-256 hex (e.g. PowerShell, or any online SHA-256 tool).
 *   3. Replace PW_HASH below with that hex string.
 */

(function () {

  // SHA-256 of the access password. Default password is "fabhotels2026".
  const PW_HASH = '09e0ba824b8bdf58703de93588ccf6311dd7f08a54375d71f868a179e3f48c33';
  const ZIP_URL = 'downloads/bdc-hygiene-app.zip';
  const SESSION_KEY = 'scraper_unlocked';

  async function sha256Hex(str) {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
    return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function unlockedView(target) {
    target.appendChild(UI.el('div', {
      style: 'max-width:680px;border:1px solid #e4e4e7;border-radius:10px;'
           + 'padding:24px 26px;background:#ffffff',
    }, [
      UI.el('div', { style: 'font-size:15px;font-weight:600;color:#16a34a;margin-bottom:4px' }, '🔓 Access granted'),
      UI.el('div', { style: 'font-size:13px;color:#52525b;margin-bottom:18px' },
        'Download the scraper, unzip it, and run it on your own machine.'),

      (() => {
        const a = UI.el('a', {
          href: ZIP_URL,
          download: 'bdc-hygiene-app.zip',
          style: 'display:inline-block;background:#18181b;color:#fff;text-decoration:none;'
               + 'font-weight:600;font-size:14px;padding:11px 22px;border-radius:8px',
        }, '⬇️  Download scraper (.zip)');
        return a;
      })(),

      UI.el('div', { class: 'page-sub', style: 'margin:22px 0 8px;font-weight:600;color:#18181b' }, 'Set up & run'),
      (() => {
        const ol = document.createElement('ol');
        ol.style.cssText = 'font-size:13px;color:#3f3f46;line-height:1.7;padding-left:20px;margin:0';
        [
          'Unzip the folder anywhere (e.g. your Desktop).',
          'Make sure <b>Python</b> and <b>Chrome</b> are installed (the launcher needs Python — Anaconda or python.org).',
          'Place your <b>service_account.json</b> (the Google key — shared with you privately) inside the unzipped folder, next to <code>app.py</code>.',
          'Double-click <b>Start Hygiene App.bat</b>. It installs requirements on first run and opens the app in your browser.',
          'In the app, log into Booking.com, then click Run / Run all (and Stop to halt).',
        ].forEach(t => { const li = document.createElement('li'); li.innerHTML = t; ol.appendChild(li); });
        return ol;
      })(),

      UI.el('div', {
        style: 'margin-top:18px;padding:11px 14px;background:#fef9c3;border:1px solid #fde047;'
             + 'border-radius:7px;font-size:12px;color:#854d0e',
      }, '⚠️ The Google key (service_account.json) is NOT in this download. Get it privately from your admin — never share it publicly.'),
    ]));

    const relock = UI.el('button', {
      style: 'margin-top:16px;background:none;border:none;color:#71717a;font-size:12px;'
           + 'cursor:pointer;text-decoration:underline',
    }, 'Lock again');
    relock.addEventListener('click', () => {
      sessionStorage.removeItem(SESSION_KEY);
      Router.navigate('scraper'); location.reload();
    });
    target.appendChild(relock);
  }

  function lockedView(target) {
    const wrap = UI.el('div', {
      style: 'max-width:420px;border:1px solid #e4e4e7;border-radius:10px;'
           + 'padding:28px 26px;background:#ffffff',
    });
    wrap.appendChild(UI.el('div', { style: 'font-size:26px;margin-bottom:6px' }, '🔒'));
    wrap.appendChild(UI.el('div', { style: 'font-size:15px;font-weight:600;color:#18181b;margin-bottom:4px' }, 'Protected'));
    wrap.appendChild(UI.el('div', { style: 'font-size:13px;color:#52525b;margin-bottom:18px' },
      'Enter the access password to download the scraper.'));

    const input = UI.el('input', {
      type: 'password', placeholder: 'Password',
      style: 'width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #d4d4d8;'
           + 'border-radius:8px;font-size:14px;margin-bottom:12px',
    });
    const btn = UI.el('button', {
      style: 'width:100%;background:#18181b;color:#fff;border:none;font-weight:600;'
           + 'font-size:14px;padding:11px;border-radius:8px;cursor:pointer',
    }, 'Unlock');
    const msg = UI.el('div', { style: 'font-size:12px;color:#dc2626;margin-top:10px;min-height:16px' }, '');

    async function tryUnlock() {
      const h = await sha256Hex(input.value);
      if (h === PW_HASH) {
        sessionStorage.setItem(SESSION_KEY, '1');
        const target2 = document.getElementById('content');
        target2.innerHTML = '';
        target2.appendChild(UI.pageHeader({ title: 'Scraper', subtitle: 'Booking.com hygiene scraper — download & run locally' }));
        unlockedView(target2);
      } else {
        msg.textContent = 'Incorrect password.';
        input.value = ''; input.focus();
      }
    }
    btn.addEventListener('click', tryUnlock);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') tryUnlock(); });

    wrap.appendChild(input);
    wrap.appendChild(btn);
    wrap.appendChild(msg);
    target.appendChild(wrap);
    setTimeout(() => input.focus(), 50);
  }

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Scraper',
      subtitle: 'Booking.com hygiene scraper — download & run locally',
    }));
    if (sessionStorage.getItem(SESSION_KEY) === '1') unlockedView(target);
    else lockedView(target);
  }

  window.PAGE_SCRAPER = { id: 'scraper', label: 'Scraper', render: render };

})();
