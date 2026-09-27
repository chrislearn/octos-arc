"""Lossless tool pairing and version-aware read compaction; no provider calls."""
from __future__ import annotations
import hashlib
import json
import re


def read_records(messages):
    calls, epochs, records, versions = {}, {}, [], {}
    for position, message in enumerate(messages):
        for call in message.get("tool_calls", []) or []:
            function = call.get("function") or {}
            try:
                args = json.loads(function.get("arguments", "{}"))
            except (ValueError, TypeError):
                args = {}
            if not isinstance(args, dict):
                args = {}
            path = args.get("path") or args.get("file_path") or args.get("file")
            calls[call.get("id")] = (function.get("name"), path, args)
        if message.get("role") != "tool":
            continue
        name, path, args = calls.get(message.get("tool_call_id"), (None, None, {}))
        if not isinstance(path, str):
            continue
        if name in {"edit_file", "write_file", "apply_patch", "diff_edit"}:
            # Even a failed edit invalidates speculation about the current file.
            epochs[path] = epochs.get(path, 0) + 1
            versions.pop(path, None)
        if name == "read_file" and isinstance(message.get("content"), str):
            content = message["content"]
            lines = {int(n): text for n, text in re.findall(r"(?m)^\s*(\d+)│ (.*)$", content)}
            range_key = json.dumps({key: args[key] for key in
                ("start_line", "end_line", "offset", "limit") if key in args}, sort_keys=True)
            previous = versions.setdefault(path, {"ranges": {}, "lines": {}})
            if ((range_key in previous["ranges"] and previous["ranges"][range_key] != content)
                    or any(n in previous["lines"] and previous["lines"][n] != value for n, value in lines.items())):
                epochs[path] = epochs.get(path, 0) + 1
                previous = versions[path] = {"ranges": {}, "lines": {}}
            previous["ranges"][range_key] = content
            previous["lines"].update(lines)
            records.append({"position": position, "tool_call_id": message.get("tool_call_id"), "path": path,
                "epoch": epochs.get(path, 0), "range": {key: args[key] for key in
                    ("start_line", "end_line", "offset", "limit") if key in args},
                "observation_sha256": hashlib.sha256(content.encode()).hexdigest(), "chars": len(content),
                "lines": lines})
    return records


def compact_context(body: bytes) -> bytes:
    """Only remove reads fully covered by later identical content in the same epoch.

    Do not mix pagination from different file versions or synthesize file contents.
    IDs/order/tool pairs and refusals are retained. A->B->A content remains explicit.
    """
    try:
        data = json.loads(body)
        messages = data.get("messages", [])
        seen, covered, changed = set(), {}, False
        for row in reversed(read_records(messages)):
            key = (row["path"], row["epoch"], row["observation_sha256"])
            lines = covered.setdefault((row["path"], row["epoch"]), {})
            identical = key in seen or (bool(row["lines"]) and all(lines.get(n) == text for n, text in row["lines"].items()))
            if identical and row["chars"] > 160:
                messages[row["position"]]["content"] = (
                    f"[Earlier read omitted: later identical read below covers {row['path']} "
                    f"range={row['range']} observation_sha256={row['observation_sha256']}. "
                    "Use the later result; reread after any edit.]")
                changed = True
            seen.add(key)
            for n, text in row["lines"].items():
                lines.setdefault(n, text)
        return json.dumps(data, ensure_ascii=False).encode() if changed else body
    except (ValueError, TypeError, AttributeError):
        return body


def context_metrics(body: bytes) -> dict:
    try:
        data = json.loads(body)
        messages = data.get("messages", [])
        records = read_records(messages)
        seen, repeated = set(), 0
        for row in records:
            key = (row["path"], row["epoch"], row["observation_sha256"])
            if key in seen:
                repeated += row["chars"]
            seen.add(key)
        return {"history_chars": sum(len(str(m.get("content") or "")) for m in messages),
                "duplicate_read_chars": repeated,
                "reads": [{k: v for k, v in row.items() if k != "lines"} for row in records],
                "tools": [t.get("function", {}).get("name") for t in data.get("tools", [])]}
    except (ValueError, TypeError, AttributeError):
        return {"error": "context metadata unavailable"}
