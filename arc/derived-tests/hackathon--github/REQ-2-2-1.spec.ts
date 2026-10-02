import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-1: Owner creates unique team without optional description or parent", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'team-create'); await h.link(page,'Teams').click(); await h.link(page,'New team').click(); const name=h.unique('pw-team');
  await h.field(page,'Team name').fill(name); await h.button(page,'Create team').click(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
});

test("REQ-2-2-1: invalid team name leaves creation form and no team", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'team-invalid'); await h.link(page,'Teams').click(); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('-invalid'); await h.button(page,'Create team').click();
  await expect(page.getByText('Team name is invalid',{exact:false})).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'-invalid',exact:true})).toHaveCount(0);
});

test("REQ-2-2-1: team legal length 50 is accepted and overlong 51 is refused without creating a team", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'team-boundaries'); await h.link(page,'Teams').click();
  const list=page.url(), name=h.unique('team').padEnd(50,'x');
  await h.link(page,'New team').click(); await h.field(page,'Team name').fill(name+'x'); await h.button(page,'Create team').click();
  await expect(h.text(page,'Team name is invalid').first()).toBeVisible(); await page.goto(list);
  await expect(h.link(page,name+'x')).toHaveCount(0); await h.link(page,'New team').click(); await h.field(page,'Team name').fill(name);
  await h.button(page,'Create team').click(); await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
});

test("REQ-2-2-1: duplicate team in the same organization does not create a second relationship", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'team-duplicate'); await h.link(page,'Teams').click(); const list=page.url();
  await expect(h.link(page,'frontend-team')).toHaveCount(1); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('frontend-team');
  await h.attemptSubmission(page,h.button(page,'Create team'));
  await page.goto(list); await h.persisted(page,()=>expect(h.link(page,'frontend-team')).toHaveCount(1));
});
