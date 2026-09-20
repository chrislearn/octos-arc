// Task-neutral optional frontend build. Run with `node build.mjs` from frontend/.
import {cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';

const root = process.cwd();
const manifest = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
const has = name => ['dependencies', 'devDependencies', 'optionalDependencies']
  .some(group => Object.hasOwn(manifest[group] || {}, name));
const localBin = name => join(root, 'node_modules', '.bin', name);

function run(name, args) {
  const bin = localBin(name);
  if (!existsSync(bin)) throw new Error(`${name} is not installed locally; declare it in frontend/package.json`);
  const result = spawnSync(bin, args, {cwd: root, stdio: 'inherit', env: process.env});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${name} build failed (${result.status ?? result.signal})`);
}

function filesBelow(directory) {
  if (!existsSync(directory)) return [];
  return readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const file = join(directory, entry.name);
    return entry.isDirectory() ? filesBelow(file) : entry.isFile() ? [file] : [];
  });
}

const source = join(root, 'src');
const output = join(root, 'dist');
if (has('vite')) {
  run('vite', ['build', '--config', 'vite.config.mjs']);
} else {
  if (filesBelow(source).some(file => /\.(jsx|tsx|ts|vue)$/.test(file))) {
    throw new Error('JSX/TypeScript/Vue sources require a local bundler; do not copy uncompiled source to dist');
  }
  rmSync(output, {recursive: true, force: true});
  if (existsSync(source)) cpSync(source, output, {recursive: true});
  else mkdirSync(output, {recursive: true});
  const publicDir = join(root, 'public');
  if (existsSync(publicDir)) cpSync(publicDir, output, {recursive: true});
  const tailwind = filesBelow(source).filter(file => file.endsWith('.css') &&
    /@import\s+["']tailwindcss(?:["'/;])/i.test(readFileSync(file, 'utf8')));
  if (tailwind.length && !has('@tailwindcss/cli')) {
    throw new Error('Tailwind CSS source needs local @tailwindcss/cli and tailwindcss packages');
  }
  for (const file of tailwind) {
    const target = join(output, relative(source, file));
    mkdirSync(dirname(target), {recursive: true});
    run('tailwindcss', ['-i', file, '-o', target]);
  }
}

if (has('htmx.org')) {
  const vendored = join(root, 'node_modules', 'htmx.org', 'dist', 'htmx.min.js');
  if (!existsSync(vendored)) throw new Error('htmx.org is declared but its local dist/htmx.min.js is missing');
  const target = join(output, 'vendor', 'htmx.min.js');
  mkdirSync(dirname(target), {recursive: true});
  cpSync(vendored, target);
}
