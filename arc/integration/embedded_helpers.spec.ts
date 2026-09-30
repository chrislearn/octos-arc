// Real-browser checks of the frozen helpers and independent CSV oracle.
// These exercise test infrastructure, not a generated product or ARC score.
import { test, expect } from '@playwright/test';
import * as sheet from '../derived-tests/hackathon--sheet/helpers';
import * as github from '../derived-tests/hackathon--github/helpers';

test('CSV oracle preserves every ordered field and rejects malformed quoting', () => {
  expect(sheet.parseCSV('名称,备注,值,空\r\n中文,"逗号,文本",12,\r\nEnglish,"双""引号\n下一行",007,')).toEqual([
    ['名称','备注','值','空'], ['中文','逗号,文本','12',''], ['English','双"引号\n下一行','007',''],
  ]);
  expect(sheet.parseCSV('a,,\n,,')).toEqual([['a','',''],['','','']]);
  expect(() => sheet.parseCSV('a,"unclosed')).toThrow('Unclosed CSV quote');
  expect(() => sheet.parseCSV('"closed"junk')).toThrow('Malformed CSV quoting');
});

test('native combobox uses labels rather than assuming server-side option IDs', async ({ page }) => {
  await page.setContent('<label>Parent team<select><option value="team-19">platform-team</option><option value="team-41">frontend-team</option></select></label>');
  await github.choose(page, 'Parent team', 'frontend-team');
  await expect(page.getByRole('combobox')).toHaveValue('team-41');
  await sheet.choose(page, 'Parent team', 'platform-team');
  await expect(page.getByRole('combobox')).toHaveValue('team-19');
});

test('custom combobox follows clickable ARIA options', async ({ page }) => {
  await page.setContent('<button role="combobox" aria-label="Order" onclick="document.getElementById(\'options\').hidden=false">Ascending</button><div id="options" hidden><div role="option" onclick="document.querySelector(\'button\').textContent=this.textContent;this.parentElement.hidden=true">Descending</div></div>');
  await sheet.choose(page, 'Order', 'Descending');
  await expect(page.getByRole('combobox')).toHaveText('Descending');
});

test('metadata scope includes nested controls and badges but excludes historical articles', async ({ page }) => {
  await page.setContent('<main><article>Previously assigned spec-triage</article><aside><section><header><span><button>Assignees</button></span></header><div>spec-triage</div></section><section><header><button>Labels</button></header><div>bug</div></section><section><button>Milestone</button><div>v1.0</div></section></aside></main>');
  await expect(github.sidebar(page, 'Assignees')).toContainText('spec-triage');
  await page.getByRole('button', { name: 'Assignees' }).evaluate(el => el.closest('section')!.querySelector('div')!.remove());
  await expect(github.sidebar(page, 'Assignees')).not.toContainText('spec-triage');
  await expect(page.getByRole('article')).toContainText('spec-triage');
});

test('cell oracle distinguishes coordinates from text elsewhere and reads exact cell value', async ({ page }) => {
  await page.setContent('<p>999</p><div role="grid" aria-label="Worksheet grid" aria-multiselectable="true"><div role="gridcell" aria-label="A1" aria-selected="true">10</div><div role="gridcell" aria-label="A2" aria-selected="false">20</div></div>');
  await sheet.values(page, { A1:'10', A2:'20' });
  expect(await sheet.cell(page, 'A1').textContent()).not.toBe('999');
  await expect(sheet.cell(page, 'A1')).toHaveAttribute('aria-selected','true');
});

test('hidden filter records retain a coordinate value oracle', async ({ page }) => {
  await page.setContent('<div role="grid" aria-label="Worksheet grid"><div role="gridcell" aria-label="A2">East</div><div role="gridcell" aria-label="A3" style="display:none">North</div></div>');
  await sheet.values(page, { A2:'East', A3:'North' });
  await sheet.visibleRows(page, ['A2'], ['A3']);
});

test('portal option selection and checked labels work when the combo is inside a region', async ({ page }) => {
  await page.setContent('<section role="region" aria-label="Pivot table editor"><button role="combobox" aria-label="Summarize by" onclick="document.getElementById(\'portal\').hidden=false">SUM</button></section><div id="portal" hidden><div role="option" onclick="document.querySelector(\'button\').textContent=this.textContent;this.parentElement.hidden=true">AVERAGE</div></div>');
  const editor=page.getByRole('region', { name:'Pivot table editor' });
  await sheet.choose(editor, 'Summarize by', 'AVERAGE');
  await sheet.chosen(editor, 'Summarize by', 'AVERAGE');
});
