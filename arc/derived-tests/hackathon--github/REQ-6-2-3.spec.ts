import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-3: create Open PR from comparison persists exact title and description", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.compare(page,'pr-create'); await h.button(page,'Create pull request').click(); const title=h.unique('pw-pr'); await h.field(page,'Title').fill(`  ${title}  `); await h.field(page,'Description').fill('Saved PR description'); await expect(h.button(page,'Create pull request')).toHaveCount(1); await h.button(page,'Create pull request').click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'Saved PR description').first()).toBeVisible(); });
});

test("REQ-6-2-3: blank PR title keeps form and creates no PR", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('pr-create-invalid')); await h.link(page,'Pull requests').click(); await expect(h.link(page,'New pull request')).toBeVisible(); const before=await page.getByRole('link').allTextContents(),listAddress=page.url(); await h.compare(page,'pr-create-invalid'); await h.button(page,'Create pull request').click(); await h.field(page,'Title').fill('   '); await h.button(page,'Create pull request').click(); await expect(page.getByText('Title is required',{exact:false})).toBeVisible(); await expect(h.field(page,'Title')).toBeVisible(); await page.goto(listAddress); await expect.poll(()=>page.getByRole('link').allTextContents()).toEqual(before); await page.reload(); await expect.poll(()=>page.getByRole('link').allTextContents()).toEqual(before);
});
