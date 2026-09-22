"""Local pass-through proxy in front of the OpenAI-compatible endpoint.

Why: the octos kernel emits DeepSeek's `reasoning_effort` / `thinking` fields
only for api.deepseek.com URLs, while the ARC proxy (api.arc-bench.com)
honours them too — measured on 2026-09-13: default 455 completion tokens,
`reasoning_effort: low` 279, `thinking: disabled` 132 for the same prompt.
This proxy injects the fields into every chat completion request and logs
the provider's `usage` block per request (exact billed tokens, cache hits).

Pure functions (`inject_reasoning`, `usage_record`) are unit-tested; the
server is stdlib `http.server` on 127.0.0.1 and forwards headers verbatim.
"""

from __future__ import annotations

import json
import hashlib
import ipaddress
import os
import re
import threading
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from reply_quality import StreamRepetitionGuard


def collect_codegen_stream(response, deadline: float | None = None) -> tuple[bytes, str | None]:
    """Collect SSE incrementally; close the connection on strong repetition.

    Report interruption as length, NEVER stop/success. Missing provider usage
    remains missing: early cancellation cannot establish final billed tokens.
    Only the tool-less codegen path calls this; native tool deltas are untouched.
    """
    guard = StreamRepetitionGuard()
    text, reasoning, usage, finish = "", "", None, None
    identity = {}
    aborted = None
    for raw in response:
        if deadline is not None and time.monotonic() >= deadline:
            aborted = "turn_deadline"
            break
        if not raw.startswith(b"data:"):
            continue
        payload = raw[5:].strip()
        if payload == b"[DONE]":
            break
        try:
            event = json.loads(payload)
        except (ValueError, UnicodeError):
            raise ValueError("invalid codegen SSE event")
        identity.update({key: event[key] for key in ("id", "model", "created") if key in event})
        if event.get("error"):
            raise ValueError("upstream codegen SSE error")
        if event.get("usage"):
            usage = event["usage"]
        for choice in event.get("choices", []):
            if choice.get("index", 0) != 0:
                raise ValueError("multiple codegen choices are unsupported")
            delta = choice.get("delta") or {}
            if delta.get("tool_calls"):
                raise ValueError("unexpected tools in tool-less codegen stream")
            text += delta.get("content") or ""
            reasoning += delta.get("reasoning_content") or ""
            finish = choice.get("finish_reason") or finish
        aborted = "response_size_limit" if len(text) + len(reasoning) > 2_000_000 else guard.check(text)
        if aborted:
            break
    if aborted or not finish:
        aborted = aborted or "incomplete_stream"
        finish = "length"
    message = {"role": "assistant", "content": text}
    if reasoning:
        message["reasoning_content"] = reasoning
    result = dict(identity, object="chat.completion", choices=[{"index": 0, "message": message, "finish_reason": finish}])
    if usage is not None:
        result["usage"] = usage
    if aborted:
        result["arc_stream_stop"] = aborted
    return json.dumps(result, ensure_ascii=False).encode(), aborted

HOP_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "accept-encoding"}


def cap_output_tokens(body: bytes, limit: int) -> bytes:
    """An explicit recovery ceiling, separate from the kernel's token floor."""
    if limit <= 0:
        return body
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or 'messages' not in data:
        return body
    field = 'max_completion_tokens' if 'max_completion_tokens' in data else 'max_tokens'
    current = data.get(field)
    data[field] = min(current, limit) if type(current) is int and current > 0 else limit
    return json.dumps(data, ensure_ascii=False).encode('utf-8')


def open_upstream(req, *, timeout: float):
    """Local providers must not traverse HTTP(S)_PROXY; remote ones still may."""
    host = (urlsplit(req.full_url).hostname or "").lower()
    local = host == "localhost" or host.endswith(".localhost") or host == "0.0.0.0"
    try:
        local = local or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if local:
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def routed_model_missing(status: int, payload: bytes, model: str) -> bool:
    """Only an explicit model-not-found response warrants a model fallback."""
    if status != 404 or not model:
        return False
    try:
        error = json.loads(payload).get("error")
    except (ValueError, AttributeError):
        return False
    if not isinstance(error, dict):
        return False
    message = str(error.get("message", ""))
    named = re.search(r"model\s+['\"]([^'\"]+)['\"]", message, re.I)
    if named and named.group(1) != model:
        return False
    return (error.get("code") in {"model_not_found", "ModelNotFound"}
            or bool(re.search(r"\bmodel\b.{0,180}\b(?:not found|does not exist)\b", message, re.I)))


def model_routes(raw: str) -> list[dict]:
    """Ordered, opt-in model policies. No model names or task IDs are defaults."""
    rules = json.loads(raw or "[]")
    if not isinstance(rules, list):
        raise ValueError("model routes must be a JSON array")
    phases = {"implement", "repair", "verify", "design"}
    parameters = {"temperature", "top_p", "max_tokens", "max_completion_tokens", "thinking", "reasoning_effort", "enable_thinking"}
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - {"model", "phases", "max_input_chars", "tools", "images", "parameters"}:
            raise ValueError("invalid model route fields")
        if not isinstance(rule.get("model"), str) or not rule["model"].strip():
            raise ValueError("model route requires a provider model ID")
        selected = rule.get("phases", list(phases))
        if not isinstance(selected, list) or not selected or any(p not in phases for p in selected):
            raise ValueError("invalid model route phases")
        limit = rule.get("max_input_chars")
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("max_input_chars must be positive")
        for name in ("tools", "images"):
            if name in rule and type(rule[name]) is not bool:
                raise ValueError(f"{name} must be boolean")
        opts = rule.get("parameters", {})
        if not isinstance(opts, dict) or set(opts) - parameters:
            raise ValueError("model route parameters cannot replace messages, tools or routing")
        if "max_tokens" in opts and "max_completion_tokens" in opts:
            raise ValueError("choose one output token limit")
    return rules


