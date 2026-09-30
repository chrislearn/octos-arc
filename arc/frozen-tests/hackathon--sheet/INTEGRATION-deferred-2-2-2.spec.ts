import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-2-2-2: column insert/delete moves complete records and persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.structure(page, "column", "B", "Insert 1 column left");
  await h.persisted(page, () => h.values(page, {"A1": "Region", "B1": "", "B2": "", "C1": "Sales", "C2": "10", "D1": "Status", "D2": "Open", "C3": "20", "D3": "Closed", "C4": "30", "D4": "Closed"}));
  await h.structure(page, "column", "B", "Delete column");
  await h.persisted(page, () => h.values(page, {"A1": "Region", "B1": "Sales", "C1": "Status", "A2": "East", "B2": "10", "C2": "Open", "A3": "North", "B3": "20", "C3": "Closed", "A4": "East", "B4": "30", "C4": "Closed"}));
});

test("INTEGRATION-deferred-2-2-2: insert right then delete source column adjusts formulas and invalid references", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'B1', '10'); await h.edit(page, 'D1', '=B1*2');
  await h.structure(page, 'co-lumn', 'A', 'Insert 1 column right'); await h.formula(page, 'E1', '=C1*2', '20');
  await h.structure(page, 'column', 'C', 'Delete column'); await h.persisted(page, () => expect(h.cell(page, 'D1')).toHaveText('#REF!'));
});

test("INTEGRATION-deferred-2-2-2: structure moves numeric validation with the original cell", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,"column","B","Insert 1 column left");
  await h.edit(page,"C2",'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{"C2":'50'}));
});

test("INTEGRATION-deferred-2-2-2: deleting populated column removes only the target and shifts all surviving record fields", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','other-sheet'); await h.tab(page,'Sheet1').click();
  await h.structure(page,"column","B","Delete column"); await h.persisted(page,()=>h.values(page,{"A1": "Region", "B1": "Status", "C1": "", "A2": "East", "B2": "Open", "C2": "", "A3": "North", "B3": "Closed", "A4": "East", "B4": "Closed"}));
  await h.tab(page,'Sheet2').click(); await h.values(page,{A1:'other-sheet',B2:''});
});

test("INTEGRATION-deferred-2-2-2: insertion moves dropdown and numeric rules with original values and leaves inserted cells unconstrained", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.validation(page,'B2','B2'); await h.validation(page,'C2','C2','Dropdown');
  await h.structure(page,"column","B","Insert 1 column left"); await page.reload();
  await h.edit(page,"C2",'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.values(page,{"C2":'10',"D2":'Open'});
  await h.button(page,'Open dropdown for '+"D2").click(); await page.getByRole('option',{name:'Closed',exact:true}).click(); await h.edit(page,"D2",'invalid');
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{"D2":'Closed'});
  await h.edit(page,"B2",'101'); await h.edit(page,"B3",'unconstrained'); await h.persisted(page,()=>h.values(page,{"C2":'10',"D2":'Closed',"B2":'101',"B3":'unconstrained'}));
});

test("INTEGRATION-deferred-2-2-2: deleted column validation is removed rather than applied to the next surviving cell", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.edit(page,"C2",'70');
  await h.structure(page,"column","B","Delete column"); await h.values(page,{"B2":'70'}); await h.edit(page,"B2",'101');
  await h.persisted(page,()=>h.values(page,{"B2":'101'}));
});

test("INTEGRATION-deferred-2-2-2: column insertion/deletion moves filter headers and preserves conditions on original data", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.condition(page,'Sales','Greater than','15'); await h.structure(page,'column','B','Insert 1 column left');
  await h.persisted(page,()=>h.visibleRows(page,['A3','A4'],['A2'])); await expect(h.button(page,'Filter Sales')).toBeVisible(); await h.structure(page,'column','B','Delete column');
  await h.persisted(page,()=>h.visibleRows(page,['A3','A4'],['A2'])); await h.data(page,'Clear filter'); await h.values(page,{B1:'Sales',B2:'10',B3:'20',B4:'30',C1:'Status',C2:'Open'});
});

test("INTEGRATION-deferred-2-2-2: pivot refresh tracks moved source headers after column insertion/deletion", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Insert 1 column left'); await h.edit(page,'C2','50');
  await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'40',B4:'60'}); await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'SUM of Sales',B2:'80',B4:'100'}));
  await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.edit(page,'B2','5'); await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'80',B4:'100'});
  await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{B2:'35',B4:'55'}));
});
