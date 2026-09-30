import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

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

test("REQ-1-1-2: generic credential rejection for spec-unavailable / account state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill("spec-unavailable"); await h.field(page,'Password').fill("Valid-password-123!"); await h.button(page,'Sign in').click();
  await expect(h.text(page,'Invalid credentials').first()).toBeVisible(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.reload(); await expect(h.button(page,'Account menu')).toHaveCount(0);
});

test("REQ-1-1-2: guide: a newly registered identity signs in by email and username across reload and an independent session", async ({ page, browser }) => {
  test.setTimeout(60_000);
  let identity: {username: string, email: string};
  await test.step('Create an account through the earlier registration capability',async()=>{ identity=await h.register(page); });
  await test.step('Use its email and retain the authenticated session after reload',async()=>{
    await h.signIn(page,identity.email); await h.persisted(page,()=>expect(h.button(page,'Account menu')).toBeVisible());
    await h.button(page,'Account menu').click(); await expect(h.text(page,identity.username).first()).toBeVisible();
  });
  await test.step('Use its username in an independent browser session',async()=>{
    const later=await browser.newContext({baseURL:new URL(page.url()).origin});
    try { const p=await later.newPage(); await h.signIn(p,identity.username); await h.persisted(p,()=>expect(h.button(p,'Account menu')).toBeVisible()); }
    finally { await later.close(); }
  });
});
