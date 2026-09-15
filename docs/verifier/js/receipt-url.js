/* Safe receipt-url handoff for verify.modelmarket.dev.
 *
 * The URL is supplied by a share link, so it is data, not navigation authority.
 * Keep the fetch surface deliberately smaller than arbitrary HTTPS: only the
 * canonical public AWR route on modelmarket.dev is accepted.  Verification is
 * still local; this helper merely retrieves the primary document the user asked
 * to inspect and never dereferences anything named inside it.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.AWRReceiptUrl = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var MAX_RECEIPT_BYTES = 1024 * 1024;
  var RECEIPT_PATH = '/ai-market/v2/p/provenance/receipt/';

  function validate(raw) {
    if (typeof raw !== 'string' || !raw.trim()) {
      return { ok: false, code: 'missing' };
    }
    var url;
    try { url = new URL(raw); } catch (_) {
      return { ok: false, code: 'invalid' };
    }
    if (url.protocol !== 'https:' || url.username || url.password) {
      return { ok: false, code: 'scheme' };
    }
    if (url.hostname !== 'modelmarket.dev' || url.port) {
      return { ok: false, code: 'host' };
    }
    var receiptId = url.pathname.slice(RECEIPT_PATH.length);
    if (!url.pathname.startsWith(RECEIPT_PATH) || !receiptId || receiptId.indexOf('/') !== -1) {
      return { ok: false, code: 'path' };
    }
    if (url.search) return { ok: false, code: 'path' };
    url.hash = '';
    return { ok: true, url: url.toString() };
  }

  function fromSearch(search) {
    var raw = new URLSearchParams(search || '').get('receipt_url');
    return raw ? validate(raw) : { ok: false, code: 'missing' };
  }

  return {
    MAX_RECEIPT_BYTES: MAX_RECEIPT_BYTES,
    validate: validate,
    fromSearch: fromSearch
  };
});
