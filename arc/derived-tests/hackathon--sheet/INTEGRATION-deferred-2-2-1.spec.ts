import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-2-2-1: row insert/delete moves complete records and persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.structure(page, "row", "2", "Insert 1 row above");
  await h.persisted(page, () => h.values(page, {"A2": "", "B2": "", "C2": "", "A3": "East", "B3": "10", "C3": "Open", "A4": "North", "B4": "20", "C4": "Closed", "A5": "East", "B5": "30", "C5": "Closed"}));
  await h.structure(page, "row", "2", "Delete row");
  await h.persisted(page, () => h.values(page, {"A1": "Region", "B1": "Sales", "C1": "Status", "A2": "East", "B2": "10", "C2": "Open", "A3": "North", "B3": "20", "C3": "Closed", "A4": "East", "B4": "30", "C4": "Closed"}));
});

test("INTEGRATION-deferred-2-2-1: insert below then delete referenced row adjusts original formulas", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'A2', '10'); await h.edit(page, 'B4', '=A2*2');
  await h.structure(page, 'row', '1', 'Insert 1 row below'); await h.formula(page, 'B5', '=A3*2', '20');
  await h.structure(page, 'row', '3', 'Delete row'); await h.persisted(page, () => expect(h.cell(page, 'B4')).toHaveText('#REF!'));
});

test("INTEGRATION-deferred-2-2-1: structure moves numeric validation with the original cell", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,"row","2","Insert 1 row above");
  await h.edit(page,"B3",'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{"B3":'50'}));
});

test("INTEGRATION-deferred-2-2-1: deleting populated row removes only the target and shifts all surviving record fields", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','other-sheet'); await h.tab(page,'Sheet1').click();
  await h.structure(page,"row","3","Delete row"); await h.persisted(page,()=>h.values(page,{"A1": "Region", "B1": "Sales", "C1": "Status", "A2": "East", "B2": "10", "C2": "Open", "A3": "East", "B3": "30", "C3": "Closed", "A4": "", "B4": "", "C4": ""}));
  await h.tab(page,'Sheet2').click(); await h.values(page,{A1:'other-sheet',B2:''});
});

test("INTEGRATION-deferred-2-2-1: insertion moves dropdown and numeric rules with original values and leaves inserted cells unconstrained", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.validation(page,'B2','B2'); await h.validation(page,'C2','C2','Dropdown');
  await h.structure(page,"row","2","Insert 1 row above"); await page.reload();
  await h.edit(page,"B3",'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.values(page,{"B3":'10',"C3":'Open'});
  await h.button(page,'Open dropdown for '+"C3").click(); await page.getByRole('option',{name:'Closed',exact:true}).click(); await h.edit(page,"C3",'invalid');
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{"C3":'Closed'});
  await h.edit(page,"B2",'101'); await h.edit(page,"C2",'unconstrained'); await h.persisted(page,()=>h.values(page,{"B3":'10',"C3":'Closed',"B2":'101',"C2":'unconstrained'}));
});

test("INTEGRATION-deferred-2-2-1: deleted row validation is removed rather than applied to the next surviving cell", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.edit(page,"B3",'70');
  await h.structure(page,"row","2","Delete row"); await h.values(page,{"B2":'70'}); await h.edit(page,"B2",'101');
  await h.persisted(page,()=>h.values(page,{"B2":'101'}));
});

test("INTEGRATION-deferred-2-2-1: row insert/delete adjusts existing filter region without deleting or reordering hidden records", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.structure(page,'row','2','Insert 1 row above');
  await h.persisted(page,()=>h.visibleRows(page,['A3','A5'],['A4'])); await h.data(page,'Clear filter'); await h.values(page,{A2:'',A3:'East',B3:'10',A4:'North',B4:'20',A5:'East',B5:'30'});
  await h.range(page,'A1','C5'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.structure(page,'row','3','Delete row');
  await h.persisted(page,()=>h.visibleRows(page,['A4'],['A3'])); await h.data(page,'Clear filter'); await h.values(page,{A2:'',A3:'North',B3:'20',A4:'East',B4:'30'});
});

test("INTEGRATION-deferred-2-2-1: overlapping row changes adjust pivot source range and leave old results until explicit refresh", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'row','3','Insert 1 row above'); await h.paste(page,'A3','South\t5\tOpen');
  await h.tab(page,'Pivot1').click(); await h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}); await h.button(page,'Refresh pivot table').click();
  await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'South',B3:'5',A4:'North',B4:'20',A5:'Grand Total',B5:'65'}));
  await h.tab(page,'Sheet1').click(); await h.structure(page,'row','3','Delete row'); await h.tab(page,'Pivot1').click(); await h.values(page,{A3:'South',B5:'65'}); await h.button(page,'Refresh pivot table').click();
  await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60',A5:'',B5:''}));
});
