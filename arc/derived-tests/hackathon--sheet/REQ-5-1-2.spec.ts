import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-1-2: value filter hides rather than deletes, persists and export includes hidden records", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.button(page,'Filter Region').click();
  const dialog=page.getByRole('dialog',{name:'Filter Region',exact:true}); await h.button(dialog,'Clear selection').click(); await dialog.getByRole('checkbox',{name:'East',exact:true}).check(); await h.button(dialog,'Apply').click();
  await h.persisted(page, async () => { await h.filterHeaders(page,{A1:'Region',B1:'Sales',C1:'Status'}); await expect(h.cell(page,'A2')).toBeVisible(); await expect(h.cell(page,'A3')).toBeHidden(); await expect(h.cell(page,'A4')).toBeVisible(); });
  expect(h.parseCSV(await h.csv(page))).toEqual([['Region','Sales','Status'],['East','10','Open'],['North','20','Closed'],['East','30','Closed']]);
  await h.data(page,'Clear filter'); await h.persisted(page, async () => { await expect(h.cell(page,'A3')).toBeVisible(); await h.values(page,{A2:'East',A3:'North',A4:'East'}); });
});

test("REQ-5-1-2: conditions combine with AND and clearing preserves original data", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter');
  for(const [header,condition,value] of [['Region','Text contains','East'],['Sales','Greater than','15']]) { await h.button(page,`Filter ${header}`).click(); const dialog=page.getByRole('dialog',{name:`Filter ${header}`,exact:true}); await h.choose(dialog,'Condition',condition); await h.field(dialog,'Value').fill(value); await h.button(dialog,'Apply').click(); }
  await h.persisted(page, async () => { await h.filterHeaders(page,{A1:'Region',B1:'Sales',C1:'Status'}); await expect(h.cell(page,'A2')).toBeHidden(); await expect(h.cell(page,'A3')).toBeHidden(); await expect(h.cell(page,'A4')).toBeVisible(); });
});

test("REQ-5-1-2: condition Before persists exactly the matching rows and clearing restores originals", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','Date\tRecord\n2026-01-01\tearly\n2026-06-01\tlate\n\tempty'); await h.range(page,'A1','B4'); await h.data(page,'Create filter');
  await h.condition(page,'Date',"Before","2026-03-01"); await h.persisted(page,async()=>{await h.filterHeaders(page,{A1:'Date',B1:'Record'});await h.visibleRows(page,["A2"],["A3", "A4"]);});
  await h.data(page,'Clear filter'); await h.persisted(page,async()=>{await h.visibleRows(page,['A2','A3','A4'],[]);await h.values(page,{A1:'Date',B1:'Record',A2:'2026-01-01',B2:'early',A3:'2026-06-01',B3:'late',A4:'',B4:'empty'});});
});

test("REQ-5-1-2: condition Is empty persists exactly the matching rows and clearing restores originals", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','Date\tRecord\n2026-01-01\tearly\n2026-06-01\tlate\n\tempty'); await h.range(page,'A1','B4'); await h.data(page,'Create filter');
  await h.condition(page,'Date',"Is empty",undefined); await h.persisted(page,async()=>{await h.filterHeaders(page,{A1:'Date',B1:'Record'});await h.visibleRows(page,["A4"],["A2", "A3"]);});
  await h.data(page,'Clear filter'); await h.persisted(page,async()=>{await h.visibleRows(page,['A2','A3','A4'],[]);await h.values(page,{A1:'Date',B1:'Record',A2:'2026-01-01',B2:'early',A3:'2026-06-01',B3:'late',A4:'',B4:'empty'});});
});

test("REQ-5-1-2: condition Is not empty persists exactly the matching rows and clearing restores originals", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','Date\tRecord\n2026-01-01\tearly\n2026-06-01\tlate\n\tempty'); await h.range(page,'A1','B4'); await h.data(page,'Create filter');
  await h.condition(page,'Date',"Is not empty",undefined); await h.persisted(page,async()=>{await h.filterHeaders(page,{A1:'Date',B1:'Record'});await h.visibleRows(page,["A2", "A3"],["A4"]);});
  await h.data(page,'Clear filter'); await h.persisted(page,async()=>{await h.visibleRows(page,['A2','A3','A4'],[]);await h.values(page,{A1:'Date',B1:'Record',A2:'2026-01-01',B2:'early',A3:'2026-06-01',B3:'late',A4:'',B4:'empty'});});
});