def configured_model_routes(env=None, bundle_dir: Path | None = None) -> str:
    """Environment wins (including empty); otherwise use optional bundle policy."""
    env = os.environ if env is None else env
    if "OCTOS_ARC_MODEL_ROUTES" in env:
        raw = env["OCTOS_ARC_MODEL_ROUTES"]
    else:
        path = (bundle_dir or Path(__file__).resolve().parent) / "model-routes.json"
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
    model_routes(raw)  # Reject invalid configuration before any provider request.
    return raw


def route_request(body: bytes, rules: list[dict], phase: str) -> bytes:
    """Choose per request from phase, complete input size and tool/image needs.

    Configuration order expresses preference; provider catalogs need not expose
    trustworthy prices. A repair can select a different model in the same task.
    Unmatched requests preserve the caller's model and parameters exactly.
    """
    if not rules:
        return body
    data = json.loads(body)
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        return body
    messages = data["messages"]
    has_images = any(isinstance(m.get("content"), list) and any(
        isinstance(c, dict) and c.get("type") in {"image_url", "input_image"}
        for c in m["content"]) for m in messages)
    needs_tools = bool(data.get("tools")) or any(m.get("tool_calls") or m.get("role") == "tool" for m in messages)
    chars = len(json.dumps({"messages": messages, "tools": data.get("tools", [])}, ensure_ascii=False, separators=(",", ":")))
    for rule in rules:
        if phase not in rule.get("phases", ["implement", "repair", "verify", "design"]):
            continue
        if rule.get("max_input_chars") is not None and chars > rule["max_input_chars"]:
            continue
        if needs_tools and not rule.get("tools", False):
            continue
        if has_images and not rule.get("images", False):
            continue
        data["model"] = rule["model"]
        # Do not carry vendor reasoning fields into a different model. The route
        # supplies supported fields explicitly; there is no name-based guess.
        data.pop("thinking", None)
        data.pop("reasoning_effort", None)
        data.pop("enable_thinking", None)
        opts = rule.get("parameters", {})
        if "max_completion_tokens" in opts:
            data.pop("max_tokens", None)
        if "max_tokens" in opts:
            data.pop("max_completion_tokens", None)
        data.update(opts)
        return json.dumps(data, ensure_ascii=False).encode()
    return body


def inject_reasoning(body: bytes, mode: str) -> bytes:
    """mode: "low"|"medium"|"high" -> reasoning_effort (+ thinking enabled);
    "none"/"off" -> thinking disabled. The turn's toggle takes precedence over
    kernel defaults; an existing enabled effort level is otherwise respected."""
    if not mode or mode == "passthrough":
        return body
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or "messages" not in data:
        return body
    model = str(data.get("model") or "").lower()
    # Qwen3.7 Plus uses a different wire parameter from DeepSeek. Sending
    # DeepSeek's thinking object (or no toggle) does not disable its default
    # reasoning mode. Limit this adapter to the documented hybrid family.
    if re.search(r"(?:^|/)qwen3\.7-plus(?:-|$)", model):
        data["enable_thinking"] = mode not in ("none", "off", "disabled")
        data.pop("thinking", None)
        data.pop("reasoning_effort", None)
        return json.dumps(data, ensure_ascii=False).encode("utf-8")
    if "deepseek" not in model:
        return body
    if mode in ("none", "off", "disabled"):
        data["thinking"] = {"type": "disabled"}
        data.pop("reasoning_effort", None)
    else:
        if data.get("reasoning_effort") in (None, "none", "off", "disabled"):
            data["reasoning_effort"] = mode
        data["thinking"] = {"type": "enabled"}
    if data.get("stream"):
        opts = data.get("stream_options") if isinstance(data.get("stream_options"), dict) else {}
        opts.setdefault("include_usage", True)
        data["stream_options"] = opts
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _usage_from_body(response_body: bytes):
    """JSON body -> its usage dict; SSE body -> usage of the last chunk carrying one."""
    text = response_body.decode("utf-8", errors="replace")
    if text.lstrip().startswith("data:"):
        usage = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            try:
                chunk = json.loads(line[5:].strip())
            except ValueError:
                continue
            if isinstance(chunk, dict) and isinstance(chunk.get("usage"), dict):
                usage = chunk["usage"]
        return usage
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data.get("usage") if isinstance(data, dict) else None


