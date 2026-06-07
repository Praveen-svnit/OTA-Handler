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
      defaultLiveTab: 'Live Sheet',
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
        UI.toast('Refreshing…');
        try {
          state.payload = await cfg.fetchMainFresh();
          state.tabs = null;
          state.pivot = null;
          render(target, cfgKey);
          UI.toast('Refreshed');
        } catch (e) {
          UI.toast('Refresh failed: ' + e.message, true);
        }
      },
    }));

    // Data
    let payload;
    try {
      UI.updateLoader('Loading ' + cfg.title + ' main sheet\u2026');
      payload = state.payload || (state.payload = await cfg.fetchMain());
      UI.updateLoader('Processing ' + cfg.title + ' data\u2026');
    } catch (e) {
      target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load sheet: ' + e.message));
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
        render: (body) => renderStatusTracker(body, cfg, state, cols, records) },
      { id: 'hygiene', label: 'Hygiene Checks',
        render: (body) => renderHygiene(body, cfg, state, cols, records) },
      { id: 'values',  label: 'Value Summaries',
        render: (body) => renderValueSummaries(body, cfg, state, cols, records) },
      { id: 'matrix',  label: matrixLabel,
        render: (body) => renderMatrix(body, cfg, state, cols, records) },
    ], target);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // TAB 1: Status & Tracker
  // ──────────────────────────────────────────────────────────────────────────
  async function renderStatusTracker(body, cfg, state, cols, records) {
    const subCol = cols[colIdx(cfg.subStatusLetter)] || cols[5];
    const staCol = cols[colIdx(cfg.statusLetter)]    || cols[4];

    // Build pivot
    const pivotMap = new Map();
    records.forEach(r => {
      const k = strip(r[subCol]) + '||' + strip(r[staCol]);
      pivotMap.set(k, (pivotMap.get(k) || 0) + 1);
    });
    let pivot = Array.from(pivotMap.entries()).map(([k, n]) => {
      const [sub, sta] = k.split('||');
      return { [subCol]: sub, [staCol]: sta, Count: n };
    });
    pivot.sort((a, b) => b.Count - a.Count);

    // Tracker comparison (auto-fetch on first render)
    if (!state.tracker) {
      try {
        UI.updateLoader('Loading tab list\u2026');
        state.availableTabs = state.availableTabs || await cfg.fetchTabs();
        const tabs = state.availableTabs.tabs || [];
        const liveTab = state.liveTab || cfg.defaultLiveTab ||
          tabs.find(t => t.toLowerCase().includes('live')) || tabs[0];
        const trackerTab = state.trackerTab || cfg.defaultTrackerTab ||
          tabs.find(t => t.toLowerCase().includes('tracker')) || tabs[1] || tabs[0];
        state.liveTab = liveTab;
        state.trackerTab = trackerTab;

        if (liveTab && trackerTab) {
          UI.updateLoader('Comparing ' + liveTab + ' vs ' + trackerTab + '\u2026');
          const [liveData, trackerData] = await Promise.all([
            cfg.fetchTab(liveTab),
            cfg.fetchTab(trackerTab),
          ]);
          const liveRecs    = UI.toRecords(liveData);
          const trackerRecs = UI.toRecords(trackerData);
          const liveIdCol = liveData.cols[state.liveIdIdx || 0];
          const trkIdCol  = trackerData.cols[state.trackerIdIdx || 0];
          const trkSet    = new Set(trackerRecs.map(r => strip(r[trkIdCol]).toLowerCase()).filter(Boolean));
          const liveIds   = liveRecs.map(r => strip(r[liveIdCol]).toLowerCase()).filter(Boolean);
          const liveSet   = new Set(liveIds);
          const missing   = new Set(liveIds.filter(id => !trkSet.has(id)));
          state.tracker = {
            liveData, trackerData, liveRecs, trackerRecs, liveIdCol, trkIdCol,
            liveCount: liveSet.size, trackerCount: trkSet.size, missingCount: missing.size,
            missingSet: missing,
          };
        }
      } catch (e) {
        state.trackerError = e.message;
      }
    }

    // Augment pivot with "Missing from Tracker" count
    let pivotHasMissing = false;
    if (state.tracker && state.tracker.liveRecs.length) {
      const tr = state.tracker;
      const subOK = tr.liveData.cols.includes(subCol);
      const staOK = tr.liveData.cols.includes(staCol);
      if (subOK && staOK) {
        const missMap = new Map();
        tr.liveRecs.forEach(r => {
          const id = strip(r[tr.liveIdCol]).toLowerCase();
          if (!tr.missingSet.has(id)) return;
          const k = strip(r[subCol]) + '||' + strip(r[staCol]);
          missMap.set(k, (missMap.get(k) || 0) + 1);
        });
        pivot.forEach(p => {
          const k = p[subCol] + '||' + p[staCol];
          p['Missing from Tracker'] = missMap.get(k) || 0;
        });
        pivotHasMissing = true;
      }
    }

    // Tracker metrics
    if (state.tracker) {
      body.appendChild(UI.metricRow([
        { label: 'Live IDs',    value: state.tracker.liveCount.toLocaleString() },
        { label: 'In Tracker',  value: state.tracker.trackerCount.toLocaleString() },
        { label: 'Missing',     value: state.tracker.missingCount.toLocaleString() },
      ]));
    } else if (state.trackerError) {
      body.appendChild(UI.el('div', { class: 'stats' }, 'Tracker comparison unavailable: ' + state.trackerError));
    }

    // Filters
    const subValues = Array.from(new Set(pivot.map(r => r[subCol]))).sort();
    const staValues = Array.from(new Set(pivot.map(r => r[staCol]))).sort();
    state.fSub = state.fSub || [];
    state.fSta = state.fSta || [];
    state.hideZero = state.hideZero !== false;

    body.appendChild(UI.sectionLabel('Filters'));
    const fbar = UI.el('div', { class: 'filters' });
    fbar.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, subCol),
      UI.multiselect({
        label: subCol, options: subValues, selected: state.fSub,
        placeholder: 'All', onChange: (v) => { state.fSub = v; redrawTable(); },
      }).el,
    ]));
    fbar.appendChild(UI.el('div', { class: 'filter' }, [
      UI.el('div', { class: 'filter-label' }, staCol),
      UI.multiselect({
        label: staCol, options: staValues, selected: state.fSta,
        placeholder: 'All', onChange: (v) => { state.fSta = v; redrawTable(); },
      }).el,
    ]));
    const hideToggle = UI.el('label', { class: 'toggle' }, [
      UI.el('input', { type: 'checkbox', onChange: (e) => { state.hideZero = e.target.checked; redrawTable(); } }),
      ' Hide zero',
    ]);
    hideToggle.querySelector('input').checked = state.hideZero;
    fbar.appendChild(hideToggle);
    body.appendChild(fbar);

    // Table area
    const tableHost = UI.el('div');
    const drillHost = UI.el('div');
    body.appendChild(tableHost);
    body.appendChild(drillHost);

    function redrawTable() {
      tableHost.innerHTML = '';
      let view = pivot.slice();
      if (state.fSub.length) view = view.filter(r => state.fSub.includes(r[subCol]));
      if (state.fSta.length) view = view.filter(r => state.fSta.includes(r[staCol]));
      if (state.hideZero) view = view.filter(r => r.Count > 0);

      const totalRow = { [subCol]: 'TOTAL', [staCol]: '', Count: view.reduce((s, r) => s + r.Count, 0) };
      if (pivotHasMissing) totalRow['Missing from Tracker'] = view.reduce((s, r) => s + (r['Missing from Tracker'] || 0), 0);

      const columns = [
        { key: subCol, label: subCol },
        { key: staCol, label: staCol },
        { key: 'Count', label: 'Count',
          fmt: v => v.toLocaleString(),
          cellClass: () => 'count-cell num' },
      ];
      if (pivotHasMissing) {
        columns.push({
          key: 'Missing from Tracker', label: 'Missing from Tracker',
          fmt: v => (v || 0).toLocaleString(),
          cellClass: (v) => 'num' + ((v || 0) > 0 ? ' missing-pos' : ''),
        });
      }

      tableHost.appendChild(UI.table({
        columns, rows: view, totalRow,
        selectedRow: state.drillIdx,
        onRowClick: (row, i) => {
          state.drillIdx = i;
          renderDrill(view[i]);
        },
      }));

      if (state.drillIdx != null && view[state.drillIdx]) renderDrill(view[state.drillIdx]);
      else drillHost.innerHTML = '';
    }

    function renderDrill(picked) {
      drillHost.innerHTML = '';
      drillHost.appendChild(UI.sectionLabel('Property View'));
      const matches = records.filter(r =>
        strip(r[subCol]) === picked[subCol] && strip(r[staCol]) === picked[staCol]
      );
      const propIdCol = cols[0];
      const channelIdCol = cols[3];
      const nameCol = cols.find(c => c.toLowerCase().includes('name'));
      const showCols = Array.from(new Set([propIdCol, channelIdCol, nameCol, subCol, staCol].filter(Boolean)));
      drillHost.appendChild(UI.el('div', { class: 'stats' },
        `<b>${subCol}</b>: ${UI.escapeHtml(picked[subCol])} · <b>${staCol}</b>: ${UI.escapeHtml(picked[staCol])} — ${matches.length.toLocaleString()} properties`));
      drillHost.appendChild(UI.table({
        columns: showCols.map(c => ({ key: c, label: c })),
        rows: matches, height: 380,
      }));
      drillHost.appendChild(UI.el('button', {
        class: 'btn btn-sm', style: 'margin-top:8px',
        onClick: () => UI.downloadCsv(`${cfg.title.toLowerCase()}_drill.csv`, showCols, matches),
      }, 'Download CSV'));
    }

    redrawTable();
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
