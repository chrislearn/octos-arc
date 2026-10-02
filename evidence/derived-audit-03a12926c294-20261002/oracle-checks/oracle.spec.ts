import { test, expect } from './helpers';
import * as h from './helpers';

// These tests exercise the downloaded oracle on controlled witnesses.
// A green result confirms the specified weakness, not product correctness.
test('downloaded values helper accepts collapsed newline and lost surrounding whitespace', async ({page})=>{
  await page.setContent('<div role="grid" aria-label="Worksheet grid"><div role="gridcell" aria-label="A1">双"引号 下一行</div></div>');
  await h.values(page,{A1:'双"引号\n下一行'});
  await expect(h.cell(page,'A1')).toHaveText('双"引号 下一行');
  expect(await h.cell(page,'A1').textContent()).not.toBe('双"引号\n下一行');
  await h.cell(page,'A1').evaluate(el=>el.textContent='a b');
  await h.values(page,{A1:'  a  b  '});
  expect(await h.cell(page,'A1').textContent()).not.toBe('  a  b  ');
});

test('downloaded values helper discards extra visible button text inside a cell',async({page})=>{
  await page.setContent('<div role="grid" aria-label="Worksheet grid"><div role="gridcell" aria-label="A1">correct<button>corrupted value fragment</button></div></div>');
  await h.values(page,{A1:'correct'});
  await expect(h.cell(page,'A1')).toHaveText('correctcorrupted value fragment');
});

test('failed-save alert assertion rejects ordinary visible error text',async({page})=>{
  await page.setContent('<label>Formula bar<input value="original"></label><p>Unable to save cell</p>');
  await expect(page.getByText('Unable to save cell',{exact:true})).toBeVisible();
  // Exact locator and assertion from REQ-3-1-1.spec.ts lines 28 and 42.
  const alerts=page.locator('[role="alert"]:visible').filter({hasText:/\S/});
  await expect(expect(alerts.first()).toBeVisible()).rejects.toThrow();
  await expect(h.field(page,'Formula bar')).toHaveValue('original');
});

test('timestamp helper accepts inline timestamp; suspected layout restriction is not reproduced',async({page})=>{
  await page.setContent('<div><a href="/book/1">Q3 Sales</a> <span>Last updated: 2026-10-02 12:00</span></div>');
  await expect(page.getByText('Last updated: 2026-10-02 12:00',{exact:true})).toBeVisible();
  expect(await h.recordUpdated(page,'Q3 Sales')).toBe('Last updated: 2026-10-02 12:00');
});

test('date-sort fixture produces identical string and chronological order',async()=>{
  const source=['2026-12-31','2026-01-02','2026-01-02','2025-12-31'];
  const lexical=source.map((key,i)=>({key,i})).sort((a,b)=>a.key.localeCompare(b.key));
  const chronological=source.map((key,i)=>({key,i})).sort((a,b)=>Date.parse(a.key)-Date.parse(b.key));
  expect(lexical).toEqual(chronological);
  const distinguishing=['2026-1-2','2026-12-31','2026-2-1'];
  expect([...distinguishing].sort()).not.toEqual([...distinguishing].sort((a,b)=>Date.parse(a)-Date.parse(b)));
});


test('downloaded values helper rejects data text rendered inside an ordinary button',async({page})=>{
  await page.setContent('<div role="grid" aria-label="Worksheet grid"><div role="gridcell" aria-label="A1"><button>Region</button></div></div>');
  await expect(h.cell(page,'A1')).toHaveText('Region');
  await expect(page.getByRole('button',{name:'Region',exact:true})).toBeVisible();
  await expect(h.values(page,{A1:'Region'})).rejects.toThrow();
});
