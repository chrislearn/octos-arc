import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-3-1-1: failed formula-bar commit retains original input and every dependent result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.edit(page,'D2','=B2*2'); await h.edit(page,'E2','=D2+1'); await h.validation(page,'B2','B3'); await h.cell(page,'B2').click();
  await h.field(page,'Formula bar').fill('101'); await h.field(page,'Formula bar').press('Enter'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
  await expect(h.field(page,'Formula bar')).toHaveValue('50'); await h.persisted(page,async()=>{ await h.values(page,{B2:'50',D2:'100',E2:'101'}); await h.formula(page,'D2','=B2*2','100'); await h.formula(page,'E2','=D2+1','101'); });
});
