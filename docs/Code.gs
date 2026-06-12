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

// ── Sheet IDs ──────────────────────────────────────────────────────────────
const CRS_SHEET_ID    = '1H2lP2zn4Ydeyex504DzmfBwXAX0Ip2H4SIu92DylRLw';
const BCOM_SHEET_ID   = '1vjm8BX1QZKMqXiLjbokCD0R91JvlscXcg5812p_IolI';
const GOMMT_SHEET_ID  = '1Pr2iEC7UvI7sWgwx4qQGQcO9Iw3dyzBqLpAr2mrQvKc';
const GMB_SHEET_ID    = '16awDYKs1jdR0x5VDJTo8CokB_fqqjr7JRpmRY0tv4Fk';
const DASH_SHEET_ID   = '1ND1SBFknF1aD4iVA_1XtwXK_u7wEonFUVYesv5sZRXU';
const LISTING_GID     = 158406294;

// OTA tracker pages — server-side whitelist (pages pass a key, never a raw ID),
// each pointing at a sheet + the tab to show. Add a line here per OTA.
const OTA_SHEETS = {
  agoda: { id: '1oArMEiRCnga_tO8VBMdz9gynhwkaVuPdfz8yzEE8Kag', tab: 'Live Properties' },
};

const CRS_TAB         = 'CRS DATA';
const DASH_TAB        = 'Prop Level Dashboard';
const LOG_TAB         = 'Last Checked';
const DETAIL_TAB      = 'Last Run Details';

const CACHE_TTL_S     = 3600;   // 1 hour

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

    case 'ota':         return cachedOtaTab(p.key, refresh);

    case 'listing':     return cachedSheetByGid('listing', DASH_SHEET_ID, LISTING_GID, refresh);

    case 'crs':         return cachedSheetByName('crs', CRS_SHEET_ID, CRS_TAB, refresh);
    case 'dashboard':   return cachedSheetByNameRaw('dashboard', DASH_SHEET_ID, DASH_TAB, refresh);

    case 'log':         return cachedSheetByName('log', CRS_SHEET_ID, LOG_TAB, refresh);
    case 'details':     return cachedSheetByName('details', CRS_SHEET_ID, DETAIL_TAB, refresh);

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

function cachedOtaTab(key, refresh) {
  const cfg = OTA_SHEETS[key];
  if (!cfg) throw new Error('Unknown OTA: ' + key);
  return withCache('ota_' + key, refresh, () => {
    const ss = SpreadsheetApp.openById(cfg.id);
    const ws = ss.getSheetByName(cfg.tab);
    if (!ws) throw new Error('Tab "' + cfg.tab + '" not found for OTA ' + key);
    return sheetToColsRows(ws);
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
    const range = ws.getDataRange();
    const vals = range.getValues();
    const disp = range.getDisplayValues();
    // Keep date cells in the sheet's display format (avoid ISO serialisation).
    const rows = vals.map((r, i) => r.map((v, j) => (v instanceof Date) ? disp[i][j] : v));
    return { rows: rows };   // raw 2-D array
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
  const range = ws.getDataRange();
  const all = range.getValues();
  if (!all || all.length === 0) return { cols: [], rows: [] };
  // Display values = exactly what the sheet shows (so dates keep the sheet's
  // own format instead of being serialised as ISO strings). We only swap them
  // in for Date cells, leaving numbers/text as real typed values.
  const disp = range.getDisplayValues();
  const headers = all[0].map(h => String(h == null ? '' : h));
  // Deduplicate headers
  const seen = {};
  const cols = headers.map(h => {
    if (seen[h] == null) { seen[h] = 0; return h; }
    seen[h] += 1;
    return h + '.' + seen[h];
  });
  const rows = all.slice(1).map((r, i) => r.map((v, j) => {
    if (v instanceof Date) return disp[i + 1][j];   // match the sheet's date format
    return v == null ? '' : v;
  }));
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

// ── Manual smoke test (run from the GAS editor) ────────────────────────────
function _smokeTest() {
  Logger.log(route('ping', {}, false));
  Logger.log(route('bcom_tabs', {}, false));
  const bcom = route('bcom', {}, false);
  Logger.log('bcom cols: ' + bcom.cols.length + ', rows: ' + bcom.rows.length);
}
