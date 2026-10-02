import {useEffect, useState} from 'react';
import {Link, useParams} from 'react-router';
import {requestJson} from '../shared/request.js';

export default function FileContent() {
  const {owner, name, branch, path} = useParams();
  const [file, setFile] = useState(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let stale = false;
    setFile(null);
    setMissing(false);
    requestJson('/api/repositories/' + encodeURIComponent(owner) + '/' + encodeURIComponent(name) +
      '/branches/' + encodeURIComponent(branch) + '/files/' + path)
      .then(record => { if (!stale) setFile(record); })
      .catch(() => { if (!stale) setMissing(true); });
    return () => { stale = true; };
  }, [owner, name, branch, path]);

  const base = '/repos/' + encodeURIComponent(owner) + '/' + encodeURIComponent(name);
  if (missing) {
    return <main style={{padding: '2rem'}}>
      <h1>File not found</h1>
      <p><Link to={base}>Back to repository</Link></p>
    </main>;
  }
  if (!file) return <main style={{padding: '2rem'}}><p>Loading…</p></main>;
  return <main style={{padding: '2rem'}}>
    <p><Link to={base}>{owner}/{name}</Link></p>
    <h1>{file.path}</h1>
    <pre style={{background: '#f6f8fa', padding: '1rem', whiteSpace: 'pre-wrap'}}>{file.content}</pre>
  </main>;
}
