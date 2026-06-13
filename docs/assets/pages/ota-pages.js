/**
 * OTA tracker pages — generic searchable/filterable table view of one tab
 * from each OTA's sheet (server-side whitelist lives in Code.gs → OTA_SHEETS).
 *
 * Add a single-tab page: one line in OTA_SHEETS (Code.gs) + one entry in OTAS.
 * Add a multi-tab page (sub-tabs): entries in OTA_SHEETS + one entry in MULTI.
 */

(function () {

  // Single-tab pages. id = route hash + order; key = OTA_SHEETS key in Code.gs.
  const OTAS = [
    { id: 'agoda', label: 'Agoda', key: 'agoda' },
    { id: 'ixigo', label: 'Ixigo', key: 'ixigo' },
    { id: 'expedia', label: 'Expedia', key: 'expedia' },
    { id: 'cleartrip', label: 'Cleartrip', key: 'cleartrip' },
    { id: 'indigo', label: 'Indigo', key: 'indigo' },
    { id: 'easemytrip', label: 'EaseMyTrip', key: 'easemytrip' },
    { id: 'yatra', label: 'Yatra', key: 'yatra' },
    { id: 'photoshoot', label: 'Photoshoot', key: 'photoshoot', subtitle: 'OTA photoshoot tracker' },
  ];

  // Multi-tab pages — one page, several sub-tabs (each a key in OTA_SHEETS).
  const MULTI = [
    { id: 'ota-dss', label: 'OTA DSS', subtitle: 'DoD / WoW / MoM summaries',
      tabs: [
        { label: 'DoD', key: 'dss_dod' },
        { label: 'WoW', key: 'dss_wow' },
        { label: 'MoM', key: 'dss_mom' },
      ] },
  ];

  // ── Shared table view (filter + search + table + CSV) for one payload ────────
  function buildTableView(host, payload, csvName) {
    host.innerHTML = '';
    const cols = payload.cols;
    const records = UI.toRecords(payload);
    const state = { filterCol: null, filterVals: [], search: '' };

    host.appendChild(UI.stats([`<b>${records.length.toLocaleString()}</b> rows`, `${cols.length} columns`]));

    const fr = UI.el('div', { class: 'filters' });
    const colSelect = UI.el('select', {
      onChange: (e) => { state.filterCol = e.target.value || null; state.filterVals = []; renderValsFilter(); redraw(); },
    });
    colSelect.appendChild(UI.el('option', { value: '' }, '— pick a column —'));
    cols.forEach(c => colSelect.appendChild(UI.el('option', { value: c }, c)));
    fr.appendChild(UI.el('div', { class: 'filter' }, [UI.el('div', { class: 'filter-label' }, 'Filter by column'), colSelect]));
    const valsHost = UI.el('div', { class: 'filter' });
    fr.appendChild(valsHost);
    function renderValsFilter() {
      valsHost.innerHTML = '';
      if (!state.filterCol) return;
      const vals = Array.from(new Set(records.map(r => String(r[state.filterCol] || '').trim()).filter(Boolean))).sort();
      valsHost.appendChild(UI.el('div', { class: 'filter-label' }, `Values of ${state.filterCol}`));
      valsHost.appendChild(UI.multiselect({
        label: state.filterCol, options: vals, selected: state.filterVals,
        placeholder: 'All values', onChange: (v) => { state.filterVals = v; redraw(); },
      }).el);
    }
    host.appendChild(fr);

    const tb = UI.toolbar({ placeholder: 'Search across all columns…', countText: '0 rows',
      onChange: (v) => { state.search = v; redraw(); } });
    host.appendChild(tb.el);

    const tableHost = UI.el('div');
    host.appendChild(tableHost);
    function redraw() {
      let view = records.slice();
      if (state.filterCol && state.filterVals.length) view = view.filter(r => state.filterVals.includes(String(r[state.filterCol] || '').trim()));
      if (state.search) { const q = state.search.toLowerCase(); view = view.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q))); }
      tb.el.querySelector('.count').textContent = `${view.length.toLocaleString()} rows`;
      tableHost.innerHTML = '';
      tableHost.appendChild(UI.table({ columns: cols.map(c => ({ key: c, label: c })), rows: view, height: 540 }));
      tableHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(csvName, cols, view) }, 'Download CSV'));
    }
    redraw();
  }

  // ── Single-tab page ─────────────────────────────────────────────────────────
  function makeSingle(cfg) {
    const cache = { payload: null };
    async function render(target) {
      target.innerHTML = '';
      target.appendChild(UI.pageHeader({
        title: cfg.label, subtitle: cfg.subtitle || 'Live property tracker',
        onRefresh: async () => {
          UI.toast('Refreshing…');
          try { cache.payload = await API.ota(cfg.key, { refresh: true }); render(target); UI.toast('Refreshed'); }
          catch (e) { UI.toast('Refresh failed: ' + e.message, true); }
        },
      }));
      const host = UI.el('div');
      target.appendChild(host);
      let payload;
      try { UI.updateLoader('Loading ' + cfg.label + '…'); payload = cache.payload || (cache.payload = await API.ota(cfg.key)); }
      catch (e) { host.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }
      buildTableView(host, payload, cfg.id + '.csv');
    }
    return { id: cfg.id, label: cfg.label, render: render };
  }

  // ── Multi-tab page (sub-tab bar) ─────────────────────────────────────────────
  function makeMulti(cfg) {
    const cache = {};                 // key -> payload
    let active = cfg.tabs[0].key;
    async function render(target) {
      target.innerHTML = '';
      target.appendChild(UI.pageHeader({
        title: cfg.label, subtitle: cfg.subtitle || '',
        onRefresh: async () => { UI.toast('Refreshing…'); cache[active] = null; await load(); UI.toast('Refreshed'); },
      }));

      const bar = UI.el('div', { style: 'display:flex;gap:8px;margin-bottom:16px' });
      cfg.tabs.forEach(t => {
        const b = UI.el('button', {
          style: 'border:1px solid #d4d4d8;border-radius:8px;padding:7px 16px;font-size:13px;'
               + 'font-weight:600;cursor:pointer;background:#fff;color:#3f3f46',
        }, t.label);
        b.dataset.key = t.key;
        b.addEventListener('click', () => { active = t.key; paint(); load(); });
        bar.appendChild(b);
      });
      target.appendChild(bar);
      const host = UI.el('div');
      target.appendChild(host);

      function paint() {
        bar.querySelectorAll('button').forEach(b => {
          const on = b.dataset.key === active;
          b.style.background = on ? '#18181b' : '#fff';
          b.style.color = on ? '#fff' : '#3f3f46';
          b.style.borderColor = on ? '#18181b' : '#d4d4d8';
        });
      }
      async function load() {
        host.innerHTML = '';
        host.appendChild(UI.el('div', { class: 'splash' }, 'Loading…'));
        let payload;
        try { payload = cache[active] || (cache[active] = await API.ota(active)); }
        catch (e) { host.innerHTML = ''; host.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }
        buildTableView(host, payload, cfg.id + '_' + active + '.csv');
      }
      paint();
      await load();
    }
    return { id: cfg.id, label: cfg.label, render: render };
  }

  // OTAs that have a full channel-style config render there instead of here.
  const channelKeys = window.OTA_CHANNEL_KEYS || [];
  const singles = OTAS.filter(o => channelKeys.indexOf(o.key) === -1);
  window.OTA_PAGES = singles.map(makeSingle).concat(MULTI.map(makeMulti));

})();
