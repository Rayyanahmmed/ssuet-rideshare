/**
 * Web-Mercator arithmetic for the in-WebView map (§13).
 *
 * The map runs inside an HTML page, and an HTML page cannot import TypeScript — so the maths
 * lives here as a **string of plain JavaScript** that `tileMapHtml.ts` inlines. Keeping one
 * copy means the numbers the tests check are exactly the numbers the phone runs.
 *
 * Everything is "world pixels": at zoom `z` the whole world is 256·2^z px square, which is
 * the convention every slippy-map server (including our own tile proxy) uses.
 *
 * Verify with: `node scripts/verify-map.mjs`
 */
export const TILE_MATH_JS = `
var EARTH = 256;

function worldSize(zoom) { return EARTH * Math.pow(2, zoom); }

function lngToWorldX(lng, zoom) {
  return (lng + 180) / 360 * worldSize(zoom);
}

function latToWorldY(lat, zoom) {
  var clamped = Math.max(-85.05112878, Math.min(85.05112878, lat));
  var rad = clamped * Math.PI / 180;
  return (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * worldSize(zoom);
}

function worldXToLng(x, zoom) {
  return x / worldSize(zoom) * 360 - 180;
}

function worldYToLat(y, zoom) {
  var n = Math.PI - 2 * Math.PI * y / worldSize(zoom);
  return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}

/** Inclusive tile range covering a viewport of w×h px whose top-left is (ox, oy). */
function tileRange(ox, oy, w, h, zoom) {
  var count = Math.pow(2, zoom);
  function clamp(v) { return Math.max(0, Math.min(count - 1, v)); }
  return {
    minX: clamp(Math.floor(ox / EARTH)),
    maxX: clamp(Math.floor((ox + w) / EARTH)),
    minY: clamp(Math.floor(oy / EARTH)),
    maxY: clamp(Math.floor((oy + h) / EARTH))
  };
}

/**
 * Zoom at which two points fit inside a viewport with padding.
 * dx/dy are their world-pixel distance AT ZOOM 0 (i.e. on a 256 px world).
 */
function zoomToFit(dx, dy, w, h, pad, maxZoom) {
  var availX = Math.max(16, w - pad * 2);
  var availY = Math.max(16, h - pad * 2);
  var zx = dx / availX > 0 ? Math.log(availX / dx) / Math.LN2 : 99;
  var zy = dy / availY > 0 ? Math.log(availY / dy) / Math.LN2 : 99;
  var zoom = Math.floor(Math.min(zx, zy));
  return Math.max(2, Math.min(maxZoom, zoom));
}
`;
