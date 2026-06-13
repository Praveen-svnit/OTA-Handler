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
  ixigo: { id: '1sTqQpcGb-lxbO-iRwfjDynS2nVxFlDjcRMP8FVgFXaY', tab: 'Ixigo Live' },
  expedia: { id: '1HR24f-LIoVXjhoqDiTiecZ-6yCaM3kWSrNsiqLhm9DU', tab: 'Live Properties' },
  cleartrip: { id: '18lqRLC9LHwRuCAAEHnG7DpfvUWR6jdF4te-xm_ZMIUE', tab: 'Live' },
  indigo: { id: '1u_RyuxHS86JvlKhCDWLn0QZZdGDqZHvJSkXskxh90pM', tab: 'Live ' },
  easemytrip: { id: '19oB4tKRaRHFps_O3VEPWnVoissGpE27NuXmsB8puZT4', tab: 'Live Properties' },
  yatra: { id: '1veWgbJHRoHHZyowHYESt3VCehIKwMUAZ0bW92SgrOHU', tab: 'Yatra Live' },
  photoshoot: { id: '1OlT0XA3Nk_RFpgbehysSCGcd955-Dyg7biWu9sbbPpQ', tab: 'OTA Photoshoot Tracker' },
  dss_dod: { id: '1xI0TjmZkmKwD27nNIhah7iaQtbpAmX5tfJYckbw2Jio', tab: 'DoD Summary' },
  dss_wow: { id: '1xI0TjmZkmKwD27nNIhah7iaQtbpAmX5tfJYckbw2Jio', tab: 'WoW Summary' },
  dss_mom: { id: '1xI0TjmZkmKwD27nNIhah7iaQtbpAmX5tfJYckbw2Jio', tab: 'MoM Summary' },
};

// Listing Overview — live FH base from the BDC Hygiene "Inv" tab (cols A-E,
// churn excluded), and each OTA's live count from its "<OTA> Status" column.
const INV_SHEET_ID = '1VkFA4keBAT3tG5NkZwmSNRbLZJgx2neOhZ7Zuj2z_98';
const INV_TAB      = 'Inv';

// statusHeader = the column in each channel's live tab whose value "Live" means
// the property is live there. Anything else is a pending reason. OTA entries use
// their OTA_SHEETS key; the original channels carry an explicit sheetId + tab.
const OVERVIEW_OTAS = [
  { label: 'Booking.com', sheetId: BCOM_SHEET_ID, tab: 'Live', statusHeader: 'Sub Status' },
  { label: 'GoMMT', sheetId: GOMMT_SHEET_ID, tab: 'Live', statusHeader: 'Sub Status' },
  { label: 'GMB', sheetId: GMB_SHEET_ID, tab: 'New Tracker', statusHeader: 'GMB Sub Status' },
  { key: 'agoda', label: 'Agoda', statusHeader: 'Agoda Status' },
  { key: 'expedia', label: 'Expedia', statusHeader: 'Expedia Status' },
  { key: 'cleartrip', label: 'Cleartrip', statusHeader: 'CT Status' },
  { key: 'yatra', label: 'Yatra', statusHeader: 'Yatra Status' },
  { key: 'easemytrip', label: 'EaseMyTrip', statusHeader: 'EMT Status' },
  { key: 'ixigo', label: 'Ixigo', statusHeader: 'Ixigo Status' },
  { key: 'indigo', label: 'Indigo', statusHeader: 'Indigo Status' },
];

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

    case 'listing_overview': return listingOverview(refresh);

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

