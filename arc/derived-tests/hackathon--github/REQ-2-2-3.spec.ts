import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-3: adding Member is immediate, listed after own login, but grants no private access", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'member-add'); await h.link(page,'People').click(); await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('spec-new-member'); await h.choose(page,'Role','Member'); await h.button(page,'Add member').last().click();
  await h.persisted(page, () => expect(h.text(page,'spec-new-member').first()).toBeVisible()); await expect(h.text(page,'Pending')).toHaveCount(0); await expect(h.text(page,'Awaiting')).toHaveCount(0);
  await h.repo(page,h.fixtureRepo('member-add')); const privateAddress=page.url(); await h.signOut(page); await h.signIn(page,'spec-new-member'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await expect(h.text(page,h.orgName('member-add')).first()).toBeVisible(); await page.goto(privateAddress); await expect(h.text(page,'Access denied').first()).toBeVisible();
});

test("REQ-2-2-3: unknown and duplicate member keep form open and do not duplicate membership", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'member-invalid'); await h.link(page,'People').click(); await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('unknown-reviewer'); await h.button(page,'Add member').last().click(); await expect(h.text(page,'Account not found').first()).toBeVisible();
  await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').last().click(); await expect(h.text(page,'Account is already a member').first()).toBeVisible(); await expect(h.field(page,'Username or email')).toBeVisible(); await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
});
