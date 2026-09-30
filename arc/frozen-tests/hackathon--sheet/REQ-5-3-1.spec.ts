import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

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

test("REQ-5-3-1: pivot naming reuses the first unused PivotN after a result sheet is deleted", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.pivot(page,'COUNT'); await expect(h.tab(page,'Pivot2')).toHaveAttribute('aria-selected','true');
  await h.sheetMenu(page,'Pivot1','Delete'); await h.button(page.getByRole('dialog',{name:'Delete worksheet',exact:true}),'Delete worksheet').click(); await h.tab(page,'Sheet1').click(); await h.pivot(page,'AVERAGE');
  await h.persisted(page,async()=>{await h.tabOrder(page,['Sheet1','Pivot2','Pivot1']);await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');await h.values(page,{B1:'AVERAGE of Sales',B2:'20',B3:'20',B4:'20'});});
  await h.tab(page,'Pivot2').click(); await h.values(page,{B1:'COUNT of Sales',B2:'2',B3:'1',B4:'3'});
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
  await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'COUNT of Status',A2:'East',B2:'2',A3:'North',B3:'1',A4:'Grand Total',B4:'3'})); await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Status',A2:'East',B2:'Open',A3:'North',B3:'Closed',A4:'East',B4:'Closed'});
});
