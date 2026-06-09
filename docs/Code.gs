/**
 * OTA Handler — Google Apps Script backend
 *
 * Deploy as Web App:
 *   - Execute as: Me (the script owner — you)
 *   - Who has access: Anyone (the HTML page will call this URL)
 *
 * The team does NOT need direct sheet access. This script reads sheets using
 * the script owner's identity, then returns JSON to the browser.
 *
 * Endpoints (all GET via doGet):
 *   ?action=ping                       → { ok: true }
 *   ?action=bcom                       → first tab of BCOM_SHEET as { cols, rows }
 *   ?action=bcom_tabs                  → { tabs: [name, ...] }
 *   ?action=bcom_tab&name=Live         → named tab as { cols, rows }
 *   ?action=gommt / gommt_tabs / gommt_tab → same shape, GoMMT sheet
 *   ?action=listing                    → Listing Tracker (gid 158406294) as { cols, rows }
 *   ?action=crs                        → CRS DATA tab as { cols, rows }
 *   ?action=dashboard                  → Prop Level Dashboard as { rows } (raw 2-D)
 *   ?action=log                        → Last Checked summary as { cols, rows }
 *   ?action=details                    → Last Run Details as { cols, rows }
 *
 * Cache: 1 hour via Apps Script CacheService. Add &refresh=1 to bypass.
 */

// ── Sheet IDs (mirror sheets.py constants) ─────────────────────────────────
const CRS_SHEET_ID    = '1H2lP2zn4Ydeyex504DzmfBwXAX0Ip2H4SIu92DylRLw';
const BCOM_SHEET_ID   = '1vjm8BX1QZKMqXiLjbokCD0R91JvlscXcg5812p_IolI';
const GOMMT_SHEET_ID  = '1Pr2iEC7UvI7sWgwx4qQGQcO9Iw3dyzBqLpAr2mrQvKc';
const GMB_SHEET_ID    = '16awDYKs1jdR0x5VDJTo8CokB_fqqjr7JRpmRY0tv4Fk';
const DASH_SHEET_ID   = '1ND1SBFknF1aD4iVA_1XtwXK_u7wEonFUVYesv5sZRXU';
const LISTING_GID     = 158406294;

const CRS_TAB         = 'CRS DATA';
const DASH_TAB        = 'Prop Level Dashboard';
const LOG_TAB         = 'Last Checked';
const DETAIL_TAB      = 'Last Run Details';

const CACHE_TTL_S     = 3600;   // 1 hour

// ── BDC Hygiene scrape queue ───────────────────────────────────────────────
// The "BDC Hygiene" sheet holds the property list + result columns E–T (the
// same sheet hygiene_scraper.py wrote to). We add two helper tabs in it:
//   'Hygiene Jobs'    — the on-demand job queue (one row per queued property)
//   (worker presence is kept in Script Properties, not a tab)
// Set WORKER_TOKEN in Project Settings → Script properties; the local workers
// send it on every mutating call.
const HYG_SHEET_ID    = '1VkFA4keBAT3tG5NkZwmSNRbLZJgx2neOhZ7Zuj2z_98';
const HYG_TAB         = 'BDC Hygiene';
const HYG_JOBS_TAB    = 'Hygiene Jobs';
const HYG_JOB_HEADERS = ['ID', 'BDC ID', 'Prop Name', 'Sheet Row', 'Submitted By',
                         'Status', 'Log', 'Error', 'Updated At', 'Result JSON'];

// ── Entry point ────────────────────────────────────────────────────────────
function doGet(e) {
  const p = (e && e.parameter) || {};
  const action = p.action || 'ping';
  const refresh = p.refresh === '1' || p.refresh === 'true';

  try {
    const result = route(action, p, refresh);
    return jsonResponse({ ok: true, data: result });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err && err.message || err) });
  }
}

