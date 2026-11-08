#!/usr/bin/env node
/**
 * Static navigation audit for the expo-router app (no device needed).
 *
 * Checks
 *   1. Every navigation target (router.push/replace/navigate, <Link href>, Redirect href)
 *      resolves to a real file route — catches typos and dead links.
 *   2. Every Stack/Tabs screen declared in a layout points to a real file.
 *   3. Every non-tab screen has a way back (router.back / canGoBack / close / replace)
 *      because the root Stack hides native headers.
 *   4. router.back() is guarded with canGoBack() or has a replace fallback, so a deep link
 *      that opens a screen with no history does not dead-end.
 *   5. Protected areas ((tabs), protected stack screens) redirect signed-out users.
 *
 * Exit code 1 when any FAIL is found. WARN lines are printed but do not fail the run.
 * Run: node scripts/verify-navigation.mjs
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const APP = join(ROOT, 'app');
const SRC = join(ROOT, 'src');

let failures = 0;
let warnings = 0;
let passes = 0;
const fail = (msg) => { failures += 1; console.log(`FAIL  ${msg}`); };
const warn = (msg) => { warnings += 1; console.log(`WARN  ${msg}`); };
const pass = (msg) => { passes += 1; console.log(`ok    ${msg}`); };

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(tsx?|jsx?)$/.test(name)) out.push(full);
  }
  return out;
}

// ---------------------------------------------------------------- route table
// Turn a file path under app/ into a route pattern: groups "(x)" vanish, "index" collapses,
// "[id]" is a dynamic segment.
const appFiles = walk(APP);
const routeFiles = appFiles.filter((f) => !/_layout\.tsx?$/.test(f));
const routes = routeFiles.map((file) => {
  const rel = relative(APP, file).split(sep).join('/').replace(/\.(tsx?|jsx?)$/, '');
  const segments = rel
    .split('/')
    .filter((s) => s && !/^\(.*\)$/.test(s));
  if (segments.at(-1) === 'index') segments.pop();
  return { file, rel, segments, pattern: '/' + segments.join('/') };
});

/** Does a concrete href (already stripped of query/hash) match a route pattern? */
function matchesRoute(href) {
  const path = href.split('?')[0].split('#')[0].replace(/\/+$/, '') || '/';
  const parts = path.split('/').filter(Boolean);
  return routes.some((route) => {
    if (route.segments.length !== parts.length) return false;
    return route.segments.every((seg, i) => {
      if (/^\[.+\]$/.test(seg)) return parts[i] !== undefined && parts[i] !== '';
      return seg === parts[i];
    });
  });
}

