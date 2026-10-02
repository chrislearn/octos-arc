import {useEffect, useRef, useState} from 'react';
import {Link, useParams} from 'react-router';
import {Dialog, DropdownMenu} from 'radix-ui';
import {DialogSurface} from '../shared/interactions.jsx';
import {requestJson} from '../shared/request.js';
import WorksheetGrid from './Grid.jsx';
import './editor.css';

function colIndex(letters) {
  let col = 0;
  for (const ch of letters) col = col * 26 + (ch.charCodeAt(0) - 64);
  return col;
}

const DEFAULT_RECT = {top: 1, left: 1, bottom: 1, right: 1};

export default function Editor() {
  const {workbookId} = useParams();
  const [workbook, setWorkbook] = useState(null);
  const [error, setError] = useState(null);
  const [activeSheetId, setActiveSheetId] = useState(null);
  const [currentCell, setCurrentCell] = useState('A1');
  const [selectionRect, setSelectionRect] = useState(DEFAULT_RECT);
  const [renameOpen, setRenameOpen] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [renameError, setRenameError] = useState(null);
  const [savingName, setSavingName] = useState(false);
  const [draft, setDraft] = useState({cell: null, text: ''});
  const draftRef = useRef(null);
  const [cellError, setCellError] = useState(null);
  const saveSequence = useRef(0);
  const [renameSheetId, setRenameSheetId] = useState(null);
  const [draftSheetName, setDraftSheetName] = useState('');
  const [sheetRenameError, setSheetRenameError] = useState(null);
  const [savingSheetName, setSavingSheetName] = useState(false);
  const [addError, setAddError] = useState(null);
  const [addingSheet, setAddingSheet] = useState(false);
  const [structureError, setStructureError] = useState(null);
  const currentCellRef = useRef('A1');
  const pasteCellsRef = useRef(null);
  const transferRef = useRef(null);
  const selectionSequence = useRef(0);
  const clipboardRef = useRef(null);
  const activeSheetRef = useRef(null);
  const selectionRectRef = useRef(DEFAULT_RECT);
  const [historyState, setHistoryState] = useState({canUndo: false, canRedo: false});
  const runHistoryRef = useRef(null);

  useEffect(() => {
    let live = true;
    requestJson(`/api/workbooks/${workbookId}`)
      .then((data) => {
        if (!live) return;
        setWorkbook(data);
        const last = data.worksheets.find((s) => s.id === data.lastActiveSheetId)
          || data.worksheets[0];
        setActiveSheetId(last?.id ?? null);
        setCurrentCell(last?.selection?.current || 'A1');
        setSelectionRect(last?.selection?.rectangle || DEFAULT_RECT);
        requestJson(`/api/workbooks/${workbookId}/history`)
          .then((state) => { if (live) setHistoryState(state); })
          .catch(() => {});
      })
      .catch((e) => { if (live) setError(e); });
    return () => { live = false; };
  }, [workbookId]);

  const activeSheet = workbook
    ? (workbook.worksheets.find((sheet) => sheet.id === activeSheetId)
      || workbook.worksheets[0])
    : null;

  useEffect(() => { currentCellRef.current = currentCell; }, [currentCell]);
  useEffect(() => { selectionRectRef.current = selectionRect; }, [selectionRect]);
  useEffect(() => { activeSheetRef.current = activeSheet; }, [activeSheet]);

  useEffect(() => {
    const handler = (event) => {
      const tag = event.target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      const sheet = activeSheetRef.current;
      if (key === 'c' || key === 'x') {
        if (!sheet) return;
        const rect = selectionRectRef.current;
        if (!rect) return;
        const mode = key === 'c' ? 'copy' : 'cut';
        navigator.clipboard.readText().catch(() => null).then((text) => {
          clipboardRef.current = {
            mode,
            sheetId: sheet.id,
            rect: {...rect},
            snapshot: typeof text === 'string' ? text : null
          };
        });
      } else if (key === 'z') {
        event.preventDefault();
        runHistoryRef.current?.('undo');
      } else if (key === 'y') {
        event.preventDefault();
        runHistoryRef.current?.('redo');
      } else if (key === 'v') {
        if (!sheet) return;
        event.preventDefault();
        const pending = clipboardRef.current;
        navigator.clipboard.readText().catch(() => null).then((text) => {
          if (pending && pending.sheetId === sheet.id &&
              pending.snapshot !== null && text === pending.snapshot) {
            transferRef.current(pending.mode, pending.rect, currentCellRef.current);
          } else if (text) {
            pasteCellsRef.current(currentCellRef.current, text);
          }
        });
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    const handler = (event) => {
      const tag = event.target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      const text = event.clipboardData?.getData('text/plain');
      if (!text || !pasteCellsRef.current) return;
      event.preventDefault();
      pasteCellsRef.current(currentCellRef.current, text);
    };
    window.addEventListener('paste', handler);
    return () => window.removeEventListener('paste', handler);
  }, []);

  if (error) {
    return <main className="editor-page">
      <p role="alert">{error.message}</p>
      <Link to="/">Back to workbooks</Link>
    </main>;
  }
  if (!workbook) return <main className="editor-page"><p>Loading…</p></main>;

  const cellAt = (coordinate) => activeSheet?.cells?.[coordinate];
  const current = cellAt(currentCell);

  const setDraftSync = (cell, text) => {
    draftRef.current = cell === null ? null : {cell, text};
    setDraft({cell, text});
  };

  const commitCell = async (coordinate, text) => {
    const sheetId = activeSheet.id;
    const original = cellAt(coordinate)?.original ?? '';
    if (text === original) return;
    const sequence = ++saveSequence.current;
    try {
      const updated = await requestJson(`/api/workbooks/${workbookId}`, {
        method: 'PATCH',
        body: {cell: {sheetId, coordinate, value: text}}
      });
      if (sequence === saveSequence.current) {
        setWorkbook(updated);
        setCellError(null);
        setHistoryState({canUndo: true, canRedo: false});
      }
    } catch (e) {
      if (sequence === saveSequence.current) setCellError(e.message);
    }
  };

  const runHistory = (direction) => {
    requestJson(`/api/workbooks/${workbookId}/${direction}`, {method: 'POST'})
      .then((data) => {
        setWorkbook(data.workbook);
        setHistoryState({canUndo: data.canUndo, canRedo: data.canRedo});
      })
      .catch(() => {});
  };
  runHistoryRef.current = runHistory;

  const structureAction = (row, action) => {
    setStructureError(null);
    const mode = action === 'Insert 1 row above' ? 'insert-above'
      : action === 'Insert 1 row below' ? 'insert-below' : 'delete';
    requestJson(`/api/workbooks/${workbookId}/worksheets/${activeSheet.id}/rows`, {
      method: 'POST',
      body: {mode, row}
    }).then((updated) => {
      setWorkbook(updated);
      setHistoryState({canUndo: true, canRedo: false});
    }).catch((e) => setStructureError(e.message));
  };

  const columnAction = (letter, action) => {
    setStructureError(null);
    const mode = action === 'Insert 1 column left' ? 'insert-left'
      : action === 'Insert 1 column right' ? 'insert-right' : 'delete';
    requestJson(`/api/workbooks/${workbookId}/worksheets/${activeSheet.id}/columns`, {
      method: 'POST',
      body: {mode, column: letter}
    }).then((updated) => {
      setWorkbook(updated);
      setHistoryState({canUndo: true, canRedo: false});
    }).catch((e) => setStructureError(e.message));
  };

  const transferCells = (mode, source, coordinate) => {
    setCellError(null);
    requestJson(`/api/workbooks/${workbookId}/worksheets/${activeSheet.id}/paste`, {
      method: 'POST',
      body: {coordinate, transfer: {mode, source}}
    }).then((updated) => {
      setWorkbook(updated);
      setHistoryState({canUndo: true, canRedo: false});
      if (mode === 'cut') clipboardRef.current = null;
    }).catch((e) => setCellError(e.message));
  };
  transferRef.current = transferCells;

  const pasteCells = (coordinate, text) => {
    setCellError(null);
    const pending = clipboardRef.current;
    if (pending && pending.sheetId === activeSheet.id &&
        pending.snapshot !== null && text === pending.snapshot) {
      transferCells(pending.mode, pending.rect, coordinate);
      return;
    }
    requestJson(`/api/workbooks/${workbookId}/worksheets/${activeSheet.id}/paste`, {
      method: 'POST',
      body: {coordinate, text}
    }).then((updated) => {
      setWorkbook(updated);
      setHistoryState({canUndo: true, canRedo: false});
    }).catch((e) => setCellError(e.message));
  };
  pasteCellsRef.current = pasteCells;

  const persistSelection = (sheetId, rectangle, current) => {
    const sequence = ++selectionSequence.current;
    requestJson(`/api/workbooks/${workbookId}`, {
      method: 'PATCH',
      body: {selection: {sheetId, rectangle, current}}
    }).then((updated) => {
      if (sequence === selectionSequence.current) setWorkbook(updated);
    }).catch(() => {});
  };

  const selectCell = (coordinate) => {
    const pending = draftRef.current;
    if (pending && pending.cell !== coordinate) {
      setDraftSync(null, '');
      commitCell(pending.cell, pending.text);
    }
    setCurrentCell(coordinate);
    const parsed = /^([A-Z]+)([0-9]+)$/.exec(coordinate);
    const rectangle = parsed
      ? {top: Number(parsed[2]), left: colIndex(parsed[1]),
         bottom: Number(parsed[2]), right: colIndex(parsed[1])}
      : DEFAULT_RECT;
    setSelectionRect(rectangle);
    if (activeSheet) persistSelection(activeSheet.id, rectangle, coordinate);
  };

  const selectRange = (rectangle, anchor) => {
    setCurrentCell(anchor);
    setSelectionRect(rectangle);
    if (activeSheet) persistSelection(activeSheet.id, rectangle, anchor);
  };

  const addWorksheet = () => {
    if (addingSheet) return;
    setAddingSheet(true);
    setAddError(null);
    requestJson(`/api/workbooks/${workbookId}/worksheets`, {method: 'POST'})
      .then((updated) => {
        setWorkbook(updated);
        const created = updated.worksheets[updated.worksheets.length - 1];
        setActiveSheetId(created.id);
        setCurrentCell('A1');
        setSelectionRect(DEFAULT_RECT);
      })
      .catch((e) => setAddError(e.message))
      .finally(() => setAddingSheet(false));
  };

  return (
    <main className="editor-page">
      <header className="editor-header">
        <h1>{workbook.name}</h1>
        <button type="button" onClick={() => runHistory('undo')}
          disabled={!historyState.canUndo}>Undo</button>
        <button type="button" onClick={() => runHistory('redo')}
          disabled={!historyState.canRedo}>Redo</button>
        <button
          type="button"
          onClick={() => {
            setDraftName(workbook.name);
            setRenameError(null);
            setRenameOpen(true);
          }}
        >
          Rename workbook
        </button>
        <span>Last updated: {workbook.lastUpdated}</span>
        <a className="export-csv-button" role="button"
          href={`/api/workbooks/${workbookId}/worksheets/${activeSheet.id}/export.csv`}
          download={`${activeSheet.name}.csv`}>Export CSV</a>
      </header>

      <Dialog.Root open={renameOpen} onOpenChange={(open) => {
        if (!open) setRenameOpen(false);
      }}>
        <DialogSurface title="Rename workbook" description="Change the workbook name">
          {renameError && <p role="alert">{renameError}</p>}
          <form onSubmit={(event) => {
            event.preventDefault();
            setSavingName(true);
            requestJson(`/api/workbooks/${workbookId}`, {
              method: 'PATCH',
              body: {name: draftName}
            }).then((updated) => {
              setWorkbook(updated);
              setRenameOpen(false);
            }).catch((e) => {
              setRenameError(e.message);
            }).finally(() => setSavingName(false));
          }}>
            <label htmlFor="workbook-name">Workbook name</label>
            <input
              id="workbook-name"
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
            />
            <button type="submit" disabled={savingName}>Save</button>
          </form>
        </DialogSurface>
      </Dialog.Root>

      <div className="formula-bar">
        <label htmlFor="formula-bar">Formula bar</label>
        {cellError && <p role="alert">{cellError}</p>}
        <textarea
          id="formula-bar"
          rows={1}
          data-cell={currentCell}
          value={draft.cell === currentCell ? draft.text : (current ? current.original : '')}
          onChange={(event) => setDraftSync(currentCell, event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              const pending = draftRef.current;
              const text = pending && pending.cell === currentCell
                ? pending.text : event.target.value;
              setDraftSync(null, '');
              commitCell(currentCell, text);
            } else if (event.key === 'Escape') {
              setDraftSync(null, '');
            }
          }}
          onBlur={() => {
            const pending = draftRef.current;
            if (pending && pending.cell === currentCell) {
              setDraftSync(null, '');
              commitCell(pending.cell, pending.text);
            }
          }}
        />
      </div>

      <div role="tablist" aria-label="Worksheets" className="worksheet-tabs">
        <button type="button" className="add-worksheet-button" disabled={addingSheet}
          onClick={addWorksheet}>Add worksheet</button>
        {addError && <p role="alert">{addError}</p>}
        {workbook.worksheets.map((sheet) => (
          <span key={sheet.id} className="worksheet-tab">
            <button
              type="button"
              role="tab"
              aria-selected={sheet.id === activeSheet.id}
              onClick={() => {
                setActiveSheetId(sheet.id);
                setCurrentCell(sheet.selection?.current || 'A1');
                setSelectionRect(sheet.selection?.rectangle || DEFAULT_RECT);
                requestJson(`/api/workbooks/${workbookId}`, {
                  method: 'PATCH',
                  body: {activeSheetId: sheet.id}
                }).then((updated) => setWorkbook(updated)).catch(() => {});
              }}
            >
              {sheet.name}
            </button>
            <DropdownMenu.Root>
              <DropdownMenu.Trigger type="button" aria-label={`Worksheet options for ${sheet.name}`}>
                ▾
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content align="start" style={{background: 'white', border: '1px solid #ccc', padding: 4, zIndex: 50}}>
                  <DropdownMenu.Item
                    onSelect={() => {
                      setDraftSheetName(sheet.name);
                      setSheetRenameError(null);
                      setRenameSheetId(sheet.id);
                    }}
                  >
                    Rename
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </span>
        ))}
      </div>

      <Dialog.Root open={renameSheetId !== null} onOpenChange={(open) => {
        if (!open) setRenameSheetId(null);
      }}>
        <DialogSurface title="Rename worksheet" description="Change the worksheet name">
          {sheetRenameError && <p role="alert">{sheetRenameError}</p>}
          <form onSubmit={(event) => {
            event.preventDefault();
            if (savingSheetName) return;
            setSavingSheetName(true);
            requestJson(`/api/workbooks/${workbookId}/worksheets/${renameSheetId}`, {
              method: 'PATCH',
              body: {name: draftSheetName}
            }).then((updated) => {
              setWorkbook(updated);
              setRenameSheetId(null);
            }).catch((e) => {
              setSheetRenameError(e.message);
            }).finally(() => setSavingSheetName(false));
          }}>
            <label htmlFor="worksheet-name">Worksheet name</label>
            <input
              id="worksheet-name"
              value={draftSheetName}
              onChange={(event) => setDraftSheetName(event.target.value)}
            />
            <button type="submit" disabled={savingSheetName}>Save</button>
          </form>
        </DialogSurface>
      </Dialog.Root>

      {structureError && <p role="alert">{structureError}</p>}
      <WorksheetGrid
        sheet={activeSheet}
        currentCell={currentCell}
        selection={selectionRect}
        onSelectCell={selectCell}
        onSelectRange={selectRange}
        onCommitCell={commitCell}
        onRowAction={structureAction}
        onColumnAction={columnAction}
        onPasteAt={pasteCells}
      />
    </main>
  );
}
