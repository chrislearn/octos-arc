import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-1-1: append blank worksheets in order and activate each new A1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);
  for(const name of ['Sheet2','Sheet3']) { await h.button(page,'Add worksheet').click(); await expect(h.tab(page,name)).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:''}); await expect(h.cell(page,'A1')).toHaveAttribute('aria-selected','true'); }
  await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Sheet2','Sheet3']); await expect(h.tab(page,'Sheet3')).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:''}); });
});

test("REQ-2-1-1: context REQ-2-1-3: rename sheet trims and persists; duplicate and empty names preserve original", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.button(page, 'Add worksheet').click(); await h.sheetMenu(page, 'Sheet2', 'Rename');
  const dialog = page.getByRole('dialog', { name: 'Rename worksheet', exact: true }); await expect(h.field(dialog, 'Worksheet name')).toHaveValue('Sheet2');
  await h.field(dialog, 'Worksheet name').fill('Sheet1'); await h.button(dialog, 'Save').click(); await expect(h.text(page, 'Worksheet name already exists').first()).toBeVisible();
  await h.field(dialog, 'Worksheet name').fill('  '); await h.button(dialog, 'Save').click(); await expect(h.text(page, 'Worksheet name cannot be empty').first()).toBeVisible();
  await page.reload(); await expect(h.tab(page, 'Sheet2')).toBeVisible(); await h.sheetMenu(page, 'Sheet2', 'Rename');
  await h.field(page, 'Worksheet name').fill('  Analysis  '); await h.button(page.getByRole('dialog', { name: 'Rename worksheet', exact: true }), 'Save').click();
  await h.persisted(page, () => expect(h.tab(page, 'Analysis')).toBeVisible()); await expect(h.tab(page, 'Sheet2')).toHaveCount(0);
});
