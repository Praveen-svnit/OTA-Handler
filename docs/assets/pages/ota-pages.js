/**
 * OTA tracker pages — generic searchable/filterable table view of one tab
 * from each OTA's sheet (server-side whitelist lives in Code.gs → OTA_SHEETS).
 *
 * Add an OTA: one line in OTA_SHEETS (Code.gs) + one entry in OTAS below.
 * These sheets are property-trackers (not the BDC hygiene layout), so they get
 * a clean table with column filter + global search + CSV, like Listing Tracker.
 */

(function () {

  // id = route hash + sidebar order; key = OTA_SHEETS key in Code.gs.
  const OTAS = [
    { id: 'agoda', label: 'Agoda', key: 'agoda' },
  ];

  function makePage(cfg) {
    const STATE = { payload: null, filterCol: null, filterVals: [], search: '' };

    async function render(target) {
      target.innerHTML = '';
      target.appendChild(UI.pageHeader({
        title: cfg.label,
        subtitle: 'Live property tracker',
        onRefresh: async () => {
          UI.toast('Refreshing…');
          try { STATE.payload = await API.ota(cfg.key, { refresh: true }); render(target); UI.toast('Refreshed'); }
          catch (e) { UI.toast('Refresh failed: ' + e.message, true); }
        },
      }));

      let payload;
      try {
        UI.updateLoader('Loading ' + cfg.label + '…');
        payload = STATE.payload || (STATE.payload = await API.ota(cfg.key));
      } catch (e) {
        target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message));
        return;
      }

      const cols = payload.cols;
      const records = UI.toRecords(payload);
      target.appendChild(UI.stats([`<b>${records.length.toLocaleString()}</b> rows`, `${cols.length} columns`]));

      // Column filter
      const fr = UI.el('div', { class: 'filters' });
      const colSelect = UI.el('select', {
        onChange: (e) => { STATE.filterCol = e.target.value || null; STATE.filterVals = []; renderValsFilter(); redraw(); },
      });
      colSelect.appendChild(UI.el('option', { value: '' }, '— pick a column —'));
      cols.forEach(c => colSelect.appendChild(UI.el('option', { value: c }, c)));
      if (STATE.filterCol) colSelect.value = STATE.filterCol;
      fr.appendChild(UI.el('div', { class: 'filter' }, [UI.el('div', { class: 'filter-label' }, 'Filter by column'), colSelect]));

      const valsHost = UI.el('div', { class: 'filter' });
      fr.appendChild(valsHost);
      function renderValsFilter() {
        valsHost.innerHTML = '';
        if (!STATE.filterCol) return;
        const vals = Array.from(new Set(records.map(r => String(r[STATE.filterCol] || '').trim()).filter(Boolean))).sort();
        valsHost.appendChild(UI.el('div', { class: 'filter-label' }, `Values of ${STATE.filterCol}`));
        valsHost.appendChild(UI.multiselect({
          label: STATE.filterCol, options: vals, selected: STATE.filterVals,
          placeholder: 'All values', onChange: (v) => { STATE.filterVals = v; redraw(); },
        }).el);
      }
      renderValsFilter();
      target.appendChild(fr);

      // Search + table
      const tb = UI.toolbar({
        placeholder: 'Search across all columns…', countText: '0 rows',
        onChange: (v) => { STATE.search = v; redraw(); },
      });
      target.appendChild(tb.el);
      tb.input.value = STATE.search || '';

      const tableHost = UI.el('div');
      target.appendChild(tableHost);

      function redraw() {
        let view = records.slice();
        if (STATE.filterCol && STATE.filterVals.length) {
          view = view.filter(r => STATE.filterVals.includes(String(r[STATE.filterCol] || '').trim()));
        }
        if (STATE.search) {
          const q = STATE.search.toLowerCase();
          view = view.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q)));
        }
        tb.el.querySelector('.count').textContent = `${view.length.toLocaleString()} rows`;
        tableHost.innerHTML = '';
        tableHost.appendChild(UI.table({ columns: cols.map(c => ({ key: c, label: c })), rows: view, height: 540 }));
        tableHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
          onClick: () => UI.downloadCsv(cfg.id + '.csv', cols, view) }, 'Download CSV'));
      }
      redraw();
    }

    return { id: cfg.id, label: cfg.label, render: render };
  }

  window.OTA_PAGES = OTAS.map(makePage);

})();