def request_shape(body: bytes) -> dict | None:
    """Character counts per message role and tool schemas — what the prompt is
    made of (kernel system prompt vs tool schemas vs conversation)."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or "messages" not in data:
        return None
    shape: dict = {"messages": len(data.get("messages") or []), "tools": len(data.get("tools") or []),
                   "tools_chars": len(json.dumps(data.get("tools") or [], ensure_ascii=False))}
    if isinstance(data.get("enable_thinking"), bool):
        shape["enable_thinking"] = data["enable_thinking"]
    for msg in data.get("messages") or []:
        role = str(msg.get("role", "?"))
        content = msg.get("content")
        chars = len(content) if isinstance(content, str) else len(json.dumps(content or "", ensure_ascii=False))
        if msg.get("tool_calls"):
            chars += len(json.dumps(msg["tool_calls"], ensure_ascii=False))
        shape[f"{role}_chars"] = shape.get(f"{role}_chars", 0) + chars
    return shape


# System-prompt sections of the octos coding profile that no ARC task uses.
# Each entry: (heading the cut starts at, heading it stops before). Cuts are
# whole sections, so the kept text stays byte-identical to the kernel's.
DROP_SECTIONS: list[tuple[str, str | None]] = [
    ("## Research & Search Rules", None),
    ("## Rich Card Rendering", None),
    ("## Pipelines", None),
    ("## Background Tasks", None),
    ("## Cancellation", None),
    ("## Scheduled Tasks (Cron)", None),
    ("## Queue Behavior", None),
    ("## Slash Commands", None),
    ("## Active Skills", "## Tool use discipline"),  # cron / skill-store skill docs (H1s inside)
]
# Tools the coding turns never need; the model cannot call what it cannot see.
DROP_TOOLS = {"spawn", "ask_user_question", "check", "tool_search", "update_plan", "exec_command"}


def trim_system_prompt(text: str, drops: list[tuple[str, str | None]] = DROP_SECTIONS) -> str:
    lines = text.split("\n")

    def level(line: str) -> int:
        stripped = line.lstrip("#")
        return len(line) - len(stripped) if line.startswith("#") and stripped.startswith(" ") else 0

    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        rule = next((d for d in drops if line.startswith(d[0])), None)
        if rule is None:
            out.append(line)
            i += 1
            continue
        start_level = level(line)
        j = i + 1
        while j < len(lines):
            if rule[1] is not None:
                if lines[j].startswith(rule[1]):
                    break
            elif 0 < level(lines[j]) <= start_level:
                break
            j += 1
        i = j
    trimmed = "\n".join(out)
    while "\n\n\n\n" in trimmed:
        trimmed = trimmed.replace("\n\n\n\n", "\n\n\n")
    return trimmed


def trim_request(body: bytes, drop_tools: set[str] = DROP_TOOLS) -> bytes:
    """Drop irrelevant system-prompt sections and unused tool schemas from a
    chat request (the platform meters request bytes; Counter: 45k -> ~17k)."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or "messages" not in data:
        return body
    for msg in data.get("messages") or []:
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
            msg["content"] = trim_system_prompt(msg["content"])
    if isinstance(data.get("tools"), list):
        data["tools"] = [t for t in data["tools"]
                         if ((t.get("function") or {}).get("name") or t.get("name")) not in drop_tools]
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


BUDGET_NOTICE = ("Tool budget for this turn is exhausted. Do not call any more tools: reply now with a one-line "
                 "summary of what you changed. The harness will build and test the app.")
WRITE_DECISION_NOTICE = ("Read-only exploration is now closed for this turn: use the source and evidence already "
                         "collected to make a focused application edit with an available write tool. If the cause "
                         "is still genuinely unknown, stop and report the precise missing fact instead of reading "
                         "more files or claiming a fix.")
WRITE_TOOLS = {"write_file", "edit_file", "create_file", "append_file", "apply_patch", "diff_edit"}


