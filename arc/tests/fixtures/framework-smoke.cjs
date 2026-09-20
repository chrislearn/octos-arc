const {chromium, expect} = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage();
    const errors = [];
    const external = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.hostname !== '127.0.0.1') { external.push(url.href); return route.abort(); }
      return route.continue();
    });
    const base = `http://127.0.0.1:${process.argv[2]}`;
    await page.goto(base);
    await expect(page.getByRole('heading', {name: 'Framework smoke'})).toBeVisible();
    await expect(page.getByRole('checkbox', {name: 'Native flag'})).not.toBeChecked();
    await expect(page.getByRole('checkbox', {name: 'Radix flag'})).not.toBeChecked();
    await page.getByRole('checkbox', {name: 'Native flag'}).check();
    await expect(page.getByRole('checkbox', {name: 'Radix flag'})).toBeChecked();
    await page.getByRole('checkbox', {name: 'Radix flag'}).click();
    await expect(page.getByRole('checkbox', {name: 'Native flag'})).not.toBeChecked();
    await page.getByRole('button', {name: 'Open editor'}).click();
    await expect(page.getByRole('dialog', {name: 'Editor'})).toBeVisible();
    await expect(page.getByRole('link', {name: 'Details'})).toHaveCount(0);
    await page.getByLabel('Draft').fill('edited');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Open editor'})).toBeFocused();
    await page.getByRole('button', {name: 'Actions', exact: true}).click();
    await page.getByRole('menuitem', {name: 'Increment once'}).click();
    await expect(page.getByLabel('Selections')).toHaveText('1');
    await page.getByRole('button', {name: 'Submit form'}).click();
    await expect(page.getByRole('alert')).toHaveText('Required');
    await page.getByRole('textbox', {name: 'Name', exact: true}).fill('Ada');
    await page.getByRole('button', {name: 'Submit form'}).click();
    await expect(page.getByLabel('Submitted')).toHaveText('Ada');
    await expect(page.getByLabel('Date', {exact: true})).toHaveText('2026-01-10');
    await expect(page.getByRole('grid')).toBeVisible();
    await expect(page.locator('strong')).toHaveText('Markdown works');
    await expect(page.getByRole('textbox', {name: 'Document body'})).toHaveText('Editable text');
    await page.getByRole('textbox', {name: 'Document body'}).fill('Edited rich text');
    await expect(page.getByRole('textbox', {name: 'Document body'})).toHaveText('Edited rich text');
    await page.getByLabel('Display mode').selectOption('expanded');
    await expect(page.getByLabel('Display mode')).toHaveValue('expanded');
    await expect(page.getByLabel('Decimal')).toHaveText('0.3');
    await page.getByRole('link', {name: 'Details'}).click();
    await expect(page.getByRole('heading', {name: 'Local deep route'})).toBeVisible();
    await page.reload();
    await expect(page.getByRole('heading', {name: 'Local deep route'})).toBeVisible();
    expect((await page.request.get(base + '/api/absent')).status()).toBe(404);
    expect((await page.request.get(base + '/assets/absent.js')).status()).toBe(404);
    expect(await (await page.request.get(base + '/local.txt')).text()).toBe('local public asset');
    expect(errors).toEqual([]);
    expect(external).toEqual([]);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
