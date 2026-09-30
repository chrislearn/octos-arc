import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-2-2-4: Owner removes membership and associated access without deleting account", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'member-remove'); await h.link(page,'People').click(); await h.button(page,'Member menu bob-reviewer').click(); await page.getByRole('menuitem',{name:'Remove from organization',exact:true}).click(); await h.button(page,'Remove').click(); await h.persisted(page, () => expect(h.text(page,'bob-reviewer')).toHaveCount(0));
  await h.repo(page,h.fixtureRepo('member-remove')); const address=page.url(); await h.signOut(page); await h.signIn(page,'bob-reviewer'); await page.goto(address); await expect(h.text(page,'Access denied').first()).toBeVisible();
});

test("REQ-2-2-4: ordinary member has no removal controls", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.organization(page,'member-read'); await h.link(page,'People').click(); await expect(h.text(page,'bob-reviewer').first()).toBeVisible(); await expect(h.button(page,'Member menu bob-reviewer')).toHaveCount(0); await expect(page.getByRole('menuitem',{name:'Remove from organization',exact:true})).toHaveCount(0);
});
