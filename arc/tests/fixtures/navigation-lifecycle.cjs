const {chromium} = require('playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless: true});
  const base = `http://127.0.0.1:${process.argv[2]}`;
  const errors = [];
  const visible = (page, name) => page.getByRole('link', {name, exact: true}).isVisible();
  const pending = (page, owner) => page.evaluate(owner => window.readHarness.pending().filter(read => read.owner === owner), owner);
  const settle = (page, id, value, failure = false) => page.evaluate(
    ({id, value, failure}) => window.readHarness.settle(id, value, failure), {id, value, failure});
  const value = (page, name) => page.getByLabel(name, {exact: true}).textContent();
  // A rendering boundary only: never release a pending read to make an assertion pass.
  const paint = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  async function open(fault = '') {
    const page = await browser.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${base}/?fault=${fault}`);
    await page.waitForFunction(() => window.readHarness?.pending().length === 1);
    return page;
  }
  async function ready(page) {
    const [read] = await pending(page, 'alpha');
    await settle(page, read.id, {name: 'Alpha'});
    await page.getByRole('link', {name: 'Account settings', exact: true}).waitFor();
  }
  async function refreshPreservesPage(page) {
    await ready(page);
    await page.getByRole('link', {name: 'Account settings', exact: true}).click();
    await paint(page);
    assert.equal(await visible(page, 'Account settings'), true, 'same-owner refresh removed navigation');
    assert.equal(await page.getByRole('heading', {name: 'Settings', exact: true}).isVisible(), true);
    assert.equal(await value(page, 'Refresh pending'), 'true');
    const [read] = await pending(page, 'alpha');
    await page.getByLabel('Draft', {exact: true}).fill('keep this draft');
    await settle(page, read.id, {name: 'Alpha'}); await paint(page);
    assert.equal(await page.getByLabel('Draft', {exact: true}).inputValue(), 'keep this draft');
  }
  async function lateOwnerResponse(page) {
    const [old] = await pending(page, 'alpha');
    await page.getByRole('button', {name: 'Use beta'}).click();
    const [current] = await pending(page, 'beta');
    await settle(page, current.id, {name: 'Beta'}); await paint(page);
    await settle(page, old.id, {name: 'Alpha'}); await paint(page);
    assert.equal(await value(page, 'Identity'), 'Beta', 'old owner overwrote current identity');
  }
  try {
    let page = await open();
    assert.equal(await visible(page, 'Account settings'), false, 'unverified identity must not expose protected controls');
    await refreshPreservesPage(page);
    await page.getByRole('link', {name: 'Documents', exact: true}).click(); await paint(page);
    assert.equal(await visible(page, 'List'), true, 'page navigation waits for its data');
    assert.equal((await pending(page, 'documents')).length, 1);
    await page.getByRole('link', {name: 'Settings', exact: true}).click(); await paint(page);
    await settle(page, (await pending(page, 'documents'))[0].id, ['late data']); await paint(page);
    assert.equal(await page.getByRole('heading', {name: 'Settings', exact: true}).isVisible(), true);
    await page.close();

    page = await open(); await lateOwnerResponse(page); await page.close();
    page = await open(); await ready(page);
    await page.getByRole('button', {name: 'Refresh identity'}).click();
    const [old] = await pending(page, 'alpha');
    await page.getByRole('button', {name: 'Refresh identity'}).click();
    const newer = (await pending(page, 'alpha')).find(read => read.id !== old.id);
    await settle(page, old.id, {message: 'stale failure'}, true); await paint(page);
    assert.equal(await value(page, 'Refresh pending'), 'true', 'old finally cleared current pending');
    assert.equal(await page.getByRole('alert').count(), 0, 'old error replaced current state');
    await settle(page, newer.id, {message: 'Network unavailable'}, true); await paint(page);
    assert.equal(await value(page, 'Identity'), 'Alpha', 'transient failure cleared verified identity');
    assert.equal(await visible(page, 'Account settings'), true);
    assert.equal(await page.getByRole('alert').textContent(), 'Network unavailable');
    await page.getByRole('button', {name: 'Refresh identity'}).click();
    await settle(page, (await pending(page, 'alpha'))[0].id, {message: 'Session expired', status: 401}, true); await paint(page);
    assert.equal(await value(page, 'Identity'), 'Anonymous');
    assert.equal(await visible(page, 'Account settings'), false, 'confirmed expiry retained protected controls');
    await page.close();

    for (const failure of [false, true]) {
      page = await open(); await ready(page);
      await page.getByRole('button', {name: 'Refresh identity'}).click();
      const [read] = await pending(page, 'alpha');
      await page.getByRole('button', {name: 'Sign out'}).click(); await paint(page);
      assert.equal(await visible(page, 'Account settings'), false);
      await settle(page, read.id, failure ? {message: 'old failure'} : {name: 'Alpha'}, failure); await paint(page);
      assert.equal(await value(page, 'Identity'), 'Anonymous');
      assert.equal(await page.getByRole('alert').count(), 0);
      assert.equal((await pending(page, 'alpha')).length, 0, 'logout must not need a replacement request');
      await page.close();
    }

    // Negative controls prove the checks fail when the reference integration
    // recreates each bug; these flags never appear in the shipped blueprint.
    for (const [fault, check, message] of [
      ['blank-refresh', refreshPreservesPage, 'same-owner refresh removed navigation'],
      ['stale', lateOwnerResponse, 'old owner overwrote current identity'],
    ]) {
      page = await open(fault);
      await assert.rejects(() => check(page), error => error.message.includes(message));
      await page.close();
    }
    assert.deepEqual(errors, []);
    console.log('browser lifecycle: loading, retained navigation/drafts, data pending, owner change, stale catch/finally, transient error, expiry, logout success/error; 2 negative controls rejected');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
