import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-owner"); await h.memberOrganization(page);await h.link(page,'Teams').click(); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('mobile-team'); await h.button(page,'Create team').click(); await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:'mobile-team'})).toBeVisible());
});

test("REQ-2-2-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-owner"); await h.memberOrganization(page);await h.link(page,'Teams').click(); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('-invalid-team'); await h.button(page,'Create team').click(); await expect(page.getByText(/Team name.*invalid/)).toBeVisible(); await expect(h.field(page,'Team name')).toHaveValue('-invalid-team');
});

test("REQ-2-2-1: Teams list and detail deny visitors and nonmembers but retain member access", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-member'); await h.memberOrganization(page); await h.link(page,'Teams').click();
  await expect(h.link(page,'frontend-team')).toBeVisible(); const listAddress=page.url();
  await h.link(page,'frontend-team').click(); await expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toBeVisible();
  const detailAddress=page.url(); await h.signOut(page);
  for (const address of [listAddress,detailAddress]) {
    await page.goto(address); await h.persisted(page,async()=>{
      await expect(page.getByRole('heading',{name:'Access denied',exact:true})).toBeVisible();
      await expect(h.link(page,'frontend-team')).toHaveCount(0);
      await expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toHaveCount(0);
    });
  }
  await h.signIn(page,'alice-dev');
  for (const address of [listAddress,detailAddress]) {
    await page.goto(address); await expect(page.getByRole('heading',{name:'Access denied',exact:true})).toBeVisible();
  }
  await h.signOut(page); await h.signIn(page,'org-member'); await h.memberOrganization(page); await h.link(page,'Teams').click();
  await h.link(page,'frontend-team').click();
  await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toBeVisible());
});

test("REQ-2-2-1: Owner creates unique team without optional description or parent", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'team-create'); await h.link(page,'Teams').click(); await h.link(page,'New team').click(); const name=h.unique('pw-team');
    await h.field(page,'Team name').fill(name); await h.button(page,'Create team').click(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
});

test("REQ-2-2-1: invalid team name leaves creation form and no team", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'team-invalid'); await h.link(page,'Teams').click(); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('-invalid'); await h.button(page,'Create team').click();
    await expect(page.getByText('Team name is invalid',{exact:false})).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'-invalid',exact:true})).toHaveCount(0);
});

test("REQ-2-2-1: team legal length 50 is accepted and overlong 51 is refused without creating a team", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'team-boundaries'); await h.link(page,'Teams').click();
    const list=page.url(), name=h.unique('team').padEnd(50,'x');
    await h.link(page,'New team').click(); await h.field(page,'Team name').fill(name+'x'); await h.button(page,'Create team').click();
    await expect(h.text(page,'Team name is invalid').first()).toBeVisible(); await page.goto(list);
    await expect(h.link(page,name+'x')).toHaveCount(0); await h.link(page,'New team').click(); await h.field(page,'Team name').fill(name);
    await h.button(page,'Create team').click(); await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
});

test("REQ-2-2-1: duplicate team in the same organization does not create a second relationship", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'team-duplicate'); await h.link(page,'Teams').click(); const list=page.url();
    await expect(h.link(page,'frontend-team')).toHaveCount(1); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('frontend-team');
    await h.attemptSubmission(page,h.button(page,'Create team'));
    await page.goto(list); await h.persisted(page,()=>expect(h.link(page,'frontend-team')).toHaveCount(1));
});
