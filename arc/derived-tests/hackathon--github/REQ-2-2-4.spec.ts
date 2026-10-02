import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-4: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-owner"); await h.memberOrganization(page);await h.link(page,'People').click(); await expect(h.text(page,'existing-member')).toBeVisible(); await h.button(page,'Member menu existing-member').click(); await page.getByRole('menuitem',{name:'Remove from organization',exact:true}).click(); await h.button(page,'Remove').click(); await h.persisted(page,()=>expect(h.text(page,'existing-member')).toHaveCount(0));
});

test("REQ-2-2-4: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-member"); await h.memberOrganization(page);await h.link(page,'People').click(); await expect(h.text(page,'protected-member')).toBeVisible(); await expect(h.button(page,'Member menu protected-member')).toHaveCount(0); await expect(page.getByRole('menuitem',{name:'Remove from organization',exact:true})).toHaveCount(0);
});

test("REQ-2-2-4: selftest removed members stay removed until explicit readdition and then reject duplicates", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
  await h.link(page,'New organization').click(); const organization=h.unique('member-ui');
  await h.field(page,'Organization name').fill(organization); await h.field(page,'Display name').fill(organization);
  await h.button(page,'Create organization').click(); await h.link(page,'People').click();
  await expect(h.button(page,'Add member')).toBeVisible();

  await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').click();
  await expect(h.text(page,'bob-reviewer')).toBeVisible(); await h.button(page,'Member menu bob-reviewer').click();
  await page.getByRole('menuitem',{name:'Remove from organization',exact:true}).click(); await h.button(page,'Remove').click();
  await h.persisted(page,()=>expect(h.text(page,'bob-reviewer')).toHaveCount(0));
  await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').click();
  await expect(h.text(page,'bob-reviewer')).toHaveCount(1); await h.button(page,'Add member').click();
  await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').click();
  await expect(h.text(page,'Account is already a member')).toBeVisible(); await h.button(page,'Cancel').click();
  await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
});

test("REQ-2-2-4: Owner removes membership and associated access without deleting account", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'member-remove'); await h.link(page,'People').click(); await h.button(page,'Member menu bob-reviewer').click(); await page.getByRole('menuitem',{name:'Remove from organization',exact:true}).click(); await h.button(page,'Remove').click(); await h.persisted(page, () => expect(h.text(page,'bob-reviewer')).toHaveCount(0));
    await h.repo(page,h.fixtureRepo('member-remove')); const address=page.url(); await h.signOut(page); await h.signIn(page,'bob-reviewer'); await page.goto(address); await expect(h.text(page,'Access denied').first()).toBeVisible();
});

test("REQ-2-2-4: ordinary member has no removal controls", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'issue-viewer'); await h.organization(page,'member-read'); await h.link(page,'People').click(); await expect(h.text(page,'bob-reviewer').first()).toBeVisible(); await expect(h.button(page,'Member menu bob-reviewer')).toHaveCount(0); await expect(page.getByRole('menuitem',{name:'Remove from organization',exact:true})).toHaveCount(0);
});

test("REQ-2-2-4: last Owner removal is rejected and retains organization and direct team membership", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'last-owner'); await h.link(page,'People').click();
    await expect(h.containsValue(page,'org-owner').first()).toBeVisible();
    await expect(h.button(page,'Member menu org-owner')).toBeVisible();
    await h.button(page,'Member menu org-owner').click(); await page.getByRole('menuitem',{name:'Remove from organization',exact:true}).click();
    const remove=h.button(page,'Remove'); if(await remove.isEnabled()) await h.attemptSubmission(page,remove);
    await h.organization(page,'last-owner'); await h.link(page,'People').click();
    await h.persisted(page,()=>expect(h.containsValue(page,'org-owner').first()).toBeVisible());
    await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Members').click();
    await h.persisted(page,()=>expect(h.button(page,'Remove org-owner')).toBeVisible());
});
