"""Version-bound decisions for harness-generated tests; never an application oracle."""
from __future__ import annotations
import hashlib
import json
import re
import time
from pathlib import Path

VERSION = 1
REASONS = {'requirement_conflict', 'unsupported_constraint', 'fixture_error', 'wrong_action'}
START = re.compile(r"^test\('((?:\\.|[^'\\])*)',", re.M)


def digest(value) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()


def test_block(source: str, title: str) -> str | None:
    starts = list(START.finditer(source))
    matches = [i for i, m in enumerate(starts) if m.group(1).replace("\\'", "'") == title]
    if len(matches) != 1:
        return None  # Ambiguous titles cannot be filtered safely.
    i = matches[0]
    return source[starts[i].start(): starts[i + 1].start() if i + 1 < len(starts) else len(source)]


def grounded_verdict(review: dict | None, requirement: str, block: str) -> bool:
    if not review or review.get('verdict') not in {'spec_error', 'oracle_dispute'}:
        return False
    quote, test_quote = review.get('requirement_quote'), review.get('test_quote')
    return (review.get('reason_code') in REASONS and isinstance(quote, str) and len(quote.strip()) >= 12
            and quote in requirement and isinstance(test_quote, str) and len(test_quote.strip()) >= 12
            and test_quote in block and ('expect' in test_quote or 'await ' in test_quote)
            and isinstance(review.get('evidence'), str) and len(review['evidence'].strip()) >= 20)


class TestPolicy:
    def __init__(self, directory: Path, requirements, helper_hash: str):
        self.directory = directory.resolve()
        self.context = digest({'version': VERSION, 'requirements': requirements, 'helper': helper_hash})
        self.control = self.directory.parent / 'test-control'
        self.path = self.control / 'test-policy.json'
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        self.records = data.get('records', {}) if data.get('context') == self.context else {}
        if not isinstance(self.records, dict):
            self.records = {}

    def identity(self, rel: str, title: str) -> str:
        return digest({'file': rel, 'title': title})[:24]

    def valid_records(self) -> list[dict]:
        valid = []
        for row in self.records.values():
            if not isinstance(row, dict) or row.get('context') != self.context:
                continue
            if (row.get('origin') != 'derived' or row.get('state') not in {'valid', 'invalid', 'unresolved'}
                    or not isinstance(row.get('file'), str) or not isinstance(row.get('title'), str)):
                continue
            rel = Path(row['file'])
            if rel.is_absolute() or '..' in rel.parts or not str(rel).endswith('.spec.ts'):
                continue
            path = self.directory / rel
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(self.directory) or digest(path.read_text()) != row.get('file_hash'):
                    continue
                if test_block(path.read_text(), row['title']) is None:
                    continue
            except (OSError, KeyError):
                continue
            valid.append(row)
        return valid

    def decide(self, rel: str, title: str, source: str, state: str, evidence: str,
               reviews=(), failure_hash: str = '') -> dict:
        path = Path(rel)
        if path.is_absolute() or '..' in path.parts or not rel.endswith('.spec.ts'):
            raise ValueError('decision must reference a generated spec within its directory')
        if state not in {'invalid', 'unresolved', 'valid'} or test_block(source, title) is None:
            raise ValueError('invalid or ambiguous generated-test decision')
        row = {'id': self.identity(rel, title), 'origin': 'derived', 'context': self.context,
               'file': rel, 'title': title, 'file_hash': digest(source),
               'test_hash': digest(test_block(source, title)), 'state': state,
               'execution': 'quarantined' if state == 'invalid' else 'not_run',
               'evidence': evidence, 'reviews': list(reviews), 'failure_hash': failure_hash,
               'timestamp': time.time(), 'version': VERSION}
        self.records[row['id']] = row
        self.control.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'version': VERSION, 'context': self.context,
                                   'records': self.records}, ensure_ascii=False, indent=2) + '\n')
        temp.replace(self.path)
        with (self.control / 'test-decisions.jsonl').open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        return row

    def quarantines(self) -> dict[str, list[dict]]:
        result = {}
        for row in self.valid_records():
            if row['state'] == 'invalid':
                result.setdefault(row['file'], []).append(row)
        return result