def reserve_edit_budget(body: bytes, used: int, budget: int, phase: str = 'repair') -> bytes:
    """Mid-turn guidance retains tools and never authorizes guessing an edit."""
    # A tool request can itself spend a minute reasoning before returning a
    # batch. Waiting until half of an eight-request turn allowed three broad
    # reads plus two test-directory scans to consume the whole node deadline.
    # Start reserving at the first quarter while still leaving enough requests
    # to inspect one genuinely missing dependency and apply the edit.
    reserve_at = max(1, (budget + 3) // 4)
    if budget < 4 or used < reserve_at or used >= budget:
        return body
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or not data.get('tools') or not isinstance(data.get('messages'), list):
        return body
    prefix = 'Implementation execution budget: ' if phase == 'implement' else 'Repair execution budget: '
    messages = [m for m in data['messages'] if not (m.get('role') == 'user'
                and isinstance(m.get('content'), str) and m['content'].startswith(prefix))]
    messages.append({'role': 'user', 'content': prefix + f'{budget - used} upstream requests remain. '
                     'Reserve them for a focused edit and verification. Reuse already-read unchanged sources; '
                     'avoid another broad shell dump or test-directory scan. Read only a specific missing '
                     'dependency if necessary. Do not guess edits or claim success without evidence; '
                     'if the cause is still unknown, report the precise blocker.'})
    data['messages'] = messages
    return json.dumps(data, ensure_ascii=False).encode('utf-8')


def enforce_turn_budget(body: bytes, used: int, budget: int) -> bytes:
    """Once `used` requests have been made in the current turn, strip the tool
    schemas and append a user notice so the model must answer (ending the turn).
    This is only a prompt-level finishing hint. The proxy admission check supplies
    the hard limit; removing tool schemas alone cannot stop unsolicited calls."""
    if budget <= 0 or used < budget:
        return body
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or "messages" not in data:
        return body
    data.pop("tools", None)
    data.pop("tool_choice", None)
    msgs = list(data.get("messages") or [])
    if not msgs or msgs[-1].get("role") != "user" or msgs[-1].get("content") != BUDGET_NOTICE:
        msgs.append({"role": "user", "content": BUDGET_NOTICE})
    data["messages"] = msgs
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def force_write_decision(body: bytes, used: int, budget: int, elapsed: float,
                         elapsed_limit: float = 180.0) -> bytes:
    """After a long read-only structured-edit turn, close further read tools.

    The current completion still has every offered write tool, so this is not a
    guessed edit or a hard cancellation. It spends the remaining request on an
    evidence-backed edit or a precise blocker instead of another broad read. A
    turn that attempted a write remains unrestricted because it may need to
    inspect an anchor after an edit failure.
    """
    if budget < 4 or used < max(2, (budget + 1) // 2):
        return body
    request_limit = max(3, (3 * budget + 3) // 4)
    if used < request_limit and elapsed < elapsed_limit:
        return body
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list) \
            or not isinstance(data.get("tools"), list):
        return body
    called = set()
    for message in data["messages"]:
        for call in message.get("tool_calls", []) or []:
            function = call.get("function") or {}
            if isinstance(function.get("name"), str):
                called.add(function["name"])
    if called & WRITE_TOOLS:
        return body
    kept = [tool for tool in data["tools"]
            if ((tool.get("function") or {}).get("name") or tool.get("name")) in WRITE_TOOLS]
    if not kept:
        return body
    data["tools"] = kept
    messages = [m for m in data["messages"] if not (
        m.get("role") == "user" and m.get("content") == WRITE_DECISION_NOTICE)]
    messages.append({"role": "user", "content": WRITE_DECISION_NOTICE})
    data["messages"] = messages
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def compact_repeated_reads(body: bytes) -> bytes:
    """Retain the latest observation of each exact read, not duplicate payloads.

    Preserve call ids, arguments, ordering, distinct ranges and all edit results.
    A superseded result is explicitly marked, never presented as current source.
    No compaction of the most recent result or of non-text/malformed messages.
    """
    try:
        data = json.loads(body)
        calls = {}
        reads = []
        for message in data.get('messages', []):
            for call in message.get('tool_calls', []) or []:
                fn = call.get('function') or {}
                # Some providers reuse ids across completions. Never classify
                # an edit result using an earlier read with the same id.
                calls.pop(call.get('id'), None)
                if fn.get('name') == 'read_file':
                    args = json.loads(fn.get('arguments', '{}'))
                    scope = {k: v for k, v in args.items() if k not in {'start_line', 'end_line', 'offset', 'limit'}}
                    calls[call['id']] = (json.dumps(args, sort_keys=True), json.dumps(scope, sort_keys=True))
            if message.get('role') == 'tool' and isinstance(message.get('content'), str):
                key = calls.get(message.get('tool_call_id'))
                if key is not None:
                    reads.append((key, message))
        seen = set()
        covered = {}
        changed = False
        for (key, scope), message in reversed(reads):
            lines = {int(n): text for n, text in re.findall(r'(?m)^\s*(\d+)│ (.*)$', message['content'])}
            later = covered.setdefault(scope, {})
            redundant_range = bool(lines) and all(later.get(n) == text for n, text in lines.items())
            if (key in seen or redundant_range) and len(message['content']) > 160:
                message['content'] = '[Earlier read omitted: a later result covers this read below. Use the later observation; edits may have changed the file.]'
                changed = True
            seen.add(key)
            for n, text in lines.items():
                later.setdefault(n, text)
        return json.dumps(data, ensure_ascii=False).encode() if changed else body
    except (ValueError, TypeError, AttributeError, KeyError):
        return body


def ensure_max_tokens(body: bytes, minimum: int) -> bytes:
    """Raise a too-small `max_tokens` (kernel arc.11 sends 4096; a whole node's
    files need 10-25k — cloud 76fb32a69d81 truncated both implement turns and
    wrote nothing). Never lowers a larger value."""
    if minimum <= 0:
        return body
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or "messages" not in data:
        return body
    current = data.get("max_tokens")
    if not isinstance(current, int) or current < minimum:
        data["max_tokens"] = minimum
        return json.dumps(data, ensure_ascii=False).encode("utf-8")
    return body


def replace_system_prompt(body: bytes, text: str) -> bytes:
    """Codegen turns have no tools; the kernel's worker system prompt (2.4k
    chars of tool guidance) is dead weight there. Keep one system message."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or "messages" not in data:
        return body
    msgs = [m for m in data.get("messages") or [] if m.get("role") != "system"]
    data["messages"] = [{"role": "system", "content": text}] + msgs
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def strip_all_tools(body: bytes) -> bytes:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or "messages" not in data:
        return body
    data.pop("tools", None)
    data.pop("tool_choice", None)
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def destream_request(body: bytes) -> tuple[bytes, bool]:
    """Turn a streaming chat request into a non-streaming one. Returns
    (new_body, was_streaming). The platform's meter sits between us and the
    model and appears to sum the cumulative `usage` of every SSE chunk
    (cloud cc066e8e11f6: provider 50.6k tokens, platform 613k); one JSON
    response carries the usage exactly once."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body, False
    if not isinstance(data, dict) or not data.get("stream"):
        return body, False
    data["stream"] = False
    data.pop("stream_options", None)
    return json.dumps(data, ensure_ascii=False).encode("utf-8"), True


def to_sse(response_body: bytes) -> bytes:
    """Re-emit a non-streaming chat completion as the SSE the client asked
    for: one delta chunk with the whole message (content, reasoning,
    tool_calls), then a finish chunk carrying usage, then [DONE]."""
    try:
        data = json.loads(response_body)
    except (ValueError, UnicodeDecodeError):
        return response_body
    if not isinstance(data, dict) or "choices" not in data:
        return response_body  # error payloads pass through as-is
    base = {"id": data.get("id"), "object": "chat.completion.chunk", "created": data.get("created"),
            "model": data.get("model")}
    lines = []
    for choice in data.get("choices") or []:
        msg = choice.get("message") or {}
        delta = {"role": msg.get("role", "assistant")}
        for key in ("content", "reasoning_content"):
            if msg.get(key) is not None:
                delta[key] = msg[key]
        if msg.get("tool_calls"):
            delta["tool_calls"] = [dict(tc, index=i) for i, tc in enumerate(msg["tool_calls"])]
        lines.append(json.dumps(dict(base, choices=[{"index": choice.get("index", 0), "delta": delta,
                                                      "finish_reason": None}]), ensure_ascii=False))
        lines.append(json.dumps(dict(base, choices=[{"index": choice.get("index", 0), "delta": {},
                                                      "finish_reason": choice.get("finish_reason", "stop")}]),
                                ensure_ascii=False))
    lines.append(json.dumps(dict(base, choices=[], usage=data.get("usage") or {}), ensure_ascii=False))
    return "".join(f"data: {l}\n\n" for l in lines).encode("utf-8") + b"data: [DONE]\n\n"


def prompt_fingerprint(request_body: bytes, previous_text: str) -> tuple[str, int, str]:
    """(sha256 of the prompt text, chars it shares as a prefix with the previous
    request's prompt text, the text). The text is the messages serialised in
    order; the shared prefix is what a provider prefix cache could reuse. ("",
    0, "") for anything that is not a chat request."""
    import hashlib
    try:
        data = json.loads(request_body)
        messages = data["messages"]
        text = "\n".join(f"{m.get('role')}:{m.get('content') if isinstance(m.get('content'), str) else json.dumps(m.get('content'))}"
                         for m in messages)
    except (ValueError, TypeError, KeyError, AttributeError):
        return "", 0, ""
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    shared = 0
    limit = min(len(text), len(previous_text))
    while shared < limit and text[shared] == previous_text[shared]:
        shared += 1
    return sha, shared, text


def error_message(response_body: bytes) -> str:
    """The upstream's error text, if the body carries one; else the body's first line."""
    text = response_body.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text.splitlines()[0] if text else ""
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error) if error else ""


def usage_record(response_body: bytes, elapsed_ms: int, mode: str) -> dict | None:
    usage = _usage_from_body(response_body)
    if not isinstance(usage, dict):
        return None
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "elapsed_ms": elapsed_ms, "mode": mode}
    text = response_body.decode("utf-8", errors="replace")
    if text.lstrip().startswith("data:"):
        rec["sse_chunks"] = sum(1 for l in text.splitlines() if l.startswith("data:") and l.strip() != "data: [DONE]")
        rec["sse_usage_chunks"] = text.count('"usage"')
    else:
        rec["sse_chunks"] = 0
    # Keep termination metadata without persisting response text. A full output
    # allowance does not by itself prove truncation; use the provider's reason.
    chunks = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")] \
        if text.lstrip().startswith("data:") else [text]
    reasons = set()
    for chunk in chunks:
        try:
            data = json.loads(chunk)
        except (ValueError, TypeError):
            continue
        choices = data.get("choices") if isinstance(data, dict) else None
        for choice in choices if isinstance(choices, list) else []:
            reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            if isinstance(reason, str) and reason:
                reasons.add(reason)
    if reasons:
        rec["finish_reasons"] = sorted(reasons)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens",
                "prompt_cache_miss_tokens"):
        if key in usage:
            rec[key] = usage[key]
    details = usage.get("completion_tokens_details") or {}
    if isinstance(details, dict) and "reasoning_tokens" in details:
        rec["reasoning_tokens"] = details["reasoning_tokens"]
    # The ARC endpoint reports cache hits OpenAI-style (prompt_tokens_details.
    # cached_tokens), not DeepSeek-style; fold either into one field.
    pdetails = usage.get("prompt_tokens_details") or {}
    if "prompt_cache_hit_tokens" not in rec and isinstance(pdetails, dict) and "cached_tokens" in pdetails:
        rec["prompt_cache_hit_tokens"] = pdetails["cached_tokens"]
    return rec


