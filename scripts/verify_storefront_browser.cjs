/* Real browser + real APIs. No route mocking or replacement catalog. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '../storefront/node_modules/playwright');
(async () => {
  const origin = process.env.STOREFRONT_URL || 'http://127.0.0.1:3000';
  const results = process.env.RESULTS_DIR || path.join(process.env.RUNTIME_RESULTS_DIR || 'docs/results/docker/runtime-illustrations-v1', process.env.SCALE || 'full');
  const out = process.env.BROWSER_RESULTS || path.join(results, 'browser', 'storefront');
  fs.mkdirSync(out, {recursive: true});
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const report = {started_at: new Date().toISOString(), origin, checks: {}, errors: [], events: [], captures: []};
  page.on('pageerror', error => report.errors.push(String(error)));
  page.on('console', message => {if (message.type() === 'error') report.errors.push(message.text())});
  page.on('request', request => {
    if (/\/api\/live\/api\/(event|feedback)$/.test(request.url())) {
      report.events.push({payload: request.postDataJSON(), request_id: request.headers()['x-recommendation-request-id'] || null});
    }
  });
  async function shot(name) {const file = path.join(out, name + '.png'); await page.screenshot({path: file, fullPage: true}); report.captures.push(file)}
  try {
    await page.goto(origin, {waitUntil: 'networkidle'});
    await page.getByRole('heading', {name: '오늘의 취향을 만나보세요'}).waitFor();
    assert(await page.locator('img').count() > 0);
    assert(await page.locator('img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0)));
    report.checks.catalog_images = true; await shot('home');
    await page.goto(origin + '/shop');
    await page.getByRole('heading', {name: '전체 상품', exact: true}).waitFor();
    await page.getByRole('combobox', {name: '상품 정렬'}).selectOption('price-asc');
    await page.waitForURL('**/shop?sort=price-asc'); report.checks.catalog_sort = true;
    await shot('catalog');
    await page.goto(origin + '/search');
    await page.getByLabel('검색어', {exact: true}).fill('검정 가방');
    await page.getByRole('button', {name: '검색하기', exact: true}).click();
    await page.getByRole('status').filter({hasText: '텍스트 검색'}).waitFor({timeout: 90000});
    const imageUrl = await page.locator('main img').first().getAttribute('src');
    const raw = await page.request.get(origin + imageUrl); assert.equal(raw.status(), 200);
    const image = await raw.body();
    await shot('text-search'); report.checks.text_search = true;
    await page.getByLabel('검색 이미지', {exact: true}).setInputFiles({name: 'catalog.jpg', mimeType: 'image/jpeg', buffer: image});
    await page.getByRole('button', {name: '검색하기', exact: true}).click();
    await page.getByRole('status').filter({hasText: '복합 검색'}).waitFor({timeout: 90000});
    report.checks.hybrid_search = true; await shot('hybrid-search');
    await page.getByLabel('검색어', {exact: true}).fill('');
    await page.getByRole('button', {name: '검색하기', exact: true}).click();
    await page.getByRole('status').filter({hasText: '이미지 검색'}).waitFor({timeout: 90000});
    report.checks.image_search = true;
    await page.goto(origin + '/recommend');
    const uid = 'storefront-browser-' + Date.now(); report.user_id = uid;
    await page.getByLabel('사용자 ID', {exact: true}).fill(uid);
    await page.getByRole('button', {name: '추천받기', exact: true}).click();
    await page.getByRole('status').filter({hasText: '노출 기록됨'}).waitFor({timeout: 90000});
    const productLink = page.locator('main a[href^="/product/"]').first();
    const href = await productLink.getAttribute('href'); report.recommendation_link = href;
    assert(new URL(href, origin).searchParams.get('rid'));
    await shot('recommend'); await productLink.click();
    await page.getByText('상품 조회가 기록되었습니다.', {exact: true}).waitFor({timeout: 30000});
    await shot('product');
    await page.getByRole('button', {name: '장바구니 담기', exact: true}).click();
    await page.getByRole('link', {name: '데모 구매', exact: true}).waitFor();
    await shot('cart');
    await page.getByRole('link', {name: '데모 구매', exact: true}).click();
    await page.getByRole('button', {name: '구매 이벤트 기록', exact: true}).click();
    await page.getByRole('status').filter({hasText: '구매 기록 완료'}).waitFor({timeout: 30000});
    await shot('purchase');
    const requestId = new URL(href, origin).searchParams.get('rid');
    for (const kind of ['view', 'cart', 'purchase']) assert(report.events.some(row => row.payload.event_type === kind && row.request_id === requestId && row.payload.user_id === uid));
    report.checks.attributed_shopping = true;
    await page.goto(origin + '/operations');
    await page.getByText('마지막 조회', {exact: false}).waitFor({timeout: 30000});
    const operations = (await page.request.get(origin + '/api/live/api/storefront/operations'));
    assert.equal(operations.status(), 200); const body = await operations.json();
    report.operations = body; report.checks.operations = true; await shot('operations');
    assert.equal((await page.request.post(origin + '/api/live/api/admin/reload', {data: {}})).status(), 404);
    assert.equal((await page.request.post(origin + '/api/live/api/event', {headers: {origin: 'https://other.example'}, data: {}})).status(), 403);
    report.checks.proxy_boundary = true;
    await page.setViewportSize({width: 390, height: 844}); await page.goto(origin + '/shop');
    await page.getByRole('heading', {name: '전체 상품', exact: true}).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole('button', {name: '메뉴 열기'}).click();
    await page.getByRole('dialog').waitFor(); report.checks.mobile = true; await shot('mobile');
    assert.deepEqual(report.errors, []); report.status = 'PASS';
  } catch (error) {report.status = 'FAIL'; report.error = String(error); await shot('failure'); process.exitCode = 1}
  finally {report.completed_at = new Date().toISOString(); fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify({status: report.status, checks: report.checks, errors: report.errors, error: report.error})); await browser.close()}
})();
