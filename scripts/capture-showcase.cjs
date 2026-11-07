// Capture real, loopback-only demo pages. No login, record creation, or DOM edits.
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const { chromium } = createRequire(path.join(root, 'frontend/package.json'))('@playwright/test');
const origin = 'http://127.0.0.1:3000';
const output = path.join(root, 'frontend/public/landing/assets/screens');
const pages = [
  ['console', '/console', '工作台'],
  ['data', '/data', '信息中心'],
  ['knowledge', '/knowledge', '原文资料库'],
  ['entrepreneurship', '/entrepreneurship', '创新创业'],
  ['tracker', '/tracker', '我的计划'],
  ['agent', '/agent', '校伴助手'],
];
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    const page = await context.newPage();
    const captures = [];
    for (const [name, route, title] of pages) {
      const response = await page.goto(origin + route);
      if (!response || response.status() !== 200 || !page.url().startsWith(origin + '/')) throw Error('Unavailable local page: ' + route);
      await page.locator('h1').first().waitFor({ state: 'visible' });
      await page.waitForFunction(() => !document.body.innerText.includes('正在读取…'));
      await page.evaluate(() => document.fonts.ready);
      const file = name + '.jpg';
      await page.screenshot({ path: path.join(output, file), type: 'jpeg', quality: 85, animations: 'disabled' });
      captures.push({ file, route, title, viewport: '1440x900', bytes: fs.statSync(path.join(output, file)).size });
    }
    console.log(JSON.stringify({ capturedAt: new Date().toISOString(), origin, mode: 'isolated local demo; unmodified browser render', captures }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
