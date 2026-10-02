import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-1-3: single worksheet rename rejects empty input then trims and persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.sheetMenu(page,'Sheet1','Rename');
  const dialog=page.getByRole('dialog',{name:'Rename worksheet',exact:true}); await expect(h.field(dialog,'Worksheet name')).toHaveValue('Sheet1');
  await h.field(dialog,'Worksheet name').fill('  '); await h.button(dialog,'Save').click(); await expect(h.text(page,'Worksheet name cannot be empty').first()).toBeVisible();
  await page.reload(); await expect(h.tab(page,'Sheet1')).toBeVisible(); await h.sheetMenu(page,'Sheet1','Rename');
  await h.field(page,'Worksheet name').fill('  Sales  '); await h.button(page.getByRole('dialog',{name:'Rename worksheet',exact:true}),'Save').click();
  await h.persisted(page,async()=>{ await h.tabOrder(page,['Sales']); await expect(h.tab(page,'Sales')).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:''}); });
});
