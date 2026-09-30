import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-data-workflow: guide: validation, atomic paste, undo, filtered export and explicit pivot refresh preserve consistent state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  let address='';
  await test.step('Create raw records, dependent formulas and inclusive numeric rules',async()=>{
    await h.sourceData(page); address=page.url(); await h.edit(page,'E2','=B2*2'); await h.edit(page,'E3','=SUM(B2:B4)'); await h.validation(page,'B2','B4');
    await h.formula(page,'E2','=B2*2','20'); await h.formula(page,'E3','=SUM(B2:B4)','60');
  });
  await test.step('One invalid destination rejects every value and leaves all dependent results unchanged',async()=>{
    await h.paste(page,'B2','15\n101\n35'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
    await h.values(page,{B2:'10',B3:'20',B4:'30',E2:'20',E3:'60'});
  });
  await test.step('Valid bulk paste recalculates; undo and redo restore the whole operation',async()=>{
    await h.paste(page,'B2','15\n25\n35'); await h.values(page,{B2:'15',B3:'25',B4:'35',E2:'30',E3:'75'});
    await h.button(page,'Undo').click(); await h.values(page,{B2:'10',B3:'20',B4:'30',E2:'20',E3:'60'});
    await h.button(page,'Redo').click(); await h.values(page,{B2:'15',B3:'25',B4:'35',E2:'30',E3:'75'});
  });
  await test.step('Filtering hides records without removing them from export or pivot aggregation',async()=>{
    await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.visibleRows(page,['A2','A4'],['A3']);
    expect(h.parseCSV(await h.csv(page))).toEqual([['Region','Sales','Status','',''],['East','15','Open','','30'],['North','25','Closed','','75'],['East','35','Closed','','']]);
    await h.pivot(page); await h.values(page,{A2:'East',B2:'50',A3:'North',B3:'25',A4:'Grand Total',B4:'75'});
  });
  await test.step('Source edits recalculate formulas but retain the old pivot result until Refresh',async()=>{
    await h.tab(page,'Sheet1').click(); await h.edit(page,'B2','20'); await h.values(page,{E2:'40',E3:'80'});
    await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'50',B3:'25',B4:'75'}); await h.button(page,'Refresh pivot table').click(); await h.values(page,{B2:'55',B3:'25',B4:'80'});
  });
  await test.step('Deleting the value field makes refresh fail without erasing the previous result',async()=>{
    await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click();
    await expect(h.text(page,'Pivot field is no longer available. Select a new field.').filter({visible:true}).first()).toBeVisible(); await h.values(page,{B2:'55',B3:'25',B4:'80'});
  });
  await test.step('Undo restores the source structure, formulas, rules and pivot validity together',async()=>{
    await h.tab(page,'Sheet1').click(); await h.button(page,'Undo').click(); await h.values(page,{B1:'Sales',B2:'20',B3:'25',B4:'35',E2:'40',E3:'80'});
    await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'20',E2:'40',E3:'80'});
    await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{B2:'55',B3:'25',B4:'80'}));
  });
  await test.step('An independent browser reads the same durable result',async()=>{
    const later=await browser.newContext();
    try { const p=await later.newPage(); await p.goto(address); await expect(h.tab(p,'Pivot1')).toHaveAttribute('aria-selected','true'); await h.values(p,{B2:'55',B3:'25',B4:'80'}); }
    finally { await later.close(); }
  });
});
