import { TILE_MATH_JS } from '@/components/map/tileMath';

/**
 * A self-contained slippy map for a WebView (§13).
 *
 * Why not the native Google map: its key is compiled into the APK, so an expired key means a
 * blank rectangle for every installed app until a new build is uploaded. This map asks **our**
 * `/maps/tiles/{z}/{x}/{y}.png` proxy for imagery, which means the provider — OpenStreetMap
 * today, Geoapify or MapTiler tomorrow — and its key are decided on the server, at runtime.
 *
 * No third-party JavaScript is loaded: the page is inline HTML, CSS and ~200 lines of
 * vanilla JS, so the only network traffic is the tiles themselves.
 *
 * Bridge (WebView → app): `{type:'ready'}`, `{type:'pin', latitude, longitude}`,
 * `{type:'tiles-error'}`. App → WebView: `window.__map.setPin(lat, lng)`.
 */
export type MapPin = {
  id: string;
  latitude: number;
  longitude: number;
  color: string;
};

export type TileMapOptions = {
  /** Absolute tile base, e.g. `http://192.168.100.32:8000/api/v1/maps/tiles`. */
  tileBase: string;
  attribution: string;
  latitude: number;
  longitude: number;
  zoom?: number;
  pins?: MapPin[];
  /** Tap and drag move `pins[0]` (the pickup pin). */
  editable?: boolean;
  /** Centre and zoom so every pin is visible (used on the ride-details screen). */
  fit?: boolean;
  hint?: string;
  maxZoom?: number;
};

const BRAND_GREEN = '#0f7a4d';

/**
 * Attribution is inserted as HTML because OpenStreetMap's licence requires a visible link.
 * Only a plain anchor is allowed through, so a compromised or mis-typed provider label can
 * never inject script into the page.
 */
function sanitizeAttribution(value: string): string {
  return value
    .replace(/<\s*(?!\/?a\b)[^>]*>/gi, '') // keep <a ...> and </a>, drop every other tag
    .replace(/\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '') // drop on* handlers
    .replace(/javascript:/gi, '')
    .slice(0, 300);
}

