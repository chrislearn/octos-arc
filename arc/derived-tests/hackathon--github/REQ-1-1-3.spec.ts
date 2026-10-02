import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-1-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.recovery(page,'recovery-visibility@example.test'); await h.home(page); await h.link(page,'Sign in').click(); await h.recovery(page,'unknown@example.test');
});

test("REQ-1-1-3: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.recovery(page,'recovery-invalid-code@example.test'); await h.field(page,'Verification code').fill('000000'); await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!'); await h.button(page,'Reset password').click(); await expect(h.text(page,'Verification code is invalid')).toBeVisible(); await h.signIn(page,"recovery-invalid-code@example.test");
});

test("REQ-1-1-3: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.recovery(page,'recovery-success@example.test'); await h.field(page,'Verification code').fill('123456'); await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!'); await h.button(page,'Reset password').click(); await expect(h.text(page,'Password updated')).toBeVisible(); await h.signIn(page,'recovery-success@example.test','Replacement-password-456!');
});

test("REQ-1-1-3: rejected recovery clears both passwords and retains verification code: Verification code is invalid", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Forgot password').click();
  await h.field(page,'Email').fill('recovery-invalid-code@example.test');
  await h.field(page,'Verification code').fill('000000');
  await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!');
  await h.button(page,'Reset password').click(); await expect(h.text(page,'Verification code is invalid')).toBeVisible();
  await expect(h.field(page,'Verification code')).toHaveValue('000000');
  await expect(h.field(page,'New password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
  await h.signIn(page,'recovery-invalid-code@example.test');
});

test("REQ-1-1-3: rejected recovery clears both passwords and retains verification code: Passwords do not match", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Forgot password').click();
  await h.field(page,'Email').fill('recovery-invalid-code@example.test');
  await h.field(page,'Verification code').fill('123456');
  await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Different-password-789!');
  await h.button(page,'Reset password').click(); await expect(h.text(page,'Passwords do not match')).toBeVisible();
  await expect(h.field(page,'Verification code')).toHaveValue('123456');
  await expect(h.field(page,'New password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
  await h.signIn(page,'recovery-invalid-code@example.test');
});

test("REQ-1-1-3: selftest recovery opens one labeled form with a code before email submission", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Forgot password').click();
  await expect(h.text(page,'123456')).toBeVisible();
  for (const label of ['Email','Verification code','New password','Confirm password']) await expect(h.field(page,label)).toBeVisible();
  for (const email of ['recovery-visibility@example.test','unknown@example.test']) {
    await h.field(page,'Email').fill(email);
    await expect(h.text(page,'123456')).toBeVisible(); await expect(h.field(page,'Email')).toHaveValue(email);
    await h.maskedPasswords(page,['New password','Confirm password']);
  }
});

test("REQ-1-1-3: selftest recovery has one success message and new credentials sign in without a reset helper", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const {username,email}=await h.register(page);
  await h.link(page,'Forgot password').click(); await h.field(page,'Email').fill(email);
  await h.field(page,'Verification code').fill('123456');
  await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!');
  await h.button(page,'Reset password').click(); await expect(h.text(page,'Password updated')).toBeVisible();
  await expect(h.link(page,'Sign in')).toHaveCount(1); await h.link(page,'Sign in').click();
  await h.field(page,'Username or email').fill(email); await h.field(page,'Password').fill('Replacement-password-456!');
  await h.button(page,'Sign in').click(); await expect(h.text(page,username)).toBeVisible();
  await page.reload(); await expect(h.text(page,username)).toBeVisible();
});

test("REQ-1-1-3: navigation readiness exposes recovery fields when the entry click completes", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Forgot password').click();
  expect(await h.field(page,'Email').isVisible(),'the recovery destination must be committed after clicking its entry').toBe(true);
  for (const label of ['Verification code','New password','Confirm password']) await expect(h.field(page,label)).toBeVisible();
  await expect(h.text(page,'123456')).toBeVisible();
  await h.field(page,'Email').fill('recovery-visibility@example.test');
  await expect(h.field(page,'Email')).toHaveValue('recovery-visibility@example.test');
});

test("REQ-1-1-3: 44831560 regression: email-only submission exposes the same recovery step for known and unknown addresses", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for (const email of ['recovery-visibility@example.test','unknown@example.test']) {
    await h.home(page); await h.link(page,'Sign in').click(); await h.recovery(page,email);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.text(page,'123456')).toBeVisible();
    for (const label of ['Verification code','New password','Confirm password']) await expect(h.field(page,label)).toHaveValue('');
    await expect(page.getByRole('alert')).toHaveCount(0);
    // A new recovery step must accept a wrong code and report that error only
    // after an actual reset attempt, while preserving the original account.
    await h.field(page,'Verification code').fill('000000');
    await h.field(page,'New password').fill('Replacement-password-456!');
    await h.field(page,'Confirm password').fill('Replacement-password-456!');
    await h.button(page,'Reset password').click();
    await expect(h.text(page,'Verification code is invalid')).toBeVisible();
  }
  await h.signIn(page,'recovery-visibility@example.test');
});

test("REQ-1-1-3: 44831560 regression: email submission and invalid code preserve original credentials", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const {username,email}=await h.register(page);
  await h.recovery(page,email);
  await h.signIn(page,username); await h.signOut(page);
  await h.link(page,'Sign in').click(); await h.recovery(page,email);
  await h.field(page,'Verification code').fill('000000');
  await h.field(page,'New password').fill('Replacement-password-456!');
  await h.field(page,'Confirm password').fill('Replacement-password-456!');
  await h.button(page,'Reset password').click();
  await expect(h.text(page,'Verification code is invalid')).toBeVisible();
  await h.signIn(page,username);
});

test("REQ-1-1-3: 44831560 regression: successful reset after email submission replaces the original credentials", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const {username,email}=await h.register(page);
  await h.recovery(page,email);
  await h.field(page,'Verification code').fill('123456');
  await h.field(page,'New password').fill('Replacement-password-456!');
  await h.field(page,'Confirm password').fill('Replacement-password-456!');
  await h.button(page,'Reset password').click(); await expect(h.text(page,'Password updated')).toBeVisible();
  await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill(username);
  await h.field(page,'Password').fill(h.PASSWORD); await h.button(page,'Sign in').click();
  await expect(h.text(page,'Invalid credentials')).toBeVisible();
  await h.signIn(page,email,'Replacement-password-456!',username);
  await page.reload(); await expect(h.button(page,'Account menu')).toBeVisible();
});

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
