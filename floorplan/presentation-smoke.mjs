import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const html = resolve('floorplan/steimmo-map-praesentation.html');
const out = resolve('floorplan/presentation-output');
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
await page.goto('file://' + html, { waitUntil: 'load', timeout: 60000 });
await page.waitForTimeout(8000);
const title = await page.title();
if (!title.includes('STEImmo')) throw Error('Missing STEImmo page title');
const zoomIn = page.locator('#z-in');
const zoomOut = page.locator('#z-out');
const fit = page.locator('#z-fit');
for (const [name, element] of [['zoom in',zoomIn],['zoom out',zoomOut],['fit',fit]]) {
  if (!await element.isVisible()) throw Error(name + ' control is missing');
}
await zoomIn.click(); await zoomOut.click(); await fit.click();
const searchBtn = page.locator('#search-btn');
if (!await searchBtn.isVisible()) throw Error('Search control is missing');
await searchBtn.click();
await page.keyboard.press('Escape');
const state = await page.evaluate(() => ({
  text: document.body.innerText.slice(0,3000),
  svg: document.querySelectorAll('svg').length,
  nodeCount: document.querySelectorAll('[data-node-id], .node, .n-card').length,
  width: document.documentElement.scrollWidth,
  height: document.documentElement.scrollHeight,
  direction: document.documentElement.getAttribute('data-presentation')
}));
if (!state.svg && !state.nodeCount) throw Error('No map visualization found');
await page.setViewportSize({width:5120,height:2880});
await fit.click();
await page.waitForTimeout(1500);
await page.screenshot({ path: out + '/steimmo-architektur-5k.png', fullPage: false, animations: 'disabled' });
console.log(JSON.stringify({ title, state, errors }, null, 2));
if (errors.length) throw Error('Browser errors: ' + errors.slice(0, 5).join(' | '));
await browser.close();
