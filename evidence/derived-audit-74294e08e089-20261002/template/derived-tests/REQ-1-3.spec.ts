import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-3: password change uses current account and old password no longer signs in", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const { username } = await h.register(page); await h.signIn(page, username); await h.button(page, 'Account menu').click(); await h.link(page, 'Settings').click(); await h.link(page, 'Password and authentication').click();
  await h.field(page, 'Current password').fill(h.PASSWORD); await h.field(page, 'New password').fill('New-password-456!'); await h.field(page, 'Confirm password').fill('New-password-456!'); await h.button(page, 'Update password').click(); await expect(h.text(page, 'Password updated').first()).toBeVisible(); await h.signOut(page);
  await h.signIn(page, username, 'New-password-456!'); await h.signOut(page); await h.link(page, 'Sign in').click(); await h.field(page, 'Username or email').fill(username); await h.field(page, 'Password').fill(h.PASSWORD); await h.button(page, 'Sign in').click(); await expect(h.text(page, 'Invalid credentials').first()).toBeVisible();
});

test("REQ-1-3: missing current password and mismatch leave original credentials usable", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const { username } = await h.register(page); await h.signIn(page, username); await h.button(page, 'Account menu').click(); await h.link(page, 'Settings').click(); await h.link(page, 'Password and authentication').click();
  await h.field(page, 'New password').fill('Required-password-789!'); await h.field(page, 'Confirm password').fill('Required-password-789!'); await h.button(page, 'Update password').click(); await expect(page.getByText('Current password is required', { exact: false })).toBeVisible();
  await h.field(page, 'Current password').fill('Wrong-password-456!'); await h.field(page, 'New password').fill('Required-password-789!'); await h.field(page, 'Confirm password').fill('does-not-match'); await h.button(page, 'Update password').click(); await expect(page.getByText(/^(Current password is incorrect|Password confirmation does not match)$/).filter({ visible: true }).first()).toBeVisible(); await h.signOut(page); await h.signIn(page, username);
});
