const { chromium } = require('/tmp/openclass-portal-phase-10/node_modules/@playwright/test');
const fs = require('node:fs');
const root = '/home/yassin/Projects/OpenClass/artifacts/application-proofs/scikit-learn-2026-10-02';
(async () => {
  const manifest = JSON.parse(fs.readFileSync(root+'/manifest.json','utf8'));
  const browser = await chromium.launch({executablePath:'/usr/bin/chromium',headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://127.0.0.1:5173/projects');
  await page.getByRole('button',{name:/Continue with Keycloak/}).click();
  await page.locator('#username').fill('owner@acme.openclass.test');
  await page.locator('#password').fill('OpenClass-Local-Owner-2026');
  await page.locator('#kc-login').click();
  await page.waitForURL('http://127.0.0.1:5173/**');
  await page.getByRole('heading',{name:'Projects',exact:true}).waitFor();
  await page.getByText('Real scikit-learn issue triage',{exact:true}).waitFor();
  await page.screenshot({path:root+'/workspace.png',fullPage:true});
  const verified = [];
  for (const [model, conf] of Object.entries(manifest.projects)) {
    await page.goto('http://127.0.0.1:5173/projects/'+conf.project.id+'/runs');
    await page.getByRole('heading',{name:/Decision history/}).waitFor({timeout:10000}).catch(()=>{});
    await page.waitForTimeout(600);
    await page.locator('tbody tr').first().click();
    await page.getByRole('dialog',{name:'Run detail'}).waitFor();
    await page.getByRole('dialog').getByText(/provider openai-compatible/).waitFor({timeout:15000});
    const text = await page.locator('body').innerText();
    verified.push({model,route:'runs',realProviderVisible:text.includes('openai-compatible'),
      modelVisible:text.includes(conf.model),simulatedBadge:text.includes('simulated')});
    await page.screenshot({path:root+'/'+model+'-run-detail.png',fullPage:true});
    await page.getByRole('button',{name:'Close',exact:true}).click();
    await page.screenshot({path:root+'/'+model+'-runs.png',fullPage:true});
    await page.goto('http://127.0.0.1:5173/projects/'+conf.project.id+'/discoveries');
    await page.waitForTimeout(600);
    await page.screenshot({path:root+'/'+model+'-discoveries.png',fullPage:true});
  }
  const report = await page.goto('http://127.0.0.1:5173/real-issue-triage-report.html');
  if(report.status()===200){
    await page.screenshot({path:root+'/report.png',fullPage:true});
    await page.locator('#filter').selectOption('trusted');
    verified.push({route:'report',trustedDisagreementRows:await page.locator('#rows tr').count()});
  }
  fs.writeFileSync(root+'/browser-verification.json',JSON.stringify({verified,errors},null,2));
  await browser.close();
  console.log(JSON.stringify({verified,errors}));
})().catch(e=>{console.error(e.message);process.exit(1)});
