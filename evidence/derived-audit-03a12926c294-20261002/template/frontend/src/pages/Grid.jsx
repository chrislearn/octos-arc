import {useRef, useState} from 'react';
import {DropdownMenu} from 'radix-ui';

function parseCoordinate(coordinate) {
  const match = /^([A-Z]+)([0-9]+)$/.exec(coordinate);
  if (!match) return null;
  let col = 0;
  for (const ch of match[1]) col = col * 26 + (ch.charCodeAt(0) - 64);
  return {col, row: Number(match[2])};
}

function rectFor(a, b) {
  return {
    top: Math.min(a.row, b.row),
    bottom: Math.max(a.row, b.row),
    left: Math.min(a.col, b.col),
    right: Math.max(a.col, b.col)
  };
}

function inRect(pos, rect) {
  return !!rect && pos.row >= rect.top && pos.row <= rect.bottom &&
    pos.col >= rect.left && pos.col <= rect.right;
}

const menuStyle = {background: 'white', border: '1px solid #ccc', padding: 4, zIndex: 50};

export default function WorksheetGrid({sheet, currentCell, selection,
  onSelectCell, onSelectRange, onCommitCell, onRowAction, onColumnAction, onPasteAt}) {
  const [editing, setEditing] = useState(null);
  const editingRef = useRef(null);
  const [rowMenu, setRowMenu] = useState(null);
  const [colMenu, setColMenu] = useState(null);
  const [pasteMenu, setPasteMenu] = useState(null);
  const pasteContextRef = useRef(false);
  const dragRef = useRef(null);
  const suppressClickRef = useRef(false);
  const [preview, setPreview] = useState(null);

  const cellAt = (coordinate) => sheet?.cells?.[coordinate];

  const setEditingSync = (next) => {
    editingRef.current = next;
    setEditing(next);
  };

  const commitInline = (coordinate, text) => {
    setEditingSync(null);
    onCommitCell(coordinate, text);
  };

  const structureAction = (row, action) => {
    setRowMenu(null);
    onRowAction(row, action);
  };

  const columnAction = (letter, action) => {
    setColMenu(null);
    onColumnAction(letter, action);
  };

  const pasteFromMenu = (coordinate) => {
    setPasteMenu(null);
    navigator.clipboard.readText()
      .then((text) => onPasteAt(coordinate, text))
      .catch(() => {});
  };

  const startDrag = (coordinate, event) => {
    const anchor = parseCoordinate(coordinate);
    if (!anchor) return;
    dragRef.current = {anchor, rect: rectFor(anchor, anchor), moved: false};
    setPreview(rectFor(anchor, anchor));
    const move = (moveEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const target = document.elementFromPoint(moveEvent.clientX, moveEvent.clientY)
        ?.closest?.('[data-coordinate]');
      const pos = target ? parseCoordinate(target.dataset.coordinate) : null;
      if (!pos) return;
      drag.moved = true;
      drag.rect = rectFor(drag.anchor, pos);
      setPreview(drag.rect);
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      const drag = dragRef.current;
      dragRef.current = null;
      setPreview(null);
      if (drag && drag.moved) {
        suppressClickRef.current = true;
        // The drag's own click (if any) fires on a common ancestor, not a cell;
        // clear the guard so the next real cell click is not swallowed.
        setTimeout(() => { suppressClickRef.current = false; }, 0);
        const anchorCoordinate = `${columnLetters(drag.anchor.col)}${drag.anchor.row}`;
        onSelectRange(drag.rect, anchorCoordinate);
      }
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const handleCellClick = (coordinate) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    onSelectCell(coordinate);
  };

  const activeRect = preview || selection;

  return (
    <div role="grid" aria-label="Worksheet grid" aria-multiselectable="true" className="worksheet-grid">
      <div role="row" className="grid-row">
        <div role="columnheader" aria-label="Row numbers" className="grid-corner" />
        {COLUMNS.map((letter) => (
          <DropdownMenu.Root key={letter} open={colMenu === letter}
            onOpenChange={(open) => setColMenu(open ? letter : null)}>
            <DropdownMenu.Trigger asChild>
              <div
                role="columnheader"
                aria-label={letter}
                className="grid-column-header"
                onContextMenu={(event) => { event.preventDefault(); setColMenu(letter); }}
              >{letter}</div>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="start" style={menuStyle}>
                <DropdownMenu.Item onSelect={() => columnAction(letter, 'Insert 1 column left')}>
                  Insert 1 column left
                </DropdownMenu.Item>
                <DropdownMenu.Item onSelect={() => columnAction(letter, 'Insert 1 column right')}>
                  Insert 1 column right
                </DropdownMenu.Item>
                <DropdownMenu.Item onSelect={() => columnAction(letter, 'Delete column')}>
                  Delete column
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        ))}
      </div>
      {ROWS.map((row) => (
        <div key={row} role="row" className="grid-row">
          <DropdownMenu.Root open={rowMenu === row} onOpenChange={(open) => setRowMenu(open ? row : null)}>
            <DropdownMenu.Trigger asChild>
              <div
                role="rowheader"
                className="grid-row-header"
                aria-label={String(row)}
                onContextMenu={(event) => { event.preventDefault(); setRowMenu(row); }}
              >{row}</div>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="start" style={menuStyle}>
                <DropdownMenu.Item onSelect={() => structureAction(row, 'Insert 1 row above')}>
                  Insert 1 row above
                </DropdownMenu.Item>
                <DropdownMenu.Item onSelect={() => structureAction(row, 'Insert 1 row below')}>
                  Insert 1 row below
                </DropdownMenu.Item>
                <DropdownMenu.Item onSelect={() => structureAction(row, 'Delete row')}>
                  Delete row
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
          {COLUMNS.map((letter) => {
            const coordinate = `${letter}${row}`;
            const record = cellAt(coordinate);
            const pos = {col: COLUMN_INDEX[letter], row};
            const isSelected = inRect(pos, activeRect);
            const isCurrent = currentCell === coordinate;
            const isEditing = editing?.coordinate === coordinate;
            return (
              <DropdownMenu.Root key={coordinate} open={pasteMenu === coordinate}
                onOpenChange={(open) => {
                  if (open && !pasteContextRef.current) return;
                  pasteContextRef.current = false;
                  setPasteMenu(open ? coordinate : null);
                }}>
                <DropdownMenu.Trigger asChild>
                  <div
                    role="gridcell"
                    aria-label={coordinate}
                    aria-selected={isSelected}
                    data-coordinate={coordinate}
                    tabIndex={isCurrent ? 0 : -1}
                    className={isSelected ? 'grid-cell selected' : 'grid-cell'}
                    onPointerDown={(event) => {
                      // Radix's menu trigger preventDefaults pointerdown, which
                      // would keep focus in the formula bar / inline editor.
                      // Focus the cell explicitly so paste and blur-commit work.
                      event.currentTarget.focus();
                      if (!isEditing) startDrag(coordinate, event);
                    }}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      pasteContextRef.current = true;
                      setPasteMenu(coordinate);
                    }}
                    onClick={() => handleCellClick(coordinate)}
                    onDoubleClick={() => {
                      if (!isEditing) {
                        setEditingSync({coordinate, text: record?.original ?? ''});
                      }
                    }}
                  >
                    {isEditing ? (
                      <input
                        className="grid-cell-editor"
                        aria-label={`Edit ${coordinate}`}
                        autoFocus
                        value={editing.text}
                        onClick={(event) => event.stopPropagation()}
                        onChange={(event) => {
                          setEditingSync({coordinate, text: event.target.value});
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            const pending = editingRef.current;
                            commitInline(coordinate, pending ? pending.text : '');
                          } else if (event.key === 'Escape') {
                            setEditingSync(null);
                          }
                        }}
                        onBlur={() => {
                          const pending = editingRef.current;
                          if (pending && pending.coordinate === coordinate) {
                            commitInline(coordinate, pending.text);
                          }
                        }}
                      />
                    ) : (record ? record.displayed : '')}
                  </div>
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content align="start" style={menuStyle}>
                    <DropdownMenu.Item onSelect={() => pasteFromMenu(coordinate)}>
                      Paste
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            );
          })}
        </div>
      ))}
    </div>
  );
}

const COLUMN_INDEX = {};
const COLUMNS = [];
for (let i = 1; i <= 26; i += 1) {
  const letter = String.fromCharCode(64 + i);
  COLUMN_INDEX[letter] = i;
  COLUMNS.push(letter);
}
const ROWS = Array.from({length: 50}, (_, i) => i + 1);

function columnLetters(col) {
  let name = '';
  let n = col;
  do {
    name = String.fromCharCode(65 + ((n - 1) % 26)) + name;
    n = Math.floor((n - 1) / 26);
  } while (n > 0);
  return name;
}
