import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-1-3: drag replaces and persists the exact rectangular ARIA selection", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.range(page,'B2','C3');
  await h.persisted(page,()=>h.selection(page,['B2','C2','B3','C3'],['A1','A2','B1','D3']));
  await h.cell(page,'A1').click(); await h.persisted(page,()=>h.selection(page,['A1'],['B2','C2','B3','C3']));
});
