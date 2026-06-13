/**
 * Per-OTA config for the full channel-style pages (Matrix / Hygiene / Values /
 * Table). Add one block per OTA. Keys are exact column HEADERS from that OTA's
 * live tab.
 *
 *   fhStatusCol  – FH status column; rows with "Churned" are excluded
 *   liveCol/liveValue – defines the "live" subset for Hygiene & Values
 *   matrixCols   – [rowColumn, columnColumn] for the Matrix cross-tab
 *   checkCols    – columns analysed in Hygiene Checks + Value Summaries
 *
 * OTAs listed here render as full channel pages; any OTA NOT listed here falls
 * back to the simple table page (ota-pages.js).
 */

(function () {

  const CONFIGS = [
    {
      id: 'agoda', label: 'Agoda', key: 'agoda',
      fhStatusCol: 'STATUS',
      liveCol: 'Agoda Status', liveValue: 'Live',
      matrixCols: ['STATUS', 'Agoda Status'],
      checkCols: ['Agoda Status', 'Sub Status', 'AI Status', 'Duplicate Listing Status', 'Category', 'Exclusive Props'],
    },
  ];

  window.OTA_CHANNEL_KEYS = CONFIGS.map(c => c.key);
  window.OTA_CHANNEL_PAGES = CONFIGS.map(c => window.makeOtaChannelPage(c));

})();
