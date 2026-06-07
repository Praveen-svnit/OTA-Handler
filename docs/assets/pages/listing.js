/**
 * Listing Tracker — simple searchable + filterable table view of the
 * Dashboard sheet's tab gid 158406294.
 */

(function () {

  const STATE = { payload: null, filterCol: null, filterVals: [], search: '' };

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Listing Tracker',
      subtitle: 'Property listing data from the dashboard sheet',
      onRefresh: async () => {
        UI.toast('Refreshing…');
        try {
          STATE.payload = await API.listing({ refresh: true });
          render(target);
          UI.toast('Refreshed');
        } catch (e) { UI.toast('Refresh failed: ' + e.message, true); }
      },
    }));

    let payload;
    try {
      payload = STATE.payload || (STATE.payload = await API.listing());
    } catch (e) {
      target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message));
      return;
    }

    const cols = payload.cols;
    const records = UI.toRecords(payload);
    target.appendChild(UI.stats([`<b>${records.length.toLocaleString()}</b> rows`, `${cols.length} columns`]));

    // Filters row
    const fr = UI.el('div', { class: 'filters' });
    const colSelect = UI.el('select', {
      onChange: (e) => {
        STATE.filterCol = e.target.value || null;
        STATE.filterVals = [];
        redraw();
      },
    });
    colSelect.appendChild(UI.el('option', { value: '' }, '— pick a column —'));
    cols.forEach(c => colSelect.appendChild(UI.el('option', { value: c }, c)));
    if (STATE.filterCol) colSelect.value = STATE.filterCol;

    fr.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Filter by column'),
      colSelect,
    ]));

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
      placeholder: 'Search across all columns…',
      countText: '0 rows',
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
      tableHost.appendChild(UI.table({
        columns: cols.map(c => ({ key: c, label: c })),
        rows: view, height: 540,
      }));

      const dl = UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv('listing_tracker.csv', cols, view) }, 'Download CSV');
      tableHost.appendChild(dl);
    }

    redraw();
  }

  window.PAGE_LISTING = {
    id: 'listing',
    label: 'Listing Tracker',
    render: render,
  };

})();
