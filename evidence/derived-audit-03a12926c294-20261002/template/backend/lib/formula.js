'use strict';
// Formula evaluation for one worksheet: ordinary text passes through, '='
// expressions are computed from same-worksheet references with transitive
// dependency resolution. Supports numeric constants, parentheses, + - * /,
// A1 references and case-insensitive SUM/AVERAGE/COUNT/MIN/MAX over
// contiguous ranges. Aggregates ignore blanks and text; COUNT counts only
// numeric cells. Stable errors: #DIV/0!, #REF!, #NAME?, #ERROR!.
const REF = /([A-Z]{1,3})([0-9]+)/g;
const FUNC_RANGE = /\b([A-Za-z][A-Za-z0-9.]*)\s*\(\s*([A-Za-z]{1,3}[0-9]+)\s*:\s*([A-Za-z]{1,3}[0-9]+)\s*\)/g;
const AGGREGATES = new Set(['SUM', 'AVERAGE', 'COUNT', 'MIN', 'MAX']);

function formatNumber(value) {
  return String(Math.round(value * 1e10) / 1e10);
}

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

function isErrorMessage(value) {
  return typeof value === 'string' && value.startsWith('#');
}

function evaluateCells(cells) {
  const out = {};
  for (const [coordinate, record] of Object.entries(cells || {})) {
    out[coordinate] = { ...record };
  }
  const memo = new Map();
  const visiting = new Set();

  // Numeric value of an ordinary cell for aggregation: null for blank, text
  // or formula cells (aggregates skip them rather than treating them as 0).
  function rawNumeric(ref) {
    const record = cells[ref];
    if (!record) return null;
    const text = String(record.original ?? '').trim();
    if (text === '') return null;
    const numeric = Number(text);
    return Number.isFinite(numeric) ? numeric : null;
  }

  function cellValue(ref) {
    if (memo.has(ref)) return memo.get(ref);
    const record = cells[ref];
    if (!record) { memo.set(ref, 0); return 0; }
    const original = String(record.original ?? '');
    if (!original.startsWith('=')) {
      const text = original.trim();
      const numeric = text === '' ? 0 : Number(text);
      const value = Number.isFinite(numeric) ? numeric : NaN;
      memo.set(ref, value);
      return value;
    }
    if (visiting.has(ref)) { memo.set(ref, '#REF!'); return '#REF!'; }
    visiting.add(ref);
    const value = evalExpression(original.slice(1));
    visiting.delete(ref);
    memo.set(ref, value);
    return value;
  }

  function aggregate(name, from, to) {
    const a = /^([A-Z]+)([0-9]+)$/.exec(from);
    const b = /^([A-Z]+)([0-9]+)$/.exec(to);
    if (!a || !b) return '#ERROR!';
    const c1 = colToIndex(a[1]);
    const c2 = colToIndex(b[1]);
    const r1 = Number(a[2]);
    const r2 = Number(b[2]);
    if (c1 > c2 || r1 > r2) return '#ERROR!';
    const numbers = [];
    for (let row = r1; row <= r2; row += 1) {
      for (let col = c1; col <= c2; col += 1) {
        const numeric = rawNumeric(`${indexToCol(col)}${row}`);
        if (numeric !== null) numbers.push(numeric);
      }
    }
    switch (name) {
      case 'SUM': return numbers.reduce((x, y) => x + y, 0);
      case 'COUNT': return numbers.length;
      case 'AVERAGE':
        return numbers.length
          ? numbers.reduce((x, y) => x + y, 0) / numbers.length
          : '#DIV/0!';
      case 'MIN': return numbers.length ? Math.min(...numbers) : NaN;
      case 'MAX': return numbers.length ? Math.max(...numbers) : NaN;
      default: return '#NAME?';
    }
  }

  function dividesByZero(expression) {
    return /\/\s*(?:\(\s*)?0(?:\.0*)?\s*\)?(?![.\d])/.test(expression);
  }

  // Returns a number for successful formulas or a stable '#...' error string.
  function evalExpression(expression) {
    try {
      if (/#REF!/.test(expression)) return '#REF!';
      let replaced = expression.replace(FUNC_RANGE, (match, fname, from, to) => {
        const upper = fname.toUpperCase();
        if (!AGGREGATES.has(upper)) throw { name: '#NAME?' };
        const value = aggregate(upper, from, to);
        if (isErrorMessage(value)) throw { name: value };
        if (!Number.isFinite(value)) throw { name: '#ERROR!' };
        return `(${formatNumber(value)})`;
      });
      if (/[A-Za-z][A-Za-z0-9.]*\s*\(/.test(replaced)) return '#NAME?';
      replaced = replaced.replace(REF, (match, letters, digits) => {
        const value = cellValue(`${letters}${digits}`);
        if (isErrorMessage(value)) throw { name: value };
        if (!Number.isFinite(value)) throw { name: '#ERROR!' };
        return `(${formatNumber(value)})`;
      });
      let result;
      try {
        result = Function(`"use strict";return (${replaced});`)();
      } catch {
        return '#ERROR!';
      }
      if (typeof result !== 'number') return '#ERROR!';
      if (Number.isFinite(result)) return result;
      if (dividesByZero(replaced)) return '#DIV/0!';
      return '#ERROR!';
    } catch (error) {
      return isErrorMessage(error?.name) ? error.name : '#ERROR!';
    }
  }

  for (const [coordinate, record] of Object.entries(out)) {
    const original = String(record.original ?? '');
    if (original.startsWith('=')) {
      const value = cellValue(coordinate);
      record.displayed = isErrorMessage(value)
        ? value
        : (Number.isFinite(value) ? formatNumber(value) : '#ERROR!');
    } else {
      record.displayed = original;
    }
  }
  return out;
}

module.exports = { evaluateCells };
