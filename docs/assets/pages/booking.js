/**
 * Booking.com page — reused for GoMMT with a config object.
 *
 * Tabs: Status & Tracker  |  Hygiene Checks  |  Value Summaries  |  E-F-L-M Matrix
 *
 * Channel config is passed in. Defaults match _BCOM_CFG in the Streamlit app.
 */

(function () {

  // ── Channel config (mirrors _BCOM_CFG / _GOMMT_CFG in app.py) ────────────
  const CFG = {
    bcom: {
      title: 'Booking.com',
      subtitle: 'Property status, substatus and hygiene checks',
      fetchMain: () => API.bcom(),
      fetchMainFresh: () => API.bcom({ refresh: true }),
      fetchTabs: () => API.bcomTabs(),
      fetchTab:  (name) => API.bcomTab(name),
      statusLetter: 'E',       // BDC Live
      statusLabel: 'BDC Live',
      subStatusLetter: 'F',
      fhStatusLetter: 'I',     // Churned filter
      matrixLetters: ['E', 'F', 'L', 'M'],
      defaultLiveTab: null,    // auto-detect
      defaultTrackerTab: null, // auto-detect
      hygExclude: [],
    },
    gommt: {
      title: 'GoMMT',
      subtitle: 'Property status, substatus and hygiene checks',
      fetchMain: () => API.gommt(),
      fetchMainFresh: () => API.gommt({ refresh: true }),
      fetchTabs: () => API.gommtTabs(),
      fetchTab:  (name) => API.gommtTab(name),
      statusLetter: 'O',
      statusLabel: 'MMT',
      subStatusLetter: 'P',
      fhStatusLetter: 'N',
      matrixLetters: ['O', 'P', 'Q', 'R'],
      defaultLiveTab: null,
      defaultTrackerTab: 'Main',
      hygExclude: ['FH Live Prop', 'MMT Shell Status', 'GO-MMT Sub Status', 'Set'],
    },
  };

  // ── Per-channel session state (filters, drill-down etc.) ─────────────────
  const STATE = { bcom: {}, gommt: {} };

  // ── Helpers ──────────────────────────────────────────────────────────────
  function colIdx(letter) {
    let n = 0;
    for (let i = 0; i < letter.length; i++) n = n * 26 + (letter.charCodeAt(i) - 64);
    return n - 1;
  }
  function strip(v) { return String(v == null ? '' : v).trim(); }

  // ── Render a channel page ────────────────────────────────────────────────
  async function render(target, cfgKey) {
    const cfg = CFG[cfgKey];
    const state = STATE[cfgKey];

    target.innerHTML = '';

    // Header
    target.appendChild(UI.pageHeader({
      title: cfg.title,
      subtitle: cfg.subtitle,
      onRefresh: async () => {
        UI.toast('Refreshing\u2026');
        try {
          state.payload = null;
          state.liveTab = null;
          render(target, cfgKey);
          UI.toast('Refreshed');
        } catch (e) {
          UI.toast('Refresh failed: ' + e.message, true);
        }
      },
    }));

    // Fetch Live tab data (used by all sub-tabs)
    let payload;
    try {
      payload = state.payload;
      if (!payload) {
        UI.updateLoader('Finding Live tab\u2026');
        let liveTab = state.liveTab;
        if (!liveTab) {
          if (cfg.defaultLiveTab) {
            liveTab = cfg.defaultLiveTab;
          } else {
            // Try exact "Live" first (avoids stale tabs cache)
            try {
              payload = await cfg.fetchTab('Live');
              liveTab = 'Live';
            } catch (_) {
              const tabs = await cfg.fetchTabs();
              liveTab = (tabs.tabs || []).find(t => t.toLowerCase().includes('live')) || tabs.tabs[0];
            }
          }
          state.liveTab = liveTab;
        }
        if (!payload) {
          UI.updateLoader('Loading ' + liveTab + '\u2026');
          payload = await cfg.fetchTab(liveTab);
          state.payload = payload;
        }
      }
      UI.updateLoader('Processing ' + cfg.title + ' data\u2026');
    } catch (e) {
      target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message));
      return;
    }

    const cols = payload.cols;
    const allRecords = UI.toRecords(payload);

    // Exclude blank col A + churned (col fhStatusLetter)
    const colA = cols[0];
    const fhCol = cols[colIdx(cfg.fhStatusLetter)] || null;
    let blankCnt = 0, churnCnt = 0;
    const records = allRecords.filter(r => {
      const blank = !strip(r[colA]);
      if (blank) { blankCnt++; return false; }
      if (fhCol && strip(r[fhCol]).toLowerCase() === 'churned') { churnCnt++; return false; }
      return true;
    });

    const parts = [
      `<b>${records.length.toLocaleString()}</b> active`,
      `${cols.length} columns`,
    ];
    if (blankCnt) parts.push(`${blankCnt.toLocaleString()} blank Col A excluded`);
    if (churnCnt) parts.push(`${churnCnt.toLocaleString()} churned excluded`);
    target.appendChild(UI.stats(parts));

    // Tabs
    const matrixLabel = cfg.matrixLetters.join('-') + ' Matrix';
    UI.tabsView([
      { id: 'status',  label: 'Status & Tracker',
        render: (body) => renderStatusTracker(body, cfg, state) },
      { id: 'hygiene', label: 'Hygiene Checks',
        render: (body) => renderHygiene(body, cfg, state, cols, records) },
      { id: 'values',  label: 'Value Summaries',
        render: (body) => renderValueSummaries(body, cfg, state, cols, records) },
      { id: 'matrix',  label: matrixLabel,
        render: (body) => renderMatrix(body, cfg, state, cols, records) },
    ], target);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // TAB 1: Status & Tracker — pivot table builder
  // ──────────────────────────────────────────────────────────────────────────
  async function renderStatusTracker(body, cfg, state) {
    const p = state.payload;
    if (!p) {
      body.appendChild(UI.el('div', { class: 'splash' }, 'No data loaded.'));
      return;
    }
    const cols = p.cols;
    const records = UI.toRecords(p);
    body.appendChild(UI.stats([`<b>${records.length.toLocaleString()}</b> rows`, cols.length + ' columns', state.liveTab || '']));

    state.pivotRows = state.pivotRows || [];
    state.pivotCols = state.pivotCols || [];
    state.pivotVal = state.pivotVal || { col: cols[0] || '', agg: 'count' };
    state.pivotFilters = state.pivotFilters || {};
    state.pivotFilterCols = state.pivotFilterCols || [];

    // Layout: left panel + main area
    const layout = UI.el('div', { style: 'display:flex;gap:24px;align-items:flex-start' });
    const side = UI.el('div', { style: 'width:260px;flex-shrink:0' });
    const main = UI.el('div', { style: 'flex:1;min-width:0' });
    layout.appendChild(side);
    layout.appendChild(main);
    body.appendChild(layout);

    // ── Side panel ──
    side.appendChild(UI.el('div', { class: 'section-label' }, 'Rows'));
    const rowMS = UI.multiselect({
      label: 'Rows', options: cols, selected: state.pivotRows,
      placeholder: 'Row columns', onChange: (v) => { state.pivotRows = v; state.drillIdx = null; refresh(); },
    });
    side.appendChild(rowMS.el);

    side.appendChild(UI.el('div', { class: 'section-label', style: 'margin-top:12px' }, 'Columns'));
    const colMS = UI.multiselect({
      label: 'Cols', options: cols, selected: state.pivotCols,
      placeholder: 'Column columns', onChange: (v) => { state.pivotCols = v; state.drillIdx = null; refresh(); },
    });
    side.appendChild(colMS.el);

    side.appendChild(UI.el('div', { class: 'section-label', style: 'margin-top:12px' }, 'Values'));
    const valRow = UI.el('div', { style: 'display:flex;gap:8px' });
    const valSel = UI.el('select', {
      style: 'flex:1', onChange: () => { state.pivotVal.col = valSel.value; refresh(); },
    });
    cols.forEach(c => valSel.appendChild(UI.el('option', { value: c }, c)));
    valSel.value = state.pivotVal.col || cols[0] || '';
    valRow.appendChild(valSel);

    const aggSel = UI.el('select', {
      style: 'width:100px', onChange: () => { state.pivotVal.agg = aggSel.value; refresh(); },
    });
    ['count', 'count unique'].forEach(a => aggSel.appendChild(UI.el('option', { value: a }, a)));
    aggSel.value = state.pivotVal.agg || 'count';
    valRow.appendChild(aggSel);
    side.appendChild(valRow);

    side.appendChild(UI.el('div', { class: 'section-label', style: 'margin-top:12px' }, 'Filters'));
    const filterMS = UI.multiselect({
      label: 'Filters', options: cols, selected: state.pivotFilterCols,
      placeholder: 'Filter columns', onChange: (v) => { state.pivotFilterCols = v; state.drillIdx = null; refresh(); },
    });
    side.appendChild(filterMS.el);

    const filterVals = UI.el('div');
    side.appendChild(filterVals);

    // ── Main area ──
    const tableHost = UI.el('div');
    const drillHost = UI.el('div');
    main.appendChild(tableHost);
    main.appendChild(drillHost);

    function currentRecords() {
      let v = records;
      state.pivotFilterCols.forEach(c => {
        const sel = state.pivotFilters[c];
        if (sel && sel.length) v = v.filter(r => sel.includes(strip(r[c])));
      });
      return v;
    }

    function renderFilterWidgets() {
      filterVals.innerHTML = '';
      state.pivotFilterCols.forEach(c => {
        const vals = Array.from(new Set(records.map(r => strip(r[c])))).sort();
        const wrap = UI.el('div', { style: 'margin-top:6px' });
        wrap.appendChild(UI.el('div', { style: 'font-size:11px;font-weight:500;color:#52525b;margin-bottom:2px' }, c));
        wrap.appendChild(UI.multiselect({
          label: c, options: vals, selected: state.pivotFilters[c] || [],
          placeholder: 'All', onChange: (v) => { state.pivotFilters[c] = v; state.drillIdx = null; refresh(); },
        }).el);
        filterVals.appendChild(wrap);
      });
    }

    function refresh() {
      renderFilterWidgets();
      const filtered = currentRecords();
      const rowCols = state.pivotRows;
      const colCols = state.pivotCols;

      if (!rowCols.length && !colCols.length) {
        tableHost.innerHTML = '<div class="splash">Select Rows and/or Columns to build the pivot.</div>';
        drillHost.innerHTML = '';
        return;
      }

      if (!colCols.length) {
        // Simple row grouping (no cross-tab)
        const grp = new Map();
        filtered.forEach(r => {
          const k = rowCols.map(c => strip(r[c])).join('||');
          grp.set(k, (grp.get(k) || 0) + 1);
        });
        let view = Array.from(grp.entries()).map(([k, n]) => {
          const parts = k.split('||');
          const row = { _count: n };
          rowCols.forEach((c, i) => row[c] = parts[i]);
          return row;
        });
        view.sort((a, b) => b._count - a._count);

        const totalRow = { _count: view.reduce((s, r) => s + r._count, 0) };
        rowCols.forEach((c, i) => totalRow[c] = i === rowCols.length - 1 ? 'TOTAL' : '');

        const columns = rowCols.map(c => ({ key: c, label: c }))
          .concat([{ key: '_count', label: 'Count', fmt: v => v.toLocaleString(), cellClass: () => 'count-cell num' }]);

        tableHost.innerHTML = '';
        tableHost.appendChild(UI.table({
          columns, rows: view, totalRow, selectedRow: state.drillIdx,
          onRowClick: (row, i) => { state.drillIdx = i; renderDrillSimple(row, filtered, rowCols); },
        }));
        if (state.drillIdx != null && view[state.drillIdx]) renderDrillSimple(view[state.drillIdx], filtered, rowCols);
        else drillHost.innerHTML = '';
        return;
      }

      // Cross-tab: rows × cols
      const rowGrp = new Map();
      const colGrp = new Map();
      const cellMap = new Map();

      const valCol = state.pivotVal.col || cols[0];
      const isUnique = state.pivotVal.agg === 'count unique';

      filtered.forEach(r => {
        const rk = rowCols.map(c => strip(r[c])).join('||');
        const ck = colCols.map(c => strip(r[c])).join('||');
        rowGrp.set(rk, (rowGrp.get(rk) || 0) + 1);
        colGrp.set(ck, (colGrp.get(ck) || 0) + 1);
        const cellKey = rk + '||' + ck;
        if (isUnique) {
          if (!cellMap.has(cellKey)) cellMap.set(cellKey, new Set());
          cellMap.get(cellKey).add(strip(r[valCol]));
        } else {
          cellMap.set(cellKey, (cellMap.get(cellKey) || 0) + 1);
        }
      });

      // Build row entries
      const rowEntries = Array.from(rowGrp.keys()).sort();
      const colEntries = Array.from(colGrp.keys()).sort();
      const totalByRow = new Map();

      const rows = rowEntries.map(rk => {
        const parts = rk.split('||');
        const row = {};
        rowCols.forEach((c, i) => row[c] = parts[i]);
        colEntries.forEach(ck => {
          const cellKey = rk + '||' + ck;
          const val = cellMap.get(cellKey);
          row[ck] = isUnique ? (val ? val.size : 0) : (val || 0);
        });
        const rowTotal = colEntries.reduce((s, ck) => s + (row[ck] || 0), 0);
        row._total = rowTotal;
        totalByRow.set(rk, rowTotal);
        return row;
      });

      // Column headers
      const colHeaders = colEntries.map(ck => {
        const parts = ck.split('||');
        return { key: ck, label: parts.join(' · ') };
      });

      // Build table columns
      const tableColumns = rowCols.map(c => ({ key: c, label: c }))
        .concat(colHeaders)
        .concat([{ key: '_total', label: 'Total', fmt: v => v.toLocaleString(), cellClass: () => 'num' }]);

      // Row total
      const grandTotal = rows.reduce((s, r) => s + r._total, 0);
      const totalRow = { _total: grandTotal };
      rowCols.forEach((c, i) => totalRow[c] = i === rowCols.length - 1 ? 'TOTAL' : '');
      colEntries.forEach(ck => { totalRow[ck] = Array.from(totalByRow.values()).reduce((s, v) => s + v, 0); });
      totalRow._total = grandTotal;

      // Filter out empty columns if too many
      let displayCols = colEntries;
      if (colEntries.length > 50) {
        // Only show top 50 by total
        const totals = colEntries.map(ck => ({ ck, total: rows.reduce((s, r) => s + (r[ck] || 0), 0) }));
        totals.sort((a, b) => b.total - a.total);
        const topKeys = new Set(totals.slice(0, 50).map(t => t.ck));
        displayCols = colEntries.filter(ck => topKeys.has(ck));
      }

      const finalColHeaders = rowCols.map(c => ({ key: c, label: c }))
        .concat(displayCols.map(ck => ({ key: ck, label: ck.replace(/\|/g, ' · ') })))
        .concat([{ key: '_total', label: 'Total', fmt: v => v.toLocaleString(), cellClass: () => 'num' }]);

      tableHost.innerHTML = '';
      tableHost.appendChild(UI.el('div', { class: 'stats' },
        `${rows.length} row groups × ${colEntries.length} column groups` +
        (colEntries.length > 50 ? ` (showing top 50 columns)` : ``)));
      tableHost.appendChild(UI.table({
        columns: finalColHeaders, rows, totalRow, selectedRow: state.drillIdx,
        onRowClick: (row, i) => { state.drillIdx = i; renderDrill(row, filtered, rowCols, colCols); },
      }));
      tableHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => {
          const fn = cfg.title.toLowerCase() + '_pivot.csv';
          UI.downloadCsv(fn, finalColHeaders.map(c => c.key), rows);
        },
      }, 'Download CSV'));

      if (state.drillIdx != null && rows[state.drillIdx]) renderDrill(rows[state.drillIdx], filtered, rowCols, colCols);
      else drillHost.innerHTML = '';
    }

    function renderDrill(picked, filtered, rowCols, colCols) {
      drillHost.innerHTML = '';
      drillHost.appendChild(UI.sectionLabel('Property View'));
      const matches = filtered.filter(r =>
        rowCols.every(c => strip(r[c]) === picked[c]) &&
        colCols.every(c => strip(r[c]) === state.activeColVal || true)
      );
      const showCols = cols.slice(0, 8);
      drillHost.appendChild(UI.el('div', { class: 'stats' },
        rowCols.map(c => `<b>${UI.escapeHtml(c)}</b>: ${UI.escapeHtml(picked[c])}`).join(' · ') +
        ` — ${matches.length.toLocaleString()} properties`));
      drillHost.appendChild(UI.table({
        columns: showCols.map(c => ({ key: c, label: c })),
        rows: matches, height: 380,
      }));
    }

    function renderDrillSimple(picked, filtered, rowCols) {
      drillHost.innerHTML = '';
      drillHost.appendChild(UI.sectionLabel('Property View'));
      const matches = filtered.filter(r =>
        rowCols.every(c => strip(r[c]) === picked[c])
      );
      const showCols = cols.slice(0, 8);
      drillHost.appendChild(UI.el('div', { class: 'stats' },
        rowCols.map(c => `<b>${UI.escapeHtml(c)}</b>: ${UI.escapeHtml(picked[c])}`).join(' · ') +
        ` — ${matches.length.toLocaleString()} properties`));
      drillHost.appendChild(UI.table({
        columns: showCols.map(c => ({ key: c, label: c })),
        rows: matches, height: 380,
      }));
      drillHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(cfg.title.toLowerCase() + '_drill.csv', showCols, matches),
      }, 'Download CSV'));
    }

    refresh();
  }

  // ──────────────────────────────────────────────────────────────────────────
  // TAB 2: Hygiene Checks (cols N–AH, filtered to subStatus=Live)
  // ──────────────────────────────────────────────────────────────────────────
  function hygCols(cols, cfg, state) {
    const start = colIdx('N'), end = colIdx('AH') + 1;
    let base = cols.slice(start, end);
    const excl = new Set((cfg.hygExclude || []).map(s => s.trim().toLowerCase()));
    base = base.filter(c => !excl.has(c.trim().toLowerCase()));
    const added = state.hygAdd || [];
    const removed = new Set(state.hygRemove || []);
    let final = base.filter(c => !removed.has(c));
    added.forEach(c => { if (!final.includes(c)) final.push(c); });
    return { base, final };
  }

  function liveRecords(records, cols, cfg) {
    const subCol = cols[colIdx(cfg.subStatusLetter)];
    if (!subCol) return records;
    return records.filter(r => strip(r[subCol]).toLowerCase() === 'live');
  }

  function renderHygiene(body, cfg, state, cols, records) {
    const live = liveRecords(records, cols, cfg);
    const { base, final } = hygCols(cols, cfg, state);

    // Customize columns expander
    const det = UI.el('details', { class: 'expander' });
    det.appendChild(UI.el('summary', null, 'Customize hygiene check columns'));
    const detBody = UI.el('div');
    det.appendChild(detBody);
    body.appendChild(det);

    const addable = cols.filter(c => !base.includes(c));
    const fr = UI.el('div', { class: 'filters' });
    fr.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, '+ Add columns'),
      UI.multiselect({
        label: 'Add', options: addable, selected: state.hygAdd || [],
        placeholder: 'Pick columns outside N–AH', onChange: (v) => { state.hygAdd = v; renderHygiene(body, cfg, state, cols, records); },
      }).el,
    ]));
    fr.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, '− Remove default columns'),
      UI.multiselect({
        label: 'Remove', options: base, selected: state.hygRemove || [],
        placeholder: 'Pick columns to hide', onChange: (v) => { state.hygRemove = v; renderHygiene(body, cfg, state, cols, records); },
      }).el,
    ]));
    detBody.appendChild(fr);

    body.appendChild(UI.stats([`Filtered to Sub Status = Live · <b>${live.length.toLocaleString()}</b> properties`]));

    // Summary table
    const total = live.length;
    const summaryRows = final.map(c => {
      const stripped = live.map(r => strip(r[c]));
      const filled = stripped.filter(v => v !== '').length;
      const missing = total - filled;
      const pct = total ? Math.round((filled / total) * 1000) / 10 : 0;
      // Top 3 values
      const vc = new Map();
      stripped.forEach(v => { if (v) vc.set(v, (vc.get(v) || 0) + 1); });
      const top = Array.from(vc.entries()).sort((a, b) => b[1] - a[1]).slice(0, 3)
        .map(([v, n]) => `${UI.escapeHtml(v)} (${n})`).join(' · ');
      return { Check: c, Filled: filled, Missing: missing, 'Completion %': pct, 'Top Values': top };
    });

    const avg = summaryRows.length ? (summaryRows.reduce((s, r) => s + r['Completion %'], 0) / summaryRows.length).toFixed(1) : '0';
    const gaps = summaryRows.filter(r => r['Completion %'] < 100).length;
    body.appendChild(UI.metricRow([
      { label: 'Hygiene Columns', value: final.length },
      { label: 'Avg Completion',  value: avg + '%' },
      { label: 'Columns with Gaps', value: gaps },
    ]));

    body.appendChild(UI.table({
      columns: [
        { key: 'Check', label: 'Check' },
        { key: 'Filled', label: '✓ Filled', fmt: v => v.toLocaleString(), cellClass: () => 'num' },
        { key: 'Missing', label: '✗ Missing', fmt: v => v.toLocaleString(), cellClass: () => 'num' },
        { key: 'Completion %', label: 'Completion %',
          fmt: v => v + '%',
          cellClass: (v) => v === 100 ? 'pct-100' : (v >= 80 ? 'pct-80' : 'pct-low') },
        { key: 'Top Values', label: 'Top Values' },
      ],
      rows: summaryRows, height: 560,
    }));
  }

  // ──────────────────────────────────────────────────────────────────────────
  // TAB 3: Value Summaries (per hygiene column, clickable drill-down)
  // ──────────────────────────────────────────────────────────────────────────
  function renderValueSummaries(body, cfg, state, cols, records) {
    const live = liveRecords(records, cols, cfg);
    const { final } = hygCols(cols, cfg, state);

    body.appendChild(UI.stats([`Filtered to Sub Status = Live · <b>${live.length.toLocaleString()}</b> properties`]));
    body.appendChild(UI.sectionLabel('Expand any column to see its value distribution'));

    state.valueSel = state.valueSel || {};

    final.forEach(hc => {
      const stripped = live.map(r => strip(r[hc]));
      const filled = stripped.filter(v => v).length;
      const total = stripped.length;
      const pct = total ? Math.round((filled / total) * 1000) / 10 : 0;
      const dot = pct === 100 ? '🟢' : (pct >= 80 ? '🟡' : '🔴');

      const det = UI.el('details', { class: 'expander' });
      det.appendChild(UI.el('summary', null, `${dot} ${hc}  (${pct}% filled · ${filled.toLocaleString()}/${total.toLocaleString()})`));
      const dbody = UI.el('div');
      det.appendChild(dbody);
      body.appendChild(det);

      det.addEventListener('toggle', () => {
        if (!det.open) return;
        if (dbody.dataset.rendered) return;
        dbody.dataset.rendered = '1';
        renderValueColumn(dbody, hc, live, cols);
      });
    });
  }

  function renderValueColumn(host, hc, live, cols) {
    const isLink = hc.toLowerCase().includes('link') || hc.toLowerCase().includes('url');

    if (isLink) {
      // Binary: With link / Without link
      const withLink = live.filter(r => strip(r[hc]));
      const withoutLink = live.filter(r => !strip(r[hc]));
      const rows = [
        { Status: '✓ With Link', Count: withLink.length },
        { Status: '✗ Without Link', Count: withoutLink.length },
      ];
      const tableHost = UI.el('div');
      const drillHost = UI.el('div');
      let sel = null;

      tableHost.appendChild(UI.table({
        columns: [{ key: 'Status', label: 'Status' }, { key: 'Count', label: 'Count', fmt: v => v.toLocaleString(), cellClass: () => 'num' }],
        rows,
        onRowClick: (r, i) => { sel = i; renderProps(); },
      }));
      function renderProps() {
        drillHost.innerHTML = '';
        const matches = sel === 0 ? withLink : withoutLink;
        const propIdCol = cols[0];
        const channelIdCol = cols[3];
        const nameCol = cols.find(c => c.toLowerCase().includes('name'));
        const showCols = Array.from(new Set([propIdCol, channelIdCol, nameCol, hc].filter(Boolean)));
        drillHost.appendChild(UI.el('div', { class: 'stats' }, `${matches.length.toLocaleString()} properties`));
        drillHost.appendChild(UI.table({
          columns: showCols.map(c => ({
            key: c, label: c,
            fmt: (c === hc && sel === 0) ? (v) => v ? `<a href="${UI.escapeHtml(v)}" target="_blank" rel="noopener">Open ↗</a>` : '' : null,
          })),
          rows: matches, height: 380,
        }));
        drillHost.appendChild(UI.el('button', {
          class: 'btn btn-sm', style: 'margin-top:8px',
          onClick: () => UI.downloadCsv(`${hc.replace(/\W/g,'_')}.csv`, showCols, matches),
        }, 'Download CSV'));
      }
      host.appendChild(tableHost);
      host.appendChild(drillHost);
      return;
    }

    // Default: value counts
    const vc = new Map();
    live.forEach(r => {
      const v = strip(r[hc]) || '(blank)';
      vc.set(v, (vc.get(v) || 0) + 1);
    });
    const rows = Array.from(vc.entries()).map(([Value, Count]) => ({ Value, Count }))
      .sort((a, b) => b.Count - a.Count);

    const tableHost = UI.el('div');
    const drillHost = UI.el('div');
    let sel = null;

    tableHost.appendChild(UI.table({
      columns: [{ key: 'Value', label: 'Value' }, { key: 'Count', label: 'Count', fmt: v => v.toLocaleString(), cellClass: () => 'num' }],
      rows,
      onRowClick: (r, i) => { sel = r.Value; renderProps(); },
    }));
    function renderProps() {
      drillHost.innerHTML = '';
      const matches = live.filter(r => {
        const v = strip(r[hc]) || '(blank)';
        return v === sel;
      });
      const propIdCol = cols[0];
      const channelIdCol = cols[3];
      const nameCol = cols.find(c => c.toLowerCase().includes('name'));
      const showCols = Array.from(new Set([propIdCol, channelIdCol, nameCol, hc].filter(Boolean)));
      drillHost.appendChild(UI.el('div', { class: 'stats' }, `<b>${UI.escapeHtml(sel)}</b> — ${matches.length.toLocaleString()} properties`));
      drillHost.appendChild(UI.table({
        columns: showCols.map(c => ({ key: c, label: c })),
        rows: matches, height: 380,
      }));
      drillHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(`${hc.replace(/\W/g,'_')}_${String(sel).slice(0,15).replace(/\W/g,'_')}.csv`, showCols, matches),
      }, 'Download CSV'));
    }
    host.appendChild(tableHost);
    host.appendChild(drillHost);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // TAB 4: E-F-L-M Matrix
  // ──────────────────────────────────────────────────────────────────────────
  function renderMatrix(body, cfg, state, cols, records) {
    const letters = cfg.matrixLetters;
    const mxCols = letters.map(L => cols[colIdx(L)] || null);
    if (mxCols.some(c => !c)) {
      body.appendChild(UI.el('div', { class: 'splash' }, `Columns ${letters.join(', ')} not all present.`));
      return;
    }

    const grp = new Map();
    records.forEach(r => {
      const k = mxCols.map(c => strip(r[c])).join('||');
      grp.set(k, (grp.get(k) || 0) + 1);
    });
    let matrix = Array.from(grp.entries()).map(([k, n]) => {
      const parts = k.split('||');
      const row = { Count: n };
      mxCols.forEach((c, i) => row[c] = parts[i]);
      return row;
    });
    matrix.sort((a, b) => b.Count - a.Count);

    body.appendChild(UI.stats([`Grouped by <b>${mxCols.join('</b> · <b>')}</b> · ${records.length.toLocaleString()} properties`]));

    // Per-column filters
    state.mxFilters = state.mxFilters || {};
    state.mxHideZero = state.mxHideZero !== false;

    body.appendChild(UI.sectionLabel('Filters'));
    const fr = UI.el('div', { class: 'filters' });
    mxCols.forEach(c => {
      const vals = Array.from(new Set(matrix.map(r => r[c]))).sort();
      fr.appendChild(UI.el('div', { class: 'filter' }, [
        UI.el('div', { class: 'filter-label' }, c),
        UI.multiselect({
          label: c, options: vals, selected: state.mxFilters[c] || [],
          placeholder: 'All', onChange: (v) => { state.mxFilters[c] = v; redraw(); },
        }).el,
      ]));
    });
    const hideToggle = UI.el('label', { class: 'toggle' }, [
      UI.el('input', { type: 'checkbox', onChange: (e) => { state.mxHideZero = e.target.checked; redraw(); } }),
      ' Hide zero',
    ]);
    hideToggle.querySelector('input').checked = state.mxHideZero;
    fr.appendChild(hideToggle);
    body.appendChild(fr);

    const tableHost = UI.el('div');
    const drillHost = UI.el('div');
    body.appendChild(tableHost);
    body.appendChild(drillHost);

    function redraw() {
      tableHost.innerHTML = '';
      drillHost.innerHTML = '';
      let view = matrix.slice();
      mxCols.forEach(c => {
        const sel = state.mxFilters[c];
        if (sel && sel.length) view = view.filter(r => sel.includes(r[c]));
      });
      if (state.mxHideZero) view = view.filter(r => r.Count > 0);

      const totalRow = { Count: view.reduce((s, r) => s + r.Count, 0) };
      mxCols.forEach((c, i) => totalRow[c] = i === mxCols.length - 1 ? 'TOTAL' : '');

      const columns = mxCols.map(c => ({ key: c, label: c }))
        .concat([{ key: 'Count', label: 'Count', fmt: v => v.toLocaleString(), cellClass: () => 'count-cell num' }]);

      tableHost.appendChild(UI.table({
        columns, rows: view, totalRow, selectedRow: state.mxDrillIdx,
        onRowClick: (row, i) => { state.mxDrillIdx = i; renderMxDrill(view[i]); },
      }));

      tableHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(`${cfg.title.toLowerCase()}_matrix.csv`,
          mxCols.concat(['Count']), view),
      }, 'Download full matrix'));

      if (state.mxDrillIdx != null && view[state.mxDrillIdx]) renderMxDrill(view[state.mxDrillIdx]);
    }

    function renderMxDrill(picked) {
      drillHost.innerHTML = '';
      drillHost.appendChild(UI.sectionLabel('Property View'));
      const matches = records.filter(r => mxCols.every(c => strip(r[c]) === picked[c]));
      const propIdCol = cols[0];
      const channelIdCol = cols[3];
      const nameCol = cols.find(c => c.toLowerCase().includes('name'));
      const showCols = Array.from(new Set([propIdCol, channelIdCol, nameCol, ...mxCols].filter(Boolean)));
      drillHost.appendChild(UI.el('div', { class: 'stats' },
        mxCols.map(c => `<b>${c}</b>: ${UI.escapeHtml(picked[c])}`).join(' · ') + ` — ${matches.length.toLocaleString()} properties`));
      drillHost.appendChild(UI.table({
        columns: showCols.map(c => ({ key: c, label: c })),
        rows: matches, height: 420,
      }));
      drillHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(`${cfg.title.toLowerCase()}_matrix_drill.csv`, showCols, matches),
      }, 'Download CSV'));
    }

    redraw();
  }

  // ── Register both pages with the router ────────────────────────────────
  window.PAGE_BOOKING = {
    id: 'booking',
    label: 'Booking.com',
    render: (target) => render(target, 'bcom'),
  };
  window.PAGE_GOMMT = {
    id: 'gommt',
    label: 'GoMMT',
    render: (target) => render(target, 'gommt'),
  };

})();
