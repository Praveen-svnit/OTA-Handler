/**
 * BDC Hygiene Scrape page.
 *
 * Like the Mapping Checker, the standalone tool lives in its own HTML file
 * (hygiene-scrape.html) and is embedded here as an iframe inside the SPA shell.
 * It talks to the same Google Apps Script backend (Code.gs) via assets/api.js:
 * team members queue BDC IDs, their local worker (riding their trusted Chrome)
 * claims and scrapes them, and Code.gs writes the BDC Hygiene sheet.
 */

(function () {

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Hygiene Scrape',
      subtitle: 'Queue BDC IDs — your local worker scrapes them in your trusted browser',
      onRefresh: () => {
        const f = document.getElementById('hygiene-frame');
        if (f) f.src = f.src;
      },
    }));

    const wrap = UI.el('div', {
      style: 'border:1px solid #e4e4e7;border-radius:8px;overflow:hidden;'
           + 'height:calc(100vh - 130px);background:#ffffff',
    });
    const iframe = UI.el('iframe', {
      id: 'hygiene-frame',
      src: 'hygiene-scrape.html',
      style: 'width:100%;height:100%;border:none;display:block',
      sandbox: 'allow-scripts allow-same-origin allow-forms',
      title: 'Hygiene Scrape',
    });
    wrap.appendChild(iframe);
    target.appendChild(wrap);
  }

  window.PAGE_HYGIENE = {
    id: 'hygiene',
    label: 'Hygiene Scrape',
    render: render,
  };

})();
