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
      fhStatusCol: 'STATUS', liveCol: 'Agoda Status', liveValue: 'Live',
      matrixCols: ['STATUS', 'Agoda Status'],
      checkCols: ['Agoda Status', 'Sub Status', 'AI Status', 'Duplicate Listing Status', 'Category', 'Exclusive Props'],
    },
    {
      id: 'expedia', label: 'Expedia', key: 'expedia',
      fhStatusCol: 'FH Status', liveCol: 'Expedia Status', liveValue: 'Live',
      matrixCols: ['FH Status', 'Expedia Status'],
      checkCols: ['Expedia Status', 'Sub Status'],
    },
    {
      id: 'cleartrip', label: 'Cleartrip', key: 'cleartrip',
      fhStatusCol: 'STATUS', liveCol: 'CT Status', liveValue: 'Live',
      matrixCols: ['STATUS', 'CT Status'],
      checkCols: ['CT Status', 'Sub Status'],
    },
    {
      id: 'yatra', label: 'Yatra', key: 'yatra',
      fhStatusCol: 'STATUS', liveCol: 'Yatra Status', liveValue: 'Live',
      matrixCols: ['STATUS', 'Yatra Status'],
      checkCols: ['Yatra Status', 'Sub Status', 'Mapping Status', 'Promotion Status'],
    },
    {
      id: 'easemytrip', label: 'EaseMyTrip', key: 'easemytrip',
      fhStatusCol: 'FH Status', liveCol: 'EMT Status', liveValue: 'Live',
      matrixCols: ['FH Status', 'EMT Status'],
      checkCols: ['EMT Status', 'Sub Status'],
    },
    {
      id: 'ixigo', label: 'Ixigo', key: 'ixigo',
      fhStatusCol: 'STATUS', liveCol: 'Ixigo Status', liveValue: 'Live',
      matrixCols: ['STATUS', 'Ixigo Status'],
      checkCols: ['Ixigo Status', 'Sub Status', 'Content Status', 'Mapping Status', 'Promotion Status'],
    },
    {
      id: 'indigo', label: 'Indigo', key: 'indigo',
      fhStatusCol: 'STATUS', liveCol: 'Indigo Status', liveValue: 'Live',
      matrixCols: ['STATUS', 'Indigo Status'],
      checkCols: ['Indigo Status', 'Sub Status', 'Content Status', 'Mapping Status', 'Promotion Status'],
    },
  ];

  window.OTA_CHANNEL_KEYS = CONFIGS.map(c => c.key);
  window.OTA_CHANNEL_PAGES = CONFIGS.map(c => window.makeOtaChannelPage(c));

})();
