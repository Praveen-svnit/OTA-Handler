/**
 * Listing Overview — OTA listing % vs the live FH base, filterable by
 * Prop Set / Prop Cat / Live Month. Backend returns (set × cat × month) groups
 * with per-OTA live counts; we filter + aggregate here for instant updates.
 * Below: a deep-dive pivot for any single channel.
 */

(function () {

  let data = null;
  const ddCache = {};
  const sel = { sets: [], cats: [], months: [] };
  function barColor(p) { return p >= 80 ? '#16a34a' : p >= 50 ? '#b45309' : '#dc2626'; }

  // Month sort: "Apr-26" -> sortable; "(blank)" last.
  const MON = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
  function monthKey(m) {
    const mm = String(m).match(/([A-Za-z]{3})[^0-9]*(\d{2,4})/);
    if (!mm) return 999999;
    let y = parseInt(mm[2]); if (y < 100) y += 2000;
    return y * 100 + (MON[mm[1].toLowerCase()] || 0);
  }

  function uniqSorted(vals, monthly) {
    const u = Array.from(new Set(vals));
    if (monthly) u.sort((a, b) => monthKey(a) - monthKey(b));
    else u.sort((a, b) => String(a).localeCompare(String(b)));
    return u;
  }

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Listing Overview',
      subtitle: 'OTA listing % vs the live FH base — filter by Prop Set / Prop Cat / Live Month',
      onRefresh: async () => {
        UI.toast('Refreshing…');
        try { data = await API.listingOverview({ refresh: true }); render(target); UI.toast('Refreshed'); }
        catch (e) { UI.toast('Refresh failed: ' + e.message, true); }
      },
    }));

    try { UI.updateLoader('Loading listing data…'); data = data || (data = await API.listingOverview()); }
    catch (e) { target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }

    const groups = data.groups || [];
    const otas = data.otas || [];
    const setOpts = uniqSorted(groups.map(g => g.s));
    const catOpts = uniqSorted(groups.map(g => g.c));
    const monthOpts = uniqSorted(groups.map(g => g.m), true);

    // keep prior selection if still valid
    sel.sets = sel.sets.filter(v => setOpts.includes(v));
    sel.cats = sel.cats.filter(v => catOpts.includes(v));
    sel.months = sel.months.filter(v => monthOpts.includes(v));

    // ── Filters ──────────────────────────────────────────────────────────────
    const fr = UI.el('div', { class: 'filters' });
    function addFilter(label, options, key, monthly) {
      fr.appendChild(UI.el('div', { class: 'filter' }, [
        UI.el('div', { class: 'filter-label' }, label),
        UI.multiselect({ label, options, selected: sel[key], placeholder: 'All',
          onChange: (v) => { sel[key] = v; recompute(); } }).el,
      ]));
    }
    addFilter('Prop Set', setOpts, 'sets');
    addFilter('Prop Cat', catOpts, 'cats');
    addFilter('Live Month', monthOpts, 'months', true);
    target.appendChild(fr);

    const statHost = UI.el('div'); target.appendChild(statHost);
    const tableHost = UI.el('div'); target.appendChild(tableHost);

    function recompute() {
      const fg = groups.filter(g =>
        (!sel.sets.length || sel.sets.includes(g.s)) &&
        (!sel.cats.length || sel.cats.includes(g.c)) &&
        (!sel.months.length || sel.months.includes(g.m)));
      const total = fg.reduce((s, g) => s + g.n, 0);
      const rows = otas.map((label, i) => {
        const live = fg.reduce((s, g) => s + (g.l[i] || 0), 0);
        return { ota: label, live, pct: total ? Math.round(live / total * 1000) / 10 : 0, pending: total - live };
      }).sort((a, b) => b.pct - a.pct);

      statHost.innerHTML = '';
      statHost.appendChild(UI.stats([`Filtered base: <b>${total.toLocaleString()}</b> properties`]));

      tableHost.innerHTML = '';
      const tbl = document.createElement('table');
      tbl.style.cssText = 'width:100%;border-collapse:collapse;font-size:13px;max-width:720px';
      tbl.innerHTML = '<thead><tr>' + ['OTA', 'Live', 'Listing %', 'Pending'].map((h, i) =>
        `<th style="text-align:${i === 0 ? 'left' : 'right'};padding:9px 12px;border-bottom:2px solid #e7e9ee;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.04em">${h}</th>`).join('') + '</tr></thead>';
      const tb = document.createElement('tbody');
      rows.forEach(r => {
        const tr = document.createElement('tr');
        tr.style.cssText = 'border-bottom:1px solid #f1f2f5';
        tr.innerHTML =
          `<td style="padding:10px 12px;font-weight:600">${r.ota}</td>` +
          `<td style="padding:10px 12px;text-align:right;font-variant-numeric:tabular-nums">${r.live.toLocaleString()}</td>` +
          `<td style="padding:10px 12px;text-align:right"><div style="display:inline-flex;align-items:center;gap:8px">` +
            `<div style="width:90px;height:7px;background:#eef2f6;border-radius:4px;overflow:hidden">` +
            `<div style="height:100%;width:${r.pct}%;background:${barColor(r.pct)}"></div></div>` +
            `<span style="font-weight:700;min-width:46px;color:${barColor(r.pct)}">${r.pct}%</span></div></td>` +
          `<td style="padding:10px 12px;text-align:right;color:#b91c1c;font-weight:600;font-variant-numeric:tabular-nums">${r.pending.toLocaleString()}</td>`;
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      tableHost.appendChild(tbl);
      tableHost.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:10px',
        onClick: () => UI.downloadCsv('listing_overview.csv', ['OTA', 'Live', 'Listing %', 'Pending'],
          rows.map(r => ({ OTA: r.ota, Live: r.live, 'Listing %': r.pct, Pending: r.pending }))) }, 'Download CSV'));
    }
    recompute();

    // ── Deep dive ────────────────────────────────────────────────────────────
    target.appendChild(UI.el('div', { style: 'height:1px;background:#e7e9ee;margin:30px 0 18px' }));
    renderDeepDive(target);
  }

  // ── Deep-dive pivot (per channel) ───────────────────────────────────────────
  const CHANNELS = [
    { label: 'Booking.com', fetch: () => API.bcomTab('Live'), matrix: ['FH Status', 'Sub Status'] },
    { label: 'GoMMT', fetch: () => API.gommtTab('Live'), matrix: ['FH Live Prop', 'Sub Status'] },
    { label: 'GMB', fetch: () => API.gmbTab('New Tracker'), matrix: ['STATUS', 'GMB Sub Status'] },
    { label: 'Agoda', fetch: () => API.ota('agoda'), matrix: ['STATUS', 'Agoda Status'] },
    { label: 'Expedia', fetch: () => API.ota('expedia'), matrix: ['FH Status', 'Expedia Status'] },
    { label: 'Cleartrip', fetch: () => API.ota('cleartrip'), matrix: ['STATUS', 'CT Status'] },
    { label: 'Yatra', fetch: () => API.ota('yatra'), matrix: ['STATUS', 'Yatra Status'] },
    { label: 'EaseMyTrip', fetch: () => API.ota('easemytrip'), matrix: ['FH Status', 'EMT Status'] },
    { label: 'Ixigo', fetch: () => API.ota('ixigo'), matrix: ['STATUS', 'Ixigo Status'] },
    { label: 'Indigo', fetch: () => API.ota('indigo'), matrix: ['STATUS', 'Indigo Status'] },
  ];

  function renderDeepDive(target) {
    target.appendChild(UI.sectionLabel('Deep dive — pick a channel, then pivot with Rows / Columns / Filters'));
    const dd = UI.el('select', { style: 'max-width:260px;margin-bottom:8px' });
    dd.appendChild(UI.el('option', { value: '' }, '— choose a channel —'));
    CHANNELS.forEach((c, i) => dd.appendChild(UI.el('option', { value: String(i) }, c.label)));
    target.appendChild(dd);
    const host = UI.el('div', { style: 'margin-top:8px' });
    target.appendChild(host);
    dd.addEventListener('change', async () => {
      const c = CHANNELS[dd.value];
      if (!c) { host.innerHTML = ''; return; }
      host.innerHTML = ''; host.appendChild(UI.el('div', { class: 'splash' }, 'Loading ' + c.label + '…'));
      let payload;
      try { payload = ddCache[c.label] || (ddCache[c.label] = await c.fetch()); }
      catch (e) { host.innerHTML = ''; host.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }
      host.innerHTML = '';
      const cols = payload.cols;
      const recs = UI.toRecords(payload).filter(r => String(r[cols[0]] == null ? '' : r[cols[0]]).trim());
      window.OTA_renderMatrix(host,
        { id: 'overview_dd_' + c.label.toLowerCase().replace(/\W/g, '_'), label: c.label, matrixCols: c.matrix },
        { payload, mx: null }, cols, recs);
    });
  }

  window.PAGE_LISTING_OVERVIEW = { id: 'overview', label: 'Listing Overview', render: render };

})();
