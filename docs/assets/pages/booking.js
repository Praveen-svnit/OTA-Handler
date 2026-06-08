/**
 * Booking.com page — reused for GoMMT with a config object.
 *
 * Tabs: Summary  |  Hygiene Checks  |  Value Summaries  |  E-F-L-M Matrix
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
      { id: 'summary',  label: 'Summary',
        render: (body) => renderSummary(body, cfg, state) },
      { id: 'hygiene', label: 'Hygiene Checks',
        render: (body) => renderHygiene(body, cfg, state, cols, records) },
      { id: 'values',  label: 'Value Summaries',
        render: (body) => renderValueSummaries(body, cfg, state, cols, records) },
      { id: 'matrix',  label: matrixLabel,
        render: (body) => renderMatrix(body, cfg, state, cols, records) },
    ], target);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // TAB 1: Summary — lightweight pivot table builder
  // ──────────────────────────────────────────────────────────────────────────
  // Uses text inputs for rows/cols (instant DOM), native select for values,
  // and only one multiselect for filters (down from 3).
  async function renderSummary(body, cfg, state) {
    const p = state.payload;
    if (!p) {
      body.appendChild(UI.el('div', { class: 'splash' }, 'No data loaded.'));
      return;
    }
    const cols = p.cols;

    // ── PERF: cache records ONCE per data load (was the biggest bottleneck) ──
    // toRecords on 17k rows × 60 cols ~ 1M property writes. Doing it on every
    // render made tab switches/filters feel slow. Cache on payload itself.
    if (!p._records) p._records = UI.toRecords(p);
    const allRecords = p._records;

    // ── PERF: pre-strip column values lazily, cache per column ──
    // strip(r[c]) being called inside the pivot loops adds up to millions of
    // String/trim calls. Cache stripped arrays per column on first request.
    if (!p._strip) p._strip = {};
    function getStripped(col) {
      if (p._strip[col]) return p._strip[col];
      const arr = new Array(allRecords.length);
      for (let i = 0; i < allRecords.length; i++) {
        const v = allRecords[i][col];
        arr[i] = v == null ? '' : String(v).trim();
      }
      p._strip[col] = arr;
      return arr;
    }

    const s = state.summary = state.summary || {};
    s.rows = s.rows || '';
    s.cols = s.cols || '';
    s.val = s.val || cols[0] || '';
    s.agg = s.agg || 'count';
    s.filters = s.filters || {};
    s.filterCols = s.filterCols || [];

    // Reuse cached controls
    const cached = state._summaryCache;
    if (cached) {
      body.appendChild(cached.stats);
      body.appendChild(cached.flex);
      buildFilters();
      buildPivot();
      return;
    }

    // ── First-time build ──
    body.appendChild(UI.stats([`<b>${allRecords.length.toLocaleString()}</b> rows`, cols.length + ' columns', state.liveTab || '']));

    const flex = UI.el('div', { style: 'display:flex;gap:24px;align-items:flex-start' });
    const mainArea = UI.el('div', { style: 'flex:1;min-width:0' });
    const side = UI.el('div', { style: 'width:260px;flex-shrink:0' });
    flex.appendChild(mainArea);
    flex.appendChild(side);
    body.appendChild(flex);

    const tableHost = UI.el('div');
    const drillHost = UI.el('div');
    mainArea.appendChild(tableHost);
    mainArea.appendChild(drillHost);

    // ── Side panel ──

    // Rows
    side.appendChild(UI.el('div', { class: 'section-label' }, 'Rows'));
    const rowInput = UI.el('input', {
      type: 'text', placeholder: 'Column names, comma separated',
      style: 'width:100%;padding:4px 8px;border:1px solid #d4d4d8;border-radius:4px;font-size:12px',
    });
    rowInput.value = s.rows;
    side.appendChild(rowInput);
    const rowListId = 'rl_' + cfg.title.replace(/\W/g, '');
    side.appendChild(UI.el('datalist', { id: rowListId }));
    cols.forEach(c => side.lastChild.appendChild(UI.el('option', { value: c })));
    rowInput.setAttribute('list', rowListId);

    // Columns
    side.appendChild(UI.el('div', { class: 'section-label', style: 'margin-top:12px' }, 'Columns'));
    const colInput = UI.el('input', {
      type: 'text', placeholder: 'Column names, comma separated (leave blank for simple rows)',
      style: 'width:100%;padding:4px 8px;border:1px solid #d4d4d8;border-radius:4px;font-size:12px',
    });
    colInput.value = s.cols;
    side.appendChild(colInput);

    // Apply button
    side.appendChild(UI.el('button', {
      class: 'btn btn-sm', style: 'margin-top:8px;width:100%',
      onClick: () => { s.rows = rowInput.value; s.cols = colInput.value; state.drillIdx = null; buildPivot(); },
    }, 'Build Pivot'));

    // Values
    side.appendChild(UI.el('div', { class: 'section-label', style: 'margin-top:12px' }, 'Value'));
    const valRow = UI.el('div', { style: 'display:flex;gap:8px' });
    const valSel = UI.el('select', { style: 'flex:1' });
    cols.forEach(c => valSel.appendChild(UI.el('option', { value: c }, c)));
    valSel.value = s.val;
    valSel.onchange = () => { s.val = valSel.value; buildPivot(); };
    valRow.appendChild(valSel);
    const aggSel = UI.el('select', { style: 'width:100px' });
    ['count'].forEach(a => aggSel.appendChild(UI.el('option', { value: a }, a)));
    aggSel.value = s.agg;
    aggSel.onchange = () => { s.agg = aggSel.value; buildPivot(); };
    valRow.appendChild(aggSel);
    side.appendChild(valRow);

    // Filters
    side.appendChild(UI.el('div', { class: 'section-label', style: 'margin-top:12px' }, 'Filters'));
    const filterMS = UI.multiselect({
      label: 'Filters', options: cols, selected: s.filterCols,
      placeholder: 'Filter columns',
      onChange: (v) => { s.filterCols = v; state.drillIdx = null; buildFilters(); buildPivot(); },
    });
    side.appendChild(filterMS.el);
    const filterVals = UI.el('div');
    side.appendChild(filterVals);

    // ── Cache ──
    state._summaryCache = { stats: body.children[0], flex, tableHost, drillHost, filterVals };

    // ── Filter widgets (rebuilt when filter columns change) ──
    function buildFilters() {
      filterVals.innerHTML = '';
      s.filterCols.forEach(c => {
        // PERF: use cached stripped column instead of stripping on every call
        const stripped = getStripped(c);
        const set = new Set();
        for (let i = 0; i < stripped.length; i++) set.add(stripped[i]);
        const vals = Array.from(set).sort();
        const wrap = UI.el('div', { style: 'margin-top:6px' });
        wrap.appendChild(UI.el('div', { style: 'font-size:11px;font-weight:500;color:#52525b;margin-bottom:2px' }, c));
        const ms = UI.multiselect({
          label: c, options: vals, selected: s.filters[c] || [],
          placeholder: 'All',
          onChange: (v) => { s.filters[c] = v; state.drillIdx = null; buildPivot(); },
        });
        wrap.appendChild(ms.el);
        filterVals.appendChild(wrap);
      });
    }

    function filteredRecordIndices() {
      // PERF: return indices instead of records — avoids object allocation
      const activeFilters = s.filterCols
        .map(c => ({ col: c, sel: s.filters[c], stripped: getStripped(c) }))
        .filter(f => f.sel && f.sel.length);
      if (!activeFilters.length) {
        const idx = new Array(allRecords.length);
        for (let i = 0; i < idx.length; i++) idx[i] = i;
        return idx;
      }
      const selSets = activeFilters.map(f => new Set(f.sel));
      const out = [];
      for (let i = 0; i < allRecords.length; i++) {
        let ok = true;
        for (let k = 0; k < activeFilters.length; k++) {
          if (!selSets[k].has(activeFilters[k].stripped[i])) { ok = false; break; }
        }
        if (ok) out.push(i);
      }
      return out;
    }
    function filteredRecords() {
      const idx = filteredRecordIndices();
      const out = new Array(idx.length);
      for (let i = 0; i < idx.length; i++) out[i] = allRecords[idx[i]];
      return out;
    }

    // ── Pivot computation ──
    function buildPivot() {
      const rowsStr = (s.rows || '').trim();
      const colsStr = (s.cols || '').trim();
      const rowCols = rowsStr ? rowsStr.split(',').map(x => x.trim()).filter(x => cols.includes(x)) : [];
      const colCols = colsStr ? colsStr.split(',').map(x => x.trim()).filter(x => cols.includes(x)) : [];

      if (!rowCols.length) {
        tableHost.innerHTML = '<div class="splash">Enter valid Row column names and click Build Pivot.</div>';
        drillHost.innerHTML = '';
        return;
      }

      // PERF: work with filtered indices + cached stripped columns
      const filteredIdx = filteredRecordIndices();
      const rowStripped = rowCols.map(c => getStripped(c));
      const colStripped = colCols.map(c => getStripped(c));

      if (!colCols.length) {
        // Simple row grouping
        const grp = new Map();
        for (let i = 0; i < filteredIdx.length; i++) {
          const idx = filteredIdx[i];
          let k = rowStripped[0][idx];
          for (let j = 1; j < rowStripped.length; j++) k += '||' + rowStripped[j][idx];
          grp.set(k, (grp.get(k) || 0) + 1);
        }
        const rows = Array.from(grp.entries()).map(([k, n]) => {
          const parts = k.split('||');
          const row = { _count: n };
          rowCols.forEach((c, i) => row[c] = parts[i]);
          return row;
        });
        rows.sort((a, b) => b._count - a._count);
        const total = rows.reduce((s, r) => s + r._count, 0);
        const totalRow = { _count: total };
        rowCols.forEach((c, i) => totalRow[c] = i === rowCols.length - 1 ? 'TOTAL' : '');

        tableHost.innerHTML = '';
        tableHost.appendChild(UI.table({
          columns: rowCols.map(c => ({ key: c, label: c }))
            .concat([{ key: '_count', label: 'Count', fmt: v => v.toLocaleString(), cellClass: () => 'count-cell num' }]),
          rows, totalRow, selectedRow: state.drillIdx,
          onRowClick: (r, i) => { state.drillIdx = i; showDrill(r, filteredRecords(), rowCols); },
        }));
        if (state.drillIdx != null && rows[state.drillIdx]) showDrill(rows[state.drillIdx], filteredRecords(), rowCols);
        else drillHost.innerHTML = '';
        return;
      }

      // Cross-tab (PERF: use cached stripped columns + index loop)
      const rowGrp = new Map(), colGrp = new Map(), cellMap = new Map();
      const valCol = s.val || cols[0];
      for (let i = 0; i < filteredIdx.length; i++) {
        const idx = filteredIdx[i];
        let rk = rowStripped[0][idx];
        for (let j = 1; j < rowStripped.length; j++) rk += '||' + rowStripped[j][idx];
        let ck = colStripped[0][idx];
        for (let j = 1; j < colStripped.length; j++) ck += '||' + colStripped[j][idx];
        rowGrp.set(rk, (rowGrp.get(rk) || 0) + 1);
        colGrp.set(ck, (colGrp.get(ck) || 0) + 1);
        const cellKey = rk + '||' + ck;
        cellMap.set(cellKey, (cellMap.get(cellKey) || 0) + 1);
      }

      const rowKeys = Array.from(rowGrp.keys()).sort();
      const colKeys = Array.from(colGrp.keys()).sort();
      let displayKeys = colKeys;
      if (colKeys.length > 60) {
        const t = colKeys.map(k => ({ k, total: colGrp.get(k) || 0 }));
        t.sort((a, b) => b.total - a.total);
        displayKeys = t.slice(0, 60).map(x => x.k);
      }

      const rows = rowKeys.map(rk => {
        const parts = rk.split('||');
        const row = {};
        rowCols.forEach((c, i) => row[c] = parts[i]);
        let rt = 0;
        displayKeys.forEach(ck => {
          const v = cellMap.get(rk + '||' + ck) || 0;
          row[ck] = v; rt += v;
        });
        row._total = rt;
        return row;
      });

      const hdrs = rowCols.map(c => ({ key: c, label: c }))
        .concat(displayKeys.map(k => ({ key: k, label: k.replace(/\|\|/g, ' \u00b7 ') })))
        .concat([{ key: '_total', label: 'Total', fmt: v => v.toLocaleString(), cellClass: () => 'num' }]);
      const grandTotal = rows.reduce((s, r) => s + r._total, 0);
      const totalRow = { _total: grandTotal };
      rowCols.forEach((c, i) => totalRow[c] = i === rowCols.length - 1 ? 'TOTAL' : '');
      displayKeys.forEach(k => { totalRow[k] = rows.reduce((s, r) => s + (r[k] || 0), 0); });

      tableHost.innerHTML = '';
      tableHost.appendChild(UI.el('div', { class: 'stats' },
        rows.length + ' row groups \u00d7 ' + colKeys.length + ' column groups' +
        (colKeys.length > 60 ? ' (top 60 shown)' : '')));
      tableHost.appendChild(UI.table({
        columns: hdrs, rows, totalRow, selectedRow: state.drillIdx,
        onRowClick: (r, i) => { state.drillIdx = i; showDrillCross(r, filteredRecords(), rowCols); },
      }));
      if (state.drillIdx != null && rows[state.drillIdx]) showDrillCross(rows[state.drillIdx], filteredRecords(), rowCols);
      else drillHost.innerHTML = '';
    }

    function showDrill(picked, filtered, rowCols) {
      drillHost.innerHTML = '';
      drillHost.appendChild(UI.sectionLabel('Property View'));
      const matches = filtered.filter(r => rowCols.every(c => strip(r[c]) === picked[c]));
      const showCols = cols.slice(0, 8);
      drillHost.appendChild(UI.el('div', { class: 'stats' },
        rowCols.map(c => '<b>' + UI.escapeHtml(c) + '</b>: ' + UI.escapeHtml(picked[c])).join(' \u00b7 ') +
        ' \u2014 ' + matches.length.toLocaleString() + ' properties'));
      drillHost.appendChild(UI.table({ columns: showCols.map(c => ({ key: c, label: c })), rows: matches, height: 380 }));
      drillHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(cfg.title.toLowerCase() + '_drill.csv', showCols, matches) }, 'Download CSV'));
    }

    function showDrillCross(picked, filtered, rowCols) {
      drillHost.innerHTML = '';
      drillHost.appendChild(UI.sectionLabel('Property View'));
      const matches = filtered.filter(r => rowCols.every(c => strip(r[c]) === picked[c]));
      const showCols = cols.slice(0, 8);
      drillHost.appendChild(UI.el('div', { class: 'stats' },
        rowCols.map(c => '<b>' + UI.escapeHtml(c) + '</b>: ' + UI.escapeHtml(picked[c])).join(' \u00b7 ') +
        ' \u2014 ' + matches.length.toLocaleString() + ' properties'));
      drillHost.appendChild(UI.table({ columns: showCols.map(c => ({ key: c, label: c })), rows: matches, height: 380 }));
      drillHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(cfg.title.toLowerCase() + '_drill.csv', showCols, matches) }, 'Download CSV'));
    }

    buildFilters();
    buildPivot();
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
