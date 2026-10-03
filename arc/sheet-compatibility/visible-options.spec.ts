import { test as base, expect, type Page, type Locator } from '@playwright/test';

// A separate browser-compatibility probe reconstructed from the first failed
// actions in the two ARC reports. It is not an official test or requirement
// oracle. Each case starts from a new workbook and reports its entry separately.
const test = base.extend({ page: async ({ page, context }, use) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await use(page);
} });
const button = (root: Page | Locator, name: string) => root.getByRole('button', { name, exact: true });
const grid = (page: Page) => page.getByRole('grid', { name: 'Worksheet grid', exact: true });
const cell = (page: Page, at: string) => grid(page).getByRole('gridcell', { name: at, exact: true, includeHidden: true });

async function source(page: Page, records: string) {
  await page.goto('/');
  await button(page, 'New blank workbook').click();
  await button(page, 'Create').click();
  await page.evaluate(value => navigator.clipboard.writeText(value), records);
  await cell(page, 'A1').click();
  await page.keyboard.press('Control+v');
  await expect(cell(page, 'A1')).not.toBeEmpty();
}

async function selectRange(page: Page, from: string, to: string) {
  const first = await cell(page, from).boundingBox();
  const last = await cell(page, to).boundingBox();
  expect(first).not.toBeNull(); expect(last).not.toBeNull();
  await page.mouse.move(first!.x + first!.width / 2, first!.y + first!.height / 2);
  await page.mouse.down();
  await page.mouse.move(last!.x + last!.width / 2, last!.y + last!.height / 2, {steps: 8});
  await page.mouse.up();
}

async function data(page: Page, command: string) {
  await button(page, 'Data').click();
  await page.getByRole('menuitem', {name: command, exact: true}).click();
}

async function visibleOption(page: Page, owner: Locator, name: string, value: string) {
  await owner.getByRole('combobox', {name, exact: true}).click();
  await page.getByRole('option', {name: value, exact: true}).click();
}

test('sort: the named field and order expose clickable options', async ({page}) => {
  await source(page, 'Region\tSales\nEast\t10\nNorth\t20');
  await selectRange(page, 'A1', 'B3'); await data(page, 'Sort range');
  const dialog = page.getByRole('dialog', {name: 'Sort range', exact: true});
  await dialog.getByRole('checkbox', {name: 'Data has header row', exact: true}).check();
  await visibleOption(page, dialog, 'Sort by', 'Sales');
  await visibleOption(page, dialog, 'Order', 'Descending');
  await button(dialog, 'Sort').click();
  await expect(cell(page, 'A2')).toContainText('North');
});

test('filter: a condition exposes a clickable option', async ({page}) => {
  await source(page, 'Date\tLabel\n2026-01-01\tearly\n2026-01-03\tlate');
  await selectRange(page, 'A1', 'B3'); await data(page, 'Create filter');
  await button(page, 'Filter Date').click();
  const dialog = page.getByRole('dialog', {name: 'Filter Date', exact: true});
  await visibleOption(page, dialog, 'Condition', 'Before');
  await dialog.getByRole('textbox', {name: 'Value', exact: true}).fill('2026-01-02');
  await button(dialog, 'Apply').click();
  await expect(cell(page, 'A2')).toBeVisible();
  await expect(cell(page, 'A3')).toBeHidden();
});

test('validation: Rule type exposes a clickable option', async ({page}) => {
  await source(page, 'Open\nClosed');
  await selectRange(page, 'A1', 'A2'); await data(page, 'Data validation');
  const dialog = page.getByRole('dialog', {name: 'Data validation', exact: true});
  await visibleOption(page, dialog, 'Rule type', 'Dropdown');
  await dialog.getByRole('textbox', {name: 'Allowed values', exact: true}).fill('Open, Closed');
  await button(dialog, 'Save').click();
  await button(page, 'Open dropdown for A1').click();
  await page.getByRole('option', {name: 'Closed', exact: true}).click();
  await expect(cell(page, 'A1')).toContainText('Closed');
});

test('pivot: the editor and its field options remain usable after creation', async ({page}) => {
  await source(page, 'Region\tSales\tStatus\nEast\t10\tOpen\nNorth\t20\tClosed\nEast\t30\tClosed');
  await selectRange(page, 'A1', 'C4'); await data(page, 'Create pivot table');
  const dialog = page.getByRole('dialog', {name: 'Create pivot table', exact: true});
  await dialog.getByRole('radio', {name: 'New worksheet', exact: true}).check();
  await button(dialog, 'Create').click();
  const editor = page.getByRole('region', {name: 'Pivot table editor', exact: true});
  await expect(editor).toBeVisible();
  // Reproduce the evaluator's first pivot action as recorded in its report.
  await editor.getByLabel(/^(rows)$/i).click();
  await page.getByRole('option', {name: 'Region', exact: true}).click();
  await visibleOption(page, editor, 'Values', 'Sales');
  await visibleOption(page, editor, 'Summarize by', 'SUM');
  await button(editor, 'Apply').click();
  await expect(cell(page, 'B2')).toContainText('40');
  await page.getByRole('tab', {name: 'Sheet1', exact: true}).click();
  await page.getByRole('tab', {name: 'Pivot1', exact: true}).click();
  await expect(button(page, 'Refresh pivot table')).toBeVisible();
});
