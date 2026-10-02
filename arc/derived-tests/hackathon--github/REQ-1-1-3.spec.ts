import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-1-3: valid local recovery updates only registered credentials; invalid code preserves old password", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const {username,email}=await h.register(page); await h.recovery(page,email);
  await expect(h.containsValue(page,'123456').first()).toBeVisible(); await h.field(page,'Verification code').fill('000000'); await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!'); await h.button(page,'Reset password').click();
  await expect(page.getByText('Verification code is invalid',{exact:false})).toBeVisible(); await h.signIn(page,username); await h.signOut(page);
  await h.recovery(page,email); await h.field(page,'Verification code').fill('123456'); await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!'); await h.button(page,'Reset password').click();
  await expect(h.text(page,'Password updated').first()).toBeVisible(); await h.signIn(page,username,'Replacement-password-456!'); await h.signOut(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill(username); await h.field(page,'Password').fill(h.PASSWORD); await h.button(page,'Sign in').click(); await expect(h.text(page,'Invalid credentials').first()).toBeVisible();
});

test("REQ-1-1-3: unknown email shows the same fixed code and reset form but cannot update an account", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const {username}=await h.register(page); await h.recovery(page,`${h.unique()}@example.test`);
  await expect(h.containsValue(page,'123456').first()).toBeVisible(); for(const label of ['Verification code','New password','Confirm password']) await expect(h.field(page,label)).toBeVisible();
  await h.field(page,'Verification code').fill('123456'); await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!'); await h.button(page,'Reset password').click(); await expect(h.text(page,'Password updated')).toHaveCount(0); await h.signIn(page,username);
});
