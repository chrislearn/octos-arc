import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-contributor"); await h.canonicalRepo(page);await h.link(page,'Compare').click(); await expect(h.text(page,'src/search.ts')).toBeVisible(); await h.button(page,'Create pull request').click(); const title=h.unique('pw-pr'); await h.field(page,'Title').fill(title); await h.button(page,'Create pull request').click(); await h.persisted(page,async()=>{await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible();});
});

test("REQ-6-2-3: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-contributor"); await h.canonicalRepo(page);await h.link(page,'Compare').click(); await expect(h.text(page,'src/search.ts')).toBeVisible(); await h.button(page,'Create pull request').click(); await h.field(page,'Title').fill('   '); await h.button(page,'Create pull request').click(); await expect(h.titleRequiredReason(page).first()).toBeVisible(); await expect(h.field(page,'Title')).toHaveValue('   ');
});

test("REQ-6-2-3: create Open PR from comparison persists exact title and description", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.compare(page,'pr-create'); await h.button(page,'Create pull request').click(); const title=h.unique('pw-pr'); await h.field(page,'Title').fill(title); await h.field(page,'Description').fill('Saved PR description'); await expect(h.button(page,'Create pull request')).toHaveCount(1); await h.button(page,'Create pull request').click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'Saved PR description').first()).toBeVisible(); });
});

test("REQ-6-2-3: blank PR title keeps form and creates no PR", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.repo(page,h.fixtureRepo('pr-create-invalid')); await h.link(page,'Pull requests').click(); await expect(h.link(page,'New pull request')).toBeVisible(); const before=await page.getByRole('link').allTextContents(),listAddress=page.url(); await h.compare(page,'pr-create-invalid'); await h.button(page,'Create pull request').click(); await h.field(page,'Title').fill('   '); await h.button(page,'Create pull request').click(); await expect(h.titleRequiredReason(page).first()).toBeVisible(); await expect(h.field(page,'Title')).toBeVisible(); await page.goto(listAddress); await expect.poll(()=>page.getByRole('link').allTextContents()).toEqual(before); await page.reload(); await expect.poll(()=>page.getByRole('link').allTextContents()).toEqual(before);
});

test("REQ-6-2-3: context REQ-6-1: Admin changes current compare-commit check pending to success and persists setter", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'repo-admin'); await h.pr(page,'check-success-node'); await expect(h.text(page,'test: pending').first()).toBeVisible(); const address=page.url(), visitor=await browser.newContext();
    try { const observed=await visitor.newPage(); await observed.goto(address); await expect(h.text(observed,'test: pending').first()).toBeVisible();
    await h.choose(page,'test','success'); await h.action(page,['Save','Update']).click();
    await h.persisted(page,()=>expect(h.text(page,'test: success').first()).toBeVisible());
    await observed.reload(); await h.persisted(observed,async()=>{ await expect(h.text(observed,'test: success').first()).toBeVisible(); await expect(h.containsValue(observed,'repo-admin').first()).toBeVisible(); });
    } finally { await visitor.close(); }
});
