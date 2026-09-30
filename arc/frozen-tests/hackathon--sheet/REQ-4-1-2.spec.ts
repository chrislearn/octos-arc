import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-4-1-2: copy adjusts relative references, keeps absolute references and rejects out-of-bounds", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'B2','20'); await h.edit(page,'C3','=A1+$A$1');
  await h.cell(page,'C3').click(); await page.keyboard.press('Control+c'); await h.cell(page,'D4').click(); await page.keyboard.press('Control+v');
  await h.formula(page,'D4','=B2+$A$1','30'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+c'); await h.cell(page,'B2').click(); await page.keyboard.press('Control+v');
  await h.persisted(page, () => h.formula(page,'B2','=#REF!','#REF!')); await h.formula(page,'C3','=A1+$A$1','20');
});
