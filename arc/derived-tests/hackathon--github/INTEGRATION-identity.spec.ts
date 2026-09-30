import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-identity: registered credentials work by email and survive a later browser session", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const {username,email}=await h.register(page); await h.signIn(page,email);
  await h.persisted(page, () => expect(h.button(page,'Account menu')).toBeVisible());
  await h.button(page,'Account menu').click(); await expect(h.text(page,username).first()).toBeVisible();
  const later=await browser.newContext();
  try { const p=await later.newPage(); await h.signIn(p,username); await expect(h.button(p,'Account menu')).toBeVisible(); }
  finally { await later.close(); }
});