// ── POST entry — used for saving Mapping Checker runs (large payloads) ────
function doPost(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || '';
    const body = (e && e.postData && e.postData.contents) ? JSON.parse(e.postData.contents) : {};
    if (action === 'save_mapping_run') {
      return jsonResponse({ ok: true, data: saveMappingRun(body) });
    }
    // ── Hygiene scrape queue ──────────────────────────────────────────────
    if (action === 'hyg_enqueue')   return jsonResponse({ ok: true, data: hygEnqueue(body) });
    if (action === 'hyg_claim')     return jsonResponse({ ok: true, data: hygClaim(body) });
    if (action === 'hyg_progress')  return jsonResponse({ ok: true, data: hygProgress(body) });
    if (action === 'hyg_result')    return jsonResponse({ ok: true, data: hygResult(body) });
    if (action === 'hyg_heartbeat') return jsonResponse({ ok: true, data: hygHeartbeat(body) });
    return jsonResponse({ ok: false, error: 'Unknown POST action: ' + action });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err && err.message || err) });
  }
}

// Append a summary row to LOG_TAB and overwrite DETAIL_TAB with flattened rows.
// Body shape: { runBy, fileName, meta:{...counts}, results:{ rr:[...], obpv:[...], ... } }
function saveMappingRun(body) {
  const ts = Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'Asia/Kolkata',
                                  'yyyy-MM-dd HH:mm');
  const runBy = body.runBy || 'anonymous';
  const fileName = body.fileName || '';
  const meta = body.meta || {};
  const results = body.results || {};

  const ss = SpreadsheetApp.openById(CRS_SHEET_ID);

  // ── 1. LOG_TAB summary row ──────────────────────────────────────────────
  const SUMMARY_HEADERS = [
    'Run At', 'Run By', 'File Name',
    'CRS Properties', 'SU Analyzed', 'Excluded',
    'rr', 'apg', 'obpv', 'obpoe', 'obpom',
    'rpmicp', 'rpmimap', 'rpmi', 'rpex',
    'chlive', 'chdead', 'ncrs',
  ];
  const CHECK_KEYS = ['rr','apg','obpv','obpoe','obpom','rpmicp','rpmimap','rpmi','rpex','chlive','chdead','ncrs'];

  let logWs = ss.getSheetByName(LOG_TAB);
  if (!logWs) {
    logWs = ss.insertSheet(LOG_TAB);
    logWs.appendRow(SUMMARY_HEADERS);
  } else if (logWs.getLastRow() === 0) {
    logWs.appendRow(SUMMARY_HEADERS);
  }
  logWs.appendRow([
    ts, runBy, fileName,
    meta.crs_props || '', meta.total_analyzed || '', meta.su_excluded || '',
    (results.rr || []).length,
    (results.apg || []).length,
    (results.obpv || []).length,
    (results.obpoe || []).length,
    (results.obpom || []).length,
    (results.rpmicp || []).length,
    (results.rpmimap || []).length,
    (results.rpmi || []).length,
    (results.rpex || []).length,
    (results.chlive || []).length,
    (results.chdead || []).length,
    (results.ncrs || []).length,
  ]);

  // ── 2. DETAIL_TAB — overwrite with flattened rows ───────────────────────
  // Flatten { rr:[{...}], ... } → [{ Run At, Run By, Check, ...row }, ...]
  // Then bulk-write as a 2-D array (way faster than appendRow per row).
  const fieldSet = new Set(['Run At', 'Run By', 'Check']);
  const flat = [];
  CHECK_KEYS.forEach(k => {
    const arr = results[k] || [];
    arr.forEach(row => {
      const flatRow = { 'Run At': ts, 'Run By': runBy, 'Check': k };
      Object.keys(row).forEach(key => {
        // Skip internal helper objects (the engine uses _rm / _rt with nested data)
        let v = row[key];
        if (v && typeof v === 'object') v = JSON.stringify(v);
        flatRow[key] = v == null ? '' : v;
        fieldSet.add(key);
      });
      flat.push(flatRow);
    });
  });

  let detailWs = ss.getSheetByName(DETAIL_TAB);
  if (!detailWs) {
    detailWs = ss.insertSheet(DETAIL_TAB);
  }
  detailWs.clear();

  const detailHeaders = Array.from(fieldSet);
  if (flat.length === 0) {
    detailWs.getRange(1, 1, 1, 4).setValues([['Run At', 'Run By', 'Check', 'Note']]);
    detailWs.getRange(2, 1, 1, 4).setValues([[ts, runBy, '—', 'No issues found']]);
  } else {
    const data = [detailHeaders];
    flat.forEach(row => {
      data.push(detailHeaders.map(h => row[h] == null ? '' : row[h]));
    });
    detailWs.getRange(1, 1, data.length, detailHeaders.length).setValues(data);
  }

  // Invalidate the cached reads so the next GET picks up the new data
  CacheService.getScriptCache().removeAll(['log', 'details']);

  return { savedAt: ts, totalRows: flat.length };
}

