'use strict';
// Strict CSV parser: preserves empty fields, quoted commas, escaped "" quotes
// and embedded newlines. Throws on an unclosed quoted field.
function parseCsv(text) {
  if (typeof text !== 'string') throw new Error('Invalid CSV file format. Import failed.');
  const rows = [];
  let row = [];
  let field = '';
  let i = 0;
  const fail = () => { throw new Error('Invalid CSV file format. Import failed.'); };
  while (i < text.length) {
    const ch = text[i];
    if (ch === '"') {
      if (field !== '') fail(); // quote must begin a field
      i += 1;
      let closed = false;
      while (i < text.length) {
        const c = text[i];
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
          closed = true;
          i += 1;
          break;
        }
        field += c;
        i += 1;
      }
      if (!closed) fail();
      // After a closing quote only a separator or end of line may follow.
      const next = text[i];
      if (next !== undefined && next !== ',' && next !== '\n' && next !== '\r') fail();
    } else if (ch === ',') {
      row.push(field);
      field = '';
      i += 1;
    } else if (ch === '\n' || ch === '\r') {
      row.push(field);
      field = '';
      rows.push(row);
      row = [];
      if (ch === '\r' && text[i + 1] === '\n') i += 1;
      i += 1;
    } else {
      field += ch;
      i += 1;
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

module.exports = {parseCsv};
