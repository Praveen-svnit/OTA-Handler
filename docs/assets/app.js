/**
 * Boot — registers pages with the router in the order they should appear
 * in the sidebar, then kicks off rendering.
 */

(function () {
  // Pages register globally via window.PAGE_*
  Router.register(window.PAGE_BOOKING);
  Router.register(window.PAGE_GOMMT);
  Router.register(window.PAGE_GMB);
  (window.OTA_PAGES || []).forEach(p => Router.register(p));
  // OTA Tools group (rendered under a section header in the sidebar)
  Router.register(window.PAGE_MAPPING);
  Router.register(window.PAGE_SCRAPER);
  // Last Checked retired — its functionality is now baked into Mapping Checker
  // (latest run is auto-loaded on open + auto-saved on Run Analysis).
  Router.start();

  // Friendly hint if the GAS URL hasn't been configured yet
  if (API.getUrl().includes('REPLACE_WITH_YOUR_DEPLOYMENT_ID')) {
    UI.toast('Edit assets/api.js and set GAS_URL before this will work.', true);
  }

  // Preload all page data in background for instant navigation
  setTimeout(async () => {
    async function findLive(fetchTab, fetchTabs) {
      try { await fetchTab('Live'); return 'Live'; } catch (_) {}
      const tabs = await fetchTabs();
      const list = tabs.tabs || [];
      return list.find(t => t.toLowerCase().includes('live')) || list[0] || null;
    }
    const [bcomLive, gommtLive] = await Promise.allSettled([
      findLive((n) => API.bcomTab(n), () => API.bcomTabs()),
      findLive((n) => API.gommtTab(n), () => API.gommtTabs()),
    ]);
    await Promise.allSettled([
      bcomLive.value ? API.bcomTab(bcomLive.value) : Promise.resolve(),
      gommtLive.value ? API.gommtTab(gommtLive.value) : Promise.resolve(),
      API.gmbTab('New Tracker'),
      API.log(),
      API.crs(),
      API.dashboard(),
    ]);
  }, 300);
})();