// ── Router ─────────────────────────────────────────────────────────────────
function route(action, p, refresh) {
  switch (action) {
    case 'ping':        return { time: new Date().toISOString() };

    case 'bcom':        return cachedSheetFirstTab('bcom', BCOM_SHEET_ID, refresh);
    case 'bcom_tabs':   return cachedTabList('bcom_tabs', BCOM_SHEET_ID, refresh);
    case 'bcom_tab':    return cachedSheetNamedTab('bcom_tab', BCOM_SHEET_ID, p.name, refresh);

    case 'gommt':       return cachedSheetFirstTab('gommt', GOMMT_SHEET_ID, refresh);
    case 'gommt_tabs':  return cachedTabList('gommt_tabs', GOMMT_SHEET_ID, refresh);
    case 'gommt_tab':   return cachedSheetNamedTab('gommt_tab', GOMMT_SHEET_ID, p.name, refresh);

    case 'gmb':         return cachedSheetFirstTab('gmb', GMB_SHEET_ID, refresh);
    case 'gmb_tabs':    return cachedTabList('gmb_tabs', GMB_SHEET_ID, refresh);
    case 'gmb_tab':     return cachedSheetNamedTab('gmb_tab', GMB_SHEET_ID, p.name, refresh);

    case 'listing':     return cachedSheetByGid('listing', DASH_SHEET_ID, LISTING_GID, refresh);

    case 'crs':         return cachedSheetByName('crs', CRS_SHEET_ID, CRS_TAB, refresh);
    case 'dashboard':   return cachedSheetByNameRaw('dashboard', DASH_SHEET_ID, DASH_TAB, refresh);

    case 'log':         return cachedSheetByName('log', CRS_SHEET_ID, LOG_TAB, refresh);
    case 'details':     return cachedSheetByName('details', CRS_SHEET_ID, DETAIL_TAB, refresh);

    // Hygiene scrape — live job list for the page (never cached)
    case 'hyg_jobs':    return hygJobs();
    // Version probe — confirm which Code.gs is actually deployed.
    case 'hyg_version': return { version: 'p1-partial-2026-06-09b' };

    default:
      throw new Error('Unknown action: ' + action);
  }
}

// ── Cached sheet readers ────────────────────────────────────────────────────
function cachedTabList(cacheKey, sheetId, refresh) {
  return withCache(cacheKey, refresh, () => {
    const ss = SpreadsheetApp.openById(sheetId);
    return { tabs: ss.getSheets().map(s => s.getName()) };
  });
}

function cachedSheetFirstTab(cacheKey, sheetId, refresh) {
  return withCache(cacheKey, refresh, () => {
    const ss = SpreadsheetApp.openById(sheetId);
    const ws = ss.getSheets()[0];
    return sheetToColsRows(ws);
  });
}

function cachedSheetNamedTab(cacheKey, sheetId, tabName, refresh) {
  if (!tabName) throw new Error('Missing tab name');
  const key = cacheKey + '_' + tabName;
  return withCache(key, refresh, () => {
    const ss = SpreadsheetApp.openById(sheetId);
    const ws = ss.getSheetByName(tabName);
    if (!ws) {
      const available = ss.getSheets().map(s => s.getName());
      throw new Error('Tab "' + tabName + '" not found. Available: ' + available.join(', '));
    }
    return sheetToColsRows(ws);
  });
}

function cachedSheetByName(cacheKey, sheetId, tabName, refresh) {
  return cachedSheetNamedTab(cacheKey, sheetId, tabName, refresh);
}

