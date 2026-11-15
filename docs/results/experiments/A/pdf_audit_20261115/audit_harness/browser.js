const {chromium} = require('/home/peachpetal/.cache/ms-playwright-go/1.57.0/package');
const fs = require('fs');
const root = 'docs/results/experiments/A/pdf_audit_20261115';
(async () => {
  const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
  const page = await browser.newPage({viewport:{width:1440,height:1080}});
  const errors = [], failed = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', r => { if(r.status()>=400) failed.push({url:r.url(),status:r.status()}); });
  const result = {tabs:[], errors, failed, scope:'Actual Chromium UI with current isolated Docker API and fresh reports; wait for Plotly rendering; audit browser uses private fontconfig with locally available Malgun font'};
  try {
    await page.goto('http://127.0.0.1:18501', {waitUntil:'networkidle'});
    await page.getByRole('tab', {name:'검색',exact:true}).waitFor({timeout:45000});
    await page.getByRole('button',{name:'검색 실행',exact:true}).waitFor({timeout:60000});
    for(const name of ['검색','추천','A/B 실험','시스템','EDA·구매 이력','상품·CLIP']) {
      await page.getByRole('tab',{name,exact:true}).click();
      await page.waitForTimeout(800);
      const panel = page.getByRole('tabpanel').filter({visible:true});
      if(['검색','추천','A/B 실험','시스템','EDA·구매 이력'].includes(name)) {
        await panel.locator('[data-testid="stPlotlyChart"] .js-plotly-plot').first().waitFor({timeout:60000});
      }
      result.tabs.push({name, text:await panel.innerText(), charts:await panel.locator('[data-testid="stPlotlyChart"]').count()});
      await page.screenshot({path:`${root}/browser_tab_${result.tabs.length}.png`});
    }
    await page.getByRole('tab',{name:'검색',exact:true}).click();
    await page.getByRole('textbox',{name:'검색어',exact:true}).fill('검정 오버핏 후드티');
    await page.getByRole('button',{name:'검색 실행',exact:true}).click();
    await page.getByText(/검정 오버핏 후드/).first().waitFor({timeout:45000});
    result.search_demo = true;
    await page.screenshot({path:root+'/browser_search.png'});
    await page.getByRole('tab',{name:'추천',exact:true}).click();
    await page.getByRole('button',{name:'추천 실행',exact:true}).click();
    await page.getByRole('button',{name:'이 상품 클릭 후 추천 비교',exact:true}).first().waitFor({timeout:45000});
    result.recommend_demo = true;
    await page.getByRole('button',{name:'이 상품 클릭 후 추천 비교',exact:true}).first().click();
    await page.getByText('클릭 전후 추천 API 응답을 모두 받았습니다.',{exact:true}).waitFor({timeout:45000});
    result.click_demo = true;
    result.after_click_text = await page.getByRole('tabpanel').filter({visible:true}).innerText();
    result.exceptions = await page.locator('[data-testid="stException"]').allTextContents();
    await page.screenshot({path:root+'/browser_recommend.png'});
    result.status = errors.length || failed.length || result.exceptions.length ? 'FAIL' : 'PASS';
  } catch(e) { result.status='FAIL';result.exception=e.message;await page.screenshot({path:root+'/browser_failure.png'}); }
  fs.writeFileSync(root+'/browser.json',JSON.stringify(result,null,2));
  console.log(JSON.stringify({status:result.status,exception:result.exception,tabs:result.tabs.map(t=>({name:t.name,charts:t.charts})),errors,failed}));
  await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
