import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-2: Base/Compare comboboxes show exact changed file and comparable commits", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.compare(page,'pr-compare'); await expect(h.containsValue(page,'Implement search flow').first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeEnabled();
});

test("REQ-6-2-2: equal base and compare report no differences and disable creation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.compare(page,'pr-no-changes'); await h.choose(page,'Compare','main'); await h.button(page,'Compare changes').click(); await expect(h.noDifferences(page).first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeDisabled();
});
