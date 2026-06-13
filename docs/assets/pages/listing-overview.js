/**
 * Listing Overview — cross-OTA listing % against the live FH base.
 *
 * Base = BDC Hygiene "Inv" tab (cols A-E), churn excluded.
 * Listed = each OTA's "<OTA> Status" column == "Live"; everything else is a
 * pending reason. Computed fresh server-side (the sheet's own Listing Summary
 * tab is unreliable). Click an OTA row to see its pending-reason breakdown.
 */

(function () {

  let data = null;
  const ddCache = {};
  function barColor(p) { return p >= 80 ? '#16a34a' : p >= 50 ? '#b45309' : '#dc2626'; }

  // Channels for the deep-dive pivot. Each loads its live tab and seeds the
  // matrix with sensible default Rows/Columns (changeable in the UI).
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
    const sel = UI.el('select', { style: 'max-width:260px;margin-bottom:8px' });
    sel.appendChild(UI.el('option', { value: '' }, '— choose a channel —'));
    CHANNELS.forEach((c, i) => sel.appendChild(UI.el('option', { value: String(i) }, c.label)));
    target.appendChild(sel);
    const host = UI.el('div', { style: 'margin-top:8px' });
    target.appendChild(host);

    sel.addEventListener('change', async () => {
      const c = CHANNELS[sel.value];
      if (!c) { host.innerHTML = ''; return; }
      host.innerHTML = '';
      host.appendChild(UI.el('div', { class: 'splash' }, 'Loading ' + c.label + '…'));
      let payload;
      try { payload = ddCache[c.label] || (ddCache[c.label] = await c.fetch()); }
      catch (e) { host.innerHTML = ''; host.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }
      host.innerHTML = '';
      const cols = payload.cols;
      const recs = UI.toRecords(payload).filter(r => String(r[cols[0]] == null ? '' : r[cols[0]]).trim());
      const state = { payload: payload, mx: null };
      window.OTA_renderMatrix(host,
        { id: 'overview_dd_' + c.label.toLowerCase().replace(/\W/g, '_'), label: c.label, matrixCols: c.matrix },
        state, cols, recs);
    });
  }

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Listing Overview',
      subtitle: 'OTA listing % vs the live FH base (churn excluded)',
      onRefresh: async () => {
        UI.toast('Refreshing…');
        try { data = await API.listingOverview({ refresh: true }); render(target); UI.toast('Refreshed'); }
        catch (e) { UI.toast('Refresh failed: ' + e.message, true); }
      },
    }));

    try { UI.updateLoader('Computing listing %…'); data = data || (data = await API.listingOverview()); }
    catch (e) { target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }

    target.appendChild(UI.stats([`Live FH base (churn excluded): <b>${data.base.toLocaleString()}</b> properties`]));

    const rows = data.rows.slice().sort((a, b) => b.pct - a.pct);

    // ── % cards ─────────────────────────────────────────────────────────────────
    const cards = UI.el('div', { style: 'display:flex;flex-wrap:wrap;gap:12px;margin:8px 0 22px' });
    rows.forEach(r => {
      cards.appendChild(UI.el('div', {
        style: 'flex:1 1 150px;min-width:150px;border:1px solid #e4e4e7;border-radius:10px;padding:14px 16px;background:#fff',
      }, [
        UI.el('div', { style: 'font-size:13px;font-weight:600;color:#3f3f46;margin-bottom:8px' }, r.ota),
        UI.el('div', { style: `font-size:24px;font-weight:700;color:${barColor(r.pct)}` }, r.pct + '%'),
        UI.el('div', { style: 'height:6px;background:#eef2f6;border-radius:3px;overflow:hidden;margin:8px 0' },
          [UI.el('div', { style: `height:100%;width:${r.pct}%;background:${barColor(r.pct)}` })]),
        UI.el('div', { style: 'font-size:11px;color:#71717a' }, `Live ${r.live.toLocaleString()} · Pending ${r.pending.toLocaleString()}`),
      ]));
    });
    target.appendChild(cards);

    // ── Summary table (clickable) ───────────────────────────────────────────────
    const tbl = document.createElement('table');
    tbl.style.cssText = 'width:100%;border-collapse:collapse;font-size:13px;max-width:720px';
    tbl.innerHTML = '<thead><tr>' + ['OTA', 'Live', 'Listing %', 'Pending'].map((h, i) =>
      `<th style="text-align:${i === 0 ? 'left' : 'right'};padding:8px 10px;border-bottom:2px solid #e4e4e7;color:#71717a;font-size:11px;text-transform:uppercase">${h}</th>`).join('') + '</tr></thead>';
    const tbody = document.createElement('tbody');
    rows.forEach(r => {
      const tr = document.createElement('tr');
      tr.style.cssText = 'cursor:pointer;border-bottom:1px solid #f1f3f5';
      tr.onmouseenter = () => tr.style.background = '#f8fafc';
      tr.onmouseleave = () => tr.style.background = '';
      tr.innerHTML =
        `<td style="padding:10px;font-weight:600">${r.ota}</td>` +
        `<td style="padding:10px;text-align:right">${r.live.toLocaleString()}</td>` +
        `<td style="padding:10px;text-align:right;font-weight:700;color:${barColor(r.pct)}">${r.pct}%</td>` +
        `<td style="padding:10px;text-align:right;color:#b91c1c;font-weight:600">${r.pending.toLocaleString()}</td>`;
      tr.addEventListener('click', () => showBreakdown(r));
      tbody.appendChild(tr);
    });
    tbl.appendChild(tbody);
    target.appendChild(tbl);
    target.appendChild(UI.el('div', { style: 'font-size:12px;color:#a1a1aa;margin-top:8px' }, 'Click an OTA to see its pending reasons.'));

    const host = UI.el('div', { style: 'margin-top:20px' });
    target.appendChild(host);

    target.appendChild(UI.el('div', { style: 'height:1px;background:#e4e4e7;margin:28px 0 18px' }));
    renderDeepDive(target);

    function showBreakdown(r) {
      host.innerHTML = '';
      host.appendChild(UI.el('div', { style: 'font-weight:700;font-size:15px;margin-bottom:10px' },
        `${r.ota} — ${r.pending.toLocaleString()} pending (by reason)`));
      const bt = document.createElement('table');
      bt.style.cssText = 'border-collapse:collapse;font-size:13px;max-width:520px';
      bt.innerHTML = '<thead><tr>' +
        `<th style="text-align:left;padding:7px 12px;border-bottom:2px solid #e4e4e7;color:#71717a;font-size:11px;text-transform:uppercase">Pending status</th>` +
        `<th style="text-align:right;padding:7px 12px;border-bottom:2px solid #e4e4e7;color:#71717a;font-size:11px;text-transform:uppercase">Count</th></tr></thead>`;
      const tb = document.createElement('tbody');
      (r.breakdown || []).forEach(b => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td style="padding:7px 12px;border-bottom:1px solid #f1f3f5">${UI.escapeHtml(b.status)}</td>` +
          `<td style="padding:7px 12px;text-align:right;border-bottom:1px solid #f1f3f5">${b.count.toLocaleString()}</td>`;
        tb.appendChild(tr);
      });
      bt.appendChild(tb);
      host.appendChild(bt);
    }
  }

  window.PAGE_LISTING_OVERVIEW = { id: 'overview', label: 'Listing Overview', render: render };

})();
