import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-3-1: SUM pivot orders groups by appearance and persists exact grand totals", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page,"SUM"); await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');
  await h.persisted(page, () => h.values(page,{"A1": "Region", "B1": "SUM of Sales", "A2": "East", "B2": "40", "A3": "North", "B3": "20", "A4": "Grand Total", "B4": "60"})); await h.tab(page,'Sheet1').click(); await h.values(page,{A2:'East',B2:'10',A3:'North',B3:'20',A4:'East',B4:'30'});
});

test("REQ-5-3-1: COUNT pivot orders groups by appearance and persists exact grand totals", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page,"COUNT"); await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');
  await h.persisted(page, () => h.values(page,{"A1": "Region", "B1": "COUNT of Sales", "A2": "East", "B2": "2", "A3": "North", "B3": "1", "A4": "Grand Total", "B4": "3"})); await h.tab(page,'Sheet1').click(); await h.values(page,{A2:'East',B2:'10',A3:'North',B3:'20',A4:'East',B4:'30'});
});

test("REQ-5-3-1: AVERAGE pivot orders groups by appearance and persists exact grand totals", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page,"AVERAGE"); await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');
  await h.persisted(page, () => h.values(page,{"A1": "Region", "B1": "AVERAGE of Sales", "A2": "East", "B2": "20", "A3": "North", "B3": "20", "A4": "Grand Total", "B4": "20"})); await h.tab(page,'Sheet1').click(); await h.values(page,{A2:'East',B2:'10',A3:'North',B3:'20',A4:'East',B4:'30'});
});

test("REQ-5-3-1: column COUNT pivot displays empty combinations as zero and correct totals", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page,'COUNT','Status'); await h.persisted(page, () => h.values(page,{A1:'Region',B1:'Open',C1:'Closed',D1:'Grand Total',A2:'East',B2:'1',C2:'1',D2:'2',A3:'North',B3:'0',C3:'1',D3:'1',A4:'Grand Total',B4:'1',C4:'2',D4:'3'}));
});

test("REQ-5-3-1: source edits do not update pivot before refresh; refresh completely replaces result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.edit(page,'B2','50'); await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'40',B4:'60'});
  await h.button(page,'Refresh pivot table').click(); await h.persisted(page, () => h.values(page,{B2:'80',B4:'100'}));
});

test("REQ-5-3-1: deleted source field refuses refresh and preserves last successful pivot", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.tab(page,'Pivot1').click();
  await h.button(page,'Refresh pivot table').click(); await expect(h.text(page,'Pivot field is no longer available. Select a new field.').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{A1:'Region',B1:'SUM of Sales',A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}));
  await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Status',A2:'East',B2:'Open',A3:'North',B3:'Closed',A4:'East',B4:'Closed'});
});

test("REQ-5-3-1: SUM without numeric values rejects and preserves source and old result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); const editor=page.getByRole('region',{name:'Pivot table editor',exact:true}); await h.choose(editor,'Values','Status'); await h.button(editor,'Apply').click();
  await expect(h.text(page,'Value field requires numeric values').first()).toBeVisible(); await h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'}); await h.tab(page,'Sheet1').click(); await h.values(page,{C2:'Open',C3:'Closed',C4:'Closed'});
});

test("REQ-5-3-1: COUNT includes nonnumeric nonempty records and blanks contribute zero", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'B2','text'); await h.edit(page,'B3',''); await h.pivot(page,'COUNT'); await h.persisted(page, () => h.values(page,{B2:'2',B3:'0',B4:'2'}));
});

test("REQ-5-3-1: SUM ignores nonnumeric and blank value records without treating blanks as zero", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'B3','text'); await h.edit(page,'B4',''); await h.pivot(page,"SUM"); await h.persisted(page,()=>h.values(page,{...{"A1": "Region", "B1": "SUM of Sales", "A2": "East", "B2": "10", "A3": "North", "A4": "Grand Total", "B4": "10"},A3:'North'}));
  await h.tab(page,'Sheet1').click(); await h.values(page,{B2:'10',B3:'text',B4:''});
});

