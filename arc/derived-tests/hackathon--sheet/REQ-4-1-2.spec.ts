import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-1-2: copy adjusts relative references, keeps absolute references and rejects out-of-bounds", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'B2','20'); await h.edit(page,'C3','=A1+$A$1');
  await h.cell(page,'C3').click(); await page.keyboard.press('Control+c'); await h.cell(page,'D4').click(); await page.keyboard.press('Control+v');
  await h.formula(page,'D4','=B2+$A$1','30'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+c'); await h.cell(page,'B2').click(); await page.keyboard.press('Control+v');
  await h.persisted(page, () => h.formula(page,'B2','=#REF!','#REF!')); await h.formula(page,'C3','=A1+$A$1','20');
});

test("REQ-4-1-2: horizontal formula copy changes only the relative axis and preserves absolute references", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','5'); await h.edit(page,'B1','7'); await h.edit(page,'A2','11'); await h.edit(page,'B2','13'); await h.edit(page,'D4','=A1+$A$1');
  await h.cell(page,'D4').click(); await page.keyboard.press('Control+c'); await h.cell(page,'E4').click(); await page.keyboard.press('Control+v');
  await h.persisted(page,async()=>{await h.formula(page,'D4','=A1+$A$1','10');await h.formula(page,'E4','=B1+$A$1','12');await h.values(page,{A1:'5',B1:'7',A2:'11',B2:'13'});});
});

test("REQ-4-1-2: vertical formula copy changes only the relative axis and preserves absolute references", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','5'); await h.edit(page,'B1','7'); await h.edit(page,'A2','11'); await h.edit(page,'B2','13'); await h.edit(page,'D4','=A1+$A$1');
  await h.cell(page,'D4').click(); await page.keyboard.press('Control+c'); await h.cell(page,'D5').click(); await page.keyboard.press('Control+v');
  await h.persisted(page,async()=>{await h.formula(page,'D4','=A1+$A$1','10');await h.formula(page,'D5','=A2+$A$1','16');await h.values(page,{A1:'5',B1:'7',A2:'11',B2:'13'});});
});

test("REQ-4-1-2: context REQ-3-2-1: copy rectangle preserves every value, adjusted formula and outside data", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page, 'A1', '2\t=A1+$A$1\n3\t=A2'); await h.edit(page, 'F6', 'outside');
  await h.range(page, 'A1', 'B2'); await page.keyboard.press('Control+c'); await h.cell(page, 'C3').click(); await page.keyboard.press('Control+v');
  await h.persisted(page, async () => { await h.values(page, { A1:'2',A2:'3',C3:'2',C4:'3',F6:'outside' }); await h.formula(page,'B1','=A1+$A$1','4'); await h.formula(page,'B2','=A2','3'); await h.formula(page,'D3','=C3+$A$1','4'); await h.formula(page,'D4','=C4','3'); });
});

test("REQ-4-1-2: b5b932 regression: copying an accepted lowercase formula to D4 offsets only relative axes", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);await h.edit(page,'A1','10');await h.edit(page,'B1','40');await h.edit(page,'A2','30');await h.edit(page,'B2','20');await h.edit(page,'F6','outside');
  await h.edit(page,'C3','=a1+$a$1');await h.formula(page,'C3','=a1+$a$1','20');await h.range(page,'C3','C3');await page.keyboard.press('Control+c');await h.cell(page,"D4").click();await page.keyboard.press('Control+v');
  await h.persisted(page,async()=>{await h.values(page,{A1:'10',B1:'40',A2:'30',B2:'20',C3:'20',F6:'outside',"D4":"30"});await h.cell(page,"D4").click();expect((await h.field(page,'Formula bar').inputValue()).toUpperCase()).toBe("=B2+$A$1");});
  await h.formula(page,'C3','=a1+$a$1','20');
});

test("REQ-4-1-2: b5b932 regression: copying an accepted lowercase formula to D3 offsets only relative axes", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);await h.edit(page,'A1','10');await h.edit(page,'B1','40');await h.edit(page,'A2','30');await h.edit(page,'B2','20');await h.edit(page,'F6','outside');
  await h.edit(page,'C3','=a1+$a$1');await h.formula(page,'C3','=a1+$a$1','20');await h.range(page,'C3','C3');await page.keyboard.press('Control+c');await h.cell(page,"D3").click();await page.keyboard.press('Control+v');
  await h.persisted(page,async()=>{await h.values(page,{A1:'10',B1:'40',A2:'30',B2:'20',C3:'20',F6:'outside',"D3":"50"});await h.cell(page,"D3").click();expect((await h.field(page,'Formula bar').inputValue()).toUpperCase()).toBe("=B1+$A$1");});
  await h.formula(page,'C3','=a1+$a$1','20');
});

test("REQ-4-1-2: b5b932 regression: copying an accepted lowercase formula to C4 offsets only relative axes", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);await h.edit(page,'A1','10');await h.edit(page,'B1','40');await h.edit(page,'A2','30');await h.edit(page,'B2','20');await h.edit(page,'F6','outside');
  await h.edit(page,'C3','=a1+$a$1');await h.formula(page,'C3','=a1+$a$1','20');await h.range(page,'C3','C3');await page.keyboard.press('Control+c');await h.cell(page,"C4").click();await page.keyboard.press('Control+v');
  await h.persisted(page,async()=>{await h.values(page,{A1:'10',B1:'40',A2:'30',B2:'20',C3:'20',F6:'outside',"C4":"40"});await h.cell(page,"C4").click();expect((await h.field(page,'Formula bar').inputValue()).toUpperCase()).toBe("=A2+$A$1");});
  await h.formula(page,'C3','=a1+$a$1','20');
});
