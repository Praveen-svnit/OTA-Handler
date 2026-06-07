/**
 * Boot — registers pages with the router in the order they should appear
 * in the sidebar, then kicks off rendering.
 */

(function () {
  // Pages register globally via window.PAGE_*
  Router.register(window.PAGE_BOOKING);
  Router.register(window.PAGE_GOMMT);
  Router.register(window.PAGE_LISTING);
  Router.register(window.PAGE_MAPPING);
  Router.register(window.PAGE_LAST_CHECKED);
  Router.start();

  // Friendly hint if the GAS URL hasn't been configured yet
  if (API.getUrl().includes('REPLACE_WITH_YOUR_DEPLOYMENT_ID')) {
    UI.toast('Edit assets/api.js and set GAS_URL before this will work.', true);
  }

  // Preload all page data in background for instant navigation
  setTimeout(async () => {
    // Start by fetching tabs lists to find Live tab names
    const [bcomTabs, gommtTabs] = await Promise.allSettled([
      API.bcomTabs(),
      API.gommtTabs(),
    ]);
    const bcomLive = (bcomTabs.value?.tabs || []).find(t => t.toLowerCase().includes('live')) || null;
    const gommtLive = 'Live Sheet';
    await Promise.allSettled([
      bcomLive ? API.bcomTab(bcomLive) : Promise.resolve(),
      gommtLive ? API.gommtTab(gommtLive) : Promise.resolve(),
      API.listing(),
      API.log(),
      API.crs(),
      API.dashboard(),
    ]);
  }, 300);
})();
