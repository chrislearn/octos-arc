'use strict';
const workbooks = require('../lib/workbookStore');
const {parseCsv} = require('../lib/csv');
const {HttpError} = require('../lib/errors');
const {evaluateCells} = require('../lib/formula');
const history = require('../lib/undo');

function importCsv(req, res) {
  const content = typeof req.body?.csv === 'string' ? req.body.csv : null;
  if (content === null) throw new HttpError(400, 'Invalid CSV file format. Import failed.');
  let rows;
  try {
    rows = parseCsv(content);
  } catch (error) {
    throw new HttpError(400, error.message || 'Invalid CSV file format. Import failed.');
  }
  const rawName = typeof req.body?.name === 'string' ? req.body.name : '';
  const name = rawName.replace(/\.csv$/i, '').trim();
  if (!name) throw new HttpError(400, 'Workbook name is required');
  const cells = {};
  rows.forEach((row, rowIndex) => {
    row.forEach((value, colIndex) => {
      if (value === '') return;
      cells[`${colIndexToName(colIndex)}${rowIndex + 1}`] = {original: value, displayed: value};
    });
  });
  const workbook = workbooks.create({
    name,
    lastUpdated: new Date().toISOString(),
    worksheets: [{
      id: `sheet-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: 'Sheet1',
      cells,
      selection: {current: 'A1', rectangle: {top: 1, left: 1, bottom: 1, right: 1}}
    }]
  });
  res.status(201).json(workbook);
}

function colIndexToName(index) {
  let name = '';
  let n = index;
  do {
    name = String.fromCharCode(65 + (n % 26)) + name;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return name;
}

function csvEscape(value) {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function exportWorksheet(req, res) {
  const workbook = workbooks.get(req.params.id);
  if (!workbook) return res.status(404).json({error: 'Workbook not found'});
  const sheet = workbook.worksheets.find((s) => s.id === req.params.sheetId);
  if (!sheet) return res.status(404).json({error: 'Worksheet not found'});
  const cells = sheet.cells || {};
  let maxRow = 0;
  let maxCol = 0;
  for (const coordinate of Object.keys(cells)) {
    const parsed = /^([A-Z]+)([0-9]+)$/.exec(coordinate);
    if (!parsed) continue;
    let col = 0;
    for (const ch of parsed[1]) col = col * 26 + (ch.charCodeAt(0) - 64);
    maxRow = Math.max(maxRow, Number(parsed[2]));
    maxCol = Math.max(maxCol, col);
  }
  const lines = [];
  for (let row = 1; row <= maxRow; row += 1) {
    const fields = [];
    for (let col = 1; col <= maxCol; col += 1) {
      let name = '';
      let n = col;
      do {
        name = String.fromCharCode(65 + ((n - 1) % 26)) + name;
        n = Math.floor((n - 1) / 26);
      } while (n > 0);
      const record = cells[`${name}${row}`];
      fields.push(csvEscape(record ? String(record.displayed ?? '') : ''));
    }
    lines.push(fields.join(','));
  }
  const body = `\uFEFF${lines.join('\r\n')}`;
  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition',
    `attachment; filename="${(sheet.name || 'worksheet').replace(/[^A-Za-z0-9_-]+/g, '_')}.csv"`);
  res.send(body);
}

function colNameToIndex(name) {
  let col = 0;
  for (const ch of name) col = col * 26 + (ch.charCodeAt(0) - 64);
  return col;
}

function indexToColName(index) {
  let name = '';
  let n = index;
  do {
    name = String.fromCharCode(65 + ((n - 1) % 26)) + name;
    n = Math.floor((n - 1) / 26);
  } while (n > 0);
  return name;
}

function adjustFormulaColumns(text, target, mode) {
  if (typeof text !== 'string' || !text.startsWith('=')) return text;
  return text.replace(/(\$?)([A-Z]+)(\$?)([0-9]+)/g, (match, c1, letters, c2, digits) => {
    const col = colNameToIndex(letters);
    if (mode === 'delete') {
      if (col === target) return '#REF!';
      return col > target ? c1 + indexToColName(col - 1) + c2 + digits : match;
    }
    if (mode === 'insert-right') {
      return col > target ? c1 + indexToColName(col + 1) + c2 + digits : match;
    }
    return col >= target ? c1 + indexToColName(col + 1) + c2 + digits : match;
  });
}

function shiftColumns(sheet, target, mode) {
  const cells = sheet.cells || {};
  const shifted = {};
  for (const [coordinate, record] of Object.entries(cells)) {
    const parsed = /^([A-Z]+)([0-9]+)$/.exec(coordinate);
    if (!parsed) { shifted[coordinate] = record; continue; }
    const col = colNameToIndex(parsed[1]);
    if (mode === 'delete' && col === target) continue;
    const next = (mode === 'delete')
      ? (col > target ? col - 1 : col)
      : (mode === 'insert-right')
        ? (col > target ? col + 1 : col)
        : (col >= target ? col + 1 : col);
    const adjusted = {...record};
    adjusted.original = adjustFormulaColumns(record.original, target, mode);
    adjusted.displayed = adjustFormulaColumns(record.displayed, target, mode);
    shifted[`${indexToColName(next)}${parsed[2]}`] = adjusted;
  }
  sheet.cells = shifted;
  const moveRange = (range) => {
    if (!range) return range;
    const adjust = (col) => {
      if (mode === 'delete') {
        if (col === target) return null;
        return col > target ? col - 1 : col;
      }
      if (mode === 'insert-right') return col > target ? col + 1 : col;
      return col >= target ? col + 1 : col;
    };
    const left = adjust(range.left);
    const right = adjust(range.right);
    if (left === null || right === null) return null;
    return {...range, left, right};
  };
  if (Array.isArray(sheet.validation_rules)) {
    sheet.validation_rules = sheet.validation_rules
      .map((rule) => ({...rule, range: moveRange(rule.range)}))
      .filter((rule) => rule.range !== null);
  }
  if (Array.isArray(sheet.filter_views)) {
    sheet.filter_views = sheet.filter_views.map((view) => ({
      ...view, source_range: moveRange(view.source_range) || view.source_range
    }));
  }
  if (sheet.pivot_state && sheet.pivot_state.source_range) {
    sheet.pivot_state = {
      ...sheet.pivot_state,
      source_range: moveRange(sheet.pivot_state.source_range) || sheet.pivot_state.source_range
    };
  }
}

function shiftRows(sheet, target, mode) {
  const cells = sheet.cells || {};
  const shifted = {};
  for (const [coordinate, record] of Object.entries(cells)) {
    const parsed = /^([A-Z]+)([0-9]+)$/.exec(coordinate);
    if (!parsed) { shifted[coordinate] = record; continue; }
    const row = Number(parsed[2]);
    if (mode === 'delete' && row === target) continue;
    const next = (mode === 'delete')
      ? (row > target ? row - 1 : row)
      : (mode === 'insert-below')
        ? (row > target ? row + 1 : row)
        : (row >= target ? row + 1 : row);
    shifted[`${parsed[1]}${next}`] = record;
  }
  sheet.cells = shifted;
  const moveRange = (range) => {
    if (!range) return range;
    const adjust = (row) => {
      if (mode === 'delete') {
        if (row === target) return null;
        return row > target ? row - 1 : row;
      }
      if (mode === 'insert-below') return row > target ? row + 1 : row;
      return row >= target ? row + 1 : row;
    };
    const top = adjust(range.top);
    const bottom = adjust(range.bottom);
    if (top === null || bottom === null) return null;
    return {...range, top, bottom};
  };
  if (Array.isArray(sheet.validation_rules)) {
    sheet.validation_rules = sheet.validation_rules
      .map((rule) => ({...rule, range: moveRange(rule.range)}))
      .filter((rule) => rule.range !== null);
  }
  if (Array.isArray(sheet.filter_views)) {
    sheet.filter_views = sheet.filter_views.map((view) => ({
      ...view, source_range: moveRange(view.source_range) || view.source_range
    }));
  }
  if (sheet.pivot_state && sheet.pivot_state.source_range) {
    sheet.pivot_state = {
      ...sheet.pivot_state,
      source_range: moveRange(sheet.pivot_state.source_range) || sheet.pivot_state.source_range
    };
  }
}

module.exports = (app) => {
  app.post('/api/workbooks/:id/worksheets/:sheetId/rows', (req, res) => {
    const workbook = workbooks.get(req.params.id);
    if (!workbook) return res.status(404).json({error: 'Workbook not found'});
    const sheet = workbook.worksheets.find((s) => s.id === req.params.sheetId);
    if (!sheet) return res.status(404).json({error: 'Worksheet not found'});
    const mode = req.body?.mode;
    const row = Number(req.body?.row);
    if (!['insert-above', 'insert-below', 'delete'].includes(mode) ||
        !Number.isInteger(row) || row < 1) {
      return res.status(400).json({error: 'Invalid row operation'});
    }
    if (mode === 'delete' && row === 1) {
      return res.status(400).json({error: 'Cannot delete row 1'});
    }
    const before = history.capture(sheet);
    shiftRows(sheet, row, mode);
    sheet.cells = evaluateCells(sheet.cells || {});
    history.record(req.params.id, sheet.id, before, sheet);
    workbook.lastUpdated = new Date().toISOString();
    res.json(workbooks.patch(req.params.id, workbook));
  });

  app.post('/api/workbooks/:id/worksheets/:sheetId/columns', (req, res) => {
    const workbook = workbooks.get(req.params.id);
    if (!workbook) return res.status(404).json({error: 'Workbook not found'});
    const sheet = workbook.worksheets.find((s) => s.id === req.params.sheetId);
    if (!sheet) return res.status(404).json({error: 'Worksheet not found'});
    const mode = req.body?.mode;
    const column = typeof req.body?.column === 'string' ? req.body.column : '';
    if (!['insert-left', 'insert-right', 'delete'].includes(mode) ||
        !/^[A-Z]+$/.test(column)) {
      return res.status(400).json({error: 'Invalid column operation'});
    }
    const target = colNameToIndex(column);
    if (mode === 'delete' && target === 1) {
      return res.status(400).json({error: 'Cannot delete column A'});
    }
    const before = history.capture(sheet);
    shiftColumns(sheet, target, mode);
    sheet.cells = evaluateCells(sheet.cells || {});
    history.record(req.params.id, sheet.id, before, sheet);
    workbook.lastUpdated = new Date().toISOString();
    res.json(workbooks.patch(req.params.id, workbook));
  });

  app.get('/api/workbooks', (req, res) => {
    res.json(workbooks.list());
  });

  app.get('/api/workbooks/:id', (req, res) => {
    const workbook = workbooks.get(req.params.id);
    if (!workbook) return res.status(404).json({error: 'Workbook not found'});
    res.json(workbook);
  });

  app.post('/api/workbooks/:id/worksheets', (req, res) => {
    const workbook = workbooks.get(req.params.id);
    if (!workbook) return res.status(404).json({error: 'Workbook not found'});
    const used = new Set(workbook.worksheets.map((s) => s.name));
    let n = 1;
    while (used.has(`Sheet${n}`)) n += 1;
    const sheet = {
      id: `sheet-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: `Sheet${n}`,
      cells: {},
      selection: {current: 'A1', rectangle: {top: 1, left: 1, bottom: 1, right: 1}}
    };
    workbook.worksheets.push(sheet);
    workbook.lastActiveSheetId = sheet.id;
    workbook.lastUpdated = new Date().toISOString();
    res.status(201).json(workbooks.patch(req.params.id, workbook));
  });

  app.patch('/api/workbooks/:id/worksheets/:sheetId', (req, res) => {
    const workbook = workbooks.get(req.params.id);
    if (!workbook) return res.status(404).json({error: 'Workbook not found'});
    const sheet = workbook.worksheets.find((s) => s.id === req.params.sheetId);
    if (!sheet) return res.status(404).json({error: 'Worksheet not found'});
    const name = typeof req.body?.name === 'string' ? req.body.name.trim() : '';
    if (!name) return res.status(400).json({error: 'Worksheet name cannot be empty'});
    if (workbook.worksheets.some((s) => s.id !== sheet.id && s.name === name)) {
      return res.status(409).json({error: 'Worksheet name already exists'});
    }
    sheet.name = name;
    workbook.lastUpdated = new Date().toISOString();
    res.json(workbooks.patch(req.params.id, workbook));
  });

  app.get('/api/workbooks/:id/worksheets/:sheetId/export.csv', exportWorksheet);

  app.patch('/api/workbooks/:id', (req, res) => {
    const workbook = workbooks.get(req.params.id);
    if (!workbook) return res.status(404).json({error: 'Workbook not found'});
    if (req.body && req.body.activeSheetId !== undefined) {
      const sheet = workbook.worksheets.find((s) => s.id === req.body.activeSheetId);
      if (!sheet) return res.status(404).json({error: 'Worksheet not found'});
      workbook.lastActiveSheetId = sheet.id;
      return res.json(workbooks.patch(req.params.id, workbook));
    }
    if (req.body && req.body.selection !== undefined) {
      const {sheetId, rectangle, current} = req.body.selection || {};
      const sheet = workbook.worksheets.find((s) => s.id === sheetId);
      if (!sheet) return res.status(404).json({error: 'Worksheet not found'});
      const r = rectangle || {};
      const values = [r.top, r.left, r.bottom, r.right];
      if (!values.every((n) => Number.isInteger(n) && n >= 1) ||
          r.top > r.bottom || r.left > r.right) {
        return res.status(400).json({error: 'Invalid selection'});
      }
      if (typeof current !== 'string' || !/^([A-Z]+)([0-9]+)$/.test(current)) {
        return res.status(400).json({error: 'Invalid cell coordinate'});
      }
      sheet.selection = {
        current,
        rectangle: {top: r.top, left: r.left, bottom: r.bottom, right: r.right}
      };
      return res.json(workbooks.patch(req.params.id, workbook));
    }
    if (req.body && req.body.cell !== undefined) {
      const {sheetId, coordinate, value} = req.body.cell;
      const sheet = workbook.worksheets.find((s) => s.id === sheetId);
      if (!sheet) return res.status(404).json({error: 'Worksheet not found'});
      if (typeof coordinate !== 'string' || !/^([A-Z]+)([0-9]+)$/.test(coordinate)) {
        return res.status(400).json({error: 'Invalid cell coordinate'});
      }
      if (typeof value !== 'string') return res.status(400).json({error: 'Invalid cell value'});
      const beforeCellState = history.capture(sheet);
      sheet.cells = sheet.cells || {};
      if (value === '') delete sheet.cells[coordinate];
      else sheet.cells[coordinate] = {original: value, displayed: value};
      sheet.cells = evaluateCells(sheet.cells);
      history.record(req.params.id, sheet.id, beforeCellState, sheet);
      workbook.lastUpdated = new Date().toISOString();
      const updated = workbooks.patch(req.params.id, workbook);
      return res.json(updated);
    }
    const name = typeof req.body?.name === 'string' ? req.body.name.trim() : '';
    if (!name) return res.status(400).json({error: 'Workbook name cannot be empty'});
    const updated = workbooks.patch(req.params.id, {name, lastUpdated: new Date().toISOString()});
    res.json(updated);
  });

  app.post('/api/workbooks/import', importCsv);

  app.post('/api/workbooks', (req, res) => {
    const name = typeof req.body?.name === 'string' ? req.body.name.trim() : '';
    if (!name) return res.status(400).json({error: 'Workbook name is required'});
    const workbook = workbooks.createBlank(name);
    res.status(201).json(workbook);
  });
};
