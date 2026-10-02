import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-1-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-owner"); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await h.link(page,'New organization').click(); await h.field(page,'Organization name').fill('mobile-guild'); await h.field(page,'Display name').fill('Mobile Guild'); await h.button(page,'Create organization').click(); await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:'mobile-guild'})).toBeVisible());
});

test("REQ-2-1-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-owner"); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await h.link(page,'New organization').click(); await h.field(page,'Organization name').fill('acme-demo'); await h.field(page,'Display name').fill(''); await h.button(page,'Create organization').click(); await expect(h.text(page,'Organization name already exists')).toBeVisible(); await expect(h.field(page,'Organization name')).toHaveValue('acme-demo');
});

test("REQ-2-1-2: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-owner"); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await h.link(page,'New organization').click(); await h.field(page,'Organization name').fill('-invalid-organization'); await h.field(page,'Display name').fill('   '); await h.button(page,'Create organization').click(); await expect(h.text(page,'Organization name format is invalid')).toBeVisible(); await expect(h.text(page,'Display name is required')).toBeVisible();
});

test("REQ-2-1-2: create organization persists identifier and creator Owner relationship", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await h.link(page,'New organization').click(); const name=h.unique('pw-org');
    await h.field(page,'Organization name').fill(name); await h.field(page,'Display name').fill('Mobile Guild'); await h.button(page,'Create organization').click(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
    await h.link(page,'People').click(); await expect(h.text(page,'alice-dev').first()).toBeVisible(); await expect(h.text(page,'Owner').first()).toBeVisible();
});

test("REQ-2-1-2: duplicate organization and malformed input remain retryable without creating organization", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await h.link(page,'New organization').click();
    await h.field(page,'Organization name').fill('regression-org-existing'); await h.field(page,'Display name').fill(''); await h.button(page,'Create organization').click(); await expect(page.getByText('Organization name already exists',{exact:false})).toBeVisible(); await expect(h.field(page,'Organization name')).toHaveValue('regression-org-existing');
    await h.field(page,'Organization name').fill('-invalid-organization'); await h.field(page,'Display name').fill('   '); await h.button(page,'Create organization').click(); await expect(page.getByText('Organization name format is invalid',{exact:false})).toBeVisible(); await expect(page.getByText('Display name is required',{exact:false})).toBeVisible();
});
