import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-1-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.scenarioIssue(page,"Improve onboarding"); await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(page.getByRole('article').first()).toBeVisible();
});

test("REQ-5-1-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.scenarioIssue(page,"Improve onboarding"); await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(page.getByRole('article').first()).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
});

test("REQ-5-1-2: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.scenarioIssue(page,"Improve onboarding"); await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(page.getByRole('article').first()).toBeVisible(); await h.scenarioIssue(page,"Improve onboarding"); await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible();
});

test("REQ-5-1-2: 81c7432a compatibility: issue navigation and named discussion entries are ready along the public chain", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Acme Demo').click(); await h.link(page,'acme-docs').click();
  expect(await h.link(page,'Issues').isVisible()).toBe(true); await h.link(page,'Issues').click();
  for (const name of ['Improve onboarding','Editable onboarding issue','Original issue title','Commentable onboarding issue',
    'Comment validation issue','Assignable onboarding issue','Labelable onboarding issue','Milestone onboarding issue',
    'Closable onboarding issue','Protected onboarding issue']) expect(await h.link(page,name).isVisible(),name).toBe(true);
  await h.link(page,'Improve onboarding').click(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
});

test("REQ-5-1-2: reference navigation: an issue direct link and reload retain its repository and sibling navigation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page); await h.link(page,'Issues').click();
  await h.link(page,'Improve onboarding').click(); const address=page.url(); await h.home(page); await page.goto(address);
  for (let attempt=0;attempt<2;attempt++) {
    await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'Pull requests')).toBeVisible();
    if (!attempt) await page.reload();
  }
  await h.link(page,'acme-docs').click(); await expect(h.link(page,'Code')).toBeVisible();
});

test("REQ-5-1-2: home workspace: every seeded issue entry is discoverable directly by its title", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for (const title of ['Improve onboarding','Legacy welcome text','Editable onboarding issue','Original issue title',
    'Commentable onboarding issue','Comment validation issue','Assignable onboarding issue','Labelable onboarding issue',
    'Milestone onboarding issue','Closable onboarding issue','Protected onboarding issue']) {
    await h.home(page); await expect(h.link(page,title)).toHaveCount(1); await h.link(page,title).click();
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  }
});

test("REQ-5-1-2: home workspace: colliding titles remain operable with repository-specific accessible names", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await expect(h.link(page,'Improve onboarding')).toHaveCount(1);
  await expect(page.getByText('Improve onboarding',{exact:true})).toHaveCount(1);
  const alternatives=page.getByRole('link',{name:/^Improve onboarding — /});
  await expect(alternatives.first()).toBeVisible(); const label=await alternatives.first().getAttribute('aria-label');
  expect(label).toMatch(/Improve onboarding — .+\/.+/);
  await alternatives.first().click(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
});

test("REQ-5-1-2: home workspace: repository search still presents exact repository results without work-item duplicates", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await expect(h.link(page,'Improve onboarding')).toBeVisible();
  const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('acme-docs'); await search.press('Enter');
  await expect(h.link(page,'acme-docs')).toHaveCount(1); await expect(h.link(page,'Improve onboarding')).toHaveCount(0);
  await h.openRepositoryResult(page,'acme-docs','Acme Demo'); await expect(h.link(page,'Code')).toBeVisible();
});

test("REQ-5-1-2: visitor issue detail shows complete title, description and readable timeline", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.issue(page); const address=page.url(); await page.goto(address); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.text(page,'Describe the onboarding improvement.').first()).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(page.getByText(/Comment|Activity/).first()).toBeVisible(); });
});
