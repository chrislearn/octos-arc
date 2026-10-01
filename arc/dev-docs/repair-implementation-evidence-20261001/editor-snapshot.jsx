import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router';
import { Dialog, DropdownMenu } from 'radix-ui';
import { requestJson } from '../shared/request.js';
import WorksheetGrid from '../components/WorksheetGrid.jsx';
import { DialogSurface } from '../shared/interactions.jsx';

function formatLastUpdated(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString();
}

function colLetter(index) {
  let result = '';
  let n = index;
  while (n >= 0) {
    result = String.fromCharCode(65 + (n % 26)) + result;
    n = Math.floor(n / 26) - 1;
  }
  return result;
}

function cellCoord(colIndex, rowIndex) {
  return colLetter(colIndex) + (rowIndex + 1);
}

function parseCoord(c) {
  const match = c.match(/^([A-Z]+)(\d+)$/);
  if (!match) return null;
  const colStr = match[1];
  const row = parseInt(match[2], 10);
  let col = 0;
  for (let i = 0; i < colStr.length; i++) {
    col = col * 26 + (colStr.charCodeAt(i) - 64);
  }
  return { col: col - 1, row: row - 1 };
}

function escapeCSV(value) {
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return '"' + str.replace(/"/g, '""') + '"';
  }
  return str;
}

function generateCSV(worksheet) {
  const cells = worksheet.cells || {};
  
  let minRow = Infinity, maxRow = -1, minCol = Infinity, maxCol = -1;
  
  for (const coord of Object.keys(cells)) {
    const parsed = parseCoord(coord);
    if (!parsed) continue;
    minRow = Math.min(minRow, parsed.row);
    maxRow = Math.max(maxRow, parsed.row);
    minCol = Math.min(minCol, parsed.col);
    maxCol = Math.max(maxCol, parsed.col);
  }
  
  if (maxRow === -1) return '';
  
  const rows = [];
  for (let r = minRow; r <= maxRow; r++) {
    const row = [];
    for (let c = minCol; c <= maxCol; c++) {
      const coord = cellCoord(c, r);
      const cell = cells[coord];
      const value = cell?.displayedValue || '';
      row.push(escapeCSV(value));
    }
    rows.push(row.join(','));
  }
  
  return rows.join('\r\n');
}

