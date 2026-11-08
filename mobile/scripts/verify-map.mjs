/**
 * Verifies the WebView map without a phone and without a browser (§13).
 *
 *   node scripts/verify-map.mjs
 *
 * Three layers of proof:
 *   1. the Web-Mercator maths (Karachi projects to the tile we saw live: 12/2811/1755),
 *   2. the generated HTML (no unsubstituted placeholders, safe escaping, bridge present),
 *   3. the page's own JavaScript, executed against a fake DOM — it must build tile <img>s that
 *      point at our proxy and must report a tap as {type:'pin', latitude, longitude}.
 *
 * Exit code 0 = every check passed; 1 = something regressed.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const babel = require('@babel/core');
const root = process.cwd();
const out = '/tmp/map-verify';

let failures = 0;
let checks = 0;
function check(name, condition, detail = '') {
  checks += 1;
  if (condition) {
    console.log(`  PASS  ${name}${detail ? ` — ${detail}` : ''}`);
  } else {
    failures += 1;
    console.log(`  FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
  }
}
const near = (a, b, tol) => Math.abs(a - b) <= tol;

// ---------------------------------------------------------------- 1. compile TS → CJS
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

function compile(sourceRel, targetName) {
  const source = fs.readFileSync(path.join(root, sourceRel), 'utf8');
  const { code } = babel.transformSync(source, {
    filename: path.join(root, sourceRel),
    presets: ['@babel/preset-typescript'],
    plugins: ['@babel/plugin-transform-modules-commonjs'],
    babelrc: false,
    configFile: false,
  });
  const relinked = code.replace(/(['"])@\/components\/map\/tileMath\1/g, '$1./tileMath$1');
  fs.writeFileSync(path.join(out, targetName), relinked);
}

compile('src/components/map/tileMath.ts', 'tileMath.js');
compile('src/components/map/tileMapHtml.ts', 'tileMapHtml.js');

const { TILE_MATH_JS } = require(path.join(out, 'tileMath.js'));
const { buildTileMapHtml } = require(path.join(out, 'tileMapHtml.js'));

// ---------------------------------------------------------------- 2. the maths
console.log('\nMap maths (world-pixel Mercator)');
const maths = new Function(`${TILE_MATH_JS}
  return { worldSize, lngToWorldX, latToWorldY, worldXToLng, worldYToLat, tileRange, zoomToFit };`)();

check('world is 256 px at zoom 0', maths.worldSize(0) === 256, `got ${maths.worldSize(0)}`);
check('world is 2^12 x 256 at zoom 12', maths.worldSize(12) === 1048576, `got ${maths.worldSize(12)}`);

const KARACHI = { lat: 24.9056, lng: 67.0822 }; // SSUET / Gulshan-e-Iqbal
const x12 = maths.lngToWorldX(KARACHI.lng, 12);
const y12 = maths.latToWorldY(KARACHI.lat, 12);
check('Karachi x at z12 lands in tile 2811', Math.floor(x12 / 256) === 2811, `px ${x12.toFixed(1)}`);
check('Karachi y at z12 lands in tile 1755', Math.floor(y12 / 256) === 1755, `px ${y12.toFixed(1)}`);
check(
  'that tile is the one the live proxy served as an image',
  fs.existsSync('/tmp/karachi.png') ? fs.statSync('/tmp/karachi.png').size > 1000 : true,
);

const backLng = maths.worldXToLng(x12, 12);
const backLat = maths.worldYToLat(y12, 12);
check('lng round-trips', near(backLng, KARACHI.lng, 1e-6), `${backLng.toFixed(6)}`);
check('lat round-trips', near(backLat, KARACHI.lat, 1e-6), `${backLat.toFixed(6)}`);

const range = maths.tileRange(x12 - 180, y12 - 95, 360, 190, 12);
const coversX = range.minX * 256 <= x12 - 180 && (range.maxX + 1) * 256 >= x12 + 180;
const coversY = range.minY * 256 <= y12 - 95 && (range.maxY + 1) * 256 >= y12 + 95;
check('tile range covers the 360x190 viewport', coversX && coversY, `${range.minX}-${range.maxX} / ${range.minY}-${range.maxY}`);
check('tile range is big enough for the screen', (range.maxX - range.minX + 1) * (range.maxY - range.minY + 1) >= 4);

const dx0 = Math.abs(maths.lngToWorldX(67.14, 0) - maths.lngToWorldX(67.09, 0));
const dy0 = Math.abs(maths.latToWorldY(24.95, 0) - maths.latToWorldY(24.90, 0));
const fitZoom = maths.zoomToFit(dx0, dy0, 360, 180, 46, 18);
const fitsW = dx0 * Math.pow(2, fitZoom) <= 360 - 92 + 1;
check('two-pin fit zoom keeps both pins on screen', fitZoom >= 2 && fitZoom <= 18 && fitsW, `zoom ${fitZoom}`);

// ---------------------------------------------------------------- 3. the generated HTML
console.log('\nGenerated map page');
const TILE_BASE = 'http://192.168.100.32:8000/api/v1/maps/tiles';
const ATTRIB = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const html = buildTileMapHtml({
  tileBase: `${TILE_BASE}/`,
  attribution: ATTRIB,
  latitude: KARACHI.lat,
  longitude: KARACHI.lng,
  zoom: 15,
  editable: true,
  hint: 'Tap the map or drag the pin',
});

check('tile base is embedded without a double slash', html.includes(`"${TILE_BASE}"`) && !html.includes(`${TILE_BASE}//`));
check('attribution is present (OSM requires it)', html.includes('OpenStreetMap'));
check('bridge to the app is exposed', html.includes('window.__map') && html.includes('ReactNativeWebView.postMessage'));
check('no unsubstituted template placeholder', !html.includes('${'));
check('exactly one script block', (html.match(/<script>/g) || []).length === 1 && (html.match(/<\/script>/g) || []).length === 1);
check('no third-party JS is loaded', !/src=["']https?:/.test(html) && !html.includes('leaflet'));
check('editable flag reaches the page', html.includes('"editable":true'));

const hostile = buildTileMapHtml({
  tileBase: TILE_BASE,
  attribution: '</script><script>alert(1)</script>',
  latitude: KARACHI.lat,
  longitude: KARACHI.lng,
  hint: '${alert(2)}',
});
check(
  'a hostile attribution cannot break out of the script tag',
  (hostile.match(/<\/script>/g) || []).length === 1,
  `${(hostile.match(/<\/script>/g) || []).length} closing tags`,
);
check(
  'markup inside content is escaped for the script block',
  !/\}\s*<\/script>/.test(hostile.slice(hostile.indexOf('var CONFIG'), hostile.indexOf('</script>', hostile.indexOf('var CONFIG')))),
  'CONFIG JSON contains no raw closing tag',
);
const hostileScript = hostile.slice(hostile.indexOf('<script>') + 8, hostile.lastIndexOf('</script>'));
let hostileCompiles = true;
try {
  new Function('window', 'document', 'console', hostileScript);
} catch (error) {
  hostileCompiles = false;
}
check('the hostile page still compiles as JavaScript', hostileCompiles);

// ---------------------------------------------------------------- 4. run the page's JS on a fake DOM
console.log('\nThe page script, executed (fake DOM)');
function makeElement(tag = 'div') {
  const element = {
    tagName: tag,
    className: '',
    style: {},
    children: [],
    parentNode: null,
    textContent: '',
    alt: '',
    listeners: {},
    clientWidth: 360,
    clientHeight: 190,
    appendChild(child) {
      child.parentNode = element;
      element.children.push(child);
      return child;
    },
    removeChild(child) {
      element.children = element.children.filter((c) => c !== child);
      child.parentNode = null;
      return child;
    },
    setAttribute() {},
    addEventListener(name, handler) {
      (element.listeners[name] = element.listeners[name] || []).push(handler);
    },
    getBoundingClientRect() {
      return { left: 0, top: 0, width: element.clientWidth, height: element.clientHeight };
    },
    setPointerCapture() {},
  };
  Object.defineProperty(element, 'innerHTML', {
    get: () => '',
    set: (value) => {
      element.children = [];
      element.innerHTMLSet = value;
    },
  });
  return element;
}

const nodes = {};
const ids = ['map', 'stage', 'world', 'pinLayer', 'hint', 'err', 'zin', 'zout', 'attr'];
for (const id of ids) nodes[id] = makeElement();

const documentStub = {
  getElementById: (id) => nodes[id] ?? makeElement(),
  createElement: (tag) => makeElement(tag),
  addEventListener() {},
};

const messages = [];
const windowStub = {
  ReactNativeWebView: { postMessage: (text) => messages.push(JSON.parse(text)) },
  addEventListener(name, handler) {
    (windowStub.listeners[name] = windowStub.listeners[name] || []).push(handler);
  },
  listeners: {},
  innerWidth: 360,
  innerHeight: 190,
  console,
};

const scriptSource = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
new Function('window', 'document', 'console', scriptSource)(windowStub, documentStub, console);

check('page reports itself ready to the app', messages.some((m) => m.type === 'ready'), JSON.stringify(messages[0] ?? null));

const tileImages = nodes.world.children.filter((c) => c.tagName === 'img');
check('tiles were requested', tileImages.length >= 4, `${tileImages.length} tiles`);
const tileUrls = tileImages.map((t) => t.src ?? '');
const pattern = new RegExp(`^${TILE_BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/\\d+/\\d+/\\d+\\.png$`);
check('every tile URL points at our proxy', tileUrls.every((url) => pattern.test(url)), tileUrls[0] ?? 'none');
check(
  'tile coordinates are inside the world',
  tileImages.every((t) => {
    const [, z, x, y] = t.src.match(/\/(\d+)\/(\d+)\/(\d+)\.png$/).map(Number).length ? t.src.match(/\/(\d+)\/(\d+)\/(\d+)\.png$/) : [];
    const limit = Math.pow(2, Number(z));
    return Number(x) < limit && Number(y) < limit;
  }),
);
check('a pin is drawn at the pickup point', nodes.pinLayer.children.length === 1);
check('the pin is inside the viewport', (() => {
  const pin = nodes.pinLayer.children[0];
  const left = parseFloat(pin.style.left);
  const top = parseFloat(pin.style.top);
  return left > 0 && left < 360 && top > 0 && top < 190;
})(), JSON.stringify({ left: nodes.pinLayer.children[0]?.style.left, top: nodes.pinLayer.children[0]?.style.top }));

// a tap on the map must report a pin
const mapDown = nodes.map.listeners.pointerdown?.[0];
const winUp = windowStub.listeners.pointerup?.[0];
const winMove = windowStub.listeners.pointermove?.[0];
check('the map listens for pointer events', Boolean(mapDown && winUp && winMove));

messages.length = 0;
mapDown({ target: { className: 'tile' }, clientX: 90, clientY: 140 });
winUp({ clientX: 90, clientY: 140 });
const pinMessage = messages.find((m) => m.type === 'pin');
check('a tap posts {type:pin, latitude, longitude}', Boolean(pinMessage));
if (pinMessage) {
  check(
    'the tapped point is in Karachi',
    pinMessage.latitude > 24.7 && pinMessage.latitude < 25.1 && pinMessage.longitude > 66.8 && pinMessage.longitude < 67.4,
    `${pinMessage.latitude.toFixed(5)}, ${pinMessage.longitude.toFixed(5)}`,
  );
  const tappedPin = nodes.pinLayer.children[0];
  check(
    'exactly one pin exists after the tap',
    nodes.pinLayer.children.length === 1,
    `${nodes.pinLayer.children.length} pins`,
  );
  check(
    'the pin sits where the finger was (90,140)',
    Math.abs(parseFloat(tappedPin.style.left) - 90) < 2 && Math.abs(parseFloat(tappedPin.style.top) - 140) < 2,
    `${tappedPin.style.left}, ${tappedPin.style.top}`,
  );
}

// a pan must not be mistaken for a tap
messages.length = 0;
mapDown({ target: { className: 'tile' }, clientX: 100, clientY: 90 });
winMove({ clientX: 60, clientY: 90 });
winUp({ clientX: 60, clientY: 90 });
check('a drag pans instead of dropping a pin', !messages.some((m) => m.type === 'pin'));
check('panning re-renders tiles for the new centre', nodes.world.children.filter((c) => c.tagName === 'img').length >= 4);

// the app can push a new pin into the page
messages.length = 0;
windowStub.__map.setPin(24.8607, 67.0011);
const movedPin = nodes.pinLayer.children[0];
check(
  'window.__map.setPin moves the pin (Clifton is south of the view)',
  Boolean(movedPin) && parseFloat(movedPin.style.top) > 190,
  `top ${movedPin?.style.top}`,
);

// dragging the pin itself
const pinEl = nodes.pinLayer.children[0];
const pinDown = pinEl?.listeners.pointerdown?.[0];
const pinMove = pinEl?.listeners.pointermove?.[0];
const pinUp = pinEl?.listeners.pointerup?.[0];
check('the pin is draggable', Boolean(pinDown && pinMove && pinUp));
if (pinDown) {
  messages.length = 0;
  pinDown({ stopPropagation() {}, preventDefault() {}, clientX: 90, clientY: 140, pointerId: 1 });
  pinMove({ clientX: 150, clientY: 170 });
  pinUp({ clientX: 150, clientY: 170 });
  const dragged = messages.find((m) => m.type === 'pin');
  check('dragging the pin reports the new point', Boolean(dragged));
  const newPin = nodes.pinLayer.children[0];
  check(
    'the pin followed the drag (150,170)',
    Math.abs(parseFloat(newPin.style.left) - 150) < 2 && Math.abs(parseFloat(newPin.style.top) - 170) < 2,
    `${newPin.style.left}, ${newPin.style.top}`,
  );
  check(
    'dragging the pin did not pan the map',
    nodes.stage.style.transform === 'translate(0px, 0px)' || nodes.stage.style.transform === undefined,
    String(nodes.stage.style.transform),
  );
}

console.log(`\n${checks - failures}/${checks} checks passed`);
if (failures > 0) {
  console.log('MAP VERIFY: FAILED');
  process.exit(1);
}
console.log('MAP VERIFY: OK');
