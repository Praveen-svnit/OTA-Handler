/**
 * Generic OTA "channel" page — same look/behaviour as Booking.com / GoMMT / GMB
 * but config-driven by COLUMN HEADERS (OTA tracker sheets lack the fixed N-AH
 * layout). Tabs: Matrix · Hygiene Checks · Value Summaries.
 *
 * Per-OTA config (ota-channel-config.js):
 *   { id, label, key, fhStatusCol, liveCol, liveValue, matrixCols:[...], checkCols:[...] }
 */

(function () {

  const STATE = {};
  const strip = v => String(v == null ? '' : v).trim();

  function liveRecords(cfg, records) {
    if (!cfg.liveCol) return records;
    const lv = String(cfg.liveValue || 'Live').toLowerCase();
    return records.filter(r => strip(r[cfg.liveCol]).toLowerCase() === lv);
  }

  // ── Matrix (ported from the Booking page: Rows/Cols/Filters + drill) ─────────
  function renderMatrix(body, cfg, state, cols, records) {
    const defaultMx = (cfg.matrixCols || []).filter(c => cols.includes(c));
    const half = Math.ceil(defaultMx.length / 2);
    const LS_KEY = 'mx_defaults_ota_' + cfg.id.toLowerCase().replace(/\W/g, '_');

    function loadDefaults() {
      try {
        const raw = localStorage.getItem(LS_KEY);
        if (!raw) return null;
        const saved = JSON.parse(raw);
        const pos = saved._positions || {};
        const resolve = (name) => {
          if (cols.includes(name)) return name;
          const idx = pos[name];
          if (idx != null && idx >= 0 && idx < cols.length) return cols[idx];
          return null;
        };
        const resolveList = (arr) => (arr || []).map(resolve).filter(Boolean);
        const filters = {};
        Object.keys(saved.filters || {}).forEach(k => {
          const live = resolve(k);
          if (live && Array.isArray(saved.filters[k])) filters[live] = saved.filters[k];
        });
        return {
          rowCols: resolveList(saved.rowCols), colCols: resolveList(saved.colCols),
          filterCols: resolveList(saved.filterCols), filters,
          hideZero: saved.hideZero !== false, drillIdx: null,
        };
      } catch (_) { return null; }
    }
    function saveDefaults() {
      const positions = {};
      const collect = (c) => { positions[c] = cols.indexOf(c); };
      mx.rowCols.forEach(collect); mx.colCols.forEach(collect); mx.filterCols.forEach(collect);
      Object.keys(mx.filters).forEach(collect);
      localStorage.setItem(LS_KEY, JSON.stringify({
        rowCols: mx.rowCols, colCols: mx.colCols, filterCols: mx.filterCols,
        filters: mx.filters, hideZero: mx.hideZero, _positions: positions,
      }));
      UI.toast('Defaults saved for ' + cfg.label);
    }
    function clearDefaults() {
      localStorage.removeItem(LS_KEY);
      delete state.mx;
      UI.toast('Defaults cleared');
      body.innerHTML = '';
      renderMatrix(body, cfg, state, cols, records);
    }

    state.mx = state.mx || loadDefaults() || {
      rowCols: defaultMx.slice(0, half), colCols: defaultMx.slice(half),
      filterCols: [], filters: {}, hideZero: true, drillIdx: null,
    };
    const mx = state.mx;

    const p = state.payload;
    p._strip = p._strip || {};
    function getStripped(col) {
      if (p._strip[col]) return p._strip[col];
      const arr = new Array(records.length);
      for (let i = 0; i < records.length; i++) { const v = records[i][col]; arr[i] = v == null ? '' : String(v).trim(); }
      p._strip[col] = arr;
      return arr;
    }

    body.appendChild(UI.stats([`<b>${records.length.toLocaleString()}</b> properties available`]));

    const cfgPanel = UI.el('div', { class: 'filters', style: 'align-items:flex-start' });
    cfgPanel.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Rows'),
      UI.multiselect({ label: 'Rows', options: cols, selected: mx.rowCols, placeholder: 'Pick row columns',
        onChange: (v) => { mx.rowCols = v; mx.drillIdx = null; redraw(); } }).el,
    ]));
    cfgPanel.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Columns'),
      UI.multiselect({ label: 'Columns', options: cols, selected: mx.colCols, placeholder: 'Pick column columns (optional)',
        onChange: (v) => { mx.colCols = v; mx.drillIdx = null; redraw(); } }).el,
    ]));
    cfgPanel.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Add Filters'),
      UI.multiselect({ label: 'Filters', options: cols, selected: mx.filterCols, placeholder: 'Pick filter columns',
        onChange: (v) => { mx.filterCols = v; mx.drillIdx = null; buildFilterControls(); redraw(); } }).el,
    ]));
    body.appendChild(cfgPanel);

    const filterHost = UI.el('div', { class: 'filters' });
    body.appendChild(filterHost);

    const toggleRow = UI.el('div', { style: 'display:flex;align-items:center;gap:14px;margin:6px 0 10px' });
    const hideToggle = UI.el('label', { class: 'toggle' }, [
      UI.el('input', { type: 'checkbox', onChange: (e) => { mx.hideZero = e.target.checked; redraw(); } }),
      ' Hide zero counts',
    ]);
    hideToggle.querySelector('input').checked = mx.hideZero;
    toggleRow.appendChild(hideToggle);
    toggleRow.appendChild(UI.el('button', { class: 'btn btn-sm', onClick: saveDefaults }, 'Save as default'));
    if (localStorage.getItem(LS_KEY)) toggleRow.appendChild(UI.el('button', { class: 'btn btn-sm', onClick: clearDefaults }, 'Clear default'));
    body.appendChild(toggleRow);

    const tableHost = UI.el('div');
    const drillHost = UI.el('div');
    body.appendChild(tableHost);
    body.appendChild(drillHost);

    function buildFilterControls() {
      filterHost.innerHTML = '';
      mx.filterCols.forEach(c => {
        const vals = Array.from(new Set(getStripped(c))).sort();
        filterHost.appendChild(UI.el('div', { class: 'filter' }, [
          UI.el('div', { class: 'filter-label' }, c),
          UI.multiselect({ label: c, options: vals, selected: mx.filters[c] || [], placeholder: 'All',
            onChange: (v) => { mx.filters[c] = v; mx.drillIdx = null; redraw(); } }).el,
        ]));
      });
    }
    function filteredIdx() {
      const active = mx.filterCols.map(c => ({ col: c, sel: mx.filters[c], stripped: getStripped(c) })).filter(f => f.sel && f.sel.length);
      if (!active.length) { const idx = new Array(records.length); for (let i = 0; i < idx.length; i++) idx[i] = i; return idx; }
      const selSets = active.map(f => new Set(f.sel));
      const out = [];
      for (let i = 0; i < records.length; i++) {
        let ok = true;
        for (let k = 0; k < active.length; k++) if (!selSets[k].has(active[k].stripped[i])) { ok = false; break; }
        if (ok) out.push(i);
      }
      return out;
    }

    function redraw() {
      tableHost.innerHTML = '';
      drillHost.innerHTML = '';
      const rowCols = (mx.rowCols || []).filter(c => cols.includes(c));
      const colCols = (mx.colCols || []).filter(c => cols.includes(c));
      if (!rowCols.length) { tableHost.appendChild(UI.el('div', { class: 'splash' }, 'Pick at least one Row column to build the matrix.')); return; }

      const fIdx = filteredIdx();
      const rowStripped = rowCols.map(c => getStripped(c));
      const colStripped = colCols.map(c => getStripped(c));

      if (!colCols.length) {
        const grp = new Map();
        for (let i = 0; i < fIdx.length; i++) {
          const idx = fIdx[i];
          let k = rowStripped[0][idx];
          for (let j = 1; j < rowStripped.length; j++) k += '||' + rowStripped[j][idx];
          grp.set(k, (grp.get(k) || 0) + 1);
        }
        let rows = Array.from(grp.entries()).map(([k, n]) => {
          const parts = k.split('||'); const row = { Count: n };
          rowCols.forEach((c, i) => row[c] = parts[i]); return row;
        });
        rows.sort((a, b) => b.Count - a.Count);
        if (mx.hideZero) rows = rows.filter(r => r.Count > 0);
        const totalRow = { Count: rows.reduce((s, r) => s + r.Count, 0) };
        rowCols.forEach((c, i) => totalRow[c] = i === rowCols.length - 1 ? 'TOTAL' : '');
        const columns = rowCols.map(c => ({ key: c, label: c }))
          .concat([{ key: 'Count', label: 'Count', fmt: v => v.toLocaleString(), cellClass: () => 'count-cell num' }]);
        tableHost.appendChild(UI.table({ columns, rows, totalRow, selectedRow: mx.drillIdx,
          onRowClick: (row, i) => { mx.drillIdx = i; renderDrill(row, rowCols); } }));
        tableHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
          onClick: () => UI.downloadCsv(cfg.id + '_matrix.csv', rowCols.concat(['Count']), rows) }, 'Download matrix'));
        if (mx.drillIdx != null && rows[mx.drillIdx]) renderDrill(rows[mx.drillIdx], rowCols);
        return;
      }

      const rowGrp = new Map(), colGrp = new Map(), cellMap = new Map();
      for (let i = 0; i < fIdx.length; i++) {
        const idx = fIdx[i];
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
      const CROSS_LIMIT = 60;
      if (colKeys.length > CROSS_LIMIT) {
        const t = colKeys.map(k => ({ k, total: colGrp.get(k) || 0 }));
        t.sort((a, b) => b.total - a.total);
        displayKeys = t.slice(0, CROSS_LIMIT).map(x => x.k);
      }
      let rows = rowKeys.map(rk => {
        const parts = rk.split('||'); const row = {};
        rowCols.forEach((c, i) => row[c] = parts[i]);
        let rt = 0;
        displayKeys.forEach(ck => { const v = cellMap.get(rk + '||' + ck) || 0; row[ck] = v; rt += v; });
        row._total = rt; return row;
      });
      if (mx.hideZero) rows = rows.filter(r => r._total > 0);
      const hdrs = rowCols.map(c => ({ key: c, label: c }))
        .concat(displayKeys.map(k => ({ key: k, label: k.replace(/\|\|/g, ' · '),
          fmt: v => v == null || v === 0 ? '' : v.toLocaleString(), cellClass: () => 'num' })))
        .concat([{ key: '_total', label: 'Total', fmt: v => v.toLocaleString(), cellClass: () => 'count-cell num' }]);
      const totalRow = { _total: rows.reduce((s, r) => s + r._total, 0) };
      rowCols.forEach((c, i) => totalRow[c] = i === rowCols.length - 1 ? 'TOTAL' : '');
      displayKeys.forEach(k => { totalRow[k] = rows.reduce((s, r) => s + (r[k] || 0), 0); });
      tableHost.appendChild(UI.el('div', { class: 'stats' },
        `${rows.length.toLocaleString()} row groups × ${colKeys.length.toLocaleString()} column groups` +
        (colKeys.length > CROSS_LIMIT ? ` (top ${CROSS_LIMIT} shown)` : '')));
      tableHost.appendChild(UI.table({ columns: hdrs, rows, totalRow, selectedRow: mx.drillIdx,
        onRowClick: (row, i) => { mx.drillIdx = i; renderDrill(row, rowCols); } }));
      tableHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(cfg.id + '_matrix.csv', rowCols.concat(displayKeys, ['_total']), rows) }, 'Download matrix'));
      if (mx.drillIdx != null && rows[mx.drillIdx]) renderDrill(rows[mx.drillIdx], rowCols);
    }

    function renderDrill(picked, rowCols) {
      drillHost.innerHTML = '';
      drillHost.appendChild(UI.sectionLabel('Property View'));
      const fIdx = filteredIdx();
      const rowStripped = rowCols.map(c => getStripped(c));
      const matches = [];
      for (let i = 0; i < fIdx.length; i++) {
        const idx = fIdx[i];
        let ok = true;
        for (let j = 0; j < rowCols.length; j++) if (rowStripped[j][idx] !== picked[rowCols[j]]) { ok = false; break; }
        if (ok) matches.push(records[idx]);
      }
      const baseCols = cols.slice(0, 3);
      const pivotCols = [...(mx.rowCols || []), ...(mx.colCols || []), ...(mx.filterCols || [])];
      const showCols = Array.from(new Set([...baseCols, ...pivotCols].filter(Boolean)));
      drillHost.appendChild(UI.el('div', { class: 'stats' },
        rowCols.map(c => `<b>${UI.escapeHtml(c)}</b>: ${UI.escapeHtml(picked[c])}`).join(' · ') +
        ` — ${matches.length.toLocaleString()} properties`));
      drillHost.appendChild(UI.table({ columns: showCols.map(c => ({ key: c, label: c })), rows: matches, height: 420 }));
      drillHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(cfg.id + '_matrix_drill.csv', showCols, matches) }, 'Download CSV'));
    }

    buildFilterControls();
    redraw();
  }

  // ── Hygiene Checks ──────────────────────────────────────────────────────────
  function renderHygiene(body, cfg, records) {
    const live = liveRecords(cfg, records);
    const checks = cfg.checkCols || [];
    body.appendChild(UI.stats([`Filtered to ${cfg.liveCol} = ${cfg.liveValue || 'Live'} · <b>${live.length.toLocaleString()}</b> properties`]));
    if (!checks.length) { body.appendChild(UI.el('div', { class: 'splash' }, 'No check columns configured.')); return; }
    const total = live.length;
    const summary = checks.map(c => {
      const s = live.map(r => strip(r[c]));
      const filled = s.filter(v => v !== '').length;
      const vc = new Map();
      s.forEach(v => { if (v) vc.set(v, (vc.get(v) || 0) + 1); });
      const top = Array.from(vc.entries()).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([v, n]) => `${UI.escapeHtml(v)} (${n})`).join(' · ');
      return { Check: c, Filled: filled, Missing: total - filled, 'Completion %': total ? Math.round(filled / total * 1000) / 10 : 0, 'Top Values': top };
    });
    const avg = summary.length ? (summary.reduce((s, r) => s + r['Completion %'], 0) / summary.length).toFixed(1) : '0';
    const gaps = summary.filter(r => r['Completion %'] < 100).length;
    body.appendChild(UI.metricRow([
      { label: 'Check Columns', value: checks.length },
      { label: 'Avg Completion', value: avg + '%' },
      { label: 'Columns with Gaps', value: gaps },
    ]));
    body.appendChild(UI.table({
      columns: [
        { key: 'Check', label: 'Check' },
        { key: 'Filled', label: '✓ Filled', fmt: v => v.toLocaleString(), cellClass: () => 'num' },
        { key: 'Missing', label: '✗ Missing', fmt: v => v.toLocaleString(), cellClass: () => 'num' },
        { key: 'Completion %', label: 'Completion %', fmt: v => v + '%', cellClass: (v) => v === 100 ? 'pct-100' : (v >= 80 ? 'pct-80' : 'pct-low') },
        { key: 'Top Values', label: 'Top Values' },
      ],
      rows: summary, height: 560,
    }));
  }

  // ── Value Summaries ─────────────────────────────────────────────────────────
  function renderValues(body, cfg, records) {
    const live = liveRecords(cfg, records);
    const checks = cfg.checkCols || [];
    body.appendChild(UI.stats([`Filtered to ${cfg.liveCol} = ${cfg.liveValue || 'Live'} · <b>${live.length.toLocaleString()}</b> properties`]));
    if (!checks.length) { body.appendChild(UI.el('div', { class: 'splash' }, 'No check columns configured.')); return; }
    body.appendChild(UI.sectionLabel('Expand any column to see its value distribution'));
    checks.forEach(hc => {
      const s = live.map(r => strip(r[hc]));
      const filled = s.filter(v => v).length, total = s.length;
      const pct = total ? Math.round(filled / total * 1000) / 10 : 0;
      const dot = pct === 100 ? '🟢' : (pct >= 80 ? '🟡' : '🔴');
      const det = UI.el('details', { class: 'expander' });
      det.appendChild(UI.el('summary', null, `${dot} ${hc}  (${pct}% filled · ${filled.toLocaleString()}/${total.toLocaleString()})`));
      const dbody = UI.el('div'); det.appendChild(dbody); body.appendChild(det);
      det.addEventListener('toggle', () => {
        if (!det.open || dbody.dataset.rendered) return;
        dbody.dataset.rendered = '1';
        const vc = new Map();
        live.forEach(r => { const v = strip(r[hc]) || '(blank)'; vc.set(v, (vc.get(v) || 0) + 1); });
        const rows = Array.from(vc.entries()).sort((a, b) => b[1] - a[1]).map(([v, n]) => ({ Value: v, Count: n, '%': live.length ? Math.round(n / live.length * 1000) / 10 : 0 }));
        dbody.appendChild(UI.table({
          columns: [{ key: 'Value', label: 'Value' }, { key: 'Count', label: 'Count', fmt: v => v.toLocaleString(), cellClass: () => 'num' }, { key: '%', label: '%', fmt: v => v + '%', cellClass: () => 'num' }],
          rows, height: 360,
        }));
      });
    });
  }

  async function renderChannel(target, cfg) {
    STATE[cfg.key] = STATE[cfg.key] || {};
    const st = STATE[cfg.key];
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: cfg.label,
      subtitle: cfg.subtitle || 'Status matrix, hygiene & value summaries',
      onRefresh: async () => { st.payload = null; st.mx = null; if (API.clearMem) API.clearMem(); UI.toast('Refreshing…'); renderChannel(target, cfg); },
    }));

    let payload;
    try { UI.updateLoader('Loading ' + cfg.label + '…'); payload = st.payload || (st.payload = await API.ota(cfg.key)); }
    catch (e) { target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }

    const cols = payload.cols;
    const all = UI.toRecords(payload);
    const colA = cols[0];
    const fhCol = cfg.fhStatusCol;
    let blank = 0, churn = 0;
    const records = all.filter(r => {
      if (!strip(r[colA])) { blank++; return false; }
      if (fhCol && strip(r[fhCol]).toLowerCase() === 'churned') { churn++; return false; }
      return true;
    });
    const parts = [`<b>${records.length.toLocaleString()}</b> active`, `${cols.length} columns`];
    if (blank) parts.push(`${blank.toLocaleString()} blank Col A excluded`);
    if (churn) parts.push(`${churn.toLocaleString()} churned excluded`);
    target.appendChild(UI.stats(parts));

    UI.tabsView([
      { id: 'matrix', label: 'Matrix', render: (b) => renderMatrix(b, cfg, st, cols, records) },
      { id: 'hygiene', label: 'Hygiene Checks', render: (b) => renderHygiene(b, cfg, records) },
      { id: 'values', label: 'Value Summaries', render: (b) => renderValues(b, cfg, records) },
    ], target);
  }

  window.makeOtaChannelPage = function (cfg) {
    return { id: cfg.id, label: cfg.label, render: (target) => renderChannel(target, cfg) };
  };

  // Reusable matrix (used by the Listing Overview deep-dive too).
  // opts = { id, label, matrixCols }; state holds { payload, mx }.
  window.OTA_renderMatrix = function (body, opts, state, cols, records) {
    renderMatrix(body, opts, state, cols, records);
  };

})();
