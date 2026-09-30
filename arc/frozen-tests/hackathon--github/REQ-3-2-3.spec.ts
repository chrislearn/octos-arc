import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-3-2-3: copy complete HTTPS clone value without modifying repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.button(page,'Code').click(); await page.getByRole('tab',{name:"HTTPS",exact:true}).click(); await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied').first()).toBeVisible();
  const value=await page.evaluate(() => navigator.clipboard.readText()); expect(value).toMatch(/^https:\/\/[^\s]+\/[^\s/]+\/acme-docs\.git$/); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-3-2-3: copy complete SSH clone value without modifying repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.button(page,'Code').click(); await page.getByRole('tab',{name:"SSH",exact:true}).click(); await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied').first()).toBeVisible();
  const value=await page.evaluate(() => navigator.clipboard.readText()); expect(value).toMatch(/^(?:[^@\s]+@[^:\s]+:[^\s/]+\/acme-docs\.git|ssh:\/\/[^\s]+\/acme-docs\.git)$/); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});
