/**
 * Mapping Checker (Phase 2).
 *
 * The full 12-check SU-mapping validation engine lives in the standalone
 * file at /docs/su-mapping-checker.html — already 1,100+ lines of working
 * vanilla JS with its own CSS, stepper UI, table rendering, and Excel export.
 *
 * Rather than rewrite all of that to use our shared UI helpers, we embed it
 * as an iframe inside the SPA shell. The standalone file was modified to:
 *   - load assets/api.js  (so it can reach the GAS proxy)
 *   - replace its gviz JSONP fetches with API.crs() / API.dashboard()
 * so it now uses the same service-account-backed data path as the rest of
 * the app. The team needs zero direct Google Sheet access.
 *
 * Phase 3 would rewrite this in our component style; not worth it today.
 */

(function () {

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Mapping Checker',
      subtitle: 'SU channel-manager mapping validation',
      onRefresh: () => {
        const f = document.getElementById('mapping-frame');
        if (f) f.src = f.src;   // simple iframe reload
      },
    }));

    // Iframe fills the remaining viewport height. Border/radius match other
    // page containers for visual consistency.
    const wrap = UI.el('div', {
      style: 'border:1px solid #e4e4e7;border-radius:8px;overflow:hidden;'
           + 'height:calc(100vh - 130px);background:#ffffff',
    });
    const iframe = UI.el('iframe', {
      id: 'mapping-frame',
      src: 'su-mapping-checker.html',
      style: 'width:100%;height:100%;border:none;display:block',
      sandbox: 'allow-scripts allow-same-origin allow-downloads allow-forms',
      title: 'Mapping Checker',
    });
    wrap.appendChild(iframe);
    target.appendChild(wrap);
  }

  window.PAGE_MAPPING = {
    id: 'mapping',
    label: 'Mapping Checker',
    render: render,
  };

})();
