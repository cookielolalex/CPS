// Screenshot reconstructed-view HTML files with the preinstalled Playwright Chromium.
// Usage: node screenshot_views.cjs /abs/dir name1.html [name2.html ...]  -> writes name.png next to each
const {chromium} = require('playwright');
const path = require('node:path');
(async () => {
const [dir, ...names] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({viewport: {width: 1400, height: 900}, deviceScaleFactor: 1});
for (const n of names) {
  await page.goto('file://' + path.join(dir, n));
  await page.screenshot({path: path.join(dir, n.replace(/\.html$/, '.png')), fullPage: true});
}
await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
