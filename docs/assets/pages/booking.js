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
      if (state.payload) {
        payload = state.payload;
      } else {
        UI.updateLoader('Finding Live tab\u2026');
        let liveTab = state.liveTab;
        if (!liveTab) {
          if (cfg.defaultLiveTab) {
            liveTab = cfg.defaultLiveTab;
          } else {
            const tabs = await cfg.fetchTabs();
            liveTab = (tabs.tabs || []).find(t => t.toLowerCase().includes('live')) || tabs.tabs[0];
          }
          state.liveTab = liveTab;
        }
        UI.updateLoader('Loading ' + liveTab + '\u2026');
        payload = await cfg.fetchTab(liveTab);
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
  // TAB 1: Status & Tracker — pivot table with configurable columns
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

    state.groupCols = state.groupCols || [];
    state.groupFilters = state.groupFilters || {};

    // Column selector (max 4)
    body.appendChild(UI.sectionLabel('Group by columns (max 4)'));
    const selRow = UI.el('div', { class: 'filters' });
    const ms = UI.multiselect({
      label: 'Columns',
      options: cols,
      selected: state.groupCols,
      placeholder: 'Pick columns to group/filter by',
      onChange: (v) => {
        state.groupCols = v.slice(0, 4);
        state.groupFilters = {};
        state.drillIdx = null;
        redraw();
      },
    });
    selRow.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, 'Pick columns'),
      ms.el,
    ]));
    body.appendChild(selRow);

    // Per-column filter widgets (rebuilt when groupCols changes)
    const filterBar = UI.el('div', { class: 'filters' });
    body.appendChild(filterBar);

    const tableHost = UI.el('div');
    const drillHost = UI.el('div');
    body.appendChild(tableHost);
    body.appendChild(drillHost);

    function buildPivot() {
      const g = state.groupCols;
      if (!g.length) return [];

      const grp = new Map();
      records.forEach(r => {
        const k = g.map(c => strip(r[c])).join('||');
        grp.set(k, (grp.get(k) || 0) + 1);
      });
      let pivot = Array.from(grp.entries()).map(([k, n]) => {
        const parts = k.split('||');
        const row = { Count: n };
        g.forEach((c, i) => row[c] = parts[i]);
        return row;
      });
      pivot.sort((a, b) => b.Count - a.Count);

      // Apply column filters
      let view = pivot.slice();
      g.forEach(c => {
        const sel = state.groupFilters[c];
        if (sel && sel.length) view = view.filter(r => sel.includes(r[c]));
      });
      return { pivot, view };
    }

    function renderFilters() {
      filterBar.innerHTML = '';
      state.groupCols.forEach(c => {
        const vals = Array.from(new Set(records.map(r => strip(r[c])))).sort();
        const wrap = UI.el('div', { class: 'filter' });
        wrap.appendChild(UI.el('div', { class: 'filter-label' }, c));
        wrap.appendChild(UI.multiselect({
          label: c, options: vals, selected: state.groupFilters[c] || [],
          placeholder: 'All', onChange: (v) => { state.groupFilters[c] = v; state.drillIdx = null; redraw(); },
        }).el);
        filterBar.appendChild(wrap);
      });
    }

    function redraw() {
      renderFilters();
      const result = buildPivot();
      if (!result.length) {
        tableHost.innerHTML = '<div class="splash">Pick columns above to build the pivot table.</div>';
        drillHost.innerHTML = '';
        return;
      }
      const { pivot, view } = result;
      const g = state.groupCols;

      const totalRow = { Count: view.reduce((s, r) => s + r.Count, 0) };
      g.forEach((c, i) => totalRow[c] = i === g.length - 1 ? 'TOTAL' : '');

      const columns = g.map(c => ({ key: c, label: c }))
        .concat([{ key: 'Count', label: 'Count', fmt: v => v.toLocaleString(), cellClass: () => 'count-cell num' }]);

      tableHost.innerHTML = '';
      tableHost.appendChild(UI.table({
        columns, rows: view, totalRow, selectedRow: state.drillIdx,
        onRowClick: (row, i) => { state.drillIdx = i; renderDrill(view[i]); },
      }));
      tableHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => {
          const fn = cfg.title.toLowerCase() + '_pivot.csv';
          const allCols = g.concat(['Count']);
          UI.downloadCsv(fn, allCols, view);
        },
      }, 'Download CSV'));

      if (state.drillIdx != null && view[state.drillIdx]) renderDrill(view[state.drillIdx]);
      else drillHost.innerHTML = '';
    }

    function renderDrill(picked) {
      drillHost.innerHTML = '';
      drillHost.appendChild(UI.sectionLabel('Property View'));
      const matches = records.filter(r =>
        state.groupCols.every(c => strip(r[c]) === picked[c])
      );
      const propCols = cols.slice(0, Math.min(6, cols.length));
      drillHost.appendChild(UI.el('div', { class: 'stats' },
        state.groupCols.map(c => `<b>${UI.escapeHtml(c)}</b>: ${UI.escapeHtml(picked[c])}`).join(' · ') +
        ` — ${matches.length.toLocaleString()} properties`));
      drillHost.appendChild(UI.table({
        columns: propCols.map(c => ({ key: c, label: c })),
        rows: matches, height: 380,
      }));
      drillHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(cfg.title.toLowerCase() + '_drill.csv', propCols, matches),
      }, 'Download CSV'));
    }

    redraw();
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
