import {useEffect, useState} from 'react';
import {Link, useNavigate} from 'react-router';
import {Dialog} from 'radix-ui';
import {requestJson} from '../shared/request.js';
import {DialogSurface} from '../shared/interactions.jsx';

export default function Home() {
  const navigate = useNavigate();
  const [workbooks, setWorkbooks] = useState(null);
  const [error, setError] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importError, setImportError] = useState(null);
  const [importPending, setImportPending] = useState(false);
  const [file, setFile] = useState(null);

  const confirmImport = async () => {
    if (!file || importPending) return;
    setImportPending(true);
    setImportError(null);
    try {
      const csv = await file.text();
      const workbook = await requestJson('/api/workbooks/import', {
        method: 'POST',
        body: {name: file.name, csv}
      });
      setImportOpen(false);
      setFile(null);
      navigate(`/workbooks/${workbook.id}`);
    } catch (e) {
      setImportError(e.status === 400 ? 'Invalid CSV file format. Import failed.' : e.message);
    } finally {
      setImportPending(false);
    }
  };

  useEffect(() => {
    let live = true;
    requestJson('/api/workbooks')
      .then((list) => { if (live) setWorkbooks(list); })
      .catch((e) => { if (live) setError(e); });
    return () => { live = false; };
  }, []);

  return (
    <main className="home-page">
      <h1>Workbooks</h1>
      <button type="button" className="new-workbook-button" onClick={() => navigate('/workbooks/new')}>New blank workbook</button>
      <button type="button" className="import-csv-button" onClick={() => { setImportError(null); setFile(null); setImportOpen(true); }}>Import CSV</button>
      <Dialog.Root open={importOpen} onOpenChange={setImportOpen}>
        <DialogSurface title="Import CSV" description="Import a CSV file as a new workbook.">
          <form onSubmit={(event) => { event.preventDefault(); confirmImport(); }}>
            <label>
              CSV file
              <input type="file" accept=".csv,text/csv" aria-label="CSV file"
                onChange={(event) => { setFile(event.target.files?.[0] || null); setImportError(null); }} />
            </label>
            {importError && <p role="alert">{importError}</p>}
            <button type="submit" disabled={!file || importPending}>Confirm import</button>
          </form>
        </DialogSurface>
      </Dialog.Root>
      {error && <p role="alert">{error.message}</p>}
      {workbooks === null && !error && <p>Loading…</p>}
      {workbooks !== null && (
        <ul className="workbook-list">
          {workbooks.map((workbook) => (
            <li key={workbook.id} className="workbook-record">
              <Link to={`/workbooks/${workbook.id}`}>{workbook.name}</Link>
              <span>Last updated: {workbook.lastUpdated}</span>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
