import {useEffect, useState} from 'react';
import {Link, useSearchParams} from 'react-router';
import {requestJson} from '../shared/request.js';

export default function Search() {
  const [params] = useSearchParams();
  const q = params.get('q') || '';
  const [results, setResults] = useState(null);

  useEffect(() => {
    let stale = false;
    setResults(null);
    requestJson('/api/repositories?q=' + encodeURIComponent(q))
      .then(items => { if (!stale) setResults(items); })
      .catch(() => { if (!stale) setResults([]); });
    return () => { stale = true; };
  }, [q]);

  return <main style={{padding: '2rem'}}>
    <h1>Search results</h1>
    {results === null ? <p>Searching…</p> : results.length === 0
      ? <p>No results</p>
      : <ul style={{listStyle: 'none', padding: 0}}>
        {results.map(item => (
          <li key={item.owner + '/' + item.name} style={{padding: '0.75rem 0', borderBottom: '1px solid #eee'}}>
            <div>
              {item.owner}/<Link to={'/repos/' + encodeURIComponent(item.owner) + '/' + encodeURIComponent(item.name)}>{item.name}</Link>
            </div>
            <div style={{color: '#666'}}>{item.visibility}</div>
            {item.description ? <div>{item.description}</div> : null}
          </li>
        ))}
      </ul>}
  </main>;
}
