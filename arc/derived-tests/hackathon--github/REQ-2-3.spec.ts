import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"repo-admin"); await h.canonicalRepo(page);await h.settings(page,'Manage access'); await h.button(page,'Add people or teams').click(); const picker=await h.accessPicker(page); await h.field(picker,'Search').fill('frontend-team'); await h.option(page,'frontend-team'); await h.choose(picker,'Role','Write'); await h.button(picker,'Add').click(); const row=page.getByRole('row',{name:/frontend-team/}); await h.persisted(page,async()=>{await expect(row).toHaveCount(1); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Write');});
});

test("REQ-2-3: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"repo-admin"); await h.canonicalRepo(page);await h.settings(page,'Manage access'); const row=page.getByRole('row',{name:/access-role-team/}); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Write'); await row.getByRole('combobox',{name:'Role',exact:true}).selectOption({label:'Read'}); await h.button(row,'Save').click(); await h.persisted(page,async()=>{await expect(row).toHaveCount(1); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Read');});
});

test("REQ-2-3: live team grant admits its member and preserves private denial and one saved grant", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'repo-admin'); const address=await h.repo(page,h.fixtureRepo('grant-add'));
    const member=await browser.newContext(), visitor=await browser.newContext();
    try {
     const bob=await member.newPage(), ungranted=await visitor.newPage();
     await h.signIn(bob,'bob-reviewer'); await bob.goto(address); await expect(h.text(bob,'Access denied').first()).toBeVisible();
     await h.signIn(ungranted,'new-member'); await ungranted.goto(address); await expect(h.text(ungranted,'Access denied').first()).toBeVisible();
     await h.settings(page,'Manage access'); await h.button(page,'Add people or teams').click(); const picker=await h.accessPicker(page);
     await picker.getByRole('textbox',{name:'Search',exact:true}).fill('frontend-team'); await page.getByRole('option',{name:/frontend-team/}).click();
     await h.choose(picker,'Role','Write'); await h.button(picker,'Add').click(); const row=page.getByRole('row',{name:/frontend-team/});
     await h.persisted(page,async()=>{ await expect(row).toHaveCount(1); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Write'); });
     await bob.reload(); await expect(bob.getByRole('heading').filter({hasText:h.fixtureRepo('grant-add')})).toBeVisible(); await expect(h.text(bob,'Access denied')).toHaveCount(0);
     await ungranted.reload(); await expect(h.text(ungranted,'Access denied').first()).toBeVisible();
     await h.button(row,'Save').click(); await h.persisted(page,()=>expect(row).toHaveCount(1));
    } finally { await member.close(); await visitor.close(); }
});

test("REQ-2-3: native Read selection replaces Write rather than appending a grant", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'repo-admin'); await h.repo(page,h.fixtureRepo('grant-replace')); await h.settings(page,'Manage access'); const row=page.getByRole('row',{name:/frontend-team/}); await h.chosen(row,'Role','Write'); await h.choose(row,'Role','Read'); await h.button(row,'Save').click();
    await h.persisted(page, async () => { await expect(row).toHaveCount(1); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Read'); });
});
