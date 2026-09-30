import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-2-1-3: rename sheet trims and persists; duplicate and empty names preserve original", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.button(page, 'Add worksheet').click(); await h.sheetMenu(page, 'Sheet2', 'Rename');
  const dialog = page.getByRole('dialog', { name: 'Rename worksheet', exact: true }); await expect(h.field(dialog, 'Worksheet name')).toHaveValue('Sheet2');
  await h.field(dialog, 'Worksheet name').fill('Sheet1'); await h.button(dialog, 'Save').click(); await expect(h.text(page, 'Worksheet name already exists').first()).toBeVisible();
  await h.field(dialog, 'Worksheet name').fill('  '); await h.button(dialog, 'Save').click(); await expect(h.text(page, 'Worksheet name cannot be empty').first()).toBeVisible();
  await page.reload(); await expect(h.tab(page, 'Sheet2')).toBeVisible(); await h.sheetMenu(page, 'Sheet2', 'Rename');
  await h.field(page, 'Worksheet name').fill('  Analysis  '); await h.button(page.getByRole('dialog', { name: 'Rename worksheet', exact: true }), 'Save').click();
  await h.persisted(page, () => expect(h.tab(page, 'Analysis')).toBeVisible()); await expect(h.tab(page, 'Sheet2')).toHaveCount(0);
});

test("INTEGRATION-deferred-2-1-3: sheet rename preserves its slot, values, selection, rules and active state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.button(page,'Add worksheet').click(); await h.edit(page,'B2','50'); await h.validation(page,'B2','B3'); await h.cell(page,'B2').click();
  await h.sheetMenu(page,'Sheet2','Rename'); const dialog=page.getByRole('dialog',{name:'Rename worksheet',exact:true}); await h.field(dialog,'Worksheet name').fill('  Analysis  '); await h.button(dialog,'Save').click();
  await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Analysis']); await expect(h.tab(page,'Analysis')).toHaveAttribute('aria-selected','true'); await expect(h.cell(page,'B2')).toHaveAttribute('aria-selected','true'); await h.values(page,{B2:'50'}); });
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'50'});
});
