import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-5-1-2: value filtering is scoped to the selected region and clearing preserves formula and validation behavior", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'B2','Region\tSales\tStatus\nEast\t10\tOpen\nNorth\t20\tClosed\nEast\t30\tClosed'); await h.edit(page,'A1','outside-origin'); await h.edit(page,'B6','outside-next-row'); await h.edit(page,'E4','outside-next-column'); await h.edit(page,'F3','=C3*2'); await h.validation(page,'C3','C5');
  await h.range(page,'B2','D5'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.persisted(page,()=>h.visibleRows(page,['B3','B5','B6'],['B4']));
  expect(h.parseCSV(await h.csv(page))).toEqual([['outside-origin','','','','',''],['','Region','Sales','Status','',''],['','East','10','Open','','20'],['','North','20','Closed','outside-next-column',''],['','East','30','Closed','',''],['','outside-next-row','','','','']]);
  await h.data(page,'Clear filter'); await h.persisted(page,async()=>{await h.values(page,{A1:'outside-origin',B3:'East',C3:'10',B4:'North',C4:'20',B5:'East',C5:'30',B6:'outside-next-row',E4:'outside-next-column'});await h.formula(page,'F3','=C3*2','20');});
  await h.edit(page,'C3','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{C3:'10',F3:'20'});
});

test("INTEGRATION-deferred-5-1-2: filtered-out source rows still contribute to pivot summary after reopening", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.visibleRows(page,['A2','A4'],['A3']);
  await h.pivot(page); await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}));
  await h.tab(page,'Sheet1').click(); await h.visibleRows(page,['A2','A4'],['A3']); await h.values(page,{B2:'10',B3:'20',B4:'30'});
});
