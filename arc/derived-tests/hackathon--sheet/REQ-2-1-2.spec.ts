import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-1-2: switch restores each sheet formula and selected cell and last active sheet", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'B2', '=2+3'); await h.cell(page, 'B2').click();
  await h.button(page, 'Add worksheet').click(); await h.edit(page, 'C3', 'other'); await h.cell(page, 'C3').click();
  await h.tab(page, 'Sheet1').click(); await expect(h.cell(page, 'B2')).toHaveAttribute('aria-selected', 'true'); await h.formula(page, 'B2', '=2+3', '5');
  await h.tab(page, 'Sheet2').click(); await h.persisted(page, async () => { await expect(h.tab(page, 'Sheet2')).toHaveAttribute('aria-selected', 'true'); await expect(h.cell(page, 'C3')).toHaveAttribute('aria-selected', 'true'); await expect(h.field(page, 'Formula bar')).toHaveValue('other'); });
  await h.tab(page, 'Sheet1').click(); await h.values(page, { B2: '5', C3: '' });
});

test("REQ-2-1-2: context REQ-1-3-2: export reads only active worksheet and preserves selection and original formulas", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.button(page,'Add worksheet').click(); await h.paste(page,'A1','Label\tValue\nOnly-second\t7'); await h.edit(page,'C2','=B2*3'); await h.cell(page,'C2').click();
  expect(h.parseCSV(await h.csv(page))).toEqual([['Label','Value',''],['Only-second','7','21']]);
  await expect(h.tab(page,'Sheet2')).toHaveAttribute('aria-selected','true'); await h.selection(page,['C2'],['A1','B2']); await expect(h.field(page,'Formula bar')).toHaveValue('=B2*3');
  await h.persisted(page,()=>h.formula(page,'C2','=B2*3','21')); await h.tab(page,'Sheet1').click(); expect(h.parseCSV(await h.csv(page))).toEqual([['Region','Sales','Status'],['East','10','Open'],['North','20','Closed'],['East','30','Closed']]);
});

test("REQ-2-1-2: context REQ-2-1-1: new sheet chooses first unused name and isolates previous data", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'A1', 'source'); await h.button(page, 'Add worksheet').click();
  await expect(h.tab(page, 'Sheet2')).toHaveAttribute('aria-selected', 'true'); await h.values(page, { A1: '' });
  await expect(h.cell(page, 'A1')).toHaveAttribute('aria-selected', 'true'); await h.tab(page, 'Sheet1').click(); await h.values(page, { A1: 'source' });
  await h.persisted(page, () => expect(h.tab(page, 'Sheet2')).toBeVisible());
});

test("REQ-2-1-2: context REQ-2-1-1: new sheet does not inherit filters or dropdown/numeric validation and preserves source state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.validation(page,'B2','B4'); await h.validation(page,'C2','C4','Dropdown'); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']);
  await h.button(page,'Add worksheet').click(); await h.values(page,{A1:'',B2:'',C2:''}); await expect(h.button(page,'Filter Region')).toHaveCount(0); await expect(h.button(page,'Open dropdown for C2')).toHaveCount(0);
  await h.edit(page,'B2','101'); await h.edit(page,'C2','unconstrained'); await h.tab(page,'Sheet1').click(); await h.visibleRows(page,['A2','A4'],['A3']); await expect(h.button(page,'Open dropdown for C2')).toBeVisible();
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'10',C2:'Open'});
  await h.tab(page,'Sheet2').click(); await h.persisted(page,()=>h.values(page,{B2:'101',C2:'unconstrained'}));
});

test("REQ-2-1-2: context REQ-2-2-1: deleting populated row removes only the target and shifts all surviving record fields", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','other-sheet'); await h.tab(page,'Sheet1').click();
  await h.structure(page,"row","3","Delete row"); await h.persisted(page,()=>h.values(page,{"A1": "Region", "B1": "Sales", "C1": "Status", "A2": "East", "B2": "10", "C2": "Open", "A3": "East", "B3": "30", "C3": "Closed", "A4": "", "B4": "", "C4": ""}));
  await h.tab(page,'Sheet2').click(); await h.values(page,{A1:'other-sheet',B2:''});
});

test("REQ-2-1-2: context REQ-2-2-2: deleting populated column removes only the target and shifts all surviving record fields", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','other-sheet'); await h.tab(page,'Sheet1').click();
  await h.structure(page,"column","B","Delete column"); await h.persisted(page,()=>h.values(page,{"A1": "Region", "B1": "Status", "C1": "", "A2": "East", "B2": "Open", "C2": "", "A3": "North", "B3": "Closed", "A4": "East", "B4": "Closed"}));
  await h.tab(page,'Sheet2').click(); await h.values(page,{A1:'other-sheet',B2:''});
});

test("REQ-2-1-2: context REQ-3-1-3: complete rectangle replaces and persists exact selected ARIA cells independently per sheet", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.range(page, 'B2', 'C3');
  const check = async () => { await expect(h.grid(page)).toHaveAttribute('aria-multiselectable', 'true'); for (const at of ['B2','C2','B3','C3']) await expect(h.cell(page, at)).toHaveAttribute('aria-selected','true'); for (const at of ['A1','A2','B1','D3']) await expect(h.cell(page, at)).toHaveAttribute('aria-selected','false'); };
  await check(); await h.button(page, 'Add worksheet').click(); await h.cell(page,'D4').click(); await h.tab(page,'Sheet1').click(); await h.persisted(page, check);
  await h.cell(page,'A1').click(); await expect(h.cell(page,'B2')).toHaveAttribute('aria-selected','false');
});

test("REQ-2-1-2: context REQ-4-2-1: row and column movement recalculates direct/transitive formulas without changing another sheet", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A2','5'); await h.edit(page,'B2','=A2*2'); await h.edit(page,'C2','=B2+1'); await h.button(page,'Add worksheet').click(); await h.edit(page,'A2','7'); await h.edit(page,'B2','=A2*2'); await h.edit(page,'C2','=B2+1');
  await h.tab(page,'Sheet1').click(); await h.structure(page,'row','2','Insert 1 row above'); await h.formula(page,'B3','=A3*2','10'); await h.formula(page,'C3','=B3+1','11'); await h.structure(page,'column','A','Insert 1 column left');
  await h.formula(page,'C3','=B3*2','10'); await h.formula(page,'D3','=C3+1','11'); await h.edit(page,'B3','9'); await h.persisted(page,async()=>{await h.formula(page,'C3','=B3*2','18');await h.formula(page,'D3','=C3+1','19');});
  await h.tab(page,'Sheet2').click(); await h.formula(page,'B2','=A2*2','14'); await h.formula(page,'C2','=B2+1','15');
});
