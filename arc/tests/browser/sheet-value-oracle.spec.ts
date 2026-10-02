import { test, expect, values } from '../../derived-tests/hackathon--sheet/helpers';

test('cell values exclude dropdown and filter decoration while preserving visible data', async ({ page }) => {
  await page.setContent(`<div role="grid" aria-label="Worksheet grid">
    <div role="gridcell" aria-label="A1">Closed<button aria-label="Open dropdown for A1">▼</button></div>
    <div role="gridcell" aria-label="B1">Region<button aria-label="Filter Region">Filter</button></div>
    <div role="gridcell" aria-label="C1"><span aria-hidden="true">decorative</span>中文  data</div>
    <div role="gridcell" aria-label="D1"><button aria-label="Open dropdown for D1">▼</button></div>
  </div>`);
  await values(page, { A1: 'Closed', B1: 'Region', C1: '中文  data', D1: '' });
  await expect(page.getByRole('button', { name: 'Open dropdown for A1', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Filter Region', exact: true })).toBeVisible();
});

test('cell oracle preserves newlines spaces and data inside an ordinary button', async ({page})=>{
  await page.setContent('<div role="grid" aria-label="Worksheet grid"><div role="gridcell" aria-label="A1">  a  b  \n中文</div><div role="gridcell" aria-label="B1"><button>Region</button></div></div>');
  await values(page,{A1:'  a  b  \n中文',B1:'Region'});
  await expect(values(page,{A1:'a b 中文'})).rejects.toThrow();
});

test('cell oracle keeps unknown button text and removes only named controls including labelledby',async({page})=>{
  await page.setContent('<span id="label">Open dropdown for B1</span><div role="grid" aria-label="Worksheet grid"><div role="gridcell" aria-label="A1">Closed<button>extra</button></div><div role="gridcell" aria-label="B1">Open<button aria-labelledby="label">▼</button></div></div>');
  await expect(values(page,{A1:'Closed'})).rejects.toThrow();
  await values(page,{B1:'Open'});
});

test('decoration exclusion still rejects incorrect or extra cell values', async ({ page }) => {
  await page.setContent(`<div role="grid" aria-label="Worksheet grid">
    <div role="gridcell" aria-label="A1">Wrong<button aria-label="Open dropdown for A1">▼</button></div>
    <div role="gridcell" aria-label="B1">Closed extra</div>
  </div>`);
  await expect(values(page, { A1: 'Closed' })).rejects.toThrow();
  await expect(values(page, { B1: 'Closed' })).rejects.toThrow();
});

test('cell oracle reads live controls rather than stale markup and rejects an empty-value false positive', async ({page})=>{
  await page.setContent('<div role="grid" aria-label="Worksheet grid"><div role="gridcell" aria-label="A1"><input value="stale"></div><div role="gridcell" aria-label="B1"><textarea>old</textarea></div><div role="gridcell" aria-label="C1"><input type="hidden" value="secret"><textarea hidden>hidden</textarea></div></div>');
  await page.locator('input').first().fill('  live 中文  '); await page.locator('textarea').first().fill('new\nline');
  await values(page,{A1:'  live 中文  ',B1:'new\nline',C1:''});
  await expect(values(page,{A1:'stale'})).rejects.toThrow();
  await expect(values(page,{A1:''})).rejects.toThrow();
  await expect(values(page,{B1:'old'})).rejects.toThrow();
});
