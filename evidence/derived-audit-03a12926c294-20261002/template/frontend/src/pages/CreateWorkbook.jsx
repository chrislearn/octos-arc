import {useNavigate} from 'react-router';
import {useAsyncAction} from '../shared/interactions.jsx';
import {requestJson} from '../shared/request.js';
import './editor.css';

export default function CreateWorkbook() {
  const navigate = useNavigate();
  const {run, pending, error} = useAsyncAction();

  const submit = (event) => {
    event.preventDefault();
    run(async () => {
      const workbook = await requestJson('/api/workbooks', {
        method: 'POST',
        body: {name: 'Untitled workbook'}
      });
      navigate(`/workbooks/${workbook.id}`);
    }).catch(() => {});
  };

  return (
    <main className="editor-page">
      <h1>New blank workbook</h1>
      {error && <p role="alert">{error.message}</p>}
      <form onSubmit={submit}>
        <button type="submit" disabled={pending}>Create</button>
      </form>
    </main>
  );
}
