import {useEffect, useState} from 'react';
import {Link, useParams} from 'react-router';
import {requestJson} from '../shared/request.js';

export default function Repository() {
  const {owner, name} = useParams();
  const [repo, setRepo] = useState(null);
  const [missing, setMissing] = useState(false);
  const [denied, setDenied] = useState('');

  useEffect(() => {
    let stale = false;
    setRepo(null);
    setMissing(false);
    setDenied('');
    requestJson('/api/repositories/' + encodeURIComponent(owner) + '/' + encodeURIComponent(name))
      .then(record => { if (!stale) setRepo(record); })
      .catch(err => {
        if (stale) return;
        if (err.status === 403) setDenied(err.message || 'Access denied');
        else setMissing(true);
      });
    return () => { stale = true; };
  }, [owner, name]);

  if (denied) {
    return <main style={{padding: '2rem'}}>
      <h1>{denied}</h1>
      <p>You do not have access to this repository.</p>
    </main>;
  }
  if (missing) {
    return <main style={{padding: '2rem'}}>
      <h1>Repository not found</h1>
      <p>This repository does not exist or you do not have access to it.</p>
    </main>;
  }
  if (!repo) return <main style={{padding: '2rem'}}><p>Loading…</p></main>;
  const base = '/repos/' + encodeURIComponent(owner) + '/' + encodeURIComponent(name);
  const ownerLink = repo.owner_type === 'organization' && repo.owner_identifier
    ? <Link to={'/orgs/' + encodeURIComponent(repo.owner_identifier)}>{repo.owner}</Link>
    : repo.owner;
  return <main style={{padding: '2rem'}}>
    <h1>{ownerLink}/{repo.name}</h1>
    <p>{repo.visibility}</p>
    {repo.description ? <p>{repo.description}</p> : null}
    <nav style={{display: 'flex', gap: '1rem', borderBottom: '1px solid #ddd', paddingBottom: '0.5rem'}}>
      <Link to={base}>Code</Link>
      <Link to={base + '/issues'}>Issues</Link>
      <Link to={base + '/pulls'}>Pull requests</Link>
    </nav>
    <p>Default branch: {repo.default_branch}</p>
    <h2>Files</h2>
    <ul style={{listStyle: 'none', padding: 0}}>
      {repo.files.map(file => (
        <li key={file} style={{padding: '0.5rem 0', borderBottom: '1px solid #eee'}}>
          <Link to={base + '/file/' + repo.default_branch + '/' + file.split('/').map(encodeURIComponent).join('/')}>{file}</Link>
        </li>
      ))}
    </ul>
  </main>;
}
