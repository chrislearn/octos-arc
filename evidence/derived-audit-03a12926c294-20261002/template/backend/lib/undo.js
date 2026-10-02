'use strict';
// Session-scoped undo/redo history per workbook, kept in memory. Each entry
// stores complete before/after worksheet state (values, formulas, rule ranges,
// filters, pivot configuration/results) so undo/redo restores whole operations.
const store = require('./store');
const workbooks = require('./workbookStore');

const stacks = new Map();
store.onReset(() => stacks.clear());

function capture(sheet) {
  return JSON.stringify({
    cells: sheet.cells ?? {},
    validation_rules: sheet.validation_rules ?? [],
    filter_views: sheet.filter_views ?? [],
    pivot_state: sheet.pivot_state ?? null
  });
}

function stackFor(workbookId) {
  let stack = stacks.get(workbookId);
  if (!stack) {
    stack = {undo: [], redo: []};
    stacks.set(workbookId, stack);
  }
  return stack;
}

// Record one successful modification: push onto undo, discard redo branch.
function record(workbookId, sheetId, before, afterSheet) {
  const stack = stackFor(workbookId);
  stack.undo.push({sheetId, before, after: capture(afterSheet)});
  if (stack.undo.length > 200) stack.undo.shift();
  stack.redo = [];
}

function status(workbookId) {
  const stack = stacks.get(workbookId);
  return {
    canUndo: !!stack && stack.undo.length > 0,
    canRedo: !!stack && stack.redo.length > 0
  };
}

function apply(workbookId, direction) {
  const stack = stacks.get(workbookId);
  if (!stack) return null;
  const entry = direction === 'undo' ? stack.undo.pop() : stack.redo.pop();
  if (!entry) return null;
  let result = null;
  workbooks.transact((items) => {
    const workbook = items.find((w) => String(w.id) === String(workbookId));
    if (!workbook) throw new Error('workbook not found');
    const sheet = workbook.worksheets.find((s) => s.id === entry.sheetId);
    if (!sheet) throw new Error('worksheet not found');
    const current = capture(sheet);
    const state = JSON.parse(direction === 'undo' ? entry.before : entry.after);
    sheet.cells = state.cells;
    sheet.validation_rules = state.validation_rules;
    sheet.filter_views = state.filter_views;
    sheet.pivot_state = state.pivot_state;
    if (direction === 'undo') {
      stack.redo.push({sheetId: entry.sheetId, before: entry.before, after: current});
    } else {
      stack.undo.push({sheetId: entry.sheetId, before: current, after: entry.after});
    }
    result = workbook;
  });
  return {workbook: result, ...status(workbookId)};
}

module.exports = {capture, record, status, apply};
