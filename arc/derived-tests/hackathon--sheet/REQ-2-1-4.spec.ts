import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-1-4: delete confirms target and keeps last worksheet safe", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.sheetMenu(page, 'Sheet1', 'Delete'); await expect(h.text(page, 'A workbook must contain at least one worksheet').first()).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Delete worksheet', exact: true })).toHaveCount(0);
  await h.button(page, 'Add worksheet').click(); await h.edit(page, 'A1', 'only-in-deleted-sheet'); await h.sheetMenu(page, 'Sheet2', 'Delete');
  const dialog = page.getByRole('dialog', { name: 'Delete worksheet', exact: true }); await expect(dialog).toContainText('Sheet2'); await h.button(dialog, 'Delete worksheet').click();
  await h.persisted(page, async () => { await expect(h.tab(page, 'Sheet2')).toHaveCount(0); await expect(h.tab(page, 'Sheet1')).toHaveAttribute('aria-selected', 'true'); await h.values(page, { A1: '' }); });
});

test("REQ-2-1-4: pivot source cannot be deleted until its result worksheet is deleted", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.sheetMenu(page,'Sheet1','Delete'); const dialog=page.getByRole('dialog',{name:'Delete worksheet',exact:true}); await h.button(dialog,'Delete worksheet').click();
  await expect(h.text(page,'Please delete or rebuild dependent pivot tables first').first()).toBeVisible(); await expect(dialog).toBeHidden(); await expect(h.tab(page,'Sheet1')).toBeVisible(); await h.values(page,{B2:'40',B4:'60'}); await page.reload(); await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'10',C2:'Open',A3:'North',B3:'20',C3:'Closed',A4:'East',B4:'30',C4:'Closed'}); await h.tab(page,'Pivot1').click();
  await h.sheetMenu(page,'Pivot1','Delete'); await h.button(dialog,'Delete worksheet').click(); await h.button(page,'Add worksheet').click(); await h.sheetMenu(page,'Sheet1','Delete'); await h.button(dialog,'Delete worksheet').click();
  await h.persisted(page, async () => { await expect(h.tab(page,'Sheet1')).toHaveCount(0); await expect(h.tab(page,'Pivot1')).toHaveCount(0); await expect(h.tab(page,'Sheet2')).toBeVisible(); });
});

test("REQ-2-1-4: deletion removes complete sheet state and activates an adjacent survivor", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','first'); await h.button(page,'Add worksheet').click(); await h.paste(page,'A1','Region\tSales\nDeleted\t50'); await h.validation(page,'B2','B2'); await h.range(page,'A1','B2'); await h.data(page,'Create filter'); await h.edit(page,'D2','=B2*2');
  await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','third'); await h.tab(page,'Sheet2').click(); await h.sheetMenu(page,'Sheet2','Delete'); const dialog=page.getByRole('dialog',{name:'Delete worksheet',exact:true}); await expect(dialog).toContainText('Sheet2'); await h.button(dialog,'Delete worksheet').click();
  await expect(h.tab(page,'Sheet2')).toHaveCount(0); const active=page.getByRole('tab').and(page.locator('[aria-selected="true"]')); await expect(active).toHaveCount(1); await expect(active).toHaveAccessibleName(/^Sheet[13]$/);
  await expect(h.button(page,'Filter Region')).toHaveCount(0); await expect(h.button(page,'Open dropdown for B2')).toHaveCount(0); await h.values(page,{B2:'',D2:''});
  await page.reload(); await expect(h.tab(page,'Sheet2')).toHaveCount(0); await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'first'}); await h.tab(page,'Sheet3').click(); await h.values(page,{A1:'third'});
});

test("REQ-2-1-4: context REQ-2-1-1: worksheet addition reuses first unused SheetN and appends in persisted order", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.button(page,'Add worksheet').click(); await h.button(page,'Add worksheet').click(); await h.sheetMenu(page,'Sheet2','Delete');
  await h.button(page.getByRole('dialog',{name:'Delete worksheet',exact:true}),'Delete worksheet').click(); await h.button(page,'Add worksheet').click();
  await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Sheet3','Sheet2']); await expect(h.tab(page,'Sheet2')).toHaveAttribute('aria-selected','true'); await h.selection(page,['A1'],['A2','B1']); });
});

test("REQ-2-1-4: context REQ-5-3-1: pivot naming reuses the first unused PivotN after a result sheet is deleted", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.pivot(page,'COUNT'); await expect(h.tab(page,'Pivot2')).toHaveAttribute('aria-selected','true');
  await h.sheetMenu(page,'Pivot1','Delete'); await h.button(page.getByRole('dialog',{name:'Delete worksheet',exact:true}),'Delete worksheet').click(); await h.tab(page,'Sheet1').click(); await h.pivot(page,'AVERAGE');
  await h.persisted(page,async()=>{await h.tabOrder(page,['Sheet1','Pivot2','Pivot1']);await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');await h.values(page,{B1:'AVERAGE of Sales',B2:'20',B3:'20',B4:'20'});});
  await h.tab(page,'Pivot2').click(); await h.values(page,{B1:'COUNT of Sales',B2:'2',B3:'1',B4:'3'});
});
