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
})();