test("REQ-5-3-1: AVERAGE ignores nonnumeric and blank value records without treating blanks as zero", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'B3','text'); await h.edit(page,'B4',''); await h.pivot(page,"AVERAGE"); await h.persisted(page,()=>h.values(page,{...{"A1": "Region", "B1": "AVERAGE of Sales", "A2": "East", "B2": "10", "A4": "Grand Total", "B4": "10"},A3:'North'}));
  await h.tab(page,'Sheet1').click(); await h.values(page,{B2:'10',B3:'text',B4:''});
});

test("REQ-5-3-1: column SUM aggregates numeric records in appearance order with exact row and column grand totals", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'A2','North'); await h.edit(page,'A3','East'); await h.edit(page,'A4','North'); await h.edit(page,'C2','Closed'); await h.edit(page,'C3','Open'); await h.edit(page,'C4','Open'); await h.pivot(page,'SUM','Status');
  await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'Closed',C1:'Open',D1:'Grand Total',A2:'North',B2:'10',C2:'30',D2:'40',A3:'East',C3:'20',D3:'20',A4:'Grand Total',B4:'10',C4:'50',D4:'60'}));
});

test("REQ-5-3-1: column AVERAGE computes grand totals from source records rather than averaging group averages", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'B2','10'); await h.edit(page,'B3','50'); await h.edit(page,'B4','30'); await h.pivot(page,'AVERAGE','Status');
  await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'Open',C1:'Closed',D1:'Grand Total',A2:'East',B2:'10',C2:'30',D2:'20',A3:'North',C3:'50',D3:'50',A4:'Grand Total',B4:'10',C4:'40',D4:'30'}));
});

test("REQ-5-3-1: SUM rejects a value field with no numbers and preserves both complete worksheets after reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); const editor=page.getByRole('region',{name:'Pivot table editor',exact:true}); await h.choose(editor,'Values','Status'); await h.choose(editor,'Summarize by',"SUM"); await h.button(editor,'Apply').click();
  await expect(h.text(page,'Value field requires numeric values').first()).toBeVisible(); await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'SUM of Sales',A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}));
  await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'10',C2:'Open',A3:'North',B3:'20',C3:'Closed',A4:'East',B4:'30',C4:'Closed'});
});

test("REQ-5-3-1: AVERAGE rejects a value field with no numbers and preserves both complete worksheets after reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); const editor=page.getByRole('region',{name:'Pivot table editor',exact:true}); await h.choose(editor,'Values','Status'); await h.choose(editor,'Summarize by',"AVERAGE"); await h.button(editor,'Apply').click();
  await expect(h.text(page,'Value field requires numeric values').first()).toBeVisible(); await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'SUM of Sales',A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}));
  await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'10',C2:'Open',A3:'North',B3:'20',C3:'Closed',A4:'East',B4:'30',C4:'Closed'});
});

test("REQ-5-3-1: refresh replacement removes obsolete groups and totals after source records change", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.edit(page,'A3','East'); await h.edit(page,'B3','5'); await h.tab(page,'Pivot1').click(); await h.values(page,{A3:'North',B4:'60'});
  await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'SUM of Sales',A2:'East',B2:'45',A3:'Grand Total',B3:'45',A4:'',B4:''}));
  await h.tab(page,'Sheet1').click(); await h.values(page,{A2:'East',B2:'10',A3:'East',B3:'5',A4:'East',B4:'30'});
});

test("REQ-5-3-1: a deleted pivot field can be reselected and successful apply replaces the saved error-state result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click();
  await expect(h.text(page,'Pivot field is no longer available. Select a new field.').first()).toBeVisible(); await h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'}); const editor=page.getByRole('region',{name:'Pivot table editor',exact:true});
  await h.choose(editor,'Rows','Region'); await h.choose(editor,'Values','Status'); await h.choose(editor,'Summarize by','COUNT'); await h.button(editor,'Apply').click();
  await h.persisted(page,async()=>{
    await expect(h.text(page,'Pivot field is no longer available. Select a new field.')).toHaveCount(0);
    await h.values(page,{A1:'Region',B1:'COUNT of Status',A2:'East',B2:'2',A3:'North',B3:'1',A4:'Grand Total',B4:'3'});
  }); await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Status',A2:'East',B2:'Open',A3:'North',B3:'Closed',A4:'East',B4:'Closed'});
});

