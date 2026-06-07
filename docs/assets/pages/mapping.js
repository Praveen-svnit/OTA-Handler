/**
 * Mapping Checker — placeholder.
 *
 * This is the largest single page (the SU-mapping-validation engine). The
 * good news: you already have a fully-working static HTML version at
 * C:\Users\cs03778\su-mapping-checker.html with all 12 check implementations
 * in vanilla JS.
 *
 * Phase 2 of the migration ports that file into this module — replacing its
 * inline JSONP gviz calls with API.crs() / API.dashboard() from api.js.
 *
 * For now this page just shows a placeholder so the navigation works and the
 * other 4 pages (Booking.com, GoMMT, Listing Tracker, Last Checked) are
 * usable as a Phase-1 POC.
 */

(function () {

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Mapping Checker',
      subtitle: 'SU channel-manager mapping validation',
    }));

    const card = UI.el('div', {
      style: 'border:1px solid #e4e4e7;border-radius:8px;padding:24px;background:#fafafa;text-align:center;color:#52525b;font-size:13px',
    });
    card.innerHTML = `
      <div style="font-size:32px;margin-bottom:8px">⚙️</div>
      <div style="font-weight:600;color:#27272a;margin-bottom:6px">Coming in Phase 2</div>
      <div>The Mapping Checker port is ~80% done — the 12-check validation engine
      from <code>su-mapping-checker.html</code> drops in here with minor adjustments to
      use the new API client.</div>
      <div style="margin-top:14px">
        <a href="../../su-mapping-checker.html" class="btn">Open standalone version</a>
      </div>
    `;
    target.appendChild(card);
  }

  window.PAGE_MAPPING = {
    id: 'mapping',
    label: 'Mapping Checker',
    render: render,
  };

})();
