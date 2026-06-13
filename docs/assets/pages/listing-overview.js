/**
 * Listing Overview — cross-OTA listing % against the live FH base.
 *
 * Base = BDC Hygiene "Inv" tab (cols A-E), churn excluded (computed in Code.gs).
 * For each OTA: listed = base ids present in its live tab, pending = the rest.
 * Click an OTA row to see its pending listings (with FH status).
 */

(function () {

  let overview = null;
  const pendingCache = {};

  function barColor(pct) { return pct >= 80 ? '#16a34a' : pct >= 50 ? '#b45309' : '#dc2626'; }

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Listing Overview',
      subtitle: 'OTA listing % vs the live FH base (churn excluded)',
      onRefresh: async () => {
        UI.toast('Refreshing…');
        try { overview = await API.listingOverview({ refresh: true }); render(target); UI.toast('Refreshed'); }
        catch (e) { UI.toast('Refresh failed: ' + e.message, true); }
      },
    }));

    let data;
    try { UI.updateLoader('Computing listing %…'); data = overview || (overview = await API.listingOverview()); }
    catch (e) { target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }

    target.appendChild(UI.stats([`Live FH base (churn excluded): <b>${data.base.toLocaleString()}</b> properties`]));

    // ── Summary table ─────────────────────────────────────────────────────────
    const rows = data.rows.slice().sort((a, b) => b.pct - a.pct);
    const tbl = document.createElement('table');
    tbl.style.cssText = 'width:100%;border-collapse:collapse;font-size:13px;margin-top:8px;max-width:720px';
    tbl.innerHTML = '<thead><tr>' +
      ['OTA', 'Listed', 'Listing %', 'Pending'].map(h =>
        `<th style="text-align:left;padding:8px 10px;border-bottom:2px solid #e4e4e7;color:#71717a;font-size:11px;text-transform:uppercase;letter-spacing:.04em">${h}</th>`).join('') +
      '</tr></thead>';
    const tbody = document.createElement('tbody');
    rows.forEach(r => {
      const tr = document.createElement('tr');
      tr.style.cssText = 'cursor:pointer;border-bottom:1px solid #f1f3f5';
      tr.onmouseenter = () => tr.style.background = '#f8fafc';
      tr.onmouseleave = () => tr.style.background = '';
      tr.innerHTML =
        `<td style="padding:10px;font-weight:600">${r.ota}</td>` +
        `<td style="padding:10px">${r.listed.toLocaleString()}</td>` +
        `<td style="padding:10px"><div style="display:flex;align-items:center;gap:8px">` +
          `<div style="flex:1;max-width:170px;height:8px;background:#eef2f6;border-radius:4px;overflow:hidden">` +
          `<div style="height:100%;width:${r.pct}%;background:${barColor(r.pct)}"></div></div>` +
          `<span style="font-weight:700;min-width:46px">${r.pct}%</span></div></td>` +
        `<td style="padding:10px;color:#b91c1c;font-weight:600">${r.pending.toLocaleString()}</td>`;
      tr.addEventListener('click', () => showPending(r));
      tbody.appendChild(tr);
    });
    tbl.appendChild(tbody);
    target.appendChild(tbl);
    target.appendChild(UI.el('div', { style: 'font-size:12px;color:#a1a1aa;margin-top:8px' },
      'Click an OTA row to see its pending listings.'));

    const host = UI.el('div', { style: 'margin-top:22px' });
    target.appendChild(host);

    async function showPending(r) {
      host.innerHTML = '';
      host.appendChild(UI.el('div', { class: 'splash' }, `Loading ${r.ota} pending…`));
      let pd;
      try { pd = pendingCache[r.key] || (pendingCache[r.key] = await API.listingPending(r.key)); }
      catch (e) { host.innerHTML = ''; host.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }

      host.innerHTML = '';
      host.appendChild(UI.el('div', { style: 'font-weight:700;font-size:15px;margin-bottom:10px' },
        `${r.ota} — ${r.pending.toLocaleString()} pending listings`));
      const records = UI.toRecords(pd);
      const tb = UI.toolbar({ placeholder: 'Search pending…', countText: records.length + ' rows',
        onChange: (v) => redraw(v) });
      host.appendChild(tb.el);
      const th = UI.el('div');
      host.appendChild(th);
      function redraw(q) {
        let view = records;
        if (q) { const s = q.toLowerCase(); view = records.filter(x => Object.values(x).some(v => String(v).toLowerCase().includes(s))); }
        tb.el.querySelector('.count').textContent = `${view.length.toLocaleString()} rows`;
        th.innerHTML = '';
        th.appendChild(UI.table({ columns: pd.cols.map(c => ({ key: c, label: c })), rows: view, height: 460 }));
        th.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:8px',
          onClick: () => UI.downloadCsv(r.key + '_pending.csv', pd.cols, view) }, 'Download CSV'));
      }
      redraw('');
    }
  }

  window.PAGE_LISTING_OVERVIEW = { id: 'overview', label: 'Listing Overview', render: render };

})();
