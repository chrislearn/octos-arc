import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-1-1-1: home entry, saved address and later browser session identify the same workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); const entry = page.getByRole('link', { name: 'Q3 Sales', exact: true });
  await expect(entry).toBeVisible(); await entry.click(); const address = page.url();
  await h.values(page, { A1: 'Region' }); await expect(h.tab(page, 'Sheet1')).toBeVisible();
  await h.edit(page, 'F8', 'unique-workbook-state');
  await h.persisted(page, () => h.values(page, { A1: 'Region', F8: 'unique-workbook-state' }));
  const later = await browser.newContext(); const other = await later.newPage(); await other.goto(address);
  await h.values(other, { A1: 'Region', F8: 'unique-workbook-state' }); await later.close();
});

test("REQ-1-1-1: home/editor timestamp agrees with persisted renamed workbook and never loads another workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); const name=h.unique(); await h.renameWorkbook(page,name); const address=page.url(); await h.edit(page,'A1','first-workbook-only');
  await page.goto('/'); const updated=await h.recordUpdated(page,name); await page.getByRole('link',{name,exact:true}).click(); await expect(h.text(page,updated).first()).toBeVisible();
  await h.persisted(page,()=>h.values(page,{A1:'first-workbook-only'})); await h.blank(page); const otherName=h.unique(); await h.renameWorkbook(page,otherName); await h.edit(page,'A1','second-workbook-only');
  await page.goto(address); await h.values(page,{A1:'first-workbook-only'}); await expect(h.text(page,name).first()).toBeVisible();
  await h.reopen(page,otherName); await h.values(page,{A1:'second-workbook-only'}); await h.reopen(page,name); await h.values(page,{A1:'first-workbook-only'});
});

test("REQ-1-1-1: home reopening restores sheet order, formulas, filter, validation and pivot state together", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); const name=h.unique(); await h.renameWorkbook(page,name); await h.edit(page,'E2','=B2*2'); await h.validation(page,'B2','B4');
  await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.pivot(page);
  await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','independent-sheet'); await h.tab(page,'Pivot1').click(); await h.cell(page,'B2').click();
  await h.reopen(page,name); await h.tabOrder(page,['Sheet1','Pivot1','Sheet2']); await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');
  await h.values(page,{A1:'Region',B1:'SUM of Sales',B2:'40',B4:'60'}); await expect(h.cell(page,'B2')).toHaveAttribute('aria-selected','true'); await expect(h.field(page,'Formula bar')).toHaveValue('40');
  const editor=page.getByRole('region',{name:'Pivot table editor',exact:true}); await h.chosen(editor,'Rows','Region'); await h.chosen(editor,'Values','Sales'); await h.chosen(editor,'Summarize by','SUM');
  await h.tab(page,'Sheet1').click(); await h.visibleRows(page,['A2','A4'],['A3']); await h.formula(page,'E2','=B2*2','20');
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'10',E2:'20'});
  await h.tab(page,'Sheet2').click(); await h.persisted(page,()=>h.values(page,{A1:'independent-sheet',E2:''}));
});
