"""Bounded, advisory source relationships; never a substitute for a compiler."""
import hashlib
import posixpath
import re


class SourceIndex:
    def __init__(self, sources):
        self.sources = dict(sources)
        self.versions = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in self.sources.items()}
        self.dependencies = {p: set() for p in self.sources}
        for path, source in self.sources.items():
            for name in re.findall(r'''(?:from\s*|import\s*|require\s*\(\s*)['"](\.[^'"]+)['"]''', source):
                base = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
                candidates = [base] + [base + ext for ext in ('.js', '.jsx', '.ts', '.tsx', '/index.js', '/index.ts', '/index.tsx')]
                target = next((p for p in candidates if p in self.sources), None)
                if target:
                    self.dependencies[path].add(target)

    def related(self, paths):
        paths = set(paths) & self.sources.keys()
        return paths | {q for p in paths for q in self.dependencies[p]} | {
            p for p, deps in self.dependencies.items() if deps & paths}

    def render(self, paths, limit=5000):
        lines = ['Source relationships (heuristic; verify callers before changing contracts):']
        for path in sorted(self.related(paths)):
            source = self.sources[path]
            symbols = re.findall(r'(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function|class|const)\s+(\w+)', source)
            props = re.findall(r'<([A-Z]\w*)\b([^<>]*?)/?>', source)
            calls = [name + '(' + ','.join(re.findall(r'\b(\w+)\s*=', attrs)) + ')' for name, attrs in props]
            lines.append(f'{path}: imports={",".join(sorted(self.dependencies[path]))}; symbols={",".join(symbols[:20])}; components={",".join(calls[:20])}')
        return '\n'.join(lines)[:limit]
