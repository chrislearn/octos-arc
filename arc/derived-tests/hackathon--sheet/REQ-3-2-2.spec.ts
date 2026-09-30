import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-2-2: undo/redo restores complete operations and a new edit discards redo branch", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'A1', 'first'); await h.paste(page, 'A1', 'second\tthird');
  await h.button(page, 'Undo').click(); await h.values(page, { A1:'first', B1:'' }); await page.keyboard.press('Control+z'); await h.values(page,{A1:'',B1:''});
  await h.button(page,'Redo').click(); await h.values(page,{A1:'first'}); await page.keyboard.press('Control+y'); await h.values(page,{A1:'second',B1:'third'});
  await h.button(page,'Undo').click(); await h.edit(page,'A1','new branch'); await expect(h.button(page,'Redo')).toBeDisabled(); await page.keyboard.press('Control+y');
  await h.persisted(page, () => h.values(page,{A1:'new branch',B1:''}));
});

test("REQ-3-2-2: undo state persists after reload and cannot modify a different saved workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); const otherName=h.unique(); await h.renameWorkbook(page,otherName); await h.edit(page,'A1','other-workbook');
  await h.blank(page); const name=h.unique(); await h.renameWorkbook(page,name); await h.edit(page,'A1','initial'); await h.edit(page,'A1','changed'); await h.button(page,'Undo').click();
  await h.persisted(page,()=>h.values(page,{A1:'initial'})); await h.reopen(page,otherName); await h.values(page,{A1:'other-workbook'}); await h.reopen(page,name); await h.values(page,{A1:'initial'});
});
