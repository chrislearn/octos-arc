import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-1-1: Ascending sort moves complete records stably and preserves header/outside cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'E5','outside'); await h.range(page,'A1','C4'); await h.data(page,'Sort range');
  const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await h.choose(dialog,'Sort by','Region'); await h.choose(dialog,'Order',"Ascending");
  await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check(); await h.button(dialog,'Sort').click();
  await h.persisted(page, () => h.values(page,{...{"A2": "East", "B2": "10", "C2": "Open", "A3": "East", "B3": "30", "C3": "Closed", "A4": "North", "B4": "20", "C4": "Closed"},A1:'Region',B1:'Sales',C1:'Status',E5:'outside'}));
});

test("REQ-5-1-1: Descending sort moves complete records stably and preserves header/outside cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'E5','outside'); await h.range(page,'A1','C4'); await h.data(page,'Sort range');
  const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await h.choose(dialog,'Sort by','Region'); await h.choose(dialog,'Order',"Descending");
  await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check(); await h.button(dialog,'Sort').click();
  await h.persisted(page, () => h.values(page,{...{"A2": "North", "B2": "20", "C2": "Closed", "A3": "East", "B3": "10", "C3": "Open", "A4": "East", "B4": "30", "C4": "Closed"},A1:'Region',B1:'Sales',C1:'Status',E5:'outside'}));
});

test("REQ-5-1-1: numeric sort moves whole records rather than lexical or single-column order", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'B2','100'); await h.edit(page,'B3','2'); await h.edit(page,'B4','30'); await h.range(page,'A1','C4'); await h.data(page,'Sort range'); const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await h.choose(dialog,'Sort by','Sales'); await h.choose(dialog,'Order','Ascending'); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check(); await h.button(dialog,'Sort').click(); await h.persisted(page, () => h.values(page,{A2:'North',B2:'2',C2:'Closed',A3:'East',B3:'30',C3:'Closed',A4:'East',B4:'100',C4:'Open'}));
});

test("REQ-5-1-1: date keys sort chronologically with stable equal keys and intact full records", async ({ page, browser }) => {
  test.setTimeout(60_000);
  // ISO date-only witnesses check stable record movement. Typed chronology
  // versus lexical order needs the supported date grammar to be specified.
  await h.blank(page); await h.paste(page,'A1','Date\tRecord\tAmount\n2026-01-03\tlate\t1\n2026-01-02\tfirst-equal\t2\n2026-01-02\tsecond-equal\t3\n2026-01-01\tearly\t4');
  await h.range(page,'A1','C5'); await h.data(page,'Sort range'); const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await h.choose(dialog,'Sort by','Date'); await h.choose(dialog,'Order','Ascending'); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check(); await h.button(dialog,'Sort').click();
  await h.persisted(page,()=>h.values(page,{A1:'Date',B1:'Record',C1:'Amount',A2:'2026-01-01',B2:'early',C2:'4',A3:'2026-01-02',B3:'first-equal',C3:'2',A4:'2026-01-02',B4:'second-equal',C4:'3',A5:'2026-01-03',B5:'late',C5:'1'}));
});

test("REQ-5-1-1: sorting moves formulas with records, adjusts their original references, and preserves validation/filter behavior", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.edit(page,'D1','Double'); await h.edit(page,'D2','=B2*2'); await h.edit(page,'D3','=B3*2'); await h.edit(page,'D4','=B4*2'); await h.validation(page,'B2','B4');
  await h.range(page,'A1','D4'); await h.data(page,'Create filter'); await h.condition(page,'Sales','Greater than','15'); await h.range(page,'A1','D4'); await h.data(page,'Sort range');
  const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await h.choose(dialog,'Sort by','Sales'); await h.choose(dialog,'Order','Descending'); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check(); await h.button(dialog,'Sort').click();
  await h.persisted(page,async()=>{await h.values(page,{A2:'East',B2:'30',C2:'Closed',A3:'North',B3:'20',C3:'Closed'});await h.visibleRows(page,['A2','A3'],['A4']);await h.formula(page,'D2','=B2*2','60');await h.formula(page,'D3','=B3*2','40');});
  await h.data(page,'Clear filter'); await h.formula(page,'D4','=B4*2','20'); await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'30',D2:'60'});
});

test("REQ-5-1-1: context REQ-3-1-3: reverse-direction drag replaces a saved rectangle and sorting uses only that rectangle", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','outside-a\toutside-b\toutside-c\toutside-d\noutside-e\tRegion\tSales\toutside-f\noutside-g\tEast\t20\toutside-h\noutside-i\tNorth\t10\toutside-j');
  await h.range(page,'C4','B2'); await h.selection(page,['B2','C2','B3','C3','B4','C4'],['A1','A2','A3','A4','B1','C1','D2','D3','D4']);
  await h.data(page,'Sort range'); const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check();
  await h.choose(dialog,'Sort by','Sales'); await h.choose(dialog,'Order','Ascending'); await h.button(dialog,'Sort').click();
  await h.persisted(page,()=>h.values(page,{B2:'Region',C2:'Sales',B3:'North',C3:'10',B4:'East',C4:'20',A1:'outside-a',B1:'outside-b',C1:'outside-c',D1:'outside-d',A2:'outside-e',D2:'outside-f',A3:'outside-g',D3:'outside-h',A4:'outside-i',D4:'outside-j'}));
  await h.range(page,'D5','E6'); await h.persisted(page,()=>h.selection(page,['D5','E5','D6','E6'],['B2','C2','B3','C3','C5','F6']));
});
