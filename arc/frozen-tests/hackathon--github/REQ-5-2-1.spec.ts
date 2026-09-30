import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-5-2-1: Write creates issue with exact title/body and list reads same persisted record", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('issue-create')); await h.link(page,'Issues').click(); const listAddress=page.url(); await h.link(page,'New issue').click(); const title=h.unique('pw-issue'); await h.field(page,'Title').fill(title); await h.field(page,'Description').fill('Complete saved issue description.'); await h.button(page,'Submit new issue').click();
  await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Complete saved issue description.').first()).toBeVisible(); }); await page.goto(listAddress); await expect(h.link(page,title)).toBeVisible();
});

test("REQ-5-2-1: blank issue title creates neither issue nor partial record", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('issue-create-invalid')); await h.link(page,'Issues').click(); const before=await page.getByRole('link').allTextContents(),address=page.url(); await h.link(page,'New issue').click(); await h.field(page,'Title').fill('   '); await h.button(page,'Submit new issue').click(); await expect(page.getByText('Title is required',{exact:false})).toBeVisible(); await page.goto(address); expect(await page.getByRole('link').allTextContents()).toEqual(before); await page.reload(); expect(await page.getByRole('link').allTextContents()).toEqual(before);
});
