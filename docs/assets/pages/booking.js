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
    gmb: {
      title: 'GMB',
      subtitle: 'Property status, substatus and hygiene checks',
      fetchMain: () => API.gmb(),
      fetchMainFresh: () => API.gmb({ refresh: true }),
      fetchTabs: () => API.gmbTabs(),
      fetchTab:  (name) => API.gmbTab(name),
      statusLetter: 'E',
      statusLabel: 'Status',
      subStatusLetter: 'F',
      fhStatusLetter: 'I',
      matrixLetters: ['E', 'F', 'L', 'M'],
      defaultLiveTab: 'New Tracker',
      defaultTrackerTab: null,
      hygExclude: [],
    },
  };

  // ── Per-channel session state (filters, drill-down etc.) ─────────────────
  const STATE = { bcom: {}, gommt: {}, gmb: {} };

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
        }
        // Always persist payload \u2014 was missing for the "Live" exact-match branch,
        // which made Summary tab show "No data loaded" on Booking.com.
        state.payload = payload;
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
    UI.tabsView([
      { id: 'matrix',  label: 'Matrix',
        render: (body) => renderMatrix(body, cfg, state, cols, records) },
      { id: 'hygiene', label: 'Hygiene Checks',
        render: (body) => renderHygiene(body, cfg, state, cols, records) },
      { id: 'values',  label: 'Value Summaries',
        render: (body) => renderValueSummaries(body, cfg, state, cols, records) },
    ], target);
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
  // TAB: Matrix — flexible pivot with rows/cols/filters customisation
  // ──────────────────────────────────────────────────────────────────────────
  function renderMatrix(body, cfg, state, cols, records) {
    // Default Rows/Cols come from the channel's matrixLetters config.
    // For E,F,L,M we split as Rows = [E,F], Cols = [L,M] — but the user can
    // change this freely and select any columns from the sheet.
    const defaultMx = cfg.matrixLetters.map(L => cols[colIdx(L)] || null).filter(Boolean);
    const half = Math.ceil(defaultMx.length / 2);

    // ── Persistent defaults ──────────────────────────────────────────────
    // Saved in localStorage as {rowCols, colCols, filterCols, filters,
    // hideZero, _positions} — _positions stores the col INDEX for each
    // saved name, used as a fallback if a column was renamed/shifted.
    const LS_KEY = 'mx_defaults_' + cfg.title.toLowerCase().replace(/\W/g, '_');

    function loadDefaults() {
      try {
        const raw = localStorage.getItem(LS_KEY);
        if (!raw) return null;
        const saved = JSON.parse(raw);
        const pos = saved._positions || {};

        // Resolve a saved column to a current column: try name first,
        // then fall back to the stored position. Returns null if neither works.
        const resolve = (name) => {
          if (cols.includes(name)) return name;
          const idx = pos[name];
          if (idx != null && idx >= 0 && idx < cols.length) return cols[idx];
          return null;
        };
        const resolveList = (arr) => (arr || []).map(resolve).filter(Boolean);

        const rowCols    = resolveList(saved.rowCols);
        const colCols    = resolveList(saved.colCols);
        const filterCols = resolveList(saved.filterCols);

        // Filter values: copy entries only for columns that still exist
        const filters = {};
        Object.keys(saved.filters || {}).forEach(k => {
          const live = resolve(k);
          if (live && Array.isArray(saved.filters[k])) {
            filters[live] = saved.filters[k];
          }
        });

        return {
          rowCols, colCols, filterCols, filters,
          hideZero: saved.hideZero !== false,
          drillIdx: null,
        };
      } catch (_) {
        return null;
      }
    }

    function saveDefaults() {
      const positions = {};
      const collect = (c) => { positions[c] = cols.indexOf(c); };
      mx.rowCols.forEach(collect);
      mx.colCols.forEach(collect);
      mx.filterCols.forEach(collect);
      Object.keys(mx.filters).forEach(collect);

      const blob = {
        rowCols: mx.rowCols,
        colCols: mx.colCols,
        filterCols: mx.filterCols,
        filters: mx.filters,
        hideZero: mx.hideZero,
        _positions: positions,
        _savedAt: new Date().toISOString(),
      };
      localStorage.setItem(LS_KEY, JSON.stringify(blob));
      UI.toast('Defaults saved for ' + cfg.title);
    }

    function clearDefaults() {
      localStorage.removeItem(LS_KEY);
      // Reset state in memory so next render uses the channel's built-in defaults
      delete state.mx;
      UI.toast('Defaults cleared');
      body.innerHTML = '';
      renderMatrix(body, cfg, state, cols, records);
    }

    // Initialize state: prefer localStorage defaults, then in-memory state,
    // then the channel config defaults.
    state.mx = state.mx || loadDefaults() || {
      rowCols: defaultMx.slice(0, half),
      colCols: defaultMx.slice(half),
      filterCols: [],
      filters: {},
      hideZero: true,
      drillIdx: null,
    };
    const mx = state.mx;

    // ── PERF: cache pre-stripped column values on the payload ─────────────
    const p = state.payload;
    p._strip = p._strip || {};
    function getStripped(col) {
      if (p._strip[col]) return p._strip[col];
      const arr = new Array(records.length);
      for (let i = 0; i < records.length; i++) {
        const v = records[i][col];
        arr[i] = v == null ? '' : String(v).trim();
      }
      p._strip[col] = arr;
      return arr;
    }
    // Pre-bind sub-status check (records already filtered for blank-A / churn at render() top)

    body.appendChild(UI.stats([`<b>${records.length.toLocaleString()}</b> properties available`]));

    // ── Pivot configuration panel ────────────────────────────────────────
    const cfgPanel = UI.el('div', { class: 'filters', style: 'align-items:flex-start' });
    cfgPanel.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Rows'),
      UI.multiselect({
        label: 'Rows', options: cols, selected: mx.rowCols,
        placeholder: 'Pick row columns',
        onChange: (v) => { mx.rowCols = v; mx.drillIdx = null; redraw(); },
      }).el,
    ]));
    cfgPanel.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Columns'),
      UI.multiselect({
        label: 'Columns', options: cols, selected: mx.colCols,
        placeholder: 'Pick column columns (optional)',
        onChange: (v) => { mx.colCols = v; mx.drillIdx = null; redraw(); },
      }).el,
    ]));
    cfgPanel.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Add Filters'),
      UI.multiselect({
        label: 'Filters', options: cols, selected: mx.filterCols,
        placeholder: 'Pick filter columns',
        onChange: (v) => { mx.filterCols = v; mx.drillIdx = null; buildFilterControls(); redraw(); },
      }).el,
    ]));
    body.appendChild(cfgPanel);

    // Dynamic filter widgets for the selected filter columns
    const filterHost = UI.el('div', { class: 'filters' });
    body.appendChild(filterHost);

    const toggleRow = UI.el('div', { style: 'display:flex;align-items:center;gap:14px;margin:6px 0 10px' });
    const hideToggle = UI.el('label', { class: 'toggle' }, [
      UI.el('input', { type: 'checkbox',
        onChange: (e) => { mx.hideZero = e.target.checked; redraw(); } }),
      ' Hide zero counts',
    ]);
    hideToggle.querySelector('input').checked = mx.hideZero;
    toggleRow.appendChild(hideToggle);
    toggleRow.appendChild(UI.el('button', {
      class: 'btn btn-sm', onClick: saveDefaults,
      title: 'Persist current Rows / Columns / Filters and their selected values across refreshes',
    }, 'Save as default'));
    if (localStorage.getItem(LS_KEY)) {
      toggleRow.appendChild(UI.el('button', {
        class: 'btn btn-sm', onClick: clearDefaults,
        title: 'Remove saved defaults — Matrix will fall back to channel built-ins',
      }, 'Clear default'));
    }
    body.appendChild(toggleRow);

    const tableHost = UI.el('div');
    const drillHost = UI.el('div');
    body.appendChild(tableHost);
    body.appendChild(drillHost);

    function buildFilterControls() {
      filterHost.innerHTML = '';
      mx.filterCols.forEach(c => {
        const stripped = getStripped(c);
        const vals = Array.from(new Set(stripped)).sort();
        filterHost.appendChild(UI.el('div', { class: 'filter' }, [
          UI.el('div', { class: 'filter-label' }, c),
          UI.multiselect({
            label: c, options: vals, selected: mx.filters[c] || [],
            placeholder: 'All',
            onChange: (v) => { mx.filters[c] = v; mx.drillIdx = null; redraw(); },
          }).el,
        ]));
      });
    }

    // Apply filters, return list of record indices
    function filteredIdx() {
      const active = mx.filterCols
        .map(c => ({ col: c, sel: mx.filters[c], stripped: getStripped(c) }))
        .filter(f => f.sel && f.sel.length);
      if (!active.length) {
        const idx = new Array(records.length);
        for (let i = 0; i < idx.length; i++) idx[i] = i;
        return idx;
      }
      const selSets = active.map(f => new Set(f.sel));
      const out = [];
      for (let i = 0; i < records.length; i++) {
        let ok = true;
        for (let k = 0; k < active.length; k++) {
          if (!selSets[k].has(active[k].stripped[i])) { ok = false; break; }
        }
        if (ok) out.push(i);
      }
      return out;
    }

    function redraw() {
      tableHost.innerHTML = '';
      drillHost.innerHTML = '';

      const rowCols = (mx.rowCols || []).filter(c => cols.includes(c));
      const colCols = (mx.colCols || []).filter(c => cols.includes(c));

      if (!rowCols.length) {
        tableHost.appendChild(UI.el('div', { class: 'splash' },
          'Pick at least one Row column to build the matrix.'));
        return;
      }

      const fIdx = filteredIdx();
      const rowStripped = rowCols.map(c => getStripped(c));
      const colStripped = colCols.map(c => getStripped(c));

      // ── Simple grouping (no column dimension) ───────────────────────────
      if (!colCols.length) {
        const grp = new Map();
        for (let i = 0; i < fIdx.length; i++) {
          const idx = fIdx[i];
          let k = rowStripped[0][idx];
          for (let j = 1; j < rowStripped.length; j++) k += '||' + rowStripped[j][idx];
          grp.set(k, (grp.get(k) || 0) + 1);
        }
        let rows = Array.from(grp.entries()).map(([k, n]) => {
          const parts = k.split('||');
          const row = { Count: n };
          rowCols.forEach((c, i) => row[c] = parts[i]);
          return row;
        });
        rows.sort((a, b) => b.Count - a.Count);
        if (mx.hideZero) rows = rows.filter(r => r.Count > 0);

        const totalRow = { Count: rows.reduce((s, r) => s + r.Count, 0) };
        rowCols.forEach((c, i) => totalRow[c] = i === rowCols.length - 1 ? 'TOTAL' : '');

        const columns = rowCols.map(c => ({ key: c, label: c }))
          .concat([{ key: 'Count', label: 'Count',
            fmt: v => v.toLocaleString(), cellClass: () => 'count-cell num' }]);

        tableHost.appendChild(UI.table({
          columns, rows, totalRow, selectedRow: mx.drillIdx,
          onRowClick: (row, i) => { mx.drillIdx = i; renderDrill(row, rowCols); },
        }));
        tableHost.appendChild(UI.el('button', {
          class: 'btn btn-sm', style: 'margin-top:8px',
          onClick: () => UI.downloadCsv(`${cfg.title.toLowerCase()}_matrix.csv`,
            rowCols.concat(['Count']), rows),
        }, 'Download matrix'));
        if (mx.drillIdx != null && rows[mx.drillIdx]) renderDrill(rows[mx.drillIdx], rowCols);
        return;
      }

      // ── Cross-tab (rows × cols) ─────────────────────────────────────────
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
      if (mx.hideZero) rows = rows.filter(r => r._total > 0);

      const hdrs = rowCols.map(c => ({ key: c, label: c }))
        .concat(displayKeys.map(k => ({
          key: k,
          label: k.replace(/\|\|/g, ' · '),
          fmt: v => v == null || v === 0 ? '' : v.toLocaleString(),
          cellClass: () => 'num',
        })))
        .concat([{ key: '_total', label: 'Total',
          fmt: v => v.toLocaleString(), cellClass: () => 'count-cell num' }]);

      const totalRow = { _total: rows.reduce((s, r) => s + r._total, 0) };
      rowCols.forEach((c, i) => totalRow[c] = i === rowCols.length - 1 ? 'TOTAL' : '');
      displayKeys.forEach(k => { totalRow[k] = rows.reduce((s, r) => s + (r[k] || 0), 0); });

      tableHost.appendChild(UI.el('div', { class: 'stats' },
        `${rows.length.toLocaleString()} row groups × ${colKeys.length.toLocaleString()} column groups` +
        (colKeys.length > CROSS_LIMIT ? ` (top ${CROSS_LIMIT} shown)` : '')));

      tableHost.appendChild(UI.table({
        columns: hdrs, rows, totalRow, selectedRow: mx.drillIdx,
        onRowClick: (row, i) => { mx.drillIdx = i; renderDrill(row, rowCols); },
      }));
      tableHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(`${cfg.title.toLowerCase()}_matrix.csv`,
          rowCols.concat(displayKeys, ['_total']), rows),
      }, 'Download matrix'));
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
        for (let j = 0; j < rowCols.length; j++) {
          if (rowStripped[j][idx] !== picked[rowCols[j]]) { ok = false; break; }
        }
        if (ok) matches.push(records[idx]);
      }

      // Show: first 3 columns of the sheet (Prop ID, Prop Name, City) + every
      // column currently used in the pivot (Rows + Columns + Filters).
      const baseCols = cols.slice(0, 3);
      const pivotCols = [...(mx.rowCols || []), ...(mx.colCols || []), ...(mx.filterCols || [])];
      const showCols = Array.from(new Set([...baseCols, ...pivotCols].filter(Boolean)));

      drillHost.appendChild(UI.el('div', { class: 'stats' },
        rowCols.map(c => `<b>${UI.escapeHtml(c)}</b>: ${UI.escapeHtml(picked[c])}`).join(' · ') +
        ` — ${matches.length.toLocaleString()} properties`));
      drillHost.appendChild(UI.table({
        columns: showCols.map(c => ({ key: c, label: c })),
        rows: matches, height: 420,
      }));
      drillHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(`${cfg.title.toLowerCase()}_matrix_drill.csv`, showCols, matches),
      }, 'Download CSV'));
    }

    buildFilterControls();
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
  window.PAGE_GMB = {
    id: 'gmb',
    label: 'GMB',
    render: (target) => render(target, 'gmb'),
  };

})();