function downloadCSV(filename, content) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export default function Editor() {
  const { id } = useParams();
  const [workbook, setWorkbook] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameName, setRenameName] = useState('');
  const [renameError, setRenameError] = useState(null);
  const [renamePending, setRenamePending] = useState(false);
  const [renameSheetId, setRenameSheetId] = useState(null);
  const [selection, setSelection] = useState(null);
  const [formulaBarValue, setFormulaBarValue] = useState('');
  const [formulaBarDraft, setFormulaBarDraft] = useState(null);
  const [formulaBarOriginCell, setFormulaBarOriginCell] = useState(null);
  const [pendingTransfer, setPendingTransfer] = useState(null);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [dataMenuOpen, setDataMenuOpen] = useState(false);
  const [validationDialogOpen, setValidationDialogOpen] = useState(false);
  const [validationRuleType, setValidationRuleType] = useState('Dropdown');
  const [validationAllowedValues, setValidationAllowedValues] = useState('');
  const [validationMinimum, setValidationMinimum] = useState('');
  const [validationMaximum, setValidationMaximum] = useState('');
  const [validationError, setValidationError] = useState(null);
  const [cellEditError, setCellEditError] = useState(null);
  const [validationPending, setValidationPending] = useState(false);
  const [editingRuleIndex, setEditingRuleIndex] = useState(null);
  const [filterDialogOpen, setFilterDialogOpen] = useState(null);
  const [filterCriteria, setFilterCriteria] = useState({});
  const [sortDialogOpen, setSortDialogOpen] = useState(false);
  const [sortBy, setSortBy] = useState('');
  const [sortOrder, setSortOrder] = useState('Ascending');
  const [hasHeaderRow, setHasHeaderRow] = useState(true);
  const [sortError, setSortError] = useState(null);
  const [sortPending, setSortPending] = useState(false);
  const [pivotDialogOpen, setPivotDialogOpen] = useState(false);
  const [pivotSourceRange, setPivotSourceRange] = useState(null);
  const [pivotRowField, setPivotRowField] = useState('');
  const [pivotColumnField, setPivotColumnField] = useState('');
  const [pivotValueField, setPivotValueField] = useState('');
  const [pivotSummarizeBy, setPivotSummarizeBy] = useState('SUM');
  const [pivotError, setPivotError] = useState(null);
  const [pivotPending, setPivotPending] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteSheetId, setDeleteSheetId] = useState(null);
  const [deleteSheetName, setDeleteSheetName] = useState('');
  const [deleteError, setDeleteError] = useState(null);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState(null);

  useEffect(() => {
    requestJson(`/api/workbooks/${id}`).then(data => {
      setWorkbook(data);
      const sheet = data.worksheets.find(ws => ws.id === data.lastActiveWorksheet) || data.worksheets[0];
      const sel = sheet?.selection || { currentCell: 'A1', rectangle: { start: 'A1', end: 'A1' } };
      setSelection(sel);
      const cellContent = sheet?.cells?.[sel.currentCell]?.originalContent || '';
      setFormulaBarValue(cellContent);
      setFormulaBarDraft(null);
      
      // Initialize pivot editor state if starting on a pivot result sheet
      if (sheet?.pivotState?.isPivotResult) {
        setPivotRowField(sheet.pivotState.rowField || '');
        setPivotColumnField(sheet.pivotState.columnField || '');
        setPivotValueField(sheet.pivotState.valueField || '');
        setPivotSummarizeBy(sheet.pivotState.summarizeBy || 'SUM');
      }
      
      setLoading(false);
      updateUndoRedoState();
    }).catch(err => {
      setError(err.message || 'Failed to load');
      setLoading(false);
    });
  }, [id]);

  const updateUndoRedoState = async () => {
    try {
      const [undoRes, redoRes] = await Promise.all([
        requestJson(`/api/workbooks/${id}/undo`),
        requestJson(`/api/workbooks/${id}/redo`)
      ]);
      setCanUndo(undoRes.canUndo);
      setCanRedo(redoRes.canRedo);
    } catch (err) {
      // Ignore errors
    }
  };

  useEffect(() => {
    if (workbook && selection && formulaBarDraft === null) {
      const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
      const cellContent = activeSheet?.cells?.[selection.currentCell]?.originalContent || '';
      setFormulaBarValue(cellContent);
    }
  }, [workbook, selection, formulaBarDraft]);

  const openRename = () => {
    if (workbook) {
      setRenameName(workbook.name);
      setRenameError(null);
      setRenameSheetId(null);
      setRenameOpen(true);
    }
  };

  const handleRenameSave = async () => {
    const trimmed = renameName.trim();
    if (!trimmed) {
      setRenameError('Workbook name cannot be empty');
      return;
    }
    setRenamePending(true);
    setRenameError(null);
    try {
      const updated = await requestJson(`/api/workbooks/${id}`, {
        method: 'PATCH',
        body: { name: trimmed }
      });
      setWorkbook(updated);
      setRenameOpen(false);
      await updateUndoRedoState();
    } catch (err) {
      setRenameError(err.message || 'Failed to save');
    } finally {
      setRenamePending(false);
    }
  };

  const openRenameWorksheet = (sheetId, currentName) => {
    setRenameSheetId(sheetId);
    setRenameName(currentName);
    setRenameError(null);
    setRenameOpen(true);
  };

  const handleRenameWorksheetSave = async () => {
    const trimmed = renameName.trim();
    if (!trimmed) {
      setRenameError('Worksheet name cannot be empty');
      return;
    }
    setRenamePending(true);
    setRenameError(null);
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${renameSheetId}`, {
        method: 'PATCH',
        body: { name: trimmed }
      });
      setWorkbook(updated);
      setRenameOpen(false);
      await updateUndoRedoState();
    } catch (err) {
      setRenameError(err.message || 'Failed to save');
    } finally {
      setRenamePending(false);
    }
  };

  const handleExportCSV = () => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    const csvContent = generateCSV(activeSheet);
    const filename = `${workbook.name}.csv`;
    downloadCSV(filename, csvContent);
  };

  const handleCreateFilter = async () => {
    if (!workbook || !selection) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/filters`, {
        method: 'POST',
        body: { sourceRange: selection.rectangle }
      });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to create filter');
    }
  };

  const handleClearFilter = async () => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet || !activeSheet.filterViews?.length) return;
    
    try {
      const filterId = activeSheet.filterViews[0].id;
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/filters/${filterId}`, {
        method: 'DELETE'
      });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to clear filter');
    }
  };

  const handleValidationSave = async () => {
    if (!workbook || !selection) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    setValidationPending(true);
    setValidationError(null);
    
    try {
      const ruleData = {
        range: selection.rectangle,
        kind: validationRuleType
      };
      
      if (validationRuleType === 'Dropdown') {
        ruleData.allowedValues = validationAllowedValues;
      } else if (validationRuleType === 'Number range') {
        ruleData.minimum = parseFloat(validationMinimum);
        ruleData.maximum = parseFloat(validationMaximum);
        if (isNaN(ruleData.minimum) || isNaN(ruleData.maximum)) {
          setValidationError('Please enter valid numbers for minimum and maximum');
          setValidationPending(false);
          return;
        }
      }
      
      let updated;
      if (editingRuleIndex !== null) {
        updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/validation-rules/${editingRuleIndex}`, {
          method: 'PATCH',
          body: ruleData
        });
      } else {
        updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/validation-rules`, {
          method: 'POST',
          body: ruleData
        });
      }
      
      setWorkbook(updated);
      setValidationDialogOpen(false);
      await updateUndoRedoState();
    } catch (err) {
      setValidationError(err.message || 'Failed to save validation rule');
    } finally {
      setValidationPending(false);
    }
  };

  const handleValidationDelete = async () => {
    if (!workbook || editingRuleIndex === null) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    setValidationPending(true);
    setValidationError(null);
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/validation-rules/${editingRuleIndex}`, {
        method: 'DELETE'
      });
      setWorkbook(updated);
      setValidationDialogOpen(false);
      await updateUndoRedoState();
    } catch (err) {
      setValidationError(err.message || 'Failed to delete validation rule');
    } finally {
      setValidationPending(false);
    }
  };

  const openValidationDialog = () => {
    if (!workbook || !selection) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    // Check if there's an existing rule for this range
    const validationRules = activeSheet.validationRules || [];
    const existingRule = validationRules.find(rule => {
      if (!rule.range) return false;
      return rule.range.start === selection.rectangle.start && rule.range.end === selection.rectangle.end;
    });
    
    if (existingRule) {
      const ruleIndex = validationRules.indexOf(existingRule);
      setEditingRuleIndex(ruleIndex);
      setValidationRuleType(existingRule.kind);
      if (existingRule.kind === 'Dropdown') {
        setValidationAllowedValues(existingRule.allowedValues || '');
      } else if (existingRule.kind === 'Number range') {
        setValidationMinimum(existingRule.minimum?.toString() || '');
        setValidationMaximum(existingRule.maximum?.toString() || '');
      }
    } else {
      setEditingRuleIndex(null);
      setValidationRuleType('Dropdown');
      setValidationAllowedValues('');
      setValidationMinimum('');
      setValidationMaximum('');
    }
    
    setValidationError(null);
    setValidationDialogOpen(true);
  };

  const handleFilterApply = async (filterId, headerText, criteria) => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    // Convert header text to column letter
    const filter = activeSheet.filterViews?.[0];
    if (!filter) return;
    
    const start = parseCoord(filter.sourceRange.start);
    const end = parseCoord(filter.sourceRange.end);
    if (!start || !end) return;
    
    let colLetter = null;
    for (let c = start.col; c <= end.col; c++) {
      const coord = cellCoord(c, start.row);
      if (activeSheet.cells[coord]?.displayedValue === headerText) {
        colLetter = cellCoord(c, 0).replace(/\d+/, ''); // Get just the letter part
        break;
      }
    }
    
    if (!colLetter) return;
    
    // Convert criteria format to match backend expectations
    let backendCriteria;
    if (criteria.condition) {
      // Condition filter
      backendCriteria = {
        type: 'condition',
        condition: criteria.condition,
        value: criteria.value || ''
      };
    } else {
      // Value filter
      backendCriteria = {
        type: 'values',
        values: criteria.selectedValues || []
      };
    }
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/filters/${filterId}`, {
        method: 'PATCH',
        body: { criteria: { [colLetter]: backendCriteria } }
      });
      setWorkbook(updated);
      setFilterDialogOpen(null);
      setFilterCriteria({});
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to apply filter');
    }
  };

  const openFilterDialog = (headerText) => {
    setFilterDialogOpen(headerText);
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    const filter = activeSheet?.filterViews?.[0];
    setFilterCriteria(filter?.criteria?.[headerText] || {});
  };

  const openSortDialog = () => {
    if (!workbook || !selection) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    // Get headers from the selected range
    const start = parseCoord(selection.rectangle.start);
    const end = parseCoord(selection.rectangle.end);
    if (!start || !end) return;
    
    const headers = [];
    for (let c = start.col; c <= end.col; c++) {
      const coord = cellCoord(c, start.row);
      const headerText = activeSheet.cells[coord]?.displayedValue || '';
      headers.push(headerText || cellCoord(c, 0).replace(/\d+/, ''));
    }
    
    setSortBy(headers[0] || '');
    setSortOrder('Ascending');
    setHasHeaderRow(true);
    setSortError(null);
    setSortDialogOpen(true);
  };

  const handleSort = async () => {
    if (!workbook || !selection) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    setSortPending(true);
    setSortError(null);
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/sort`, {
        method: 'POST',
        body: {
          range: selection.rectangle,
          sortBy,
          order: sortOrder,
          hasHeaderRow
        }
      });
      setWorkbook(updated);
      setSortDialogOpen(false);
      await updateUndoRedoState();
    } catch (err) {
      setSortError(err.message || 'Failed to sort');
    } finally {
      setSortPending(false);
    }
  };

  const openPivotDialog = () => {
    if (!workbook || !selection) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    setPivotSourceRange(selection.rectangle);
    setPivotRowField('');
    setPivotColumnField('');
    setPivotValueField('');
    setPivotSummarizeBy('SUM');
    setPivotError(null);
    setPivotDialogOpen(true);
  };

  const handlePivotCreate = async () => {
    if (!workbook || !pivotSourceRange) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    setPivotPending(true);
    setPivotError(null);
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/pivot/create`, {
        method: 'POST',
        body: { sourceRange: pivotSourceRange }
      });
      setWorkbook(updated);
      setPivotDialogOpen(false);
      await updateUndoRedoState();
    } catch (err) {
      setPivotError(err.message || 'Failed to create pivot table');
    } finally {
      setPivotPending(false);
    }
  };

  const handlePivotApply = async () => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    // If we're on the pivot result sheet, find the source sheet
    const sourceSheetId = activeSheet.pivotState?.isPivotResult 
      ? activeSheet.pivotState.sourceWorksheetId 
      : activeSheet.id;
    
    setPivotPending(true);
    setPivotError(null);
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${sourceSheetId}/pivot/apply`, {
        method: 'POST',
        body: {
          rowField: pivotRowField,
          columnField: pivotColumnField || null,
          valueField: pivotValueField,
          summarizeBy: pivotSummarizeBy
        }
      });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setPivotError(err.message || 'Failed to apply pivot');
    } finally {
      setPivotPending(false);
    }
  };

  const handlePivotRefresh = async () => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet || !activeSheet.pivotState?.isPivotResult) return;
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/pivot/refresh`, {
        method: 'POST'
      });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to refresh pivot table');
    }
  };

  const handleRowAction = async (action, rowIndex) => {
    if (!workbook || !activeSheet) return;
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/rows`, {
        method: 'POST',
        body: { action, rowIndex }
      });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to perform row operation');
    }
  };

  const handleColumnAction = async (action, colIndex) => {
    if (!workbook || !activeSheet) return;
    
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/columns`, {
        method: 'POST',
        body: { action, colIndex }
      });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to perform column operation');
    }
  };

  const handleAddWorksheet = async () => {
    try {
      // Save current selection before adding new worksheet
      const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
      if (activeSheet && selection) {
        await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/selection`, {
          method: 'PATCH',
          body: selection
        });
      }
      
      const updated = await requestJson(`/api/workbooks/${id}/worksheets`, {
        method: 'POST'
      });
      setWorkbook(updated);
      setSelection({ currentCell: 'A1', rectangle: { start: 'A1', end: 'A1' } });
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to add worksheet');
    }
  };

  const openDeleteWorksheet = (sheetId, sheetName) => {
    if (workbook.worksheets.length === 1) {
      setDeleteMessage('A workbook must contain at least one worksheet');
      setTimeout(() => setDeleteMessage(null), 4000);
      return;
    }
    setDeleteSheetId(sheetId);
    setDeleteSheetName(sheetName);
    setDeleteError(null);
    setDeleteDialogOpen(true);
  };

  const handleDeleteWorksheet = async () => {
    if (!deleteSheetId) return;
    setDeletePending(true);
    setDeleteError(null);
    try {
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${deleteSheetId}`, {
        method: 'DELETE'
      });
      setWorkbook(updated);
      setDeleteDialogOpen(false);
      
      // Update selection to match new active worksheet
      const newActiveSheet = updated.worksheets.find(ws => ws.id === updated.lastActiveWorksheet) || updated.worksheets[0];
      const sel = newActiveSheet?.selection || { currentCell: 'A1', rectangle: { start: 'A1', end: 'A1' } };
      setSelection(sel);
      setFormulaBarDraft(null);
      
      await updateUndoRedoState();
    } catch (err) {
      setDeleteDialogOpen(false);
      setDeleteMessage(err.message || 'Failed to delete worksheet');
      setTimeout(() => setDeleteMessage(null), 5000);
    } finally {
      setDeletePending(false);
    }
  };

  const handleSelectionChange = async (newSelection) => {
    // Commit any pending formula bar draft before changing selection
    if (formulaBarOriginCell && formulaBarDraft !== null) {
      const activeSheet = workbook?.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook?.worksheets[0];
      if (activeSheet) {
        const currentContent = activeSheet.cells?.[formulaBarOriginCell]?.originalContent || '';
        if (formulaBarDraft !== currentContent) {
          try {
            const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/cells`, {
              method: 'POST',
              body: { coord: formulaBarOriginCell, content: formulaBarDraft }
            });
            setWorkbook(updated);
          } catch (err) {
            // Ignore commit errors during selection change
          }
        }
      }
      setFormulaBarDraft(null);
      setFormulaBarOriginCell(null);
    }
    
    setSelection(newSelection);
    const activeSheet = workbook?.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook?.worksheets[0];
    if (activeSheet) {
      try {
        await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/selection`, {
          method: 'PATCH',
          body: newSelection
        });
      } catch (err) {
        // Ignore selection save errors
      }
    }
  };

  const handleTabClick = async (sheetId) => {
    if (sheetId === workbook.lastActiveWorksheet) return;
    
    try {
      const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
      if (activeSheet && selection) {
        await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/selection`, {
          method: 'PATCH',
          body: selection
        });
      }
      
      const updated = await requestJson(`/api/workbooks/${id}`, {
        method: 'PATCH',
        body: { lastActiveWorksheet: sheetId }
      });
      setWorkbook(updated);
      const sheet = updated.worksheets.find(ws => ws.id === sheetId);
      const sel = sheet?.selection || { currentCell: 'A1', rectangle: { start: 'A1', end: 'A1' } };
      setSelection(sel);
      setFormulaBarDraft(null);
      
      // Initialize pivot editor state when switching to a pivot result sheet
      if (sheet?.pivotState?.isPivotResult) {
        setPivotRowField(sheet.pivotState.rowField || '');
        setPivotColumnField(sheet.pivotState.columnField || '');
        setPivotValueField(sheet.pivotState.valueField || '');
        setPivotSummarizeBy(sheet.pivotState.summarizeBy || 'SUM');
        setPivotError(null);
      }
    } catch (err) {
      setError(err.message || 'Failed to switch worksheet');
    }
  };

  const commitCellEdit = async (coord, content) => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    const currentContent = activeSheet.cells?.[coord]?.originalContent || '';
    if (content === currentContent) return;
    
    try {
      setCellEditError(null);
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/cells`, {
        method: 'POST',
        body: { coord, content }
      });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setCellEditError(err.message || 'Failed to save cell');
    }
  };

  const handleCopy = async (rectangle) => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    const start = parseCoord(rectangle.start);
    const end = parseCoord(rectangle.end);
    if (!start || !end) return;
    
    const minCol = Math.min(start.col, end.col);
    const maxCol = Math.max(start.col, end.col);
    const minRow = Math.min(start.row, end.row);
    const maxRow = Math.max(start.row, end.row);
    
    let text = '';
    for (let r = minRow; r <= maxRow; r++) {
      const row = [];
      for (let c = minCol; c <= maxCol; c++) {
        const coord = cellCoord(c, r);
        const cell = activeSheet.cells[coord];
        row.push(cell?.originalContent || '');
      }
      text += row.join('\t') + '\n';
    }
    
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      // Clipboard access denied
    }
    
    setPendingTransfer({
      mode: 'copy',
      sourceRange: rectangle
    });
  };

  const handleCut = async (rectangle) => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    const start = parseCoord(rectangle.start);
    const end = parseCoord(rectangle.end);
    if (!start || !end) return;
    
    const minCol = Math.min(start.col, end.col);
    const maxCol = Math.max(start.col, end.col);
    const minRow = Math.min(start.row, end.row);
    const maxRow = Math.max(start.row, end.row);
    
    let text = '';
    for (let r = minRow; r <= maxRow; r++) {
      const row = [];
      for (let c = minCol; c <= maxCol; c++) {
        const coord = cellCoord(c, r);
        const cell = activeSheet.cells[coord];
        row.push(cell?.originalContent || '');
      }
      text += row.join('\t') + '\n';
    }
    
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      // Clipboard access denied
    }
    
    setPendingTransfer({
      mode: 'cut',
      sourceRange: rectangle
    });
  };

  const handlePaste = async (targetCoord) => {
    if (!workbook) return;
    const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
    if (!activeSheet) return;
    
    try {
      let body;
      if (pendingTransfer) {
        body = {
          mode: pendingTransfer.mode,
          sourceRange: pendingTransfer.sourceRange,
          targetCoord
        };
      } else {
        const text = await navigator.clipboard.readText();
        body = {
          mode: 'external',
          targetCoord,
          text
        };
      }
      
      const updated = await requestJson(`/api/workbooks/${id}/worksheets/${activeSheet.id}/transfer`, {
        method: 'POST',
        body
      });
      setWorkbook(updated);
      
      if (pendingTransfer) {
        setPendingTransfer(null);
      }
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to paste');
    }
  };

  const handleFormulaBarChange = (e) => {
    setFormulaBarValue(e.target.value);
    if (formulaBarDraft === null) {
      setFormulaBarOriginCell(selection?.currentCell);
    }
    setFormulaBarDraft(e.target.value);
  };

  const handleFormulaBarKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (formulaBarOriginCell && formulaBarDraft !== null) {
        commitCellEdit(formulaBarOriginCell, formulaBarDraft);
        setFormulaBarDraft(null);
        setFormulaBarOriginCell(null);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setFormulaBarDraft(null);
      setFormulaBarOriginCell(null);
      const activeSheet = workbook?.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook?.worksheets[0];
      const cellContent = activeSheet?.cells?.[selection?.currentCell]?.originalContent || '';
      setFormulaBarValue(cellContent);
    }
  };

  const handleFormulaBarBlur = () => {
    if (formulaBarOriginCell && formulaBarDraft !== null) {
      commitCellEdit(formulaBarOriginCell, formulaBarDraft);
      setFormulaBarDraft(null);
      setFormulaBarOriginCell(null);
    }
  };

  const handleUndo = async () => {
    if (!workbook) return;
    try {
      const updated = await requestJson(`/api/workbooks/${id}/undo`, { method: 'POST' });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to undo');
    }
  };

  const handleRedo = async () => {
    if (!workbook) return;
    try {
      const updated = await requestJson(`/api/workbooks/${id}/redo`, { method: 'POST' });
      setWorkbook(updated);
      await updateUndoRedoState();
    } catch (err) {
      setError(err.message || 'Failed to redo');
    }
  };

  useEffect(() => {
    const handleKeyDown = async (e) => {
      if (e.ctrlKey && e.key === 'z') {
        e.preventDefault();
        if (canUndo) await handleUndo();
      } else if (e.ctrlKey && e.key === 'y') {
        e.preventDefault();
        if (canRedo) await handleRedo();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [canUndo, canRedo, workbook]);

  if (loading) return <main><p>Loading...</p></main>;
  if (error) return <main><p role="alert">{error}</p></main>;
  if (!workbook) return <main><p>Workbook not found</p></main>;

  const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];

  return (
    <main style={{ padding: 0, maxWidth: '100%' }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        <Link to="/" style={{ marginRight: '4px' }}>← Home</Link>
        <strong>{workbook.name}</strong>
        <button
          type="button"
          onClick={handleUndo}
          disabled={!canUndo}
          style={{
            padding: '4px 12px',
            background: 'var(--subtle)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            cursor: canUndo ? 'pointer' : 'not-allowed',
            fontSize: '13px',
            opacity: canUndo ? 1 : 0.5
          }}
        >
          Undo
        </button>
        <button
          type="button"
          onClick={handleRedo}
          disabled={!canRedo}
          style={{
            padding: '4px 12px',
            background: 'var(--subtle)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            cursor: canRedo ? 'pointer' : 'not-allowed',
            fontSize: '13px',
            opacity: canRedo ? 1 : 0.5
          }}
        >
          Redo
        </button>
        <button
          type="button"
          onClick={openRename}
          style={{
            padding: '4px 12px',
            background: 'var(--subtle)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          Rename workbook
        </button>
        <button
          type="button"
          onClick={handleExportCSV}
          style={{
            padding: '4px 12px',
            background: 'var(--subtle)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          Export CSV
        </button>
        <DropdownMenu.Root open={dataMenuOpen} onOpenChange={setDataMenuOpen}>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              style={{
                padding: '4px 12px',
                background: 'var(--subtle)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              Data
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              style={{
                background: 'white',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                padding: '4px 0',
                minWidth: '160px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                zIndex: 1000
              }}
            >
              <DropdownMenu.Item
                onSelect={handleCreateFilter}
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--subtle)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                Create filter
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={handleClearFilter}
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--subtle)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                Clear filter
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={openValidationDialog}
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--subtle)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                Data validation
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={openSortDialog}
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--subtle)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                Sort range
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={openPivotDialog}
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--subtle)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                Create pivot table
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        <span style={{ color: 'var(--muted)', marginLeft: 'auto' }}>
          Last updated: {formatLastUpdated(workbook.lastUpdated)}
        </span>
      </header>
      <div style={{ padding: '0' }}>
        <div role="tablist" style={{ display: 'flex', borderBottom: '1px solid var(--border)', background: 'var(--subtle)', alignItems: 'center' }}>
          {workbook.worksheets.map(ws => (
            <div key={ws.id} style={{ display: 'flex', alignItems: 'center', position: 'relative' }}>
              <button
                role="tab"
                aria-selected={ws.id === activeSheet?.id}
                onClick={() => handleTabClick(ws.id)}
                style={{
                  padding: '8px 16px',
                  border: 'none',
                  borderBottom: ws.id === activeSheet?.id ? '2px solid var(--accent)' : '2px solid transparent',
                  background: 'transparent',
                  cursor: 'pointer',
                  fontWeight: ws.id === activeSheet?.id ? 600 : 400
                }}
              >
                {ws.name}
              </button>
              <DropdownMenu.Root>
                <DropdownMenu.Trigger
                  aria-label={`Worksheet options for ${ws.name}`}
                  style={{
                    padding: '4px 8px',
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    fontSize: '16px',
                    lineHeight: 1
                  }}
                >
                  ⋮
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    style={{
                      background: 'white',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      padding: '4px 0',
                      minWidth: '120px',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                      zIndex: 1000
                    }}
                  >
                    <DropdownMenu.Item
                      onSelect={() => openRenameWorksheet(ws.id, ws.name)}
                      style={{
                        padding: '8px 16px',
                        cursor: 'pointer',
                        fontSize: '14px'
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--subtle)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      Rename
                    </DropdownMenu.Item>
                    <DropdownMenu.Item
                      onSelect={() => openDeleteWorksheet(ws.id, ws.name)}
                      style={{
                        padding: '8px 16px',
                        cursor: 'pointer',
                        fontSize: '14px'
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--subtle)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      Delete
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            </div>
          ))}
          <button
            type="button"
            onClick={handleAddWorksheet}
            aria-label="Add worksheet"
            style={{
              padding: '8px 16px',
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: '18px',
              lineHeight: 1,
              fontWeight: 600
            }}
          >
            +
          </button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', padding: '4px 12px', borderBottom: '1px solid var(--border)', background: 'var(--subtle)', gap: '8px' }}>
          <span style={{ fontFamily: 'monospace', fontSize: '13px', fontWeight: 600, minWidth: '40px' }}>
            {selection?.currentCell || ''}
          </span>
          <label htmlFor="formula-bar" style={{ display: 'flex', alignItems: 'center', flex: 1, gap: '4px' }}>
            <span style={{ position: 'absolute', width: '1px', height: '1px', padding: 0, margin: '-1px', overflow: 'hidden', clip: 'rect(0,0,0,0)', whiteSpace: 'nowrap', border: 0 }}>Formula bar</span>
            <textarea
              id="formula-bar"
              aria-label="Formula bar"
              rows={1}
              value={formulaBarValue}
              onChange={handleFormulaBarChange}
              onKeyDown={handleFormulaBarKeyDown}
              onBlur={handleFormulaBarBlur}
              style={{
                flex: 1,
                padding: '4px 8px',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                fontFamily: 'monospace',
                fontSize: '13px',
                background: 'white',
                minHeight: '24px',
                resize: 'none',
                overflow: 'hidden'
              }}
            />
          </label>
        </div>
        {activeSheet && <WorksheetGrid worksheet={activeSheet} selection={selection} onSelectionChange={handleSelectionChange} onRowAction={handleRowAction} onColumnAction={handleColumnAction} onCellEdit={commitCellEdit} onCopy={handleCopy} onCut={handleCut} onPaste={handlePaste} onFilterClick={openFilterDialog} />}
        {cellEditError && <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: '4px 0', fontSize: '13px' }}>{cellEditError}</p>}
      </div>
      {filterDialogOpen && (() => {
        const activeSheet = workbook.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook.worksheets[0];
        const filter = activeSheet?.filterViews?.[0];
        if (!filter) return null;
        
        const start = parseCoord(filter.sourceRange.start);
        const end = parseCoord(filter.sourceRange.end);
        if (!start || !end) return null;
        
        const headerCol = start.col + Array.from({length: end.col - start.col + 1}, (_, i) => i).find(i => {
          const coord = cellCoord(start.col + i, start.row);
          return activeSheet.cells[coord]?.displayedValue === filterDialogOpen;
        });
        
        if (headerCol === undefined) return null;
        
        const headerCoord = cellCoord(start.col + headerCol, start.row);
        const values = new Set();
        for (let r = start.row + 1; r <= end.row; r++) {
          const coord = cellCoord(start.col + headerCol, r);
          const val = activeSheet.cells[coord]?.displayedValue || '';
          values.add(val);
        }
        
        const criteria = filter.criteria?.[filterDialogOpen] || {};
        
        return (
          <Dialog.Root open={true} onOpenChange={() => setFilterDialogOpen(null)}>
            <DialogSurface title={`Filter ${filterDialogOpen}`} description="Filter values for this column">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <button
                  type="button"
                  onClick={() => setFilterCriteria({selectedValues: []})}
                  style={{
                    padding: '6px 12px',
                    background: 'var(--subtle)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                    cursor: 'pointer',
                    fontSize: '13px',
                    alignSelf: 'flex-start'
                  }}
                >
                  Clear selection
                </button>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '200px', overflow: 'auto' }}>
                  {Array.from(values).sort().map(val => (
                    <label key={val} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <input
                        type="checkbox"
                        aria-label={val}
                        checked={(filterCriteria.selectedValues || criteria.selectedValues || Array.from(values)).includes(val)}
                        onChange={e => {
                          const current = filterCriteria.selectedValues || criteria.selectedValues || Array.from(values);
                          const next = e.target.checked
                            ? [...current, val]
                            : current.filter(v => v !== val);
                          setFilterCriteria({...filterCriteria, selectedValues: next});
                        }}
                      />
                      <span>{val}</span>
                    </label>
                  ))}
                </div>
                <div style={{ borderTop: '1px solid var(--border)', paddingTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span>Condition</span>
                    <select
                      aria-label="Condition"
                      value={filterCriteria.condition || criteria.condition || ''}
                      onChange={e => setFilterCriteria({...filterCriteria, condition: e.target.value})}
                      style={{
                        padding: '6px 8px',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        fontSize: '14px'
                      }}
                    >
                      <option value="">Select condition</option>
                      <option value="Text contains">Text contains</option>
                      <option value="Greater than">Greater than</option>
                      <option value="Before">Before</option>
                      <option value="Is empty">Is empty</option>
                      <option value="Is not empty">Is not empty</option>
                    </select>
                  </label>
                  {(filterCriteria.condition || criteria.condition) && !['Is empty', 'Is not empty'].includes(filterCriteria.condition || criteria.condition) && (
                    <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <span>Value</span>
                      <input
                        type="text"
                        aria-label="Value"
                        value={filterCriteria.value || criteria.value || ''}
                        onChange={e => setFilterCriteria({...filterCriteria, value: e.target.value})}
                        style={{
                          padding: '6px 8px',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius)',
                          fontSize: '14px'
                        }}
                      />
                    </label>
                  )}
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                  <button
                    type="button"
                    onClick={() => setFilterDialogOpen(null)}
                    style={{
                      padding: '6px 12px',
                      background: 'var(--subtle)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      cursor: 'pointer'
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => handleFilterApply(filter.id, filterDialogOpen, filterCriteria)}
                    style={{
                      padding: '6px 12px',
                      background: 'var(--accent)',
                      color: 'white',
                      border: 'none',
                      borderRadius: 'var(--radius)',
                      cursor: 'pointer',
                      fontWeight: 600
                    }}
                  >
                    Apply
                  </button>
                </div>
              </div>
            </DialogSurface>
          </Dialog.Root>
        );
      })()}
      <Dialog.Root open={renameOpen && renameSheetId === null} onOpenChange={setRenameOpen}>
        <DialogSurface title="Rename workbook" description="Change the workbook name">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <label htmlFor="rename-workbook-name" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span>Workbook name</span>
              <input
                id="rename-workbook-name"
                type="text"
                value={renameName}
                onChange={e => setRenameName(e.target.value)}
                style={{
                  padding: '6px 8px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  fontSize: '14px'
                }}
              />
            </label>
            {renameError && (
              <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: 0, fontSize: '13px' }}>
                {renameError}
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setRenameOpen(false)}
                style={{
                  padding: '6px 12px',
                  background: 'var(--subtle)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRenameSave}
                disabled={renamePending}
                style={{
                  padding: '6px 12px',
                  background: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  cursor: renamePending ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                Save
              </button>
            </div>
          </div>
        </DialogSurface>
      </Dialog.Root>
      <Dialog.Root open={renameOpen && renameSheetId !== null} onOpenChange={setRenameOpen}>
        <DialogSurface title="Rename worksheet" description="Change the worksheet name">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <label htmlFor="rename-worksheet-name" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span>Worksheet name</span>
              <input
                id="rename-worksheet-name"
                type="text"
                value={renameName}
                onChange={e => setRenameName(e.target.value)}
                style={{
                  padding: '6px 8px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  fontSize: '14px'
                }}
              />
            </label>
            {renameError && (
              <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: 0, fontSize: '13px' }}>
                {renameError}
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setRenameOpen(false)}
                style={{
                  padding: '6px 12px',
                  background: 'var(--subtle)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRenameWorksheetSave}
                disabled={renamePending}
                style={{
                  padding: '6px 12px',
                  background: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  cursor: renamePending ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                Save
              </button>
            </div>
          </div>
        </DialogSurface>
      </Dialog.Root>
      <Dialog.Root open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogSurface title="Delete worksheet" description={`Delete worksheet ${deleteSheetName}`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <p style={{ margin: 0 }}>
              Are you sure you want to delete <strong>{deleteSheetName}</strong>? This will remove all data, formulas, filters, validation, and pivot results in this worksheet.
            </p>
            {deleteError && (
              <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: 0, fontSize: '13px' }}>
                {deleteError}
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setDeleteDialogOpen(false)}
                style={{
                  padding: '6px 12px',
                  background: 'var(--subtle)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteWorksheet}
                disabled={deletePending}
                style={{
                  padding: '6px 12px',
                  background: 'var(--danger, #d32f2f)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  cursor: deletePending ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                Delete worksheet
              </button>
            </div>
          </div>
        </DialogSurface>
      </Dialog.Root>
      {deleteMessage && (
        <div role="alert" style={{
          position: 'fixed',
          bottom: '20px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'var(--danger, #d32f2f)',
          color: 'white',
          padding: '12px 24px',
          borderRadius: 'var(--radius)',
          zIndex: 9999,
          boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
        }}>
          {deleteMessage}
        </div>
      )}
      <Dialog.Root open={validationDialogOpen} onOpenChange={setValidationDialogOpen}>
        <DialogSurface title="Data validation" description="Configure validation rules for the selected range">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <label htmlFor="validation-rule-type" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span>Rule type</span>
              <select
                id="validation-rule-type"
                value={validationRuleType}
                onChange={e => setValidationRuleType(e.target.value)}
                style={{
                  padding: '6px 8px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  fontSize: '14px'
                }}
              >
                <option value="Dropdown">Dropdown</option>
                <option value="Number range">Number range</option>
              </select>
            </label>
            {validationRuleType === 'Dropdown' && (
              <label htmlFor="validation-allowed-values" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span>Allowed values</span>
                <input
                  id="validation-allowed-values"
                  type="text"
                  value={validationAllowedValues}
                  onChange={e => setValidationAllowedValues(e.target.value)}
                  placeholder="Comma-separated values"
                  style={{
                    padding: '6px 8px',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                    fontSize: '14px'
                  }}
                />
              </label>
            )}
            {validationRuleType === 'Number range' && (
              <>
                <label htmlFor="validation-minimum" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span>Minimum</span>
                  <input
                    id="validation-minimum"
                    type="number"
                    value={validationMinimum}
                    onChange={e => setValidationMinimum(e.target.value)}
                    style={{
                      padding: '6px 8px',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      fontSize: '14px'
                    }}
                  />
                </label>
                <label htmlFor="validation-maximum" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span>Maximum</span>
                  <input
                    id="validation-maximum"
                    type="number"
                    value={validationMaximum}
                    onChange={e => setValidationMaximum(e.target.value)}
                    style={{
                      padding: '6px 8px',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      fontSize: '14px'
                    }}
                  />
                </label>
              </>
            )}
            {validationError && (
              <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: 0, fontSize: '13px' }}>
                {validationError}
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              {editingRuleIndex !== null && (
                <button
                  type="button"
                  onClick={handleValidationDelete}
                  disabled={validationPending}
                  style={{
                    padding: '6px 12px',
                    background: 'var(--danger, #d32f2f)',
                    color: 'white',
                    border: 'none',
                    borderRadius: 'var(--radius)',
                    cursor: validationPending ? 'not-allowed' : 'pointer',
                    marginRight: 'auto'
                  }}
                >
                  Delete rule
                </button>
              )}
              <button
                type="button"
                onClick={() => setValidationDialogOpen(false)}
                style={{
                  padding: '6px 12px',
                  background: 'var(--subtle)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleValidationSave}
                disabled={validationPending}
                style={{
                  padding: '6px 12px',
                  background: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  cursor: validationPending ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                Save
              </button>
            </div>
          </div>
        </DialogSurface>
      </Dialog.Root>
      <Dialog.Root open={sortDialogOpen} onOpenChange={setSortDialogOpen}>
        <DialogSurface title="Sort range" description="Sort the selected data range">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <label htmlFor="sort-by" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span>Sort by</span>
              <select
                id="sort-by"
                aria-label="Sort by"
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                style={{
                  padding: '6px 8px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  fontSize: '14px'
                }}
              >
                {(() => {
                  const activeSheet = workbook?.worksheets.find(ws => ws.id === workbook.lastActiveWorksheet) || workbook?.worksheets[0];
                  if (!activeSheet || !selection) return null;
                  const start = parseCoord(selection.rectangle.start);
                  const end = parseCoord(selection.rectangle.end);
                  if (!start || !end) return null;
                  const options = [];
                  for (let c = start.col; c <= end.col; c++) {
                    const coord = cellCoord(c, start.row);
                    const headerText = activeSheet.cells[coord]?.displayedValue || '';
                    const label = headerText || cellCoord(c, 0).replace(/\d+/, '');
                    options.push(<option key={c} value={label}>{label}</option>);
                  }
                  return options;
                })()}
              </select>
            </label>
            <label htmlFor="sort-order" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span>Order</span>
              <select
                id="sort-order"
                aria-label="Order"
                value={sortOrder}
                onChange={e => setSortOrder(e.target.value)}
                style={{
                  padding: '6px 8px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  fontSize: '14px'
                }}
              >
                <option value="Ascending">Ascending</option>
                <option value="Descending">Descending</option>
              </select>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="checkbox"
                aria-label="Data has header row"
                checked={hasHeaderRow}
                onChange={e => setHasHeaderRow(e.target.checked)}
              />
              <span>Data has header row</span>
            </label>
            {sortError && (
              <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: 0, fontSize: '13px' }}>
                {sortError}
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setSortDialogOpen(false)}
                style={{
                  padding: '6px 12px',
                  background: 'var(--subtle)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSort}
                disabled={sortPending}
                style={{
                  padding: '6px 12px',
                  background: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  cursor: sortPending ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                Sort
              </button>
            </div>
          </div>
        </DialogSurface>
      </Dialog.Root>
      <Dialog.Root open={pivotDialogOpen} onOpenChange={setPivotDialogOpen}>
        <DialogSurface title="Create pivot table" description="Create a pivot table from the selected data range">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <p style={{ margin: 0, fontSize: '14px' }}>
              Source range: {pivotSourceRange ? `${pivotSourceRange.start}:${pivotSourceRange.end}` : ''}
            </p>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="radio"
                name="pivot-location"
                value="new-worksheet"
                checked={true}
                readOnly
              />
              <span>New worksheet</span>
            </label>
            {pivotError && (
              <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: 0, fontSize: '13px' }}>
                {pivotError}
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setPivotDialogOpen(false)}
                style={{
                  padding: '6px 12px',
                  background: 'var(--subtle)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handlePivotCreate}
                disabled={pivotPending}
                style={{
                  padding: '6px 12px',
                  background: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  cursor: pivotPending ? 'not-allowed' : 'pointer',
                  fontWeight: 600
                }}
              >
                Create
              </button>
            </div>
          </div>
        </DialogSurface>
      </Dialog.Root>
      {activeSheet?.pivotState?.isPivotResult && (
        <div role="region" aria-label="Pivot table editor" style={{ padding: '12px', borderBottom: '1px solid var(--border)', background: 'var(--subtle)' }}>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            {(() => {
              const sourceSheet = workbook.worksheets.find(ws => ws.id === activeSheet.pivotState.sourceWorksheetId);
              if (!sourceSheet) return null;
              const sourceRange = activeSheet.pivotState.sourceRange;
              if (!sourceRange) return null;
              const start = parseCoord(sourceRange.start);
              const end = parseCoord(sourceRange.end);
              if (!start || !end) return null;
              const headers = [];
              for (let c = start.col; c <= end.col; c++) {
                const coord = cellCoord(c, start.row);
                const headerText = sourceSheet.cells[coord]?.displayedValue || '';
                if (headerText) headers.push(headerText);
              }
              return (
                <>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span>Rows</span>
                    <select
                      aria-label="Rows"
                      value={pivotRowField}
                      onChange={e => setPivotRowField(e.target.value)}
                      style={{
                        padding: '6px 8px',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        fontSize: '14px'
                      }}
                    >
                      <option value="">Select field</option>
                      {headers.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </label>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span>Columns</span>
                    <select
                      aria-label="Columns"
                      value={pivotColumnField}
                      onChange={e => setPivotColumnField(e.target.value)}
                      style={{
                        padding: '6px 8px',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        fontSize: '14px'
                      }}
                    >
                      <option value="">None</option>
                      {headers.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </label>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span>Values</span>
                    <select
                      aria-label="Values"
                      value={pivotValueField}
                      onChange={e => setPivotValueField(e.target.value)}
                      style={{
                        padding: '6px 8px',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        fontSize: '14px'
                      }}
                    >
                      <option value="">Select field</option>
                      {headers.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </label>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span>Summarize by</span>
                    <select
                      aria-label="Summarize by"
                      value={pivotSummarizeBy}
                      onChange={e => setPivotSummarizeBy(e.target.value)}
                      style={{
                        padding: '6px 8px',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        fontSize: '14px'
                      }}
                    >
                      <option value="SUM">SUM</option>
                      <option value="COUNT">COUNT</option>
                      <option value="AVERAGE">AVERAGE</option>
                    </select>
                  </label>
                </>
              );
            })()}
            <button
              type="button"
              onClick={handlePivotApply}
              disabled={pivotPending}
              style={{
                padding: '6px 12px',
                background: 'var(--accent)',
                color: 'white',
                border: 'none',
                borderRadius: 'var(--radius)',
                cursor: pivotPending ? 'not-allowed' : 'pointer',
                fontWeight: 600
              }}
            >
              Apply
            </button>
            <button
              type="button"
              onClick={handlePivotRefresh}
              style={{
                padding: '6px 12px',
                background: 'var(--subtle)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                cursor: 'pointer',
                fontWeight: 600
              }}
            >
              Refresh pivot table
            </button>
          </div>
          {pivotError && (
            <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: '8px 0 0 0', fontSize: '13px' }}>
              {pivotError}
            </p>
          )}
          {activeSheet.pivotState.errorMessage && (
            <p role="alert" style={{ color: 'var(--danger, #d32f2f)', margin: '8px 0 0 0', fontSize: '13px' }}>
              {activeSheet.pivotState.errorMessage}
            </p>
          )}
        </div>
      )}
    </main>
  );
}
