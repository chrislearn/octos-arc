import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-2-1-1: new sheet chooses first unused name and isolates previous data", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'A1', 'source'); await h.button(page, 'Add worksheet').click();
  await expect(h.tab(page, 'Sheet2')).toHaveAttribute('aria-selected', 'true'); await h.values(page, { A1: '' });
  await expect(h.cell(page, 'A1')).toHaveAttribute('aria-selected', 'true'); await h.tab(page, 'Sheet1').click(); await h.values(page, { A1: 'source' });
  await h.persisted(page, () => expect(h.tab(page, 'Sheet2')).toBeVisible());
});

test("REQ-2-1-1: worksheet addition reuses first unused SheetN and appends in persisted order", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.button(page,'Add worksheet').click(); await h.button(page,'Add worksheet').click(); await h.sheetMenu(page,'Sheet2','Delete');
  await h.button(page.getByRole('dialog',{name:'Delete worksheet',exact:true}),'Delete worksheet').click(); await h.button(page,'Add worksheet').click();
  await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Sheet3','Sheet2']); await expect(h.tab(page,'Sheet2')).toHaveAttribute('aria-selected','true'); await h.selection(page,['A1'],['A2','B1']); });
});

test("REQ-2-1-1: new sheet does not inherit filters or dropdown/numeric validation and preserves source state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.validation(page,'B2','B4'); await h.validation(page,'C2','C4','Dropdown'); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']);
  await h.button(page,'Add worksheet').click(); await h.values(page,{A1:'',B2:'',C2:''}); await expect(h.button(page,'Filter Region')).toHaveCount(0); await expect(h.button(page,'Open dropdown for C2')).toHaveCount(0);
  await h.edit(page,'B2','101'); await h.edit(page,'C2','unconstrained'); await h.tab(page,'Sheet1').click(); await h.visibleRows(page,['A2','A4'],['A3']); await expect(h.button(page,'Open dropdown for C2')).toBeVisible();
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'10',C2:'Open'});
  await h.tab(page,'Sheet2').click(); await h.persisted(page,()=>h.values(page,{B2:'101',C2:'unconstrained'}));
});
