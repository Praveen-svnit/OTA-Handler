/**
 * Hygiene App — a simple landing page with a download link + setup steps for
 * the local BDC Hygiene scraper (lives in /hygiene-app of this repo).
 */

(function () {

  const DOWNLOAD_URL =
    'https://minhaskamal.github.io/DownGit/#/home?url=' +
    'https://github.com/Praveen-svnit/OTA-Handler/tree/main/hygiene-app';
  const REPO_FOLDER =
    'https://github.com/Praveen-svnit/OTA-Handler/tree/main/hygiene-app';

  function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Scraper Set up',
      subtitle: 'Download & set up the local Booking.com hygiene scraper — runs on your PC, writes to the shared BDC Hygiene sheet',
    }));

    const card = UI.el('div', {
      style: 'background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:18px 20px;max-width:760px',
    });
    card.innerHTML = `
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:10px">
        <a class="btn btn-primary" href="${DOWNLOAD_URL}" target="_blank" rel="noopener"
           style="font-size:14px;padding:10px 18px">⬇️ Download the Hygiene App (zip)</a>
        <a href="${REPO_FOLDER}" target="_blank" rel="noopener" style="font-size:12.5px">View on GitHub ↗</a>
      </div>
      <div style="font-size:12.5px;color:#64748b;margin-bottom:18px">
        The download is <b>code only</b> — it does <b>not</b> include the Google key
        (<code>service_account.json</code>). Ask the admin (Praveen / Sujeet) for that file;
        you add it once in the app's UI. That's why the code can be public while the key stays private.
      </div>

      <div style="font-weight:700;font-size:13px;margin-bottom:8px">First-time setup</div>
      <ol style="font-size:13px;line-height:1.7;color:#1e293b;padding-left:18px;margin:0 0 16px">
        <li>Make sure you have <b>Python</b> (Anaconda is fine) and <b>Google Chrome</b>.</li>
        <li><b>Download</b> the zip above and <b>unzip</b> it somewhere you'll remember (e.g. Desktop).</li>
        <li>Double-click <b>Start Hygiene App.bat</b>. First run installs dependencies (~1–2 min),
            then opens the control panel and drops a <b>"BDC Hygiene" shortcut on your Desktop</b>.</li>
        <li>In the panel, use <b>"One-time setup — add your Google key"</b> to locate your
            <code>service_account.json</code>. It's saved locally and never leaves your PC.</li>
        <li>Click <b>"Open Booking &amp; log in"</b>, log into Booking.com in the Chrome window, and you're ready.</li>
      </ol>

      <div style="font-weight:700;font-size:13px;margin-bottom:8px">Using it</div>
      <ul style="font-size:13px;line-height:1.7;color:#1e293b;padding-left:18px;margin:0">
        <li>Scrapers are grouped by speed: <b>Fast (endpoint)</b>, <b>Fast — needs verification</b>, and <b>Page render</b>.</li>
        <li><b>Run</b> a single scraper, or <b>Run all (N)</b> on a category to fill every field in one pass (property by property).</li>
        <li>Use the <b>Test limit</b> box to try a small batch first; use <b>Stop</b> to halt safely.</li>
        <li>Everyone writes to the <b>same BDC Hygiene sheet</b>, so results stay in one place.</li>
      </ul>
    `;
    target.appendChild(card);
  }

  window.PAGE_HYGIENE = {
    id: 'hygiene',
    label: 'Scraper Set up',
    render: render,
  };

})();
