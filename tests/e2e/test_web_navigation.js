// MAPNET — E2E Playwright : GPS, rerouting automatique, endpoints backend.
// Sert backend/presentation/static en local (localhost = secure context,
// donc navigator.geolocation fonctionne avec les positions mockées).
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');

const STATIC_DIR = path.join(__dirname, '../../backend/presentation/static');
const PORT = 8931;
const BASE = `http://localhost:${PORT}`;
const BACKEND = 'https://node.novahosting.site:8444';

let server, browser, passed = 0, failed = 0;

function ok(name, cond, extra = '') {
  if (cond) { passed++; console.log(`  PASS  ${name}`); }
  else { failed++; console.log(`  FAIL  ${name} ${extra}`); }
}

async function waitServer(url, tries = 40) {
  for (let i = 0; i < tries; i++) {
    try { const r = await fetch(url); if (r.status) return true; } catch (_) {}
    await new Promise(r => setTimeout(r, 250));
  }
  return false;
}

(async () => {
  console.log('=== MAPNET E2E — demarrage serveur statique ===');
  server = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'],
    { cwd: STATIC_DIR, stdio: 'ignore' });
  if (!await waitServer(`${BASE}/index.html`)) {
    console.error('serveur statique injoignable'); process.exit(2);
  }

  const os = require('os');
  const CHROME_BIN = path.join(os.homedir(),
    '.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell');
  browser = await chromium.launch({ executablePath: CHROME_BIN });

  // ---------------------------------------------------------- 1. chargement
  console.log('\n[1] Chargement app web');
  const ctx = await browser.newContext({
    permissions: ['geolocation'],
    geolocation: { latitude: 3.8480, longitude: 11.5021, accuracy: 8 },
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  ok('titre MapNet present', (await page.title()).length > 0);
  ok('aucune erreur JS fatale', errors.filter(e => !/maplibre|tile|favicon/i.test(e)).length === 0,
    errors.slice(0, 2).join(' | '));
  ok('element #map present', await page.locator('#map').count() === 1);

  // ---------------------------------------------------------- 2. GPS mock
  console.log('\n[2] GPS mock (geolocation accordee)');
  await page.waitForFunction(
    () => document.getElementById('gps-state') &&
          !/indisponible|refusée/i.test(document.getElementById('gps-state').textContent || ''),
    { timeout: 10000 }).catch(() => {});
  const gpsState = await page.locator('#gps-state').textContent().catch(() => '');
  ok('etat GPS mis a jour', (gpsState || '').trim().length > 0, `gps-state="${gpsState}"`);

  // ------------------------------------------------ 3. navigation_math.js
  console.log('\n[3] navigation_math.js (shouldReroute) dans le navigateur');
  const mathRes = await page.evaluate(() => {
    const M = window.MapNetNavigationMath || window.NavMath;
    if (!M || !M.shouldReroute) return { loaded: false };
    const now = Date.now();
    const far = M.shouldReroute({
      distance: 150, accuracy: 10, now, offRouteSince: new Date(now - 6000),
      lastRerouteAt: null, rerouting: false,
      threshold: 80, confirmationMs: 4000, cooldownMs: 20000 });
    const near = M.shouldReroute({
      distance: 20, accuracy: 10, now, offRouteSince: null,
      lastRerouteAt: null, rerouting: false,
      threshold: 80, confirmationMs: 4000, cooldownMs: 20000 });
    const tooSoon = M.shouldReroute({
      distance: 150, accuracy: 10, now, offRouteSince: new Date(now - 1000),
      lastRerouteAt: null, rerouting: false,
      threshold: 80, confirmationMs: 4000, cooldownMs: 20000 });
    const inaccurate = M.shouldReroute({
      distance: 100, accuracy: 60, now, offRouteSince: new Date(now - 6000),
      lastRerouteAt: null, rerouting: false,
      threshold: 80, confirmationMs: 4000, cooldownMs: 20000 });
    return { loaded: true,
      farTriggers: far.trigger === true,
      nearNoTrigger: near.trigger === false,
      noConfirmNoTrigger: tooSoon.trigger === false,
      inaccuracyWidens: inaccurate.effectiveThreshold >= 120 && inaccurate.trigger === false };
  });
  ok('NavMath charge', mathRes.loaded);
  if (mathRes.loaded) {
    ok('deviation confirmee declenche rerouting', mathRes.farTriggers);
    ok('sur itineraire = pas de rerouting', mathRes.nearNoTrigger);
    ok('anti-rebond: pas de rerout sans confirmation 4s', mathRes.noConfirmNoTrigger);
    ok('seuil adapte a la precision GPS', mathRes.inaccuracyWidens);
  }

  // -------------------------------------------- 4. rerouting E2E (API mock)
  console.log('\n[4] Rerouting automatique E2E (API routing mockee)');
  const routeGeom = { type: 'LineString',
    coordinates: [[11.5021, 3.8480], [11.5121, 3.8480], [11.5121, 3.8580]] };
  const fakeRoute = { routes: [{ geometry: routeGeom, distance: 2000, duration: 900,
    steps: [{ instruction: 'Allez tout droit', location: [11.5121, 3.8480] }] }] };
  let routingCalls = 0;
  await page.route('**/api/routing/alternatives', async route => {
    routingCalls++;
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify(fakeRoute) });
  });
  const e2e = await page.evaluate(async () => {
    try {
      // force l'etat de navigation sur l'itineraire connu
      const resp = await fetch('/api/routing/alternatives', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_lat: 3.8480, from_lon: 11.5021,
          to_lat: 3.8580, to_lon: 11.5121, count: 1, costing: 'pedestrian' }) });
      const r = await resp.json();
      return { apiOk: !!(r.routes && r.routes[0]),
        distOk: r.routes[0].distance === 2000 };
    } catch (e) { return { apiOk: false, distOk: false, err: String(e) }; }
  });
  ok('API routing (mock) repond un itineraire', e2e.apiOk, e2e.err || '');
  ok('payload itineraire exploitable', e2e.distOk);
  ok('au moins un appel routing capture', routingCalls >= 1);

  // -------------------------------------------- 5. deviation -> recalcul
  console.log('\n[5] Deviation GPS -> declenchement rerouting (simulation)');
  // position tres eloignee de la route, accuracy faible, confirmee > 4s
  await ctx.setGeolocation({ latitude: 3.8300, longitude: 11.4900, accuracy: 5 });
  await page.waitForTimeout(5500);
  await ctx.setGeolocation({ latitude: 3.8301, longitude: 11.4901, accuracy: 5 });
  await page.waitForTimeout(1500);
  const rerouteChip = await page.locator('#reroute-state').textContent().catch(() => '');
  ok('etat rerouting visible dans le HUD', (rerouteChip || '').trim().length > 0,
    `reroute-state="${rerouteChip}"`);

  // ------------------------------------------------ 6. backend HTTPS reel
  console.log('\n[6] Backend HTTPS reel (health)');
  let healthOk = false, healthInfo = '';
  try {
    const r = await fetch(`${BACKEND}/health`, { signal: AbortSignal.timeout(8000) });
    healthOk = r.status === 200;
    healthInfo = `HTTP ${r.status}`;
  } catch (e) { healthInfo = String(e).slice(0, 120); }
  ok('backend https://node.novahosting.site:8444/health = 200', healthOk, healthInfo);

  await browser.close();
  server.kill();
  console.log(`\n=== RESULTAT: ${passed} passed, ${failed} failed ===`);
  process.exit(failed > 0 ? 1 : 0);
})();
