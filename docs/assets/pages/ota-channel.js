/**
 * Generic OTA "channel" page — same look as Booking.com / GoMMT / GMB, but
 * config-driven by COLUMN HEADERS (the OTA tracker sheets don't share the
 * fixed N-AH layout). Tabs: Matrix · Hygiene Checks · Value Summaries · Table.
 *
 * Per-OTA config (see ota-channel-config.js):
 *   { id, label, key,                       // key = OTA_SHEETS key in Code.gs
 *     fhStatusCol,                          // FH status col; "Churned" excluded
 *     liveCol, liveValue,                   // defines the "live" subset (default value "Live")
 *     matrixCols: [rowCol, colCol],         // 2 columns to cross-tabulate
 *     checkCols: [ ... ] }                  // columns analysed in Hygiene + Values
 */

(function () {

  const STATE = {};
  const strip = v => String(v == null ? '' : v).trim();

  function liveRecords(cfg, records) {
    if (!cfg.liveCol) return records;
    const lv = String(cfg.liveValue || 'Live').toLowerCase();
    return records.filter(r => strip(r[cfg.liveCol]).toLowerCase() === lv);
  }

  // ── Matrix: rowCol × colCol counts ──────────────────────────────────────────
  function renderMatrix(body, cfg, records) {
    const mc = cfg.matrixCols || [];
    const rowCol = mc[0], colCol = mc[1];
    if (!rowCol || !colCol) { body.appendChild(UI.el('div', { class: 'splash' }, 'Matrix columns not configured.')); return; }
    body.appendChild(UI.stats([`${records.length.toLocaleString()} active · <b>${rowCol}</b> (rows) × <b>${colCol}</b> (columns)`]));

    const colVals = Array.from(new Set(records.map(r => strip(r[colCol]) || '(blank)'))).sort();
    const rowMap = new Map();
    records.forEach(r => {
      const rk = strip(r[rowCol]) || '(blank)';
      const ck = strip(r[colCol]) || '(blank)';
      if (!rowMap.has(rk)) rowMap.set(rk, {});
      const o = rowMap.get(rk); o[ck] = (o[ck] || 0) + 1;
    });
    const rows = Array.from(rowMap.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([rk, o]) => {
      const row = { __row: rk }; let tot = 0;
      colVals.forEach(cv => { row[cv] = o[cv] || 0; tot += o[cv] || 0; });
      row.Total = tot; return row;
    });
    const columns = [{ key: '__row', label: rowCol + ' ╲ ' + colCol }]
      .concat(colVals.map(cv => ({ key: cv, label: cv, fmt: v => v ? v.toLocaleString() : '', cellClass: () => 'num' })))
      .concat([{ key: 'Total', label: 'Total', fmt: v => v.toLocaleString(), cellClass: () => 'num' }]);
    body.appendChild(UI.table({ columns, rows, height: 560 }));
  }

  // ── Hygiene Checks: completion of checkCols (live subset) ────────────────────
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

  // ── Value Summaries: per-column value distribution (live subset) ─────────────
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

  // ── Raw table (search + CSV) ────────────────────────────────────────────────
  function renderTable(body, cfg, payload, records) {
    const cols = payload.cols;
    let q = '';
    const tb = UI.toolbar({ placeholder: 'Search…', countText: records.length + ' rows', onChange: (v) => { q = v; redraw(); } });
    body.appendChild(tb.el);
    const th = UI.el('div'); body.appendChild(th);
    function redraw() {
      let view = records;
      if (q) { const s = q.toLowerCase(); view = records.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(s))); }
      tb.el.querySelector('.count').textContent = `${view.length.toLocaleString()} rows`;
      th.innerHTML = '';
      th.appendChild(UI.table({ columns: cols.map(c => ({ key: c, label: c })), rows: view, height: 520 }));
      th.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px', onClick: () => UI.downloadCsv(cfg.id + '.csv', cols, view) }, 'Download CSV'));
    }
    redraw();
  }

  async function renderChannel(target, cfg) {
    STATE[cfg.key] = STATE[cfg.key] || {};
    const st = STATE[cfg.key];
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: cfg.label,
      subtitle: cfg.subtitle || 'Status matrix, hygiene & value summaries',
      onRefresh: async () => { st.payload = null; if (API.clearMem) API.clearMem(); UI.toast('Refreshing…'); renderChannel(target, cfg); },
    }));

    let payload;
    try { UI.updateLoader('Loading ' + cfg.label + '…'); payload = st.payload || (st.payload = await API.ota(cfg.key, st.payload ? undefined : (st.fresh ? { refresh: true } : undefined))); }
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
      { id: 'matrix', label: 'Matrix', render: (b) => renderMatrix(b, cfg, records) },
      { id: 'hygiene', label: 'Hygiene Checks', render: (b) => renderHygiene(b, cfg, records) },
      { id: 'values', label: 'Value Summaries', render: (b) => renderValues(b, cfg, records) },
      { id: 'table', label: 'Table', render: (b) => renderTable(b, cfg, payload, records) },
    ], target);
  }

  window.makeOtaChannelPage = function (cfg) {
    return { id: cfg.id, label: cfg.label, render: (target) => renderChannel(target, cfg) };
  };

})();
