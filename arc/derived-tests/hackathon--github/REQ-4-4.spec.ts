import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-4: file creation persists exact contents", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('file-create')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); const name=`${h.unique('pw-file')}.md`,message=`Add ${name}`;
  await h.field(page,'File name').fill(name); await h.field(page,'File contents').fill('Persisted file contents'); await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click(); await h.persisted(page, () => expect(h.text(page,'Persisted file contents').first()).toBeVisible());
});

test("REQ-4-4: invalid path rejects even with a valid commit message", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-invalid-path')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
  await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved'); await h.field(page,'Commit message').fill('Attempt invalid path'); await h.button(page,'Commit changes').click();
  await expect(h.text(page,'Invalid file path').first()).toBeVisible(); await page.goto(address); await h.persisted(page,()=>expect(h.link(page,'invalid.md')).toHaveCount(0));
});

test("REQ-4-4: empty commit message rejects even with a valid file path", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-invalid-message')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); const name=`${h.unique('valid')}.md`;
  await h.field(page,'File name').fill(name); await h.field(page,'File contents').fill('must not be saved'); await h.button(page,'Commit changes').click();
  await expect(h.text(page,'Commit message is required').first()).toBeVisible(); await page.goto(address); await h.persisted(page,()=>expect(h.link(page,name)).toHaveCount(0));
});