/** JSON that is safe inside a `<script>` block. */
function inlineJson(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/`/g, '\\u0060')
    .replace(/\u2028|\u2029/g, '');
}

export function buildTileMapHtml(options: TileMapOptions): string {
  const config = {
    tileBase: options.tileBase.replace(/\/+$/, ''),
    attribution: sanitizeAttribution(options.attribution),
    lat: options.latitude,
    lng: options.longitude,
    zoom: options.zoom ?? 14,
    maxZoom: options.maxZoom ?? 18,
    editable: options.editable ?? false,
    fit: options.fit ?? false,
    hint: options.hint ?? (options.editable ? 'Tap the map to drop a pin' : ''),
    pins: options.pins ?? [
      { id: 'pin', latitude: options.latitude, longitude: options.longitude, color: BRAND_GREEN },
    ],
  };

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<style>
  html, body { margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden;
    background: #e9edf1; font-family: -apple-system, Roboto, system-ui, sans-serif;
    -webkit-user-select: none; user-select: none; -webkit-tap-highlight-color: transparent; }
  #map { position: absolute; inset: 0; overflow: hidden; touch-action: none; }
  #stage { position: absolute; left: 0; top: 0; width: 0; height: 0; will-change: transform; }
  .tile { position: absolute; width: 256px; height: 256px; pointer-events: none;
    -webkit-user-drag: none; opacity: 0; transition: opacity .18s linear; }
  .pin { position: absolute; width: 20px; height: 20px; margin: -20px 0 0 -10px; z-index: 10;
    border: 2px solid #fff; border-radius: 50% 50% 50% 0; transform: rotate(-45deg);
    box-shadow: 0 1px 4px rgba(0,0,0,.45); cursor: grab; }
  .pin.draggable { cursor: move; }
  .pin::after { content: ''; position: absolute; inset: 4px; background: rgba(255,255,255,.85);
    border-radius: 50%; }
  #zoom { position: absolute; right: 10px; top: 10px; display: flex; flex-direction: column;
    gap: 6px; z-index: 20; }
  #zoom button { width: 34px; height: 34px; border: 1px solid #cfd6dd; border-radius: 8px;
    background: rgba(255,255,255,.96); color: #123; font-size: 20px; line-height: 1;
    font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,.18); touch-action: manipulation; }
  #hint { position: absolute; left: 8px; right: 8px; bottom: 6px; z-index: 20;
    font-size: 11px; line-height: 1.35; color: #2b3a45; background: rgba(255,255,255,.85);
    border-radius: 6px; padding: 3px 7px; }
  #attr { position: absolute; right: 3px; top: 3px; z-index: 20; font-size: 8px;
    color: #45525c; background: rgba(255,255,255,.72); border-radius: 3px; padding: 1px 4px;
    max-width: 55%; text-align: right; }
  #attr a { color: #0f7a4d; text-decoration: none; }
  #err { position: absolute; inset: 0; display: none; align-items: center; justify-content: center;
    z-index: 30; padding: 16px; text-align: center; font-size: 12px; color: #7a2b2b;
    background: rgba(255,255,255,.92); }
</style>
</head>
<body>
  <div id="map">
    <div id="stage"><div id="world"></div><div id="pinLayer"></div></div>
    <div id="zoom"><button id="zin" aria-label="Zoom in">+</button><button id="zout" aria-label="Zoom out">&minus;</button></div>
    <div id="attr">${config.attribution}</div>
    <div id="hint"></div>
    <div id="err"></div>
  </div>
<script>
var CONFIG = ${inlineJson(config)};
${TILE_MATH_JS}
var mapEl = document.getElementById('map');
var stage = document.getElementById('stage');
var world = document.getElementById('world');
var pinLayer = document.getElementById('pinLayer');
var hintEl = document.getElementById('hint');
var errEl = document.getElementById('err');

var state = { lat: CONFIG.lat, lng: CONFIG.lng, zoom: CONFIG.zoom, w: 0, h: 0, ox: 0, oy: 0 };
var pins = [];
var tiles = {};
var drag = null;
var failedTiles = 0;
var reportedTilesFailure = false;
var MIN_ZOOM = 3;

for (var i = 0; i < CONFIG.pins.length; i++) {
  pins.push({ id: CONFIG.pins[i].id, lat: CONFIG.pins[i].latitude, lng: CONFIG.pins[i].longitude,
              color: CONFIG.pins[i].color || '${BRAND_GREEN}' });
}

function post(message) {
  var text = JSON.stringify(message);
  if (window.ReactNativeWebView && window.ReactNativeWebView.postMessage) {
    window.ReactNativeWebView.postMessage(text);
  } else if (window.console && console.log) {
    console.log('map->app ' + text);
  }
}

function clampZoom(zoom) { return Math.max(MIN_ZOOM, Math.min(CONFIG.maxZoom, zoom)); }

function setHint(text) { hintEl.textContent = text || ''; hintEl.style.display = text ? 'block' : 'none'; }

function showError(text) {
  errEl.textContent = text;
  errEl.style.display = 'flex';
}

/**
 * Tiles are fetched with the ngrok warning-skip header and shown from a blob URL. A plain
 * <img src> cannot send that header, so a free ngrok tunnel answers with its warning page
 * instead of the tile and the map stays grey. Requests use the same credentials-free path
 * as the rest of the API, which already works through the tunnel.
 */
function loadTile(el, url) {
  fetch(url, { headers: { 'ngrok-skip-browser-warning': '1' }, credentials: 'omit' })
    .then(function (response) {
      if (!response.ok) { throw new Error('tile ' + response.status); }
      return response.blob();
    })
    .then(function (blob) {
      el.src = URL.createObjectURL(blob);
    })
    .catch(function () {
      el.style.opacity = 0;
      tileFailed();
    });
}

function tileFailed() {
  failedTiles++;
  if (failedTiles >= 4 && !reportedTilesFailure) {
    reportedTilesFailure = true;
    post({ type: 'tiles-error' });
  }
}

function measure() {
  state.w = mapEl.clientWidth || window.innerWidth;
  state.h = mapEl.clientHeight || window.innerHeight;
}

function placeTiles() {
  var range = tileRange(state.ox, state.oy, state.w, state.h, state.zoom);
  var needed = {};
  for (var x = range.minX; x <= range.maxX; x++) {
    for (var y = range.minY; y <= range.maxY; y++) {
      var key = state.zoom + '/' + x + '/' + y;
      needed[key] = true;
      var el = tiles[key];
      if (!el) {
        el = document.createElement('img');
        el.className = 'tile';
        el.alt = '';
        el.onload = function () { this.style.opacity = 1; };
        el.onerror = function () { this.style.opacity = 0; tileFailed(); };
        loadTile(el, CONFIG.tileBase + '/' + state.zoom + '/' + x + '/' + y + '.png');
        world.appendChild(el);
        tiles[key] = el;
      }
      el.style.left = (x * 256 - state.ox) + 'px';
      el.style.top = (y * 256 - state.oy) + 'px';
    }
  }
  for (var k in tiles) {
    if (!needed[k]) {
      if (tiles[k].src && tiles[k].src.indexOf('blob:') === 0) { URL.revokeObjectURL(tiles[k].src); }
      if (tiles[k].parentNode) { tiles[k].parentNode.removeChild(tiles[k]); }
      delete tiles[k];
    }
  }
}

function placePins() {
  pinLayer.innerHTML = '';
  for (var i = 0; i < pins.length; i++) {
    var p = pins[i];
    var el = document.createElement('div');
    el.className = 'pin';
    if (CONFIG.editable && i === 0) { el.className += ' draggable'; }
    el.style.background = p.color;
    el.style.left = (lngToWorldX(p.lng, state.zoom) - state.ox) + 'px';
    el.style.top = (latToWorldY(p.lat, state.zoom) - state.oy) + 'px';
    el.setAttribute('data-pin', String(i));
    if (CONFIG.editable && i === 0) { attachPinDrag(el, 0); }
    pinLayer.appendChild(el);
  }
}

function layout() {
  measure();
  state.zoom = clampZoom(state.zoom);

  var size = worldSize(state.zoom);
  var cx = lngToWorldX(state.lng, state.zoom);
  var cy = latToWorldY(state.lat, state.zoom);
  state.ox = cx - state.w / 2;
  state.oy = cy - state.h / 2;

  if (size <= state.h) {
    state.oy = (size - state.h) / 2;
  } else {
    state.oy = Math.max(0, Math.min(size - state.h, state.oy));
  }

  stage.style.transform = 'translate(0px, 0px)';
  placeTiles();
  placePins();
}

function fitPins() {
  if (pins.length < 2) { return false; }
  var minLat = pins[0].lat, maxLat = pins[0].lat, minLng = pins[0].lng, maxLng = pins[0].lng;
  for (var i = 1; i < pins.length; i++) {
    minLat = Math.min(minLat, pins[i].lat); maxLat = Math.max(maxLat, pins[i].lat);
    minLng = Math.min(minLng, pins[i].lng); maxLng = Math.max(maxLng, pins[i].lng);
  }
  state.lat = (minLat + maxLat) / 2;
  state.lng = (minLng + maxLng) / 2;
  var dx = Math.abs(lngToWorldX(maxLng, 0) - lngToWorldX(minLng, 0));
  var dy = Math.abs(latToWorldY(maxLat, 0) - latToWorldY(minLat, 0));
  state.zoom = clampZoom(zoomToFit(dx, dy, state.w, state.h, 46, CONFIG.maxZoom));
  return true;
}

function pointToLatLng(clientX, clientY) {
  var rect = mapEl.getBoundingClientRect();
  var wx = state.ox + (clientX - rect.left);
  var wy = state.oy + (clientY - rect.top);
  return { lat: worldYToLat(wy, state.zoom), lng: worldXToLng(wx, state.zoom) };
}

function movePin(index, lat, lng) {
  if (!pins[index]) { return; }
  pins[index].lat = lat;
  pins[index].lng = lng;
  placePins();
}

function settle(dx, dy) {
  state.lat = worldYToLat(latToWorldY(state.lat, state.zoom) - dy, state.zoom);
  state.lng = worldXToLng(lngToWorldX(state.lng, state.zoom) - dx, state.zoom);
  layout();
}

function onDown(event) {
  if (event.target && event.target.className && String(event.target.className).indexOf('pin') === 0) { return; }
  drag = { mode: 'pan', x: event.clientX, y: event.clientY, moved: false };
}

function onMove(event) {
  if (!drag) { return; }
  if (drag.mode === 'pan') {
    var dx = event.clientX - drag.x;
    var dy = event.clientY - drag.y;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) { drag.moved = true; }
    stage.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
  } else if (drag.mode === 'pin') {
    var point = pointToLatLng(event.clientX, event.clientY);
    drag.moved = true;
    movePin(drag.index, point.lat, point.lng);
    setHint('Release to confirm this point');
  }
}

function onUp(event) {
  if (!drag) { return; }
  var finished = drag;
  drag = null;

  if (finished.mode === 'pan') {
    var dx = event.clientX - finished.x;
    var dy = event.clientY - finished.y;
    if (!finished.moved) {
      if (CONFIG.editable && pins.length > 0) {
        var point = pointToLatLng(event.clientX, event.clientY);
        movePin(0, point.lat, point.lng);
        setHint('Pin moved — drag the pin to fine-tune');
        post({ type: 'pin', latitude: point.lat, longitude: point.lng });
      }
      return;
    }
    settle(dx, dy);
  } else if (finished.mode === 'pin' && pins[finished.index]) {
    var chosen = pins[finished.index];
    setHint('Pin moved — drag the pin to fine-tune');
    post({ type: 'pin', latitude: chosen.lat, longitude: chosen.lng });
  }
}

function attachPinDrag(el, index) {
  el.addEventListener('pointerdown', function (event) {
    event.stopPropagation();
    event.preventDefault();
    drag = { mode: 'pin', index: index, x: event.clientX, y: event.clientY, moved: false };
    try { el.setPointerCapture(event.pointerId); } catch (error) { /* older WebView */ }
  });
  el.addEventListener('pointermove', function (event) {
    if (drag && drag.mode === 'pin') { onMove(event); }
  });
  el.addEventListener('pointerup', function (event) {
    if (drag && drag.mode === 'pin') { onUp(event); }
  });
}

function zoomBy(delta) {
  state.zoom = clampZoom(state.zoom + delta);
  layout();
}

mapEl.addEventListener('pointerdown', onDown);
window.addEventListener('pointermove', onMove);
window.addEventListener('pointerup', onUp);
window.addEventListener('pointercancel', onUp);
window.addEventListener('resize', layout);
document.getElementById('zin').addEventListener('click', function (event) { event.stopPropagation(); zoomBy(1); });
document.getElementById('zout').addEventListener('click', function (event) { event.stopPropagation(); zoomBy(-1); });
document.addEventListener('touchmove', function (event) { event.preventDefault(); }, { passive: false });

window.__map = {
  setPin: function (lat, lng) { movePin(0, lat, lng); },
  setView: function (lat, lng, zoom) {
    state.lat = lat; state.lng = lng;
    state.zoom = clampZoom(zoom || state.zoom);
    layout();
  },
  recentre: function () { layout(); },
  refresh: function () { tiles = {}; world.innerHTML = ''; layout(); }
};

layout();
if (CONFIG.fit) { fitPins(); layout(); }
setHint(CONFIG.hint);
post({ type: 'ready' });
</script>
</body>
</html>`;
}
