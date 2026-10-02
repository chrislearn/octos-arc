import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-1-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"alice-dev"); await h.persisted(page,()=>expect(h.containsValue(page,'alice-dev').first()).toBeVisible());
});

test("REQ-1-1-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill("alice.dev@example.test"); await h.field(page,'Password').fill("Valid-password-123!-incorrect"); await h.button(page,'Sign in').click(); await expect(h.text(page,'Invalid credentials')).toBeVisible(); await expect(h.button(page,'Account menu')).toHaveCount(0);
});

test("REQ-1-1-2: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"alice.dev@example.test");
});

test("REQ-1-1-2: requirement scenario 4", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill("unknown@example.test"); await h.field(page,'Password').fill("Valid-password-123!"); await h.button(page,'Sign in').click(); await expect(h.text(page,'Invalid credentials')).toBeVisible(); await expect(h.button(page,'Account menu')).toHaveCount(0); await h.home(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill("alice-dev"); await h.field(page,'Password').fill("Valid-password-123!-wrong"); await h.button(page,'Sign in').click(); await expect(h.text(page,'Invalid credentials')).toBeVisible(); await expect(h.button(page,'Account menu')).toHaveCount(0);
});

test("REQ-1-1-2: existing alice-dev creates persistent session", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"alice-dev"); await h.persisted(page, () => expect(h.button(page,'Account menu')).toBeVisible());
});

test("REQ-1-1-2: existing alice.dev@example.test creates persistent session", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"alice.dev@example.test"); await h.persisted(page, () => expect(h.button(page,'Account menu')).toBeVisible());
});

test("REQ-1-1-2: generic credential rejection for unknown-reviewer / account state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill("unknown-reviewer"); await h.field(page,'Password').fill("Valid-password-123!"); await h.button(page,'Sign in').click();
    await expect(h.text(page,'Invalid credentials').first()).toBeVisible(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.reload(); await expect(h.button(page,'Account menu')).toHaveCount(0);
});

test("REQ-1-1-2: generic credential rejection for alice-dev / wrong password", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill("alice-dev"); await h.field(page,'Password').fill("Wrong-password-456!"); await h.button(page,'Sign in').click();
    await expect(h.text(page,'Invalid credentials').first()).toBeVisible(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.reload(); await expect(h.button(page,'Account menu')).toHaveCount(0);
});

test("REQ-1-1-2: generic credential rejection for unavailable-user / account state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill("unavailable-user"); await h.field(page,'Password').fill("Valid-password-123!"); await h.button(page,'Sign in').click();
    await expect(h.text(page,'Invalid credentials').first()).toBeVisible(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.reload(); await expect(h.button(page,'Account menu')).toHaveCount(0);
});

test("REQ-1-1-2: guide: a newly registered identity signs in by email and username across reload and an independent session", async ({ page, browser }) => {
  test.setTimeout(60_000);
  let identity: {username: string, email: string};
    await test.step('Create an account through the earlier registration capability',async()=>{ identity=await h.register(page); });
    await test.step('Use its email and retain the authenticated session after reload',async()=>{
      await h.signIn(page,identity.email,h.PASSWORD,identity.username); await h.persisted(page,()=>expect(h.button(page,'Account menu')).toBeVisible());
      await h.button(page,'Account menu').click(); await expect(h.containsValue(page,identity.username).first()).toBeVisible();
    });
    await test.step('Use its username in an independent browser session',async()=>{
      const later=await browser.newContext({baseURL:new URL(page.url()).origin});
      try { const p=await later.newPage(); await h.signIn(p,identity.username); await h.persisted(p,()=>expect(h.button(p,'Account menu')).toBeVisible()); }
      finally { await later.close(); }
    });
});

test("REQ-1-1-2: registration accepts password boundary 12 and trimmed email; email sign-in persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const username=h.unique('accepted'), email=`${username}@example.test`, password='Aa1!'+'x'.repeat(12-4);
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(`  ${email}  `);
    await h.field(page,'Password').fill(password); await h.field(page,'Confirm password').fill(password);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(h.field(page,'Username or email')).toBeVisible(); await h.signIn(page,email,password,username);
});

test("REQ-1-1-2: registration accepts password boundary 128 and trimmed email; email sign-in persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const username=h.unique('accepted'), email=`${username}@example.test`, password='Aa1!'+'x'.repeat(128-4);
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(`  ${email}  `);
    await h.field(page,'Password').fill(password); await h.field(page,'Confirm password').fill(password);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(h.field(page,'Username or email')).toBeVisible(); await h.signIn(page,email,password,username);
});

test("REQ-1-1-2: context REQ-1-1-1: registered credentials work by email and survive a later browser session", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const {username,email}=await h.register(page); await h.signIn(page,email,h.PASSWORD,username);
    await h.persisted(page, () => expect(h.button(page,'Account menu')).toBeVisible());
    await h.button(page,'Account menu').click(); await expect(h.containsValue(page,username).first()).toBeVisible();
    const later=await browser.newContext();
    try { const p=await later.newPage(); await h.signIn(p,username); await expect(h.button(p,'Account menu')).toBeVisible(); }
    finally { await later.close(); }
});
