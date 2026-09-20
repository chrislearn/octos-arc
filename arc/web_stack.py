"""Versioned, domain-neutral web stack and requirement-driven recommendations.

Only the small core is installed automatically. Capability hints never supply
domain behavior, fixtures, selectors, or acceptance outcomes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

STACK_ID = "react-radix-v1"
CORE = {"react": "19.3.0", "react-dom": "19.3.0", "radix-ui": "1.6.7",
        "react-router": "7.18.4"}
BUILD = {"vite": "7.3.6", "@vitejs/plugin-react": "5.2.0"}

# (semantic requirement pattern, frontend pins, backend pins, compact API contract)
CAPABILITIES = {
    "styling": (r".*", {"tailwindcss": "4.3.3", "@tailwindcss/vite": "4.3.3"}, {},
        'Optional utility CSS: import "tailwindcss" in CSS; the existing Vite config loads its plugin. No CDN script.'),
    "forms": (r"\b(?:forms?|validat\w*|registration|checkout|password)\b|表单|注册|校验", {
        "react-hook-form": "7.88.0", "zod": "4.6.5", "@hookform/resolvers": "5.9.1"}, {"zod": "4.6.5"},
        "useForm + zodResolver from @hookform/resolvers/zod; Controller adapts Radix values. Keep booleans boolean; server validates too. Native forms suffice for simple inputs."),
    "calendar": (r"\b(?:calendar|departure date|return date|date range|date bar|nearby date)\b|日期|日历", {
        "date-fns": "4.4.0", "react-day-picker": "9.14.0"}, {},
        "DayPicker from react-day-picker, import react-day-picker/style.css. Use native date inputs when enough; preserve date-only YYYY-MM-DD without UTC conversion."),
    "markdown": (r"markdown", {"react-markdown": "10.1.0", "remark-gfm": "4.0.1"}, {},
        "Markdown default export + remarkGfm; controlled textarea for source/toolbar edits, ReactMarkdown for preview. No raw HTML plugin or hand-written Markdown parser; override images to local assets."),
    "richtext": (r"\b(?:rich[- ]text|wysiwyg|page content)\b|富文本", {
        "@tiptap/react": "3.31.3", "@tiptap/core": "3.31.3", "@tiptap/pm": "3.31.3",
        "@tiptap/starter-kit": "3.31.3"}, {},
        "useEditor/EditorContent + StarterKit; set editorProps.attributes role='textbox', aria-label and aria-multiline='true' on the editable region. Store editor JSON, read current content on save; do not reset content on every render. Plain text needs no rich-text editor."),
    "money": (r"\b(?:prices?|pricing|payment|cart|refund|invoice)\b|金额|价格|支付", {"decimal.js": "10.6.0"}, {"decimal.js": "10.6.0"},
        "Prefer integer minor units; Decimal when fractional arithmetic is needed. Backend computes authoritative totals; Intl.NumberFormat is presentation only."),
    "carousel": (r"carousel|轮播", {"embla-carousel-react": "8.6.0"}, {},
        "useEmblaCarousel; React effect cleanup for any autoplay timer. Slides and images remain local."),
    "icons": (r"\bicons?\b|图标", {"lucide-react": "1.47.0"}, {},
        "Named icon imports only; keep accessible names on the surrounding buttons, hide decorative SVGs from assistive technology."),
    "documents": (r"download.*invoice|pdf|下载.*发票", {}, {"pdfkit": "0.20.2"},
        "Generate real PDFs on the backend with PDFDocument; correct Content-Type and Content-Disposition, local fonts/assets."),
}

REACT_CONTRACT = """\
Fixed frontend baseline: React + Vite + Radix + React Router; preserve the installed exact versions and lockfile. frontend/src/main.jsx mounts App.jsx inside BrowserRouter; app-specific views are React modules. npm run build emits local frontend/dist; the Express entry serves SPA deep links (arc.spa=true). Do not switch this app to Vue/htmx, copy-build JSX, or implement another DOM/widget/router system.
Use import {Dialog, DropdownMenu, Popover, AlertDialog} from 'radix-ui'; import {Routes, Route, Link, useNavigate} from 'react-router'. Use native labeled inputs/selects/checkboxes where sufficient; Radix for overlays, focus, Escape and outside-click. Dialog.Content belongs in Dialog.Portal with Overlay, Title and Description. Radix is unstyled: provide overlay positioning/z-index and visible focus styles. asChild wraps exactly one element; never nest buttons. DropdownMenu.Item uses onSelect, not a second delegated click handler. Do not make every popover modal or block unrelated navigation unnecessarily.
State invariants: one owner per draft/open state; controlled fields use value/onChange or checked/onChange, stable record IDs as keys. Radix Checkbox uses checked/onCheckedChange (true/false/'indeterminate'), not a native change event. Opening an editor is synchronous; await save before closing when required, retain draft on failure, and apply the returned canonical record. Abort/ignore stale fetch responses; clean up subscriptions/timers. No direct DOM mutations inside React roots, duplicate global handlers, or background refresh that resets an active draft. Framework primitives do not define domain transitions: specify them from requirements.
"""


def recommended_capabilities(tree: dict) -> list[str]:
    selected = {"styling"}

    def positive_text(value: str) -> str:
        # Conservative clause filter, not a semantic parser. A negated request
        # is not a reason to install a library; do not discard later positive clauses.
        value = re.sub(r"!?\[[^\]]*\]\([^)]*\)", "", value)
        clauses = re.split(r"[.!?;。；\n]|\bbut\b|但是|但需要", value, flags=re.I)
        return "\n".join(clause for clause in clauses if not re.search(
            r"^\s*(?:no\b|without\b|do not\b|don't\b|不需要|无需|不支持)|"
            r"\b(?:not (?:needed|required|supported)|out of scope)\b", clause, re.I))

    def visit(node: dict, markdown_context: bool = False) -> None:
        # Resource filenames are not capabilities (e.g. homepage_content.png).
        text = [str(node.get(key, "")) for key in ("name", "description")]
        for scenario in node.get("scenarios") or []:
            if isinstance(scenario, dict):
                text.append(str(scenario.get("name", "")))
                text.extend(str(step.get("content", "")) for step in scenario.get("steps") or []
                            if isinstance(step, dict))
        requirements = positive_text("\n".join(text)).lower()
        markdown_context = markdown_context or "markdown" in requirements
        for name, (pattern, *_) in CAPABILITIES.items():
            if not re.search(pattern, requirements):
                continue
            # A Markdown editor may be called rich text. This only applies in
            # its own subtree, never to a separate document editor elsewhere.
            if name == "richtext" and markdown_context and not re.search(
                    r"wysiwyg|separate.*rich[- ]text|独立.*富文本", requirements):
                continue
            selected.add(name)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child, markdown_context)

    visit(tree)
    return [name for name in CAPABILITIES if name in selected]


def react_manifest(capabilities: list[str]) -> dict:
    return {"name": "arc-frontend", "private": True, "type": "module",
            "scripts": {"build": "node build.mjs"},
            "engines": {"node": "^20.19.0 || >=22.12.0"},
            "arc": {"spa": True, "stack": STACK_ID, "capabilities": capabilities},
            "dependencies": dict(CORE), "devDependencies": dict(BUILD)}


def stack_note(output_dir: Path | None) -> str:
    if output_dir is None:
        return ""
    try:
        manifest = json.loads((output_dir / "frontend/package.json").read_text())
        arc = manifest.get("arc", {})
        if arc.get("stack") != STACK_ID:
            return ""
        selected = arc.get("capabilities", [])
    except (OSError, ValueError, AttributeError):
        return ""
    lines = [REACT_CONTRACT,
             "Add exact dependencies to package.json only; npm install updates the lockfile. Never emit or hand-edit lockfile blocks.",
             "Optional pinned recommendations (not installed; add only when needed, never all by default):"]
    for name, (_, frontend, backend, hint) in CAPABILITIES.items():
        if name not in selected:
            continue
        pins = "; ".join(f"{side}: " + ", ".join(f"{p}@{v}" for p, v in deps.items())
                         for side, deps in (("frontend", frontend), ("backend", backend)) if deps)
        lines.append(f"{name}: {pins}. {hint}")
    return "\n".join(lines) + "\n"
