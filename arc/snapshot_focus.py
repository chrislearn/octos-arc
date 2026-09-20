"""Select relevant portions of a rendered accessibility tree, without DOM writes."""
import re


def focus_interaction_snapshot(text: str) -> str:
    """Put visible interaction surfaces before lengthy background record lists.

    This selects lines, not YAML objects: diagnostics can contain placeholders
    and elision markers. Preserve source lines/indentation and identify omission.
    No surface means no change. Hidden subtrees never become a focus candidate.
    """
    lines = text.splitlines()

    def indent(line):
        return len(line) - len(line.lstrip())

    def end_of(start):
        depth = indent(lines[start])
        end = start + 1
        while end < len(lines):
            if lines[end].strip() and indent(lines[end]) <= depth:
                break
            end += 1
        return end

    hidden = set()
    for i, line in enumerate(lines):
        if re.match(r'^\s*-\s+[\w-]+\b.*\[aria-hidden\](?::|\s|$)', line):
            hidden.update(range(i, end_of(i)))
    spans = []
    covered = set()
    for i, line in enumerate(lines):
        if i in hidden or i in covered:
            continue
        if re.match(r'^\s*-\s+(?:dialog|alertdialog|menu|listbox)\b', line):
            end = end_of(i)
            spans.append((i, end))
            covered.update(range(i, end))
    if not spans:
        return text
    focus = [lines[i] for start, end in spans for i in range(start, end) if i not in hidden]
    background = [line for i, line in enumerate(lines) if i not in covered and i not in hidden]
    return ('[Interaction surfaces first; aria-hidden background omitted]\n'
            + '\n'.join(focus) + '\n[Other rendered content]\n' + '\n'.join(background))
