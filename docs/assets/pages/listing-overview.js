/**
 * Listing Overview — surfaces the BDC Hygiene "Listing Summary" tab:
 *   - % listed per OTA (against the live FH base) as cards
 *   - the full status breakdown (Live / Not Live / Pending / Pending at OTA …)
 *
 * Data shape from API.listingOverview():
 *   { pcts:    ['1610','97.33%',...,'14.09%'],     // col0 = base count
 *     headers: ['Prop Set','Agoda',...,'Total'],
 *     categories: [ ['Live','1567',...], ['Not Live',...], ... ] }
 */

(function () {

  let data = null;

  function pctNum(s) { const m = String(s).match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : null; }
  function barColor(p) { return p >= 80 ? '#16a34a' : p >= 50 ? '#b45309' : '#dc2626'; }

  async function render(target) {
    target.innerHTML = '';
    target.appendChild(UI.pageHeader({
      title: 'Listing Overview',
      subtitle: 'OTA listing % vs the live FH base (from Listing Summary)',
      onRefresh: async () => {
        UI.toast('Refreshing…');
        try { data = await API.listingOverview({ refresh: true }); render(target); UI.toast('Refreshed'); }
        catch (e) { UI.toast('Refresh failed: ' + e.message, true); }
      },
    }));

    try { UI.updateLoader('Loading listing summary…'); data = data || (data = await API.listingOverview()); }
    catch (e) { target.appendChild(UI.el('div', { class: 'splash' }, 'Could not load: ' + e.message)); return; }

    const { pcts, headers, categories } = data;
    const base = pcts[0];
    const catRow = (label) => categories.find(r => String(r[0]).trim().toLowerCase() === label.toLowerCase()) || [];
    const liveRow = catRow('Live'), notLiveRow = catRow('Not Live'), pendRow = catRow('Pending');

    target.appendChild(UI.stats([`Live FH base (Prop Set): <b>${base}</b> properties`]));

    // ── OTA % cards (skip the leading "Prop Set" label col and trailing "Total") ─
    const cards = UI.el('div', { style: 'display:flex;flex-wrap:wrap;gap:12px;margin:8px 0 24px' });
    const otaCols = [];
    for (let j = 1; j < headers.length; j++) {
      const name = String(headers[j]).trim();
      if (!name || name.toLowerCase() === 'total') continue;
      const p = pctNum(pcts[j]);
      if (p === null) continue;                       // skip OTAs with no % (inactive)
      otaCols.push({ j, name, p });
    }
    otaCols.sort((a, b) => b.p - a.p).forEach(({ j, name, p }) => {
      cards.appendChild(UI.el('div', {
        style: 'flex:1 1 150px;min-width:150px;border:1px solid #e4e4e7;border-radius:10px;padding:14px 16px;background:#fff',
      }, [
        UI.el('div', { style: 'font-size:13px;font-weight:600;color:#3f3f46;margin-bottom:8px' }, name),
        UI.el('div', { style: `font-size:24px;font-weight:700;color:${barColor(p)}` }, p + '%'),
        UI.el('div', { style: 'height:6px;background:#eef2f6;border-radius:3px;overflow:hidden;margin:8px 0' },
          [UI.el('div', { style: `height:100%;width:${p}%;background:${barColor(p)}` })]),
        UI.el('div', { style: 'font-size:11px;color:#71717a' },
          `Live ${liveRow[j] || 0} · Not Live ${notLiveRow[j] || 0} · Pending ${pendRow[j] || 0}`),
      ]));
    });
    target.appendChild(cards);

    // ── Full status breakdown table ─────────────────────────────────────────────
    target.appendChild(UI.el('div', { class: 'page-sub', style: 'font-weight:600;color:#18181b;margin-bottom:8px' },
      'Status breakdown'));
    const tbl = document.createElement('table');
    tbl.style.cssText = 'width:100%;border-collapse:collapse;font-size:13px';
    const thead = '<thead><tr>' + headers.map((h, i) =>
      `<th style="text-align:${i === 0 ? 'left' : 'right'};padding:8px 10px;border-bottom:2px solid #e4e4e7;` +
      `color:#71717a;font-size:11px;text-transform:uppercase;letter-spacing:.03em;white-space:nowrap">${UI.escapeHtml(h)}</th>`).join('') + '</tr></thead>';
    // percentage row first (emphasised), then each category row
    const pctTr = '<tr style="background:#fafafa">' + pcts.map((c, i) =>
      `<td style="padding:8px 10px;text-align:${i === 0 ? 'left' : 'right'};font-weight:700;` +
      `border-bottom:1px solid #e4e4e7">${i === 0 ? 'Listing %' : UI.escapeHtml(c)}</td>`).join('') + '</tr>';
    const bodyRows = categories.map(r => '<tr>' + r.map((c, i) =>
      `<td style="padding:8px 10px;text-align:${i === 0 ? 'left' : 'right'};border-bottom:1px solid #f1f3f5;` +
      `${i === 0 ? 'font-weight:600' : 'color:#3f3f46'}">${UI.escapeHtml(c)}</td>`).join('') + '</tr>').join('');
    tbl.innerHTML = thead + '<tbody>' + pctTr + bodyRows + '</tbody>';
    target.appendChild(tbl);

    target.appendChild(UI.el('button', { class: 'btn btn-sm', style: 'margin-top:14px',
      onClick: () => UI.downloadCsv('listing_summary.csv', headers, [pcts].concat(categories)) }, 'Download CSV'));
  }

  window.PAGE_LISTING_OVERVIEW = { id: 'overview', label: 'Listing Overview', render: render };

})();
