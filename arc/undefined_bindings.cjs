// Harness-owned, read-only source check. Uses Babel already installed by the React/Vite stack.
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');

const frontend = process.argv[2];
const fromFrontend = createRequire(path.join(frontend, 'package.json'));
let parser, traverse;
try {
  parser = fromFrontend('@babel/parser');
  traverse = fromFrontend('@babel/traverse').default;
} catch (error) {
  process.stdout.write(JSON.stringify({ status: 'unknown', reason: `Babel parser unavailable: ${error.message}` }));
  process.exit(0);
}

const allowed = new Set([...Object.getOwnPropertyNames(globalThis),
  'window', 'document', 'navigator', 'location', 'history', 'localStorage', 'sessionStorage',
  'alert', 'confirm', 'prompt', 'File', 'FileReader', 'Blob', 'Image', 'ResizeObserver',
  'IntersectionObserver', 'MutationObserver', 'HTMLElement', 'HTMLInputElement',
  'CustomEvent', 'Event', 'KeyboardEvent', 'MouseEvent', 'URL', 'URLSearchParams',
  'requestAnimationFrame', 'cancelAnimationFrame', 'atob', 'btoa', 'crypto', 'performance',
  'indexedDB', 'matchMedia', 'getComputedStyle', 'FormData', 'TextEncoder', 'TextDecoder',
  'AbortController', 'fetch', 'WebSocket', 'Worker', 'CSS', 'DOMParser', 'Node', 'NodeFilter',
  'process', 'Buffer', 'global']);

const diagnostics = [];
let skippedTypeScript = 0;
const sourceRoot = path.join(frontend, 'src');
function scan(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) { scan(file); continue; }
    if (!entry.isFile() || !/\.[cm]?[jt]sx?$/.test(entry.name)) continue;
    if (/\.[cm]?tsx?$/.test(entry.name)) { skippedTypeScript++; continue; }
    let ast;
    try {
      ast = parser.parse(fs.readFileSync(file, 'utf8'), {
        sourceType: 'unambiguous', plugins: ['jsx', 'typescript']
      });
    } catch (error) {
      // The build owns syntax failures. Avoid misclassifying a parser mismatch.
      continue;
    }
    const seen = new Set();
    traverse(ast, { ReferencedIdentifier(identifier) {
      const name = identifier.node.name;
      if (allowed.has(name) || identifier.scope.hasBinding(name)) return;
      const line = identifier.node.loc?.start.line || 0;
      const key = `${name}:${line}`;
      if (seen.has(key)) return;
      seen.add(key);
      diagnostics.push({ file: path.relative(frontend, file), line, name });
    }});
  }
}
try {
  if (fs.existsSync(sourceRoot)) scan(sourceRoot);
  const names = new Map();
  for (const row of diagnostics) {
    const current = names.get(row.name);
    if (current) current.count++;
    else names.set(row.name, { name: row.name, count: 1, file: row.file, line: row.line });
  }
  process.stdout.write(JSON.stringify({ status: diagnostics.length ? 'failed' : skippedTypeScript ? 'unknown' : 'passed',
                                     diagnostics: diagnostics.slice(0, 40),
                                     total: diagnostics.length,
                                     names: [...names.values()],
                                     reason: skippedTypeScript ? `${skippedTypeScript} TypeScript files require compiler-based scope checking` : undefined }));
} catch (error) {
  process.stdout.write(JSON.stringify({ status: 'unknown', reason: String(error.message || error) }));
}
