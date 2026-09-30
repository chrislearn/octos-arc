import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-4-2-1: row and column movement recalculates direct/transitive formulas without changing another sheet", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A2','5'); await h.edit(page,'B2','=A2*2'); await h.edit(page,'C2','=B2+1'); await h.button(page,'Add worksheet').click(); await h.edit(page,'A2','7'); await h.edit(page,'B2','=A2*2'); await h.edit(page,'C2','=B2+1');
  await h.tab(page,'Sheet1').click(); await h.structure(page,'row','2','Insert 1 row above'); await h.formula(page,'B3','=A3*2','10'); await h.formula(page,'C3','=B3+1','11'); await h.structure(page,'column','A','Insert 1 column left');
  await h.formula(page,'C3','=B3*2','10'); await h.formula(page,'D3','=C3+1','11'); await h.edit(page,'B3','9'); await h.persisted(page,async()=>{await h.formula(page,'C3','=B3*2','18');await h.formula(page,'D3','=C3+1','19');});
  await h.tab(page,'Sheet2').click(); await h.formula(page,'B2','=A2*2','14'); await h.formula(page,'C2','=B2+1','15');
});
