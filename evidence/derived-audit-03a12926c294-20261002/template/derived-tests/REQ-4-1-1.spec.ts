import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-1-1: formula =(2+3)*4-6/2 uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=(2+3)*4-6/2");
  await h.persisted(page, () => h.formula(page,'B1',"=(2+3)*4-6/2","17"));
});

test("REQ-4-1-1: formula =sUm(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=sUm(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=sUm(A1:A4)","30"));
});

test("REQ-4-1-1: formula =AVERAGE(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=AVERAGE(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=AVERAGE(A1:A4)","15"));
});

test("REQ-4-1-1: formula =COUNT(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=COUNT(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=COUNT(A1:A4)","2"));
});

test("REQ-4-1-1: formula =MIN(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=MIN(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=MIN(A1:A4)","10"));
});

test("REQ-4-1-1: formula =MAX(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=MAX(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=MAX(A1:A4)","20"));
});

test("REQ-4-1-1: MAX ignores blank cells rather than using zero when every numeric input is negative", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','-20'); await h.edit(page,'A3','-10'); await h.edit(page,'A4','text'); await h.edit(page,'B1','=mAx(A1:A4)');
  await h.persisted(page,()=>h.formula(page,'B1','=mAx(A1:A4)','-10'));
});

test("REQ-4-1-1: context REQ-1-3-2: CSV downloads actual values with escaping and leaves active state intact", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); await h.button(page,'Import CSV').click(); const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
  await h.field(dialog,'CSV file').setInputFiles({name:`${h.unique()}.csv`,mimeType:'text/csv',buffer:Buffer.from('"中文,comma",,"quote""line\nnext"\n5,,10')}); await h.button(dialog,'Confirm import').click();
  await h.edit(page, 'A2', '5'); await h.edit(page, 'C2', '=A2*2');
  await h.formula(page, 'C2', '=A2*2', '10');
  expect(h.parseCSV(await h.csv(page))).toEqual([['中文,comma', '', 'quote"line\nnext'], ['5', '', '10']]);
  await expect(h.tab(page, 'Sheet1')).toHaveAttribute('aria-selected', 'true'); await expect(h.field(page, 'Formula bar')).toHaveValue('=A2*2');
  await h.persisted(page, () => h.formula(page, 'C2', '=A2*2', '10'));
});

test("REQ-4-1-1: context REQ-2-2-1: insert below then delete referenced row adjusts original formulas", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'A2', '10'); await h.edit(page, 'B4', '=A2*2');
  await h.structure(page, 'row', '1', 'Insert 1 row below'); await h.formula(page, 'B5', '=A3*2', '20');
  await h.structure(page, 'row', '3', 'Delete row'); await h.persisted(page, () => expect(h.cell(page, 'B4')).toHaveText('#REF!'));
});

test("REQ-4-1-1: context REQ-2-2-2: insert right then delete source column adjusts formulas and invalid references", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'B1', '10'); await h.edit(page, 'D1', '=B1*2');
  await h.structure(page, 'column', 'A', 'Insert 1 column right'); await h.formula(page, 'E1', '=C1*2', '20');
  await h.structure(page, 'column', 'C', 'Delete column'); await h.persisted(page, () => expect(h.cell(page, 'D1')).toHaveText('#REF!'));
});

test("REQ-4-1-1: context REQ-3-1-2: paste rectangle through Ctrl+V preserves empties and outside cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'D4', 'outside'); await h.edit(page, 'C2', '=1+1');
  await h.paste(page, 'B2', 'East\t\t1200\nNorth\t800\t', false);
  await h.persisted(page, () => h.values(page, { B2: 'East', C2: '', D2: '1200', B3: 'North', C3: '800', D3: '', D4: 'outside' }));
});

test("REQ-4-1-1: context REQ-3-1-2: paste rectangle through menu preserves empties and outside cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'D4', 'outside'); await h.edit(page, 'C2', '=1+1');
  await h.paste(page, 'B2', 'East\t\t1200\nNorth\t800\t', true);
  await h.persisted(page, () => h.values(page, { B2: 'East', C2: '', D2: '1200', B3: 'North', C3: '800', D3: '', D4: 'outside' }));
});

test("REQ-4-1-1: context REQ-3-1-2: bulk paste recalculates outside dependent formulas without overwriting them", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','1'); await h.edit(page,'B1','2'); await h.edit(page,'D1','=A1+B1'); await h.paste(page,'A1','3\t4'); await h.persisted(page, () => h.formula(page,'D1','=A1+B1','7'));
});

test("REQ-4-1-1: context REQ-3-2-1: cut rectangle clears every source only after all target values and formulas commit", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','2\t=2+3\n3\t=6/2'); await h.edit(page,'F6','outside');
  await h.range(page,'A1','B2'); await page.keyboard.press('Control+x'); await h.values(page,{A1:'2',B1:'5',A2:'3',B2:'3'});
  await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
  await h.persisted(page,async()=>{ await h.values(page,{A1:'',B1:'',A2:'',B2:'',C3:'2',C4:'3',F6:'outside'}); await h.formula(page,'D3','=2+3','5'); await h.formula(page,'D4','=6/2','3'); });
});

test("REQ-4-1-1: context REQ-3-2-2: undo row structure restores formulas and redo result persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A2','10'); await h.edit(page,'B2','=A2*2'); await h.structure(page,'row','2','Insert 1 row above');
  await h.formula(page,'B3','=A3*2','20'); await h.button(page,'Undo').click(); await h.formula(page,'B2','=A2*2','20');
  await h.button(page,'Redo').click(); await h.persisted(page, () => h.formula(page,'B3','=A3*2','20'));
});

test("REQ-4-1-1: context REQ-3-2-2: undo and redo a range cut restore both rectangles and original formulas as one operation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','2\t=2+3\n3\t=6/2'); await h.paste(page,'C3','old-1\told-2\nold-3\told-4'); await h.edit(page,'F6','outside'); await h.range(page,'A1','B2');
  await page.keyboard.press('Control+x'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v'); await h.button(page,'Undo').click();
  await h.values(page,{A1:'2',A2:'3',C3:'old-1',D3:'old-2',C4:'old-3',D4:'old-4',F6:'outside'}); await h.formula(page,'B1','=2+3','5'); await h.formula(page,'B2','=6/2','3');
  await h.button(page,'Redo').click(); await h.persisted(page,async()=>{await h.values(page,{A1:'',B1:'',A2:'',B2:'',C3:'2',C4:'3',F6:'outside'}); await h.formula(page,'D3','=2+3','5'); await h.formula(page,'D4','=6/2','3');});
});
