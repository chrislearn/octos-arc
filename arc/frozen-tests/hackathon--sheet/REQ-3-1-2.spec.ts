import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-3-1-2: paste rectangle through Ctrl+V preserves empties and outside cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'D4', 'outside'); await h.edit(page, 'C2', '=1+1');
  await h.paste(page, 'B2', 'East\t\t1200\nNorth\t800\t', false);
  await h.persisted(page, () => h.values(page, { B2: 'East', C2: '', D2: '1200', B3: 'North', C3: '800', D3: '', D4: 'outside' }));
});

test("REQ-3-1-2: paste rectangle through menu preserves empties and outside cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'D4', 'outside'); await h.edit(page, 'C2', '=1+1');
  await h.paste(page, 'B2', 'East\t\t1200\nNorth\t800\t', true);
  await h.persisted(page, () => h.values(page, { B2: 'East', C2: '', D2: '1200', B3: 'North', C3: '800', D3: '', D4: 'outside' }));
});

test("REQ-3-1-2: bulk paste recalculates outside dependent formulas without overwriting them", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','1'); await h.edit(page,'B1','2'); await h.edit(page,'D1','=A1+B1'); await h.paste(page,'A1','3\t4'); await h.persisted(page, () => h.formula(page,'D1','=A1+B1','7'));
});

test("REQ-3-1-2: invalid clipboard rectangle is rejected atomically through Ctrl+V", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','10\t20\n30\t40'); await h.validation(page,'A1','B2'); await h.edit(page,'D1','=A1+B1');
  await h.paste(page,'A1','50\t60\n70\t101',false); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
  await h.persisted(page,async()=>{ await h.values(page,{A1:'10',B1:'20',A2:'30',B2:'40'}); await h.formula(page,'D1','=A1+B1','30'); });
});

test("REQ-3-1-2: invalid clipboard rectangle is rejected atomically through Paste menu", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','10\t20\n30\t40'); await h.validation(page,'A1','B2'); await h.edit(page,'D1','=A1+B1');
  await h.paste(page,'A1','50\t60\n70\t101',true); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
  await h.persisted(page,async()=>{ await h.values(page,{A1:'10',B1:'20',A2:'30',B2:'40'}); await h.formula(page,'D1','=A1+B1','30'); });
});
