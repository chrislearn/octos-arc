// Requirement seed preflight. Uses public UI and the named requirement accounts,
// rather than replacing them with spec-* fixtures or changing application state.
const {chromium, expect} = require('@playwright/test');
const fs = require('node:fs');
const origin = process.env.E2E_BASE_URL || 'http://127.0.0.1:3000';

async function organization(page) {
  await page.goto(origin);
  const search = page.getByRole('searchbox', {name:'Search', exact:true});
  await search.fill('acme-docs'); await search.press('Enter');
  const links = page.getByRole('link', {name:'acme-docs', exact:true});
  await expect(links.first()).toBeVisible();
  const index = await links.evaluateAll(nodes => nodes.findIndex(node => {
    for (let group = node.parentElement; group; group = group.parentElement) {
      if ([...group.querySelectorAll('a')].filter(a => a.textContent.trim() === 'acme-docs').length > 1) return false;
      if (/acme-demo\s*\/\s*acme-docs|Acme Demo\s*\/\s*acme-docs/.test(group.textContent)) return true;
    }
    return false;
  }));
  expect(index, 'Search results expose the Acme Demo repository owner').toBeGreaterThanOrEqual(0);
  await links.nth(index).click();
  await page.getByRole('link', {name:'Acme Demo', exact:true}).click();
  await expect(page.getByRole('heading').filter({hasText:'Acme Demo'})).toBeVisible();
}

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/opt/google/chrome/chrome',args:['--no-sandbox']});
  const checks=[];
  async function check(name, action) {
    const context=await browser.newContext(),page=await context.newPage();
    try { await action(page);checks.push({name,passed:true}); }
    catch(error) { checks.push({name,passed:false,error:error.message}); }
    finally { await context.close(); }
  }
  try {
    await check('REQ-2 seed: visitor discovers frontend-team in Acme Demo',async page => {
      await organization(page);
      await page.getByRole('link',{name:'Teams',exact:true}).click();
      await expect(page.getByRole('link',{name:'frontend-team',exact:true})).toBeVisible({timeout:2500});
    });
    await check('REQ-2 actor: alice-dev can enter seeded organization and create teams',async page => {
      await page.goto(origin);
      await page.getByRole('link',{name:'Sign in',exact:true}).click();
      await page.getByLabel('Username or email',{exact:true}).fill('alice-dev');
      await page.getByLabel('Password',{exact:true}).fill('Valid-password-123!');
      await page.getByRole('button',{name:'Sign in',exact:true}).click();
      await page.getByRole('button',{name:'Account menu',exact:true}).click();
      await page.getByRole('link',{name:'Your organizations',exact:true}).click();
      await expect(page.getByText('Acme Demo',{exact:true})).toBeVisible({timeout:2500});
      await organization(page);
      await page.getByRole('link',{name:'Teams',exact:true}).click();
      await expect(page.getByRole('link',{name:'New team',exact:true})).toBeVisible({timeout:2500});
      await page.getByRole('link',{name:'People',exact:true}).click();
      await expect(page.getByText('bob-reviewer',{exact:true})).toBeVisible({timeout:2500});
    });
    await check('REQ-2 discovery: named public repository and private exclusion',async page => {
      await organization(page);
      await page.getByRole('link',{name:'Repositories',exact:true}).click();
      await page.getByLabel('Find a repository',{exact:true}).fill('acme-docs');
      await expect(page.getByRole('link',{name:'acme-docs',exact:true})).toBeVisible();
      await page.getByLabel('Find a repository',{exact:true}).fill('secret-research');
      await expect(page.getByRole('link',{name:'secret-research',exact:true})).toHaveCount(0);
    });
    await check('REQ-3 prerequisite: global Search remains usable from the organization page',async page => {
      await organization(page);
      await page.getByRole('link',{name:'Teams',exact:true}).click();
      const search=page.getByRole('searchbox',{name:'Search',exact:true});
      await expect(search).toBeVisible({timeout:2500});
      await search.fill('acme-docs'); await search.press('Enter');
      await expect(page.getByRole('link',{name:'acme-docs',exact:true}).first()).toBeVisible();
    });
  } finally { await browser.close(); }
  if(process.env.GUIDE_REPORT)fs.writeFileSync(process.env.GUIDE_REPORT,JSON.stringify({origin,checks},null,2)+'\n');
  console.log(JSON.stringify(checks,null,2));
  if(checks.some(c=>!c.passed))process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