function cachedSheetByNameRaw(cacheKey, sheetId, tabName, refresh) {
  return withCache(cacheKey, refresh, () => {
    const ss = SpreadsheetApp.openById(sheetId);
    const ws = ss.getSheetByName(tabName);
    if (!ws) throw new Error('Tab "' + tabName + '" not found.');
    return { rows: ws.getDataRange().getValues() };   // raw 2-D array
  });
}

function cachedSheetByGid(cacheKey, sheetId, gid, refresh) {
  return withCache(cacheKey, refresh, () => {
    const ss = SpreadsheetApp.openById(sheetId);
    const sheets = ss.getSheets();
    let target = null;
    for (let i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId() === gid) { target = sheets[i]; break; }
    }
    if (!target) {
      const available = sheets.map(s => '[' + s.getSheetId() + '] ' + s.getName());
      throw new Error('Tab with gid ' + gid + ' not found. Available: ' + available.join(', '));
    }
    return sheetToColsRows(target);
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────
function sheetToColsRows(ws) {
  const all = ws.getDataRange().getValues();
  if (!all || all.length === 0) return { cols: [], rows: [] };
  const headers = all[0].map(h => String(h == null ? '' : h));
  // Deduplicate headers (mirrors sheets.py _rows_to_df behaviour)
  const seen = {};
  const cols = headers.map(h => {
    if (seen[h] == null) { seen[h] = 0; return h; }
    seen[h] += 1;
    return h + '.' + seen[h];
  });
  const rows = all.slice(1).map(r => r.map(v => v == null ? '' : v));
  return { cols: cols, rows: rows };
}

function withCache(key, refresh, fn) {
  const cache = CacheService.getScriptCache();
  if (!refresh) {
    const hit = cache.get(key);
    if (hit) {
      try { return JSON.parse(hit); } catch (_) { /* fall through */ }
    }
  }
  const result = fn();
  try { cache.put(key, JSON.stringify(result), CACHE_TTL_S); } catch (_) { /* >100KB ignored */ }
  return result;
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ── Hygiene scrape queue ───────────────────────────────────────────────────
function hygCheckToken_(body) {
  const expected = PropertiesService.getScriptProperties().getProperty('WORKER_TOKEN') || '';
  if (!expected || (body && body.token) !== expected) {
    throw new Error('Bad worker token');
  }
}

function hygTs_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'Asia/Kolkata', 'yyyy-MM-dd HH:mm:ss');
}

function hygJobsSheet_() {
  const ss = SpreadsheetApp.openById(HYG_SHEET_ID);
  let ws = ss.getSheetByName(HYG_JOBS_TAB);
  if (!ws) { ws = ss.insertSheet(HYG_JOBS_TAB); ws.appendRow(HYG_JOB_HEADERS); }
  else if (ws.getLastRow() === 0) { ws.appendRow(HYG_JOB_HEADERS); }
  return ws;
}

// BDC ID -> { row, propName } from the BDC Hygiene tab (row = 1-based sheet row).
function hygPropIndex_() {
  const ws = SpreadsheetApp.openById(HYG_SHEET_ID).getSheetByName(HYG_TAB);
  if (!ws) throw new Error('Tab "' + HYG_TAB + '" not found');
  const values = ws.getDataRange().getValues();
  const headers = values[0].map(h => String(h == null ? '' : h).toLowerCase());
  let bdcCol = -1, nameCol = -1;
  for (let i = 0; i < headers.length; i++) {
    if (bdcCol < 0 && /bdc\s*id/.test(headers[i])) bdcCol = i;
    if (nameCol < 0 && /(prop|hotel).*name/.test(headers[i])) nameCol = i;
  }
  if (bdcCol < 0) throw new Error('No "BDC ID" column found in ' + HYG_TAB);
  const map = {};
  for (let r = 1; r < values.length; r++) {
    const id = String(values[r][bdcCol] == null ? '' : values[r][bdcCol]).trim().replace(/\.0+$/, '');
    if (id && !map[id]) map[id] = { row: r + 1, propName: nameCol >= 0 ? String(values[r][nameCol] || '') : '' };
  }
  return map;
}

function hygEnqueue(body) {
  // Shared pool: all team members use one BDC account, so any worker can run
  // any job. No per-person name needed — jobs go into one common queue.
  const submittedBy = String((body && body.submittedBy) || '').trim();
  const ids = (body && body.bdcIds) || [];
  if (!ids.length) throw new Error('No BDC IDs provided');

  const index = hygPropIndex_();
  const ws = hygJobsSheet_();
  const ts = hygTs_();
  const created = [], notFound = [], toAppend = [];
  ids.forEach(raw => {
    const id = String(raw).trim().replace(/\.0+$/, '');
    if (!id) return;
    const hit = index[id];
    if (!hit) { notFound.push(id); return; }
    toAppend.push({ id: id, row: hit.row, name: hit.propName });
  });
  if (toAppend.length) {
    const startRow = ws.getLastRow() + 1;
    const rows = toAppend.map((t, i) => {
      const jobId = startRow + i;
      return [jobId, t.id, t.name, t.row, submittedBy, 'pending', '', '', ts, ''];
    });
    ws.getRange(startRow, 1, rows.length, HYG_JOB_HEADERS.length).setValues(rows);
    rows.forEach(r => created.push({ id: r[0], bdc_id: r[1], prop_name: r[2], sheet_row: r[3] }));
  }
  return { created: created, notFound: notFound };
}

function hygFindJobRow_(ws, id) {
  const row = Number(id);
  if (row >= 2 && row <= ws.getLastRow() && String(ws.getRange(row, 1).getValue()) === String(id)) return row;
  const ids = ws.getRange(2, 1, Math.max(0, ws.getLastRow() - 1), 1).getValues();
  for (let i = 0; i < ids.length; i++) if (String(ids[i][0]) === String(id)) return i + 2;
  return -1;
}

function hygClaim(body) {
  hygCheckToken_(body);
  const worker = String((body && body.worker) || '').trim();
  if (!worker) throw new Error('worker required');
  hygTouchWorker_(worker, body && body.chromeOk, '');

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const ws = hygJobsSheet_();
    const last = ws.getLastRow();
    if (last < 2) return { job: null };
    const data = ws.getRange(2, 1, last - 1, HYG_JOB_HEADERS.length).getValues();
    for (let i = 0; i < data.length; i++) {
      if (String(data[i][5]) === 'pending') {     // shared pool: take any pending job
        const row = i + 2;
        ws.getRange(row, 6).setValue('claimed');
        ws.getRange(row, 7).setValue('claimed by ' + worker);
        ws.getRange(row, 9).setValue(hygTs_());
        return { job: { id: data[i][0], bdc_id: String(data[i][1]), prop_name: data[i][2], sheet_row: data[i][3] } };
      }
    }
    return { job: null };
  } finally {
    lock.releaseLock();
  }
}

