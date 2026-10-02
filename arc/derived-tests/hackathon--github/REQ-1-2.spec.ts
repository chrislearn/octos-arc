import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"alice-dev"); await h.button(page,'Account menu').click(); await h.link(page,'Settings').click(); const address=page.url(); await h.signOut(page); await page.reload(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.goBack(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.goto(address); await expect(h.link(page,'Sign in')).toBeVisible();
});

test("REQ-1-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"alice-dev"); await h.button(page,'Account menu').click(); await h.link(page,'Settings').click(); const address=page.url(); await h.signOut(page); await page.reload(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.goBack(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.goto(address); await expect(h.link(page,'Sign in')).toBeVisible();
});

test("REQ-1-2: cancel retains session and confirm invalidates protected page after reload/back/direct entry", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page); await h.button(page,'Account menu').click(); await h.link(page,'Settings').click(); const protectedAddress=page.url();
    await h.button(page,'Account menu').click(); await h.link(page,'Sign out').click(); const dialog=page.getByRole('dialog',{name:'Sign out',exact:true}); await h.button(dialog,'Cancel').click();
    await expect(h.button(page,'Account menu')).toBeVisible(); await expect(page).toHaveURL(protectedAddress); await h.signOut(page);
    await page.reload(); await expect(h.link(page,'Sign in')).toBeVisible(); await page.goBack(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.goto(protectedAddress); await expect(h.link(page,'Sign in')).toBeVisible();
});

test("REQ-1-2: sign-out invalidates only this browser session and preserves another session", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const {username}=await h.register(page); await h.signIn(page,username);
    const other=await browser.newContext(); const p=await other.newPage();
    try { await h.signIn(p,username); await h.button(p,'Account menu').click(); await h.link(p,'Settings').click(); const address=p.url();
    await h.signOut(page); await expect(h.button(page,'Account menu')).toHaveCount(0);
    await p.reload(); await expect(h.button(p,'Account menu')).toBeVisible(); await p.goto(address); await expect(h.button(p,'Account menu')).toBeVisible();
    } finally { await other.close(); }
});
