import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-file-history: invalid path and empty message cannot change files or history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-invalid')); await h.link(page,'Commits').click(); const before=await h.historyLinks(page); await page.goto(address); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved'); await h.button(page,'Commit changes').click(); await expect(h.fileValidationReason(page).first()).toBeVisible(); await page.goto(address); await expect(h.link(page,'invalid.md')).toHaveCount(0); await h.link(page,'Commits').click(); await expect.poll(()=>h.historyLinks(page),{message:'Rejected commit must preserve history'}).toEqual(before); await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(before);
});

test("INTEGRATION-file-history: successful file write adds a commit while an earlier revision keeps its original bytes", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-history')); await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); const original=page.url();
    await page.goto(address); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await h.button(page,'Edit').click(); const message=h.unique('Update');
    await h.field(page,'File contents').fill('export const search = "new immutable snapshot";'); await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click(); await expect(h.text(page,'export const search = "new immutable snapshot";')).toBeVisible();
    await h.link(page,'Commits').click(); await expect(h.link(page,message)).toBeVisible(); await page.goto(original);
    await h.persisted(page,async()=>{ await expect(page.locator('body')).toContainText('export const search = "search flow";'); await expect(page.locator('body')).not.toContainText('new immutable snapshot'); });
});
