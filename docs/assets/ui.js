/**
 * Shared UI primitives — tables, multiselects, filters, drill-down panels.
 * Vanilla DOM, no dependencies.
 */

const UI = (() => {

  // ── DOM helpers ─────────────────────────────────────────────────────────
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
  function el(tag, attrs, kids) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === 'class') e.className = attrs[k];
        else if (k === 'style') e.style.cssText = attrs[k];
        else if (k.indexOf('on') === 0) e.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
        else if (k === 'html') e.innerHTML = attrs[k];
        else e.setAttribute(k, attrs[k]);
      }
    }
    if (kids != null) {
      if (Array.isArray(kids)) kids.forEach(k => k != null && e.appendChild(typeof k === 'string' ? document.createTextNode(k) : k));
      else if (typeof kids === 'string') e.textContent = kids;
      else e.appendChild(kids);
    }
    return e;
  }
  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // ── Toast ──────────────────────────────────────────────────────────────
  let toastTimer = null;
  function toast(msg, isError) {
    const t = $('#toast');
    t.textContent = msg;
    t.className = (isError ? 'error ' : '') + 'show';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.className = isError ? 'error' : '', 3500);
  }

  // ── Page chrome (title + refresh) ──────────────────────────────────────
  function pageHeader(opts) {
    const wrap = el('div', { class: 'page-head' });
    wrap.appendChild(el('div', null, [
      el('div', { class: 'page-title' }, opts.title),
      el('div', { class: 'page-sub' }, opts.subtitle || ''),
    ]));
    if (opts.onRefresh) {
      wrap.appendChild(el('button', { class: 'btn', onClick: opts.onRefresh }, 'Refresh'));
    }
    return wrap;
  }

  function stats(parts) {
    const div = el('div', { class: 'stats' });
    div.innerHTML = parts.filter(Boolean).join(' · ');
    return div;
  }

  function sectionLabel(text) {
    return el('div', { class: 'section-label' }, text);
  }

  // ── Tabs ───────────────────────────────────────────────────────────────
  function tabsView(tabs, container) {
    // tabs = [{ id, label, render(target) }]
    const bar = el('div', { class: 'tabs' });
    const body = el('div');
    let active = tabs[0].id;

    function select(id) {
      active = id;
      bar.querySelectorAll('.tab').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === id);
      });
      body.innerHTML = '';
      const t = tabs.find(x => x.id === id);
      if (t && t.render) t.render(body);
    }

    tabs.forEach(t => {
      bar.appendChild(el('button', {
        class: 'tab' + (t.id === active ? ' active' : ''),
        'data-tab': t.id,
        onClick: () => select(t.id),
      }, t.label));
    });

    container.appendChild(bar);
    container.appendChild(body);
    select(active);
  }

  // ── Metric tiles ───────────────────────────────────────────────────────
  function metricRow(items) {
    const row = el('div', { class: 'metric-row' });
    items.forEach(it => {
      row.appendChild(el('div', { class: 'metric' }, [
        el('div', { class: 'metric-label' }, it.label),
        el('div', { class: 'metric-value' }, String(it.value)),
      ]));
    });
    return row;
  }

  // ── Custom multiselect ─────────────────────────────────────────────────
  // opts: { label, options: [...], selected: [...], onChange: (vals)=>void, placeholder }
  function multiselect(opts) {
    const sel = new Set(opts.selected || []);
    const wrap = el('div', { class: 'ms' });
    const trigger = el('div', { class: 'ms-trigger', tabindex: '0' });
    const panel = el('div', { class: 'ms-panel' });
    const searchInput = el('input', { type: 'search', placeholder: 'Filter…' });
    const ctrl = el('div', { class: 'ms-controls' }, searchInput);
    const list = el('div', { class: 'ms-list' });
    const actions = el('div', { class: 'ms-actions' });
    const allBtn = el('button', { class: 'btn btn-sm', onClick: () => { opts.options.forEach(o => sel.add(o)); refresh(true); } }, 'Select all');
    const clrBtn = el('button', { class: 'btn btn-sm', onClick: () => { sel.clear(); refresh(true); } }, 'Clear');
    actions.appendChild(allBtn); actions.appendChild(clrBtn);

    panel.appendChild(ctrl); panel.appendChild(list); panel.appendChild(actions);
    wrap.appendChild(trigger); wrap.appendChild(panel);

    function refresh(emit) {
      // Trigger text
      if (sel.size === 0) {
        trigger.innerHTML = '<span class="placeholder">' + escapeHtml(opts.placeholder || ('All ' + (opts.label || ''))) + '</span>';
      } else if (sel.size <= 2) {
        trigger.textContent = Array.from(sel).join(', ');
      } else {
        trigger.textContent = sel.size + ' selected';
      }
      // List
      const q = (searchInput.value || '').toLowerCase();
      list.innerHTML = '';
      opts.options.forEach(opt => {
        if (q && !String(opt).toLowerCase().includes(q)) return;
        const checked = sel.has(opt);
        const row = el('label', { class: 'ms-opt' }, [
          el('input', {
            type: 'checkbox',
            onChange: (e) => {
              if (e.target.checked) sel.add(opt); else sel.delete(opt);
              refresh(true);
            },
          }),
          el('span', null, String(opt)),
        ]);
        row.querySelector('input').checked = checked;
        list.appendChild(row);
      });
      if (emit && opts.onChange) opts.onChange(Array.from(sel));
    }

    trigger.addEventListener('click', () => wrap.classList.toggle('open'));
    document.addEventListener('click', (e) => {
      if (!wrap.contains(e.target)) wrap.classList.remove('open');
    });
    searchInput.addEventListener('input', () => refresh(false));

    refresh(false);
    return { el: wrap, getValue: () => Array.from(sel), setValue: (v) => { sel.clear(); v.forEach(x => sel.add(x)); refresh(true); } };
  }

  // ── Renderable HTML table ─────────────────────────────────────────────
  // opts: { columns: [{key, label, fmt?, cellClass?}], rows, onRowClick?, selectedRow?, totalRow?, height? }
  function table(opts) {
    const wrap = el('div', { class: 'table-wrap', style: opts.height ? `max-height:${opts.height}px` : '' });
    const t = el('table');
    const thead = el('thead');
    const trh = el('tr');
    opts.columns.forEach(c => trh.appendChild(el('th', null, c.label)));
    thead.appendChild(trh);
    t.appendChild(thead);

    const tbody = el('tbody');
    const totalIdx = opts.totalRow ? opts.rows.length : -1;
    const rowsAll = opts.totalRow ? [...opts.rows, opts.totalRow] : opts.rows;

    rowsAll.forEach((row, i) => {
      const tr = el('tr');
      if (i === totalIdx) tr.className = 'total-row';
      else if (i === opts.selectedRow) tr.className = 'selected clickable';
      else if (opts.onRowClick) tr.className = 'clickable';

      opts.columns.forEach(c => {
        let raw = row[c.key];
        const txt = c.fmt ? c.fmt(raw, row, i) : (raw == null ? '' : String(raw));
        const td = el('td', { class: c.cellClass ? c.cellClass(raw, row, i) : '' });
        td.innerHTML = txt;
        tr.appendChild(td);
      });

      if (opts.onRowClick && i !== totalIdx) {
        tr.addEventListener('click', () => opts.onRowClick(rowsAll[i], i));
      }

      tbody.appendChild(tr);
    });

    t.appendChild(tbody);
    wrap.appendChild(t);
    return wrap;
  }

  // ── Search/toolbar above tables ───────────────────────────────────────
  function toolbar(opts) {
    const bar = el('div', { class: 'toolbar' });
    const input = el('input', { type: 'search', placeholder: opts.placeholder || 'Search…' });
    input.addEventListener('input', () => opts.onChange(input.value));
    bar.appendChild(input);
    bar.appendChild(el('span', { class: 'count', id: opts.countId || '' }, opts.countText || ''));
    if (opts.actions) opts.actions.forEach(a => bar.appendChild(a));
    return { el: bar, input };
  }

  // ── Download CSV ──────────────────────────────────────────────────────
  function downloadCsv(filename, columns, rows) {
    const escape = (v) => {
      const s = String(v == null ? '' : v).replace(/"/g, '""');
      return /[",\n]/.test(s) ? `"${s}"` : s;
    };
    const header = columns.join(',');
    const body = rows.map(r => columns.map(c => escape(r[c])).join(',')).join('\n');
    const csv = header + '\n' + body;
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }

  // ── DataFrame helpers (cols/rows → records) ───────────────────────────
  function toRecords(payload) {
    const cols = payload.cols || [];
    return (payload.rows || []).map(r => {
      const obj = {};
      cols.forEach((c, i) => { obj[c] = r[i] == null ? '' : r[i]; });
      return obj;
    });
  }

  // ── Loading overlay ─────────────────────────────────────────────────────
  let loaderCount = 0;

  function showLoader(msg) {
    loaderCount++;
    if (loaderCount > 1) { updateLoader(msg); return; }
    const overlay = document.createElement('div');
    overlay.id = 'loader-overlay';
    overlay.innerHTML =
      '<div class="loader-bg"></div>' +
      '<div class="loader-card">' +
        '<div class="loader-spinner"></div>' +
        '<div class="loader-msg">' + escapeHtml(msg || 'Loading\u2026') + '</div>' +
      '</div>';
    document.body.appendChild(overlay);
  }

  function updateLoader(msg) {
    const el = document.getElementById('loader-overlay');
    if (el) {
      const m = el.querySelector('.loader-msg');
      if (m) m.textContent = msg || '';
    }
  }

  function hideLoader() {
    loaderCount = Math.max(0, loaderCount - 1);
    if (loaderCount === 0) {
      const el = document.getElementById('loader-overlay');
      if (el) el.remove();
    }
  }

  return { $, $$, el, escapeHtml, toast, pageHeader, stats, sectionLabel,
           tabsView, metricRow, multiselect, table, toolbar, downloadCsv, toRecords,
           showLoader, updateLoader, hideLoader };
})();
