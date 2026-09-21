"""Task-neutral diagnostics for exact-edit degeneration (no model calls or writes).

This module is deliberately independent of the live runner so captured responses
can be inspected without changing an in-progress experiment.
"""
from collections import Counter

from codegen import EDIT_BLOCK, FILE_BLOCK, iter_blocks


class StreamRepetitionGuard:
    """Conservative stop signal, never a rewrite or proof of completion.

    Check at most once per 2048 new characters. Complete repeated operation
    envelopes are stronger evidence than repeated ordinary source lines.
    """
    def __init__(self):
        self.checked_chars = 0

    def check(self, text: str) -> str | None:
        if len(text) - self.checked_chars < 2048:
            return None
        self.checked_chars = len(text)
        blocks = list(iter_blocks(text))
        noops = [m for m in blocks if m.re is EDIT_BLOCK and m['search'] == m['replacement']]
        if len(noops) >= 6 and sum(len(m[0]) for m in noops) >= 2048:
            return "repeated_noop_edits"
        for width in range(1, min(8, len(blocks) // 3) + 1):
            tail = blocks[-3 * width:]
            keys = [m[0] for m in tail]
            if (keys[:width] == keys[width:2 * width] == keys[2 * width:]
                    and sum(map(len, keys)) >= 2048
                    and not any(text[a.end():b.start()].strip() for a, b in zip(tail, tail[1:]))):
                return "repeated_operation_cycle"
        # Long exact periodic suffixes also catch degeneration inside an
        # unfinished FILE. Six copies and >= 4096 chars avoid small UI patterns.
        tail = text[-49152:]
        for width in range(256, min(8192, len(tail) // 6) + 1):
            if width * 6 >= 4096 and tail[-width * 6:] == tail[-width:] * 6:
                return "periodic_text_suffix"
        return None


def _blocks(text):
    yield from iter_blocks(text)


def reply_quality(text: str) -> dict:
    blocks = list(_blocks(text))
    edits = [m for m in blocks if m.re is EDIT_BLOCK]
    files = [m for m in blocks if m.re is FILE_BLOCK]
    counts = Counter((m['path'], m['search'], m['replacement']) for m in edits)
    noops = [m for m in edits if m['search'] == m['replacement']]
    return {
        'chars': len(text),
        'file_blocks': len(files),
        'edit_blocks': len(edits),
        'noop_edits': len(noops),
        'noop_chars': sum(m.end() - m.start() for m in noops),
        'repeated_edit_blocks': sum(n - 1 for n in counts.values()),
        'edits_by_path': dict(Counter(m['path'] for m in edits)),
    }


def prune_degenerate_edits(text: str) -> tuple[str, dict]:
    """Drop inert edits and bound an exact, long, periodic EDIT-only suffix.

    Never deduplicate arbitrary edits: A->B, B->A, A->B has meaningful order.
    Only a suffix repeating the same block cycle at least three times qualifies;
    keep its first cycle plus the final phase and flag incomplete generation. All retained
    anchors still need normal atomic validation before any file is written.
    A non-periodic later block prevents cycle trimming. No-op edits need no anchor
    lookup because they cannot change a byte, even if their SEARCH is stale.
    """
    info = reply_quality(text)
    # Remove from the end to preserve earlier spans.
    cleaned = text
    for match in reversed(list(_blocks(text))):
        if match.re is EDIT_BLOCK and match['search'] == match['replacement']:
            cleaned = cleaned[:match.start()] + cleaned[match.end():]
    blocks = list(_blocks(cleaned))
    keys = [(m.re.pattern, m.group(0)) for m in blocks]
    cut = None
    for width in range(1, min(8, len(blocks) // 3) + 1):
        start = len(blocks) - width
        while start > 0 and keys[start - 1] == keys[start - 1 + width]:
            start -= 1
        if len(blocks) - start < width * 3:
            continue
        suffix = blocks[start:]
        if any(m.re is not EDIT_BLOCK for m in suffix):
            continue
        if sum(m.end() - m.start() for m in suffix) < 1024:
            continue
        # Do not erase unrelated prose/unknown protocols embedded in the cycle.
        if any(cleaned[a.end():b.start()].strip() for a, b in zip(suffix, suffix[1:])):
            continue
        tail = cleaned[blocks[-1].end():].strip()
        if tail and not tail.startswith('<<<EDIT ') and tail != '<<<NO CHANGE>>>':
            continue
        # A periodic tail may end halfway through a cycle. Preserve that final
        # phase: A->B, B->A repeated and ending in A->B must still end in B.
        retained = width + (len(blocks) - start) % width
        candidate = blocks[start + retained].start()
        cut = candidate if cut is None else min(cut, candidate)
    info['cycle_trimmed'] = cut is not None
    if cut is not None:
        cleaned = cleaned[:cut].rstrip() + '\n'
    info['retained_chars'] = len(cleaned)
    return cleaned, info
