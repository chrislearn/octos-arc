import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-3-2-1: copy rectangle preserves every value, adjusted formula and outside data", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page, 'A1', '2\t=A1+$A$1\n3\t=A2'); await h.edit(page, 'F6', 'outside');
  await h.range(page, 'A1', 'B2'); await page.keyboard.press('Control+c'); await h.cell(page, 'C3').click(); await page.keyboard.press('Control+v');
  await h.persisted(page, async () => { await h.values(page, { A1:'2',A2:'3',C3:'2',C4:'3',F6:'outside' }); await h.formula(page,'B1','=A1+$A$1','4'); await h.formula(page,'B2','=A2','3'); await h.formula(page,'D3','=C3+$A$1','4'); await h.formula(page,'D4','=C4','3'); });
});

test("INTEGRATION-deferred-3-2-1: cut rectangle clears every source only after all target values and formulas commit", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','2\t=2+3\n3\t=6/2'); await h.edit(page,'F6','outside');
  await h.range(page,'A1','B2'); await page.keyboard.press('Control+x'); await h.values(page,{A1:'2',B1:'5',A2:'3',B2:'3'});
  await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
  await h.persisted(page,async()=>{ await h.values(page,{A1:'',B1:'',A2:'',B2:'',C3:'2',C4:'3',F6:'outside'}); await h.formula(page,'D3','=2+3','5'); await h.formula(page,'D4','=6/2','3'); });
});

test("INTEGRATION-deferred-3-2-1: rejected range cut preserves source and all validated target cells atomically", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','50\n101'); await h.edit(page,'C1','10'); await h.edit(page,'C2','20'); await h.validation(page,'C1','C2'); await h.range(page,'A1','A2'); await page.keyboard.press('Control+x'); await h.cell(page,'C1').click(); await page.keyboard.press('Control+v'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.persisted(page, () => h.values(page,{A1:'50',A2:'101',C1:'10',C2:'20'}));
});

test("INTEGRATION-deferred-3-2-1: rejected copy preserves every source/target formula and outside dependent calculation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','50\n101'); await h.paste(page,'C1','10\n20'); await h.validation(page,'C1','C2'); await h.edit(page,'E1','=C1+C2'); await h.range(page,'A1','A2');
  await page.keyboard.press('Control+c'); await h.cell(page,'C1').click(); await page.keyboard.press('Control+v'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
  await h.persisted(page,async()=>{await h.values(page,{A1:'50',A2:'101',C1:'10',C2:'20'});await h.formula(page,'E1','=C1+C2','30');});
});
