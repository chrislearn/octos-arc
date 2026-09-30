import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-3-2-2: undo/redo restores complete operations and a new edit discards redo branch", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'A1', 'first'); await h.paste(page, 'A1', 'second\tthird');
  await h.button(page, 'Undo').click(); await h.values(page, { A1:'first', B1:'' }); await page.keyboard.press('Control+z'); await h.values(page,{A1:'',B1:''});
  await h.button(page,'Redo').click(); await h.values(page,{A1:'first'}); await page.keyboard.press('Control+y'); await h.values(page,{A1:'second',B1:'third'});
  await h.button(page,'Undo').click(); await h.edit(page,'A1','new branch'); await expect(h.button(page,'Redo')).toBeDisabled(); await page.keyboard.press('Control+y');
  await h.persisted(page, () => h.values(page,{A1:'new branch',B1:''}));
});

test("REQ-3-2-2: undo row structure restores formulas and redo result persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A2','10'); await h.edit(page,'B2','=A2*2'); await h.structure(page,'row','2','Insert 1 row above');
  await h.formula(page,'B3','=A3*2','20'); await h.button(page,'Undo').click(); await h.formula(page,'B2','=A2*2','20');
  await h.button(page,'Redo').click(); await h.persisted(page, () => h.formula(page,'B3','=A3*2','20'));
});

test("REQ-3-2-2: undo and redo a range cut restore both rectangles and original formulas as one operation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','2\t=2+3\n3\t=6/2'); await h.paste(page,'C3','old-1\told-2\nold-3\told-4'); await h.edit(page,'F6','outside'); await h.range(page,'A1','B2');
  await page.keyboard.press('Control+x'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v'); await h.button(page,'Undo').click();
  await h.values(page,{A1:'2',A2:'3',C3:'old-1',D3:'old-2',C4:'old-3',D4:'old-4',F6:'outside'}); await h.formula(page,'B1','=2+3','5'); await h.formula(page,'B2','=6/2','3');
  await h.button(page,'Redo').click(); await h.persisted(page,async()=>{await h.values(page,{A1:'',B1:'',A2:'',B2:'',C3:'2',C4:'3',F6:'outside'}); await h.formula(page,'D3','=2+3','5'); await h.formula(page,'D4','=6/2','3');});
});

test("REQ-3-2-2: undo/redo row structure restores numeric rule ranges and last visible values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,"row","2","Insert 1 row above");
  await h.values(page,{B2:'',"B3":'50'}); await h.button(page,'Undo').click(); await h.values(page,{B2:'50',"B3":''});
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'50'});
  await h.button(page,'Redo').click(); await h.persisted(page,()=>h.values(page,{B2:'',"B3":'50'})); await h.edit(page,"B3",'101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{"B3":'50'});
});

test("REQ-3-2-2: undo/redo column structure restores numeric rule ranges and last visible values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,"column","B","Insert 1 column left");
  await h.values(page,{B2:'',"C2":'50'}); await h.button(page,'Undo').click(); await h.values(page,{B2:'50',"C2":''});
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'50'});
  await h.button(page,'Redo').click(); await h.persisted(page,()=>h.values(page,{B2:'',"C2":'50'})); await h.edit(page,"C2",'101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{"C2":'50'});
});

test("REQ-3-2-2: undo makes deleted pivot source fields valid again and preserves last result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.button(page,'Undo').click(); await h.values(page,{B1:'Sales',B2:'10',C1:'Status'});
  await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click(); await h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'});
  // Refresh may itself create a new history operation; validate the restored
  // source/result state after refresh without assuming how history counts it.
  await h.persisted(page,()=>h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'})); await h.tab(page,'Sheet1').click(); await h.values(page,{B1:'Sales',B2:'10',B3:'20',B4:'30'});
});

test("REQ-3-2-2: undo state persists after reload and cannot modify a different saved workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); const otherName=h.unique(); await h.renameWorkbook(page,otherName); await h.edit(page,'A1','other-workbook');
  await h.blank(page); const name=h.unique(); await h.renameWorkbook(page,name); await h.edit(page,'A1','initial'); await h.edit(page,'A1','changed'); await h.button(page,'Undo').click();
  await h.persisted(page,()=>h.values(page,{A1:'initial'})); await h.reopen(page,otherName); await h.values(page,{A1:'other-workbook'}); await h.reopen(page,name); await h.values(page,{A1:'initial'});
});