test("REQ-5-3-1: undo and redo restore structural changes together with another sheet pivot source", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page);
  await h.tab(page,'Sheet1').click(); await h.structure(page,'row','1','Insert 1 row above'); await h.values(page,{A1:'',A2:'Region',B3:'10'});
  await h.button(page,'Undo').click(); await h.values(page,{A1:'Region',B2:'10'});
  await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click(); await h.values(page,{B2:'40',B3:'20',B4:'60'});
  await h.tab(page,'Sheet1').click(); await h.button(page,'Redo').click(); await h.values(page,{A1:'',A2:'Region',B3:'10'});
  await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click();
  await h.persisted(page,()=>h.values(page,{B2:'40',B3:'20',B4:'60'}));
});

test("REQ-5-3-1: context REQ-2-2-1: overlapping row changes adjust pivot source range and leave old results until explicit refresh", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'row','3','Insert 1 row above'); await h.paste(page,'A3','South\t5\tOpen');
  await h.tab(page,'Pivot1').click(); await h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}); await h.button(page,'Refresh pivot table').click();
  await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'South',B3:'5',A4:'North',B4:'20',A5:'Grand Total',B5:'65'}));
  await h.tab(page,'Sheet1').click(); await h.structure(page,'row','3','Delete row'); await h.tab(page,'Pivot1').click(); await h.values(page,{A3:'South',B5:'65'}); await h.button(page,'Refresh pivot table').click();
  await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60',A5:'',B5:''}));
});

test("REQ-5-3-1: context REQ-2-2-2: pivot refresh tracks moved source headers after column insertion/deletion", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Insert 1 column left'); await h.edit(page,'C2','50');
  await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'40',B4:'60'}); await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'SUM of Sales',B2:'80',B4:'100'}));
  await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.edit(page,'B2','5'); await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'80',B4:'100'});
  await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{B2:'35',B4:'55'}));
});

test("REQ-5-3-1: context REQ-3-2-2: undo makes deleted pivot source fields valid again and preserves last result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.button(page,'Undo').click(); await h.values(page,{B1:'Sales',B2:'10',C1:'Status'});
  await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click(); await h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'});
  // Refresh may itself create a new history operation; validate the restored
  // source/result state after refresh without assuming how history counts it.
  await h.persisted(page,()=>h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'})); await h.tab(page,'Sheet1').click(); await h.values(page,{B1:'Sales',B2:'10',B3:'20',B4:'30'});
});

test("REQ-5-3-1: context REQ-5-1-2: filtered-out source rows still contribute to pivot summary after reopening", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.visibleRows(page,['A2','A4'],['A3']);
  await h.pivot(page); await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}));
  await h.tab(page,'Sheet1').click(); await h.visibleRows(page,['A2','A4'],['A3']); await h.values(page,{B2:'10',B3:'20',B4:'30'});
});

test("REQ-5-3-1: context REQ-1-1-1: home reopening restores sheet order, formulas, filter, validation and pivot state together", async ({ page, browser }) => {
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

test("REQ-5-3-1: context REQ-1-2-1: new workbook has no imported values, filter, validation or pivot from another workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); const original=page.url(); await h.validation(page,'B2','B4'); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.pivot(page);
  await h.blank(page); await expect(page.getByRole('tab')).toHaveCount(1); await expect(h.grid(page)).toHaveAttribute('aria-multiselectable','true'); await h.selection(page,['A1'],['B1','A2','B2']);
  await h.values(page,{A1:'',B2:'',C4:''}); await expect(h.button(page,'Filter Region')).toHaveCount(0); await expect(h.button(page,'Open dropdown for B2')).toHaveCount(0); await expect(h.button(page,'Refresh pivot table')).toHaveCount(0);
  await h.edit(page,'B2','101'); await h.persisted(page,()=>h.values(page,{B2:'101'})); await page.goto(original); await expect(h.tab(page,'Pivot1')).toBeVisible(); await h.tab(page,'Sheet1').click(); await h.values(page,{B2:'10'});
});

test("REQ-5-3-1: context REQ-5-3-1: guide: validation, atomic paste, undo, filtered export and explicit pivot refresh preserve consistent state", async ({ page, browser }) => {
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
