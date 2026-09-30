import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-4-4: file creation persists exact contents and immutable commit history entry", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('file-create')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); const name=`${h.unique('pw-file')}.md`,message=`Add ${name}`;
  await h.field(page,'File name').fill(name); await h.field(page,'File contents').fill('Persisted file contents'); await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click(); await h.persisted(page, () => expect(h.text(page,'Persisted file contents').first()).toBeVisible()); await h.link(page,'Commits').click(); await expect(h.text(page,message).first()).toBeVisible();
});

test("REQ-4-4: invalid path and empty message cannot change files or history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-invalid')); await h.link(page,'Commits').click(); const before=await page.getByRole('link').allTextContents(); await page.goto(address); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
  await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved'); await h.button(page,'Commit changes').click(); await expect(page.getByText(/Invalid file path|Commit message is required/)).toBeVisible(); await page.goto(address); await expect(h.link(page,'invalid.md')).toHaveCount(0); await h.link(page,'Commits').click(); expect(await page.getByRole('link').allTextContents()).toEqual(before); await page.reload(); expect(await page.getByRole('link').allTextContents()).toEqual(before);
});
