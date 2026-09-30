import { test, expect, values } from '../../derived-tests/hackathon--sheet/helpers';

test('cell values exclude dropdown and filter decoration while preserving visible data', async ({ page }) => {
  await page.setContent(`<div role="grid" aria-label="Worksheet grid">
    <div role="gridcell" aria-label="A1">Closed<button aria-label="Open dropdown for A1">▼</button></div>
    <div role="gridcell" aria-label="B1">Region<button aria-label="Filter Region">Filter</button></div>
    <div role="gridcell" aria-label="C1"><span aria-hidden="true">decorative</span>中文  data</div>
    <div role="gridcell" aria-label="D1"><button aria-label="Open dropdown for D1">▼</button></div>
  </div>`);
  await values(page, { A1: 'Closed', B1: 'Region', C1: '中文 data', D1: '' });
  await expect(page.getByRole('button', { name: 'Open dropdown for A1', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Filter Region', exact: true })).toBeVisible();
});

test('decoration exclusion still rejects incorrect or extra cell values', async ({ page }) => {
  await page.setContent(`<div role="grid" aria-label="Worksheet grid">
    <div role="gridcell" aria-label="A1">Wrong<button aria-label="Open dropdown for A1">▼</button></div>
    <div role="gridcell" aria-label="B1">Closed extra</div>
  </div>`);
  await expect(values(page, { A1: 'Closed' })).rejects.toThrow();
  await expect(values(page, { B1: 'Closed' })).rejects.toThrow();
});