function hygProgress(body) {
  hygCheckToken_(body);
  const ws = hygJobsSheet_();
  const row = hygFindJobRow_(ws, body && body.id);
  if (row < 0) throw new Error('job not found');
  if (body.status) ws.getRange(row, 6).setValue(String(body.status));
  if (body.log != null) ws.getRange(row, 7).setValue(String(body.log).slice(0, 500));
  ws.getRange(row, 9).setValue(hygTs_());
  return { ok: true };
}

function hygResult(body) {
  hygCheckToken_(body);
  const ws = hygJobsSheet_();
  const row = hygFindJobRow_(ws, body && body.id);
  if (row < 0) throw new Error('job not found');
  const sheetRow = Number(ws.getRange(row, 4).getValue());
  const ts = hygTs_();

  if (body.error || (body.scrapStatus && body.scrapStatus !== 'Successful')) {
    const status = body.scrapStatus || 'Error';
    // Only stamp status (E) + timestamp (T); don't blank existing metric values.
    const sheet = SpreadsheetApp.openById(HYG_SHEET_ID).getSheetByName(HYG_TAB);
    sheet.getRange('E' + sheetRow).setValue(status);
    sheet.getRange('T' + sheetRow).setValue(ts);
    ws.getRange(row, 6).setValue('error');
    ws.getRange(row, 8).setValue(String(body.error || status).slice(0, 1000));
    ws.getRange(row, 9).setValue(ts);
    return { status: 'error' };
  }

  // Partial update: write ONLY the metric fields the worker actually sent, so
  // each phase fills its own columns without blanking the others. Always stamp
  // Scrap Status (E) + Last Checked (T).
  const m = body.result || {};
  const sheet = SpreadsheetApp.openById(HYG_SHEET_ID).getSheetByName(HYG_TAB);
  // field key -> column letter in the BDC Hygiene tab
  const COLS = {
    review_score: 'F', review_count: 'G', genius_eligibility: 'H', genius_status: 'I',
    genius_level: 'J', preferred_status: 'K', preferred_eligibility: 'L', perf_score: 'M',
    top_promotion: 'N', commission_pct: 'O', search_result_views: 'P', views: 'Q',
    conversion_pct: 'R', page_score: 'S',
  };
  sheet.getRange('E' + sheetRow).setValue('Successful');
  Object.keys(COLS).forEach(function (k) {
    if (m[k] !== undefined && m[k] !== null && m[k] !== '') {
      sheet.getRange(COLS[k] + sheetRow).setValue(m[k]);
    }
  });
  sheet.getRange('T' + sheetRow).setValue(ts);

  ws.getRange(row, 6).setValue('done');
  ws.getRange(row, 8).setValue('');
  ws.getRange(row, 9).setValue(ts);
  ws.getRange(row, 10).setValue(JSON.stringify(m).slice(0, 4000));
  return { status: 'done' };
}

