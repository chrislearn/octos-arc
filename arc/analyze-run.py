#!/usr/bin/env python3
"""Read-only cost/failure diagnostics; never prints prompts or credentials."""
import argparse
from collections import Counter
import json
from pathlib import Path

from metrics import _iter_jsonl, summarize
from reply_quality import prune_degenerate_edits


def analyze(root: Path) -> dict:
    result = summarize(root)
    labels = {}
    for row in _iter_jsonl(root / '.arc/llm-usage.jsonl'):
        label = row.get('label', 'unknown')
        item = labels.setdefault(label, {'requests': 0, 'prompt_tokens': 0,
            'completion_tokens': 0, 'elapsed_ms': 0, 'cache_hit': 0})
        item['requests'] += int(row.get('requests') or 1)
        for key in ('prompt_tokens', 'completion_tokens', 'elapsed_ms'):
            item[key] += row.get(key, 0) or 0
        item['cache_hit'] += row.get('prompt_cache_hit_tokens', 0) or 0
    result['costliest_labels'] = sorted(
        ({'label': name, **row} for name, row in labels.items()),
        key=lambda row: row['prompt_tokens'] + row['completion_tokens'], reverse=True)
    result['retained_truncated_replies'] = {
        path.name: prune_degenerate_edits(path.read_text(encoding='utf-8'))[1]
        for path in sorted((root / '.arc/truncated-replies').glob('*.txt'))}
    result['traceability_state_counts'] = dict(Counter(result['node_states'].values()))
    result['traceability_state_scope'] = 'May include folder/alias nodes; use full-suite measurements for the score.'
    replies = list(result['retained_truncated_replies'].values())
    result['truncated_reply_totals'] = {
        'replies': len(replies),
        **{field: sum(row[field] for row in replies) for field in (
            'chars', 'retained_chars', 'edit_blocks', 'noop_edits', 'noop_chars',
            'repeated_edit_blocks', 'cycle_trimmed')},
    }
    # These are payload diagnostics, not saved/billed token estimates: raw
    # outputs were already charged, and trimming does not validate semantics.
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.output_dir.resolve()), ensure_ascii=False, indent=2))