// ------------------------------------------------------- navigation targets
const TARGET_RE = /router\.(?:push|replace|navigate)\(\s*(?:\{\s*pathname:\s*)?(['"`])([^'"`]+)\1/g;
const HREF_RE = /href=\{?\s*(['"`])([^'"`]+)\1/g;
const REDIRECT_RE = /<Redirect\s+href=\{?\s*(['"`])([^'"`]+)\1/g;

const allSrc = [...walk(APP), ...walk(SRC)];
const targetsSeen = [];
for (const file of allSrc) {
  const text = readFileSync(file, 'utf8');
  for (const re of [TARGET_RE, HREF_RE, REDIRECT_RE]) {
    re.lastIndex = 0;
    let match;
    while ((match = re.exec(text))) {
      const raw = match[2];
      if (!raw.startsWith('/')) continue; // relative or external — not a route
      // template placeholders → a concrete sample value so the dynamic segment matches
      const sample = raw.replace(/\$\{[^}]+\}/g, 'sample-id');
      targetsSeen.push({ file, raw, sample });
    }
  }
}

console.log('\n== 1. navigation targets resolve to real routes');
const seen = new Set();
for (const t of targetsSeen) {
  const key = `${t.raw}`;
  if (seen.has(key)) continue;
  seen.add(key);
  const where = relative(ROOT, t.file);
  // "/(tabs)/publish" is a valid href in expo-router; strip the group for matching.
  const normalised = t.sample.replace(/\/\([^)]*\)/g, '');
  const ok = normalised === '/' ? true : matchesRoute(normalised) || matchesRoute(normalised + '/');
  if (ok || normalised === '/') pass(`${t.raw.padEnd(34)} ← ${where}`);
  else fail(`${t.raw} has no matching route  ← ${where}`);
}
const literalTargets = targetsSeen.filter((t) => !t.raw.includes('${')).length;
console.log(`      (${targetsSeen.length} navigation calls scanned, ${literalTargets} literal)`);

// --------------------------------------------------- 2. declared screens exist
console.log('\n== 2. layout-declared screens exist as files');
const layoutFiles = appFiles.filter((f) => /_layout\.tsx?$/.test(f));
for (const layout of layoutFiles) {
  const dir = join(layout, '..');
  const text = readFileSync(layout, 'utf8');
  const declared = [...text.matchAll(/<(?:Stack|Tabs)\.Screen\s+name="([^"]+)"/g)].map((m) => m[1]);
  for (const name of declared) {
    const base = join(dir, name);
    const exists =
      appFiles.some((f) => f === base + '.tsx' || f === base + '.ts' || f === join(base, 'index.tsx')) ||
      // a group such as "(auth)" is a directory with its own _layout
      appFiles.some((f) => f === join(base, '_layout.tsx') || f === join(base, '_layout.ts'));
    const where = relative(ROOT, layout);
    if (exists) pass(`${name.padEnd(22)} declared in ${where}`);
    else fail(`${name} declared in ${where} but no file exists`);
  }
}

// ------------------------------------------------------------- 3. back control
console.log('\n== 3. every pushed screen has a way back');
const TAB_ROOTS = new Set(['(tabs)']);
const ENTRY_ROUTES = new Set(['/', '/welcome', '/login', '/signup', '/forgot-password']);
const BACK_HINT_RE = /goBackOr\(|router\.back\(|router\.canGoBack|router\.replace\(|accessibilityLabel="[^"]*(back|close)[^"]*"|arrow-back|chevron-back|name="close"|close-outline|Back|Cancel|Close/i;
for (const route of routes) {
  const firstSeg = route.rel.split('/')[0];
  if (TAB_ROOTS.has(firstSeg) || ENTRY_ROUTES.has(route.pattern)) continue;
  // (auth) welcome/login/signup are entry screens, which are checked above
  if (route.rel.startsWith('(auth)')) continue;
  const text = readFileSync(route.file, 'utf8');
  const where = relative(ROOT, route.file);
  if (BACK_HINT_RE.test(text)) pass(`${route.pattern.padEnd(26)} has a back/close control`);
  else fail(`${route.pattern} has no back/close control (root Stack hides headers)  ← ${where}`);
}

// ------------------------------------------------- 4. router.back() fallbacks
console.log('\n== 4. router.back() is safe without history (deep links)');
for (const file of allSrc) {
  const text = readFileSync(file, 'utf8');
  if (!/router\.back\(\)/.test(text)) continue;
  const where = relative(ROOT, file);
  const guarded = /canGoBack\(\)/.test(text) || /router\.replace\(/.test(text) || /goBackOr\(/.test(text);
  if (guarded) pass(`${where} guards router.back()`);
  else warn(`${where} calls router.back() with no canGoBack()/replace fallback (dead-ends on a deep link)`);
}

// ------------------------------------------------------------ 5. auth guard
console.log('\n== 5. protected areas redirect signed-out users');
{
  // One guard in the root layout covers tabs AND every protected stack screen.
  const rootLayout = join(APP, '_layout.tsx');
  const text = readFileSync(rootLayout, 'utf8');
  const where = relative(ROOT, rootLayout);
  const guarded = /function AuthGuard/.test(text) && /useSegments/.test(text) && /\/\(auth\)\/welcome/.test(text);
  if (guarded) pass(`${where} AuthGuard redirects signed-out deep links to welcome`);
  else fail(`${where} has no AuthGuard — a signed-out deep link can open protected screens`);
}

console.log('\n== 6. goBackOr behaviour (history vs no history)');
{
  const ts = await import('typescript');
  const src = readFileSync(join(SRC, 'lib', 'navigation.ts'), 'utf8');
  const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const mod = { exports: {} };
  new Function('exports', 'module', js)(mod.exports, mod);
  const { goBackOr } = mod.exports;
  const calls = [];
  const make = (canGoBack) => ({
    canGoBack: () => canGoBack,
    back: () => calls.push('back'),
    replace: (href) => calls.push(`replace:${href}`),
  });
  goBackOr(make(true));
  goBackOr(make(false));
  goBackOr(make(false), '/chats');
  if (calls[0] === 'back') pass('with history → router.back()'); else fail(`with history expected back, got ${calls[0]}`);
  if (calls[1] === 'replace:/(tabs)') pass('no history → replace to Home'); else fail(`no history expected replace:/(tabs), got ${calls[1]}`);
  if (calls[2] === 'replace:/chats') pass('no history → custom fallback honoured'); else fail(`custom fallback got ${calls[2]}`);
}

console.log(
  `\n${passes} passed · ${warnings} warnings · ${failures} failed`,
);
console.log(failures ? 'NAVIGATION VERIFY: FAIL' : 'NAVIGATION VERIFY: OK');
process.exit(failures ? 1 : 0);