// Write columns E..T (16 cells) of one row in the BDC Hygiene tab.
function hygWriteRow_(sheetRow, vals16) {
  const ws = SpreadsheetApp.openById(HYG_SHEET_ID).getSheetByName(HYG_TAB);
  ws.getRange(sheetRow, 5, 1, 16).setValues([vals16]);
}

function hygTouchWorker_(worker, chromeOk, note) {
  const props = PropertiesService.getScriptProperties();
  const key = 'hw_' + worker;
  let cur = {};
  try { cur = JSON.parse(props.getProperty(key) || '{}'); } catch (e) {}
  cur.lastSeen = (new Date()).getTime();
  if (chromeOk != null) cur.chromeOk = !!chromeOk;
  if (note != null) cur.note = note;
  props.setProperty(key, JSON.stringify(cur));
}

function hygHeartbeat(body) {
  hygCheckToken_(body);
  const worker = String((body && body.worker) || '').trim();
  if (!worker) throw new Error('worker required');
  hygTouchWorker_(worker, body && body.chromeOk, (body && body.note) || '');
  return { ok: true };
}

function hygJobs() {
  const ws = hygJobsSheet_();
  const last = ws.getLastRow();
  let jobs = [];
  if (last >= 2) {
    ws.getRange(2, 1, last - 1, HYG_JOB_HEADERS.length).getValues().forEach(r => {
      jobs.push({ id: r[0], bdc_id: String(r[1]), prop_name: r[2], status: String(r[5]),
                  log: r[6], error: r[7], updated_at: r[8] ? String(r[8]) : '' });
    });
    jobs = jobs.slice(-300).reverse();
  }
  // Count workers seen in the last 30s, and whether any has its Chrome logged in.
  let workersOnline = 0, anyChromeOk = false, lastNote = '';
  try {
    const props = PropertiesService.getScriptProperties().getProperties();
    const nowMs = (new Date()).getTime();
    Object.keys(props).forEach(k => {
      if (k.indexOf('hw_') !== 0) return;
      try {
        const c = JSON.parse(props[k]);
        if (c.lastSeen && (nowMs - c.lastSeen) < 30000) {
          workersOnline++;
          if (c.chromeOk) anyChromeOk = true;
          if (c.note) lastNote = c.note;
        }
      } catch (e) {}
    });
  } catch (e) {}
  const counts = {};
  jobs.forEach(j => { counts[j.status] = (counts[j.status] || 0) + 1; });
  return { jobs: jobs, counts: counts, workersOnline: workersOnline, anyChromeOk: anyChromeOk, note: lastNote };
}

// ── Manual smoke test (run from the GAS editor) ────────────────────────────
function _smokeTest() {
  Logger.log(route('ping', {}, false));
  Logger.log(route('bcom_tabs', {}, false));
  const bcom = route('bcom', {}, false);
  Logger.log('bcom cols: ' + bcom.cols.length + ', rows: ' + bcom.rows.length);
}
