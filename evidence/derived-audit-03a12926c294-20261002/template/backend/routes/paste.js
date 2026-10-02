'use strict';
const workbooks = require('../lib/workbookStore');
const {evaluateCells} = require('../lib/formula');
const history = require('../lib/undo');

function colToIndex(name) {
  let col = 0;
  for (const ch of name) col = col * 26 + (ch.charCodeAt(0) - 64);
  return col;
}

function indexToCol(index) {
  let name = '';
  let n = index;
  do {
    name = String.fromCharCode(65 + ((n - 1) % 26)) + name;
    n = Math.floor((n - 1) / 26);
  } while (n > 0);
  return name;
}

// Relative references shift by the target offset; absolute references stay.
function adjustFormula(text, dRow, dCol) {
  if (typeof text !== 'string' || !text.startsWith('=')) return text;
  return text.replace(/(\$?)([A-Z]+)(\$?)([0-9]+)/g, (match, c1, letters, c2, digits) => {
    const col = c1 ? colToIndex(letters) : Math.max(1, colToIndex(letters) + dCol);
    const row = c2 ? Number(digits) : Math.max(1, Number(digits) + dRow);
    return `${c1}${indexToCol(col)}${c2}${row}`;
  });
}

module.exports = (app) => {
  app.post('/api/workbooks/:id/worksheets/:sheetId/paste', (req, res) => {
    const workbook = workbooks.get(req.params.id);
    if (!workbook) return res.status(404).json({error: 'Workbook not found'});
    const sheet = workbook.worksheets.find((s) => s.id === req.params.sheetId);
    if (!sheet) return res.status(404).json({error: 'Worksheet not found'});
    const coordinate = typeof req.body?.coordinate === 'string' ? req.body.coordinate : '';
    const parsed = /^([A-Z]+)([0-9]+)$/.exec(coordinate);
    if (!parsed) return res.status(400).json({error: 'Invalid paste request'});
    const startCol = colToIndex(parsed[1]);
    const startRow = Number(parsed[2]);
    const before = history.capture(sheet);

    const transfer = req.body?.transfer;
    if (transfer !== undefined) {
      const mode = transfer?.mode;
      const source = transfer?.source || {};
      if (!['copy', 'cut'].includes(mode)) {
        return res.status(400).json({error: 'Invalid transfer mode'});
      }
      const bounds = [source.top, source.left, source.bottom, source.right];
      if (!bounds.every((n) => Number.isInteger(n) && n >= 1) ||
          source.top > source.bottom || source.left > source.right) {
        return res.status(400).json({error: 'Invalid transfer source'});
      }
      const dRow = startRow - source.top;
      const dCol = startCol - source.left;
      const sourceCells = sheet.cells || {};
      const grid = [];
      for (let i = source.top; i <= source.bottom; i += 1) {
        const rowValues = [];
        for (let j = source.left; j <= source.right; j += 1) {
          const record = sourceCells[`${indexToCol(j)}${i}`];
          rowValues.push(record
            ? adjustFormula(String(record.original ?? ''), dRow, dCol)
            : '');
        }
        grid.push(rowValues);
      }
      const rules = Array.isArray(sheet.validation_rules) ? sheet.validation_rules : [];
      for (const rule of rules) {
        if (rule.kind !== 'Number range' || !rule.range) continue;
        const range = rule.range;
        for (let i = 0; i < grid.length; i += 1) {
          for (let j = 0; j < grid[i].length; j += 1) {
            const row = startRow + i;
            const col = startCol + j;
            if (row < range.top || row > range.bottom || col < range.left || col > range.right) continue;
            const value = grid[i][j];
            if (value.trim() === '' || value.startsWith('=')) continue;
            const numeric = Number(value);
            if (!Number.isFinite(numeric) || numeric < rule.minimum || numeric > rule.maximum) {
              return res.status(422).json({
                error: `Please enter a number from ${rule.minimum} to ${rule.maximum}`
              });
            }
          }
        }
      }
      const cells = {...sourceCells};
      grid.forEach((rowValues, i) => {
        rowValues.forEach((value, j) => {
          const target = `${indexToCol(startCol + j)}${startRow + i}`;
          if (value === '') delete cells[target];
          else cells[target] = {original: value, displayed: value};
        });
      });
      if (mode === 'cut') {
        const width = Math.max(...grid.map((r) => r.length));
        const targetBottom = startRow + grid.length - 1;
        const targetRight = startCol + width - 1;
        for (let i = source.top; i <= source.bottom; i += 1) {
          for (let j = source.left; j <= source.right; j += 1) {
            // Clear every source cell not itself covered by the target
            // rectangle; covered cells are overwritten by the pasted content.
            const coveredByTarget = i >= startRow && i <= targetBottom &&
              j >= startCol && j <= targetRight;
            if (!coveredByTarget) delete cells[`${indexToCol(j)}${i}`];
          }
        }
      }
      sheet.cells = evaluateCells(cells);
      sheet.selection = {
        current: coordinate,
        rectangle: {
          top: startRow,
          left: startCol,
          bottom: startRow + grid.length - 1,
          right: startCol + Math.max(...grid.map((r) => r.length)) - 1
        }
      };
      history.record(req.params.id, sheet.id, before, sheet);
      workbook.lastUpdated = new Date().toISOString();
      return res.json(workbooks.patch(req.params.id, workbook));
    }

    const text = typeof req.body?.text === 'string' ? req.body.text : null;
    if (text === null) return res.status(400).json({error: 'Invalid paste request'});
    const lines = text.replace(/\r\n?/g, '\n').split('\n');
    if (lines.length && lines[lines.length - 1] === '') lines.pop();
    const grid = lines.map((line) => line.split('\t'));
    const rules = Array.isArray(sheet.validation_rules) ? sheet.validation_rules : [];
    for (const rule of rules) {
      if (rule.kind !== 'Number range' || !rule.range) continue;
      const range = rule.range;
      for (let i = 0; i < grid.length; i += 1) {
        for (let j = 0; j < grid[i].length; j += 1) {
          const row = startRow + i;
          const col = startCol + j;
          if (row < range.top || row > range.bottom || col < range.left || col > range.right) continue;
          const value = grid[i][j];
          if (value.trim() === '') continue;
          const numeric = Number(value);
          if (!Number.isFinite(numeric) || numeric < rule.minimum || numeric > rule.maximum) {
            return res.status(422).json({
              error: `Please enter a number from ${rule.minimum} to ${rule.maximum}`
            });
          }
        }
      }
    }
    const cells = {...(sheet.cells || {})};
    grid.forEach((rowValues, i) => {
      rowValues.forEach((value, j) => {
        const target = `${indexToCol(startCol + j)}${startRow + i}`;
        if (value === '') delete cells[target];
        else cells[target] = {original: value, displayed: value};
      });
    });
    sheet.cells = evaluateCells(cells);
    sheet.selection = {
      current: coordinate,
      rectangle: {
        top: startRow,
        left: startCol,
        bottom: startRow + grid.length - 1,
        right: startCol + Math.max(...grid.map((r) => r.length)) - 1
      }
    };
    history.record(req.params.id, sheet.id, before, sheet);
    workbook.lastUpdated = new Date().toISOString();
    res.json(workbooks.patch(req.params.id, workbook));
  });
};