// ── Listing overview ────────────────────────────────────────────────────────
// Returns per (Prop Set × Prop Cat × Live Month) groups with per-OTA live counts,
// so the page can filter on those dimensions and aggregate instantly.
//   Base attributes (Set/Cat) come from Inv; Live Month from Booking's
//   "FH Live Month"; each OTA's live status from its own sheet (authoritative).
function listingOverview(refresh) {
  return withCache('listing_overview', refresh, function () {
    // 1) base attributes from Inv (cols A=id, E=STATUS, F=Pre/Post, G=Prop Cat)
    var iv = SpreadsheetApp.openById(INV_SHEET_ID).getSheetByName(INV_TAB);
    var ivVals = iv.getRange(1, 1, iv.getLastRow(), 7).getValues();
    var ivHdr = ivVals[0];
    function ci(name) { for (var i = 0; i < ivHdr.length; i++) if (String(ivHdr[i]).trim() === name) return i; return -1; }
    var cId = 0, cStatus = ci('STATUS'), cSet = ci('Pre/Post'), cCat = ci('Prop Cat');
    var attr = {}, order = [];
    for (var i = 1; i < ivVals.length; i++) {
      var id = String(ivVals[i][cId]).trim();
      var st = String(ivVals[i][cStatus]).trim();
      if (!id || st.toLowerCase() === 'churned' || attr[id]) continue;
      attr[id] = {
        s: cSet >= 0 ? (String(ivVals[i][cSet]).trim() || '(blank)') : '(blank)',
        c: cCat >= 0 ? (String(ivVals[i][cCat]).trim() || '(blank)') : '(blank)',
      };
      order.push(id);
    }

    // 2) per-OTA live + exception sets (from each channel's status column).
    // Live = "Live"; Exception = value containing "exception" (a not-live subset).
    var otaLabels = [], liveSets = [], excSets = [];
    OVERVIEW_OTAS.forEach(function (o) {
      var cfg = o.sheetId ? { id: o.sheetId, tab: o.tab } : OTA_SHEETS[o.key];
      var ws = SpreadsheetApp.openById(cfg.id).getSheetByName(cfg.tab);
      var hdr = ws.getRange(1, 1, 1, ws.getLastColumn()).getValues()[0];
      var si = -1; for (var c = 0; c < hdr.length; c++) if (String(hdr[c]).trim() === o.statusHeader) { si = c; break; }
      var ids = ws.getRange(1, 1, ws.getLastRow(), 1).getValues();
      var sts = si >= 0 ? ws.getRange(1, si + 1, ws.getLastRow(), 1).getValues() : null;
      var set = {}, exc = {}, seen = {};
      for (var r = 1; r < ids.length; r++) {
        var pid = String(ids[r][0]).trim();
        if (!attr[pid] || seen[pid]) continue;
        seen[pid] = true;
        var sv = sts ? String(sts[r][0]).trim().toLowerCase() : '';
        if (sv === 'live') set[pid] = true;
        else if (sv.indexOf('exception') >= 0) exc[pid] = true;
      }
      otaLabels.push(o.label); liveSets.push(set); excSets.push(exc);
    });

    // 3) live month from Booking's "FH Live Month"
    var monthMap = {};
    try {
      var bk = SpreadsheetApp.openById(BCOM_SHEET_ID).getSheetByName('Live');
      var bh = bk.getRange(1, 1, 1, bk.getLastColumn()).getValues()[0];
      var mi = -1; for (var c = 0; c < bh.length; c++) if (String(bh[c]).trim() === 'FH Live Month') { mi = c; break; }
      if (mi >= 0) {
        var bids = bk.getRange(1, 1, bk.getLastRow(), 1).getValues();
        var bms = bk.getRange(1, mi + 1, bk.getLastRow(), 1).getValues();
        for (var r2 = 1; r2 < bids.length; r2++) {
          var p2 = String(bids[r2][0]).trim();
          if (p2 && !monthMap[p2]) monthMap[p2] = String(bms[r2][0]).trim();
        }
      }
    } catch (e) { /* month optional */ }

    // 4) aggregate by (set, cat, month)
    var groupMap = {};
    order.forEach(function (id) {
      var a = attr[id], m = monthMap[id] || '(blank)';
      var key = a.s + '|' + a.c + '|' + m;
      var g = groupMap[key];
      if (!g) {
        g = groupMap[key] = { s: a.s, c: a.c, m: m, n: 0,
          l: otaLabels.map(function () { return 0; }), e: otaLabels.map(function () { return 0; }) };
      }
      g.n++;
      for (var i = 0; i < liveSets.length; i++) {
        if (liveSets[i][id]) g.l[i]++;
        if (excSets[i][id]) g.e[i]++;
      }
    });
    return { otas: otaLabels, groups: Object.keys(groupMap).map(function (k) { return groupMap[k]; }) };
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
