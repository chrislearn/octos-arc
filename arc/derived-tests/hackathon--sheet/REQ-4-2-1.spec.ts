import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-1: direct and transitive dependent formulas update after edit and paste", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','2'); await h.edit(page,'B1','=A1*2'); await h.edit(page,'C1','=B1+1');
  await h.edit(page,'A1','5'); await h.values(page,{B1:'10',C1:'11'}); await h.paste(page,'A1','7');
  await h.persisted(page, async () => { await h.formula(page,'B1','=A1*2','14'); await h.formula(page,'C1','=B1+1','15'); });
});

test("REQ-4-2-1: successful range move recalculates formulas depending on target values in dependency order", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','3\t4'); await h.edit(page,'C3','1'); await h.edit(page,'D3','2'); await h.edit(page,'F3','=C3+D3'); await h.edit(page,'G3','=F3*2');
  await h.range(page,'A1','B1'); await page.keyboard.press('Control+x'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
  await h.persisted(page,async()=>{await h.values(page,{A1:'',B1:'',C3:'3',D3:'4'});await h.formula(page,'F3','=C3+D3','7');await h.formula(page,'G3','=F3*2','14');});
});
