import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-2-3: live team search creates one Write grant and reload retains it", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('grant-add')); await h.settings(page,'Manage access'); await h.button(page,'Add people or teams').click(); await h.field(page,'Search').fill('frontend-team'); await page.getByRole('option',{name:/frontend-team/}).click(); await h.choose(page,'Role','Write'); await h.button(page,'Add').click();
  const row=page.getByRole('row',{name:/frontend-team/}); await h.persisted(page, async () => { await expect(row).toHaveCount(1); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Write'); });
});

test("REQ-2-3: native Read selection replaces Write rather than appending a grant", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('grant-replace')); await h.settings(page,'Manage access'); const row=page.getByRole('row',{name:/frontend-team/}); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Write'); await row.getByRole('combobox',{name:'Role',exact:true}).selectOption({label:'Read'}); await h.button(row,'Save').click();
  await h.persisted(page, async () => { await expect(row).toHaveCount(1); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Read'); });
});
