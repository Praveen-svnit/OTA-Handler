/**
 * Last Checked — shared history of Mapping Checker runs.
 * Read-only viewer for the `Last Checked` and `Last Run Details` tabs in CRS.
 */

(function () {

  const STATE = { log: null, details: null, checkFilter: 'All', search: '' };

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Last Checked',
      subtitle: 'Mapping Checker run history (shared)',
      onRefresh: async () => {
        UI.toast('Refreshing…');
        try {
          STATE.log = await API.log({ refresh: true });
          STATE.details = await API.details({ refresh: true });
          render(target);
          UI.toast('Refreshed');
        } catch (e) { UI.toast('Refresh failed: ' + e.message, true); }
      },
    }));

    try {
      if (!STATE.log)     STATE.log     = await API.log();
      if (!STATE.details) STATE.details = await API.details();
    } catch (e) {
      target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message));
      return;
    }

    target.appendChild(UI.sectionLabel('Run history'));
    if (!STATE.log.rows || STATE.log.rows.length === 0) {
      target.appendChild(UI.el('div', { class: 'stats' }, 'No runs recorded yet.'));
    } else {
      const recs = UI.toRecords(STATE.log).reverse();
      target.appendChild(UI.table({
        columns: STATE.log.cols.map(c => ({ key: c, label: c })),
        rows: recs, height: 240,
      }));
    }

    target.appendChild(UI.sectionLabel('Last saved run — full details'));
    if (!STATE.details.rows || STATE.details.rows.length === 0) {
      target.appendChild(UI.el('div', { class: 'stats' }, 'No detailed results saved.'));
      return;
    }

    const records = UI.toRecords(STATE.details);

    // Check type filter
    const checks = ['All'].concat(Array.from(new Set(records.map(r => r.Check).filter(Boolean))).sort());
    const fr = UI.el('div', { class: 'filters' });
    const sel = UI.el('select', {
      onChange: (e) => { STATE.checkFilter = e.target.value; redraw(); },
    });
    checks.forEach(c => sel.appendChild(UI.el('option', { value: c }, c)));
    sel.value = STATE.checkFilter;
    fr.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Filter by check'), sel,
    ]));
    target.appendChild(fr);

    const tb = UI.toolbar({
      placeholder: 'Search Property ID, OTA, issue…',
      countText: '',
      onChange: (v) => { STATE.search = v; redraw(); },
    });
    target.appendChild(tb.el);
    tb.input.value = STATE.search || '';

    const tableHost = UI.el('div');
    target.appendChild(tableHost);

    function redraw() {
      let view = records;
      if (STATE.checkFilter && STATE.checkFilter !== 'All') {
        view = view.filter(r => r.Check === STATE.checkFilter);
      }
      if (STATE.search) {
        const q = STATE.search.toLowerCase();
        view = view.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q)));
      }
      tb.el.querySelector('.count').textContent = `${view.length.toLocaleString()} rows`;
      tableHost.innerHTML = '';
      tableHost.appendChild(UI.table({
        columns: STATE.details.cols.map(c => ({ key: c, label: c })),
        rows: view, height: 480,
      }));
      tableHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv('last_run_details.csv', STATE.details.cols, view) },
        'Download CSV'));
    }

    redraw();
  }

  window.PAGE_LAST_CHECKED = {
    id: 'last-checked',
    label: 'Last Checked',
    render: render,
  };

})();
