import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-2-2-1: Owner creates unique team without optional description or parent", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'team-create'); await h.link(page,'Teams').click(); await h.link(page,'New team').click(); const name=h.unique('pw-team');
  await h.field(page,'Team name').fill(name); await h.button(page,'Create team').click(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
});

test("REQ-2-2-1: invalid team name leaves creation form and no team", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'team-invalid'); await h.link(page,'Teams').click(); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('-invalid'); await h.button(page,'Create team').click();
  await expect(page.getByText('Team name format is invalid',{exact:false})).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'-invalid',exact:true})).toHaveCount(0);
});
