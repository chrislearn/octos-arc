// Optional multi-page Vite config for frontend/src/**/*.html.
import {readFileSync, readdirSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const project = dirname(fileURLToPath(import.meta.url));
const root = join(project, 'src');
const manifest = JSON.parse(readFileSync(join(project, 'package.json'), 'utf8'));
const has = name => ['dependencies', 'devDependencies', 'optionalDependencies']
  .some(group => Object.hasOwn(manifest[group] || {}, name));

function htmlBelow(directory) {
  return readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const file = join(directory, entry.name);
    return entry.isDirectory() ? htmlBelow(file) : entry.isFile() && entry.name.endsWith('.html') ? [file] : [];
  });
}

const input = Object.fromEntries(htmlBelow(root).map(file => [relative(root, file), file]));
const plugins = [];
if (has('@vitejs/plugin-react')) plugins.push((await import('@vitejs/plugin-react')).default());
if (has('@tailwindcss/vite')) plugins.push((await import('@tailwindcss/vite')).default());

export default {
  root,
  plugins,
  build: {outDir: resolve(project, 'dist'), emptyOutDir: true, rollupOptions: {input}},
};
