/**
 * API client — talks to the Google Apps Script backend.
 *
 * Configure GAS_URL below after deploying Code.gs:
 *   1. In the GAS editor: Deploy → New deployment → Web app
 *      Execute as: Me, Who has access: Anyone
 *   2. Copy the deployment URL (ends in /exec) and paste below.
 */

const API = (() => {
  // ── EDIT THIS after deploying Code.gs ────────────────────────────────────
  const GAS_URL = 'https://script.google.com/macros/s/AKfycbwy49f6Y8P7_FZgdhfRmKaIJiEsoc4AZZQXYUah3IRijKzFqmTrVTLO6WaJ5Bpxf8kBnQ/exec';

  const memCache = new Map();          // in-browser memory cache per session
  const inFlight = new Map();          // dedupe concurrent identical requests

  function call(action, params, opts) {
    params = params || {};
    opts = opts || {};
    const refresh = !!opts.refresh;

    const qs = new URLSearchParams({ action, ...params });
    if (refresh) qs.set('refresh', '1');
    const url = GAS_URL + '?' + qs.toString();
    const cacheKey = url.replace(/refresh=1&?/, '');   // cache key ignores refresh flag

    if (!refresh && memCache.has(cacheKey)) {
      return Promise.resolve(memCache.get(cacheKey));
    }
    if (inFlight.has(url)) return inFlight.get(url);

    const p = fetch(url, { method: 'GET' })
      .then(r => r.json())
      .then(payload => {
        inFlight.delete(url);
        if (!payload.ok) throw new Error(payload.error || 'Unknown error');
        memCache.set(cacheKey, payload.data);
        return payload.data;
      })
      .catch(err => {
        inFlight.delete(url);
        throw err;
      });

    inFlight.set(url, p);
    return p;
  }

  function clearMem() { memCache.clear(); }

  // ── POST helper (for endpoints that take a large JSON body) ──────────────
  // GAS web-app POST is intentionally a no-preflight request: content-type is
  // text/plain so the browser doesn't trigger CORS preflight (Apps Script
  // doesn't respond to OPTIONS). The server still parses postData.contents
  // as JSON.
  function callPost(action, body) {
    const url = GAS_URL + '?action=' + encodeURIComponent(action);
    return fetch(url, {
      method: 'POST',
      body: JSON.stringify(body || {}),
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
    })
      .then(r => r.json())
      .then(payload => {
        if (!payload.ok) throw new Error(payload.error || 'Unknown error');
        return payload.data;
      });
  }

  // Convenience wrappers per endpoint
  return {
    ping:        ()        => call('ping'),
    bcom:        (opts)    => call('bcom', {}, opts),
    bcomTabs:    (opts)    => call('bcom_tabs', {}, opts),
    bcomTab:     (name, o) => call('bcom_tab', { name }, o),
    gommt:       (opts)    => call('gommt', {}, opts),
    gommtTabs:   (opts)    => call('gommt_tabs', {}, opts),
    gommtTab:    (name, o) => call('gommt_tab', { name }, o),
    gmb:         (opts)    => call('gmb', {}, opts),
    gmbTabs:     (opts)    => call('gmb_tabs', {}, opts),
    gmbTab:      (name, o) => call('gmb_tab', { name }, o),
    listing:     (opts)    => call('listing', {}, opts),
    ota:         (key, o)  => call('ota', { key }, o),
    listingOverview: (o)   => call('listing_overview', {}, o),
    crs:         (opts)    => call('crs', {}, opts),
    dashboard:   (opts)    => call('dashboard', {}, opts),
    log:         (opts)    => call('log', {}, opts),
    details:     (opts)    => call('details', {}, opts),
    saveMappingRun: (body) => callPost('save_mapping_run', body),
    clearMem,
    getUrl: () => GAS_URL,
  };
})();