def terminal_account_error(status: int, payload: bytes) -> bool:
    """Latch explicit account failures; ordinary rate limits remain retryable."""
    if status in {401, 402}:
        return True
    if status not in {403, 429}:
        return False
    try:
        error = json.loads(payload).get('error', {})
    except (ValueError, AttributeError, UnicodeError):
        return False
    if not isinstance(error, dict):
        return False
    codes = {str(error.get(k, '')).lower() for k in ('code', 'type')}
    return bool(codes & {'insufficient_quota', 'insufficient_balance', 'invalid_api_key',
                         'authentication_error'}) or any(term in str(error.get('message', '')).lower()
                         for term in ('quota exhausted', 'balance too low', 'balance is exhausted'))


class LlmProxy:
    def __init__(self, upstream_base: str, mode: str, log_path: Path | None = None, host: str = "127.0.0.1",
                 dump_dir: Path | None = None, dump_limit: int = 3, destream: bool = True, trim: bool = True,
                 extra_drop_tools: set[str] | None = None, min_max_tokens: int = 32768) -> None:
        self.upstream = upstream_base.rstrip("/")
        self.mode = mode
        self.routes = model_routes(configured_model_routes())
        self.phase = "implement"
        self.min_max_tokens = min_max_tokens
        self.codegen_max_tokens = 0
        self.destream = destream
        self.trim = trim
        # Tools removed from every request in addition to DROP_TOOLS (mutable:
        # the flow can take the shell away for one-turn tasks and give it back).
        self.extra_drop_tools: set[str] = set(extra_drop_tools or ())
        self.no_tools = False  # codegen turns: strip every tool schema
        self.system_override: str | None = None  # codegen turns: replace the kernel system prompt
        # Per-turn request cap (0 = unlimited); the flow calls begin_turn().
        self.turn_budget = 0
        self.turn_requests = 0
        self.turn_upstream_requests = 0
        self.budget_hits = 0
        self.hard_budget_exhausted = False
        self.compact_reads = False
        # Run-wide cost-guard usage: exact provider tokens when present, plus a
        # conservative reserve for requests that returned no usage block.
        self.total_requests = 0
        self.total_tokens = 0
        self.estimated_tokens = 0
        # Explicit absolute cap is enforced before EVERY upstream completion,
        # including requests inside a tool turn. In-flight usage may overshoot.
        self.max_total_tokens_abs = int(os.environ.get("OCTOS_ARC_MAX_TOTAL_TOKENS_ABS", "0"))
        self.blocked_requests = 0
        self.turn_serial = 0
        self.truncated_reply = None
        self.log_path = log_path
        self.dump_dir = dump_dir      # OCTOS_ARC_PROXY_DUMP=1: first N request bodies for prefix analysis
        self.dump_limit = dump_limit
        self._dumped = 0
        self._lock = threading.Lock()
        self._inflight: dict[tuple, Future] = {}
        self._terminal_accounts: dict[tuple, tuple] = {}
        self.terminal_blocked_requests = 0
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):  # silence stderr noise
                pass

            def _forward(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                was_streaming = False
                unrouted = None
                if method == "POST" and self.path.rstrip("/").endswith("/chat/completions"):
                    body = inject_reasoning(body, proxy.mode)
                    body = ensure_max_tokens(body, proxy.min_max_tokens)
                    with proxy._lock:
                        used = proxy.turn_requests
                        proxy.turn_requests += 1
                        upstream_used = proxy.turn_upstream_requests
                    if proxy.phase in {'implement', 'repair'} and not proxy.no_tools:
                        body = reserve_edit_budget(body, upstream_used, proxy.turn_budget, proxy.phase)
                    if proxy.compact_reads and proxy.phase in {'implement', 'repair'} and not proxy.no_tools:
                        elapsed = max(0.0, time.monotonic() - getattr(
                            proxy, "turn_started_at", time.monotonic()))
                        body = force_write_decision(
                            body, upstream_used, proxy.turn_budget, elapsed,
                            float(os.environ.get("OCTOS_ARC_NO_WRITE_SECONDS", "180")))
                    capped = enforce_turn_budget(body, used, proxy.turn_budget)
                    if capped is not body:
                        proxy.budget_hits += 1
                    body = capped
                    if proxy.trim or proxy.extra_drop_tools:
                        body = trim_request(body, (DROP_TOOLS if proxy.trim else set()) | proxy.extra_drop_tools)
                    if proxy.no_tools:
                        body = strip_all_tools(body)
                    if proxy.system_override:
                        body = replace_system_prompt(body, proxy.system_override)
                    if proxy.compact_reads:
                        body = compact_repeated_reads(body)
                    if proxy.destream:
                        body, was_streaming = destream_request(body)
                    limit = proxy.codegen_max_tokens if proxy.no_tools else getattr(proxy, "tool_max_tokens", 0)
                    body = cap_output_tokens(body, limit)
                    unrouted = body
                    with proxy._lock:
                        body = route_request(body, proxy.routes, proxy.phase)
                    body = cap_output_tokens(body, limit)
                    proxy._dump(body)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
                headers["Content-Length"] = str(len(body))
                path = proxy.forward_path(self.path)
                status, payload, resp_headers = proxy._request_upstream(method, path, body, headers)
                if unrouted is not None and body != unrouted:
                    selected = json.loads(body).get("model")
                    original = json.loads(unrouted).get("model")
                    if selected != original and routed_model_missing(status, payload, selected):
                        # Once only, with the caller's model AND original parameters.
                        # Do not hide auth, quota, URL or unrelated 404 errors.
                        with proxy._lock:
                            proxy.routes = [r for r in proxy.routes if r["model"] != selected]
                        headers["Content-Length"] = str(len(unrouted))
                        proxy._dump(unrouted)
                        status, payload, resp_headers = proxy._request_upstream(method, path, unrouted, headers)
                ctype = resp_headers.get("Content-Type", "application/json") if resp_headers else "application/json"
                if was_streaming and status == 200:
                    payload, ctype = to_sse(payload), "text/event-stream; charset=utf-8"
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # A timed-out client may have retried while upstream was pending.

            def do_POST(self):
                self._forward("POST")

            def do_GET(self):
                self._forward("GET")

        self.server = ThreadingHTTPServer((host, 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.base_url = f"http://{host}:{self.port}/v1"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def forward_path(self, path: str) -> str:
        # A configured provider prefix is already the API root, not necessarily /v1.
        if urlsplit(self.upstream).path.strip("/"):
            if path == "/v1" or path.startswith("/v1?"):
                return "/" + path[3:]
            if path.startswith("/v1/"):
                return path[3:]
        return path

    def _request_upstream(self, method: str, path: str, body: bytes, headers: dict) -> tuple:
        # Only pending identical completions are shared. Include credentials and
        # all forwarded headers; never share across distinct requests or phases.
        key = (method, path, body, tuple(sorted((k.lower(), v) for k, v in headers.items())), self.phase) \
            if method == "POST" and path.rstrip("/").endswith("/chat/completions") else None
        # Account failures survive phase/model/input changes, but never cross
        # credentials or provider endpoints. Keep credentials out of diagnostics.
        account = (self.upstream, tuple(sorted((k.lower(), v) for k, v in headers.items()
                   if k.lower() in {'authorization', 'x-api-key', 'api-key',
                                    'openai-organization', 'openai-project'})))
        with self._lock:
            if key is not None and account in self._terminal_accounts:
                self.terminal_blocked_requests += 1
                return self._terminal_accounts[account]
            future = self._inflight.get(key) if key is not None else None
            if (key is not None and future is None and self.turn_budget > 0
                    and self.turn_upstream_requests >= self.turn_budget):
                # A local terminal message ends the kernel loop without provider
                # retries. Flow marks the turn incomplete and measures partial edits.
                # The kernel requires usage. Zero here means a LOCAL response
                # with no upstream request, never an estimate of provider usage.
                # It is deliberately absent from provider llm-usage.jsonl.
                self.hard_budget_exhausted = True
                payload = {'id': 'arc-local-turn-limit', 'object': 'chat.completion',
                           'model': json.loads(body).get('model', 'arc-local'),
                           'created': int(time.time()),
                           'arc_local_response': True,
                           'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                           'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
                               'role': 'assistant', 'content': 'local_turn_budget_exhausted: '
                               'repair incomplete; evaluate current files before further work.'}}]}
                return 200, json.dumps(payload).encode(), {'Content-Type': 'application/json'}
            if key is not None and self.max_total_tokens_abs > 0 and self.total_tokens >= self.max_total_tokens_abs:
                self.blocked_requests += 1
                return 402, json.dumps({"error": {
                    "code": "local_token_budget_exhausted",
                    "message": "Local absolute token budget exhausted; no upstream request was sent."
                }}).encode(), {"Content-Type": "application/json"}
            owner = future is None
            if owner:
                future = Future()
                if key is not None:
                    self.turn_upstream_requests += 1
                    self._inflight[key] = future
        if not owner:
            return future.result()
        try:
            guarded_stream = (self.no_tools and self.phase in {"implement", "repair"}
                              and os.environ.get("OCTOS_ARC_STREAM_GUARD", "1") != "0"
                              and method == "POST" and path.rstrip("/").endswith("/chat/completions"))
            if guarded_stream:
                data = json.loads(body)
                data["stream"] = True
                data["stream_options"] = {**(data.get("stream_options") or {}), "include_usage": True}
                body = json.dumps(data, ensure_ascii=False).encode()
                headers = {k: v for k, v in headers.items() if k.lower() != "content-length"}
                headers["Content-Length"] = str(len(body))
            req = urllib.request.Request(self.upstream + path, data=body if body else None,
                                         headers=headers, method=method)
            t0 = time.time()
            meta = self.request_meta(body)   # attribution fixed at issue time, not at response time
            try:
                deadline = getattr(self, "turn_deadline", None)
                request_timeout = min(600, max(1, deadline - time.monotonic())) if deadline else 600
                with open_upstream(req, timeout=request_timeout) as resp:
                    if guarded_stream and "text/event-stream" in resp.headers.get("Content-Type", ""):
                        payload, stopped = collect_codegen_stream(resp, deadline)
                        meta["stream_guard"] = stopped or "completed"
                        result = resp.status, payload, {"Content-Type": "application/json"}
                    else:
                        result = resp.status, resp.read(), resp.headers
            except urllib.error.HTTPError as exc:
                result = exc.code, exc.read(), exc.headers
                exc.close()
            except Exception as exc:  # noqa: BLE001
                result = 502, json.dumps({"error": {"message": f"proxy: {exc}"}}).encode(), {}
            status, payload, _ = result
            if key is not None and terminal_account_error(status, payload):
                with self._lock:
                    self._terminal_accounts[account] = result
            if (status == 200 and getattr(self, "edit_arguments_dir", None)
                    and meta.get("turn_serial") == self.turn_serial):
                self.retain_edit_arguments(payload)
            if status == 200 and meta.get("codegen"):
                self.capture_truncated_reply(payload, meta)
            self._log(payload, int((time.time() - t0) * 1000), body, len(body), len(payload), status=status, meta=meta)
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            if key is not None:
                with self._lock:
                    self._inflight.pop(key, None)

    def begin_turn(self, budget: int) -> None:
        with self._lock:
            self.turn_serial += 1
            self.truncated_reply = None
            self.turn_budget = int(budget)
            self.turn_requests = 0
            self.turn_upstream_requests = 0
            self.hard_budget_exhausted = False
            self.turn_started_at = time.monotonic()

    def enable_edit_preflight(self) -> str:
        """Private transport of complete args to the trusted ARC hook.

        The kernel limits hook payloads to 1 KB. Keep full arguments keyed by
        the provider tool-call id so large edits receive the same validation.
        Not sent to the model or included in the deployment/application output.
        """
        self._edit_arguments_temp = tempfile.TemporaryDirectory(prefix="arc-edit-args-")
        self.edit_arguments_dir = Path(self._edit_arguments_temp.name)
        return str(self.edit_arguments_dir)

    def retain_edit_arguments(self, payload: bytes) -> None:
        try:
            data = json.loads(payload)
            # Native tool execution completes before the next model request.
            # Providers may reuse call ids in a later completion; only duplicate
            # ids inside the CURRENT completion are an ambiguity.
            for previous in self.edit_arguments_dir.glob("*.json"):
                previous.unlink()
            for choice in data.get("choices", []):
                for call in choice.get("message", {}).get("tool_calls", []):
                    function = call.get("function") or {}
                    if function.get("name") != "edit_file" or not isinstance(call.get("id"), str):
                        continue
                    args = json.loads(function.get("arguments", "{}"))
                    if not isinstance(args, dict):
                        continue
                    filename = hashlib.sha256(call["id"].encode()).hexdigest() + ".json"
                    target = self.edit_arguments_dir / filename
                    record = {"id": call["id"], "name": "edit_file", "arguments": args}
                    encoded = json.dumps(record, ensure_ascii=False)
                    if target.exists() and target.read_text() != encoded:
                        encoded = json.dumps({"id": call["id"], "error": "conflicting tool call ids; issue a new edit"})
                    target.write_text(encoded)
        except (ValueError, TypeError, AttributeError, OSError):
            pass  # large truncated calls fail closed in the hook if unavailable

    def capture_truncated_reply(self, payload: bytes, meta: dict) -> None:
        """Keep actual response text the kernel otherwise discards on length.

        Only complete protocol blocks may later be applied. Never change the
        provider finish reason to success, and never reuse a late previous turn.
        """
        try:
            choices = json.loads(payload).get("choices", [])
            choice = choices[0] if len(choices) == 1 else {}
            content = choice.get("message", {}).get("content")
            if choice.get("finish_reason") != "length" or not isinstance(content, str):
                return
            if len(content) > 2_000_000:
                return
        except (ValueError, TypeError, AttributeError):
            return
        with self._lock:
            if meta.get("turn_serial") != self.turn_serial:
                return
            self.truncated_reply = {"text": content, "label": meta.get("label"), "turn_serial": self.turn_serial}
        if self.log_path:
            try:
                folder = self.log_path.parent / "truncated-replies"
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"turn-{meta['turn_serial']}.txt").write_text(content, encoding="utf-8")
            except OSError:
                pass

    def take_truncated_reply(self, label: str) -> str | None:
        with self._lock:
            reply = self.truncated_reply
            if not reply or reply["label"] != label or reply["turn_serial"] != self.turn_serial:
                return None
            self.truncated_reply = None
            return reply["text"]

    def _dump(self, body: bytes) -> None:
        if not self.dump_dir or self._dumped >= self.dump_limit:
            return
        try:
            self.dump_dir.mkdir(parents=True, exist_ok=True)
            self._dumped += 1
            (self.dump_dir / f"request-{self._dumped:02d}.json").write_bytes(body)
        except OSError:
            pass

    def request_meta(self, request_body: bytes) -> dict:
        """The turn a request belongs to, captured when it is issued. A request
        that outlives its turn (client timeout, upstream still generating) used
        to be attributed to whatever turn was current when its response ended,
        and its prefix reuse measured against whichever prompt finished last."""
        shape = request_shape(request_body)
        if not shape:
            return {}
        with self._lock:
            sha, shared, text = prompt_fingerprint(request_body, getattr(self, "_last_prompt_text", ""))
            self._last_prompt_text = text
            request = json.loads(request_body)
            return {"request": shape, "model": request.get("model"), "phase": self.phase,
                    "mode": self.mode,
                    "output_limit": request.get("max_completion_tokens", request.get("max_tokens")),
                    "label": getattr(self, "label", ""), "prompt_sha256": sha, "prefix_shared_chars": shared,
                    "turn_serial": self.turn_serial, "codegen": self.no_tools}

    def _log(self, payload: bytes, elapsed_ms: int, request_body: bytes = b"", req_bytes: int = 0,
             resp_bytes: int = 0, status: int | None = None, meta: dict | None = None) -> None:
        rec = usage_record(payload, elapsed_ms, self.mode)
        if rec is None:
            # Every exchange is logged, usage block or not. Until 2026-09-19 an
            # exchange without one (error, timeout, empty stream) left no record,
            # and the platform's meter counted 1.2-3.2x the proxy's tokens on the
            # big runs with nothing to reconcile the gap against.
            rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "elapsed_ms": elapsed_ms,
                   "mode": self.mode, "no_usage": True}
            error = error_message(payload)
            if error:
                rec["error"] = error[:300]
        if status is not None:
            rec["status"] = status
        rec["request_bytes"], rec["response_bytes"] = req_bytes, resp_bytes
        rec.update(meta if meta is not None else self.request_meta(request_body))
        exact = int(rec.get("prompt_tokens") or 0) + int(rec.get("completion_tokens") or 0)
        estimated = 0
        if rec.get("no_usage"):
            # A request that timed out is not known to be free. Charge a
            # conservative input estimate and reserve its advertised output
            # allowance when generation may have happened before disconnect.
            estimated = (req_bytes + 2) // 3
            output_limit = rec.get("output_limit")
            if (status is None or status == 200 or status >= 500) and isinstance(output_limit, int):
                estimated += max(0, output_limit)
            rec["guard_token_estimate"] = estimated
        with self._lock:
            self.total_requests += 1
            self.total_tokens += exact + estimated
            self.estimated_tokens += estimated
        if not self.log_path:
            return
        with self._lock:
            try:
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
            except OSError:
                pass

    def start(self) -> "LlmProxy":
        self._thread.start()
        return self

    def stop(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        if getattr(self, "_edit_arguments_temp", None):
            self._edit_arguments_temp.cleanup()
