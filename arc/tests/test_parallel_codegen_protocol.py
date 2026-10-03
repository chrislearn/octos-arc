import hashlib
import json
import unittest

from parallel_codegen_protocol import parse_candidate


EXISTING = "frontend/src/App.jsx"
NEW = "frontend/src/New.jsx"
SHARED = "backend/server.js"
SNAPSHOT = {EXISTING: "one\ntwo\n", SHARED: "shared\n"}


def file_block(path, body):
    return f"<<<FILE {path}>>>\n{body}\n<<<END FILE>>>"


def edit_block(path, search, replacement):
    return (f"<<<EDIT {path}>>>\n<<<SEARCH>>>\n{search}\n"
            f"<<<REPLACE>>>\n{replacement}\n<<<END EDIT>>>")


def parse(reply, *, allowed=None, shown=None):
    return parse_candidate(reply, allowed_paths=allowed or {EXISTING, NEW},
                           shared_paths={SHARED}, snapshot=SNAPSHOT,
                           shown_paths=shown if shown is not None else {EXISTING})


class CandidateProtocolTests(unittest.TestCase):
    def test_stages_owned_file_and_edit_without_writing(self):
        reply = edit_block(EXISTING, "one", "ONE") + "\n" + file_block(NEW, "export default 1;")
        result = parse(reply)
        self.assertEqual(result.kind, "candidate")
        self.assertEqual(result.files, {EXISTING: "ONE\ntwo\n", NEW: "export default 1;\n"})
        self.assertEqual(SNAPSHOT[EXISTING], "one\ntwo\n")

    def test_multiple_edits_are_ordered_and_atomic(self):
        good = edit_block(EXISTING, "one", "ONE") + "\n" + edit_block(EXISTING, "two", "TWO")
        self.assertEqual(parse(good).files[EXISTING], "ONE\nTWO\n")
        bad = good + "\n" + edit_block(EXISTING, "missing", "x")
        self.assertEqual(parse(bad).kind, "rejected")

    def test_rejects_unowned_shared_blind_and_unshown_paths(self):
        cases = [
            file_block(SHARED, "shared changed"),
            file_block("backend/private.js", "x"),
            file_block("frontend/../backend/server.js", "x"),
            file_block("frontend/tests/a.js", "x"),
            file_block(EXISTING, "x") + "\n" + edit_block(EXISTING, "one", "ONE"),
        ]
        for reply in cases:
            with self.subTest(reply=reply):
                self.assertEqual(parse(reply).kind, "rejected")
        self.assertEqual(parse(file_block(EXISTING, "x"), shown=set()).reason,
                         "blind_file_rewrite")
        self.assertEqual(parse(edit_block(EXISTING, "one", "ONE"), shown=set()).reason,
                         "unshown_edit_path")
        self.assertEqual(parse_candidate(file_block("frontend/Tests/a.js", "x"),
                                         allowed_paths={"frontend/Tests/a.js"}, shared_paths=set(),
                                         snapshot={}, shown_paths=set()).reason, "unsafe_path")

    def test_rejects_junk_partial_and_mixed_protocol(self):
        valid = file_block(NEW, "x")
        for reply in ["before\n" + valid, valid + "\nafter", valid + "\n<<<FILE backend/x.js>>>",
                      valid + "\n<<<NO CHANGE>>>", valid + "\n<<<SHARED_CHANGE_REQUEST>>>\n{}\n<<<END SHARED_CHANGE_REQUEST>>>"]:
            with self.subTest(reply=reply):
                self.assertEqual(parse(reply).kind, "rejected")
        self.assertEqual(parse("<<<NO CHANGE>>>").kind, "no_change")
        self.assertEqual(parse("<<<NO CHANGE>>> and prose").kind, "rejected")
        self.assertEqual(parse(file_block(NEW, "   ")).reason, "empty_file")

    def test_shared_request_is_exclusive_and_versioned(self):
        payload = {"path": SHARED, "reason": "A shared route is needed",
                   "desired_change": "Add /items while preserving /health",
                   "requirement_ids": ["n1"],
                   "base_hash": hashlib.sha256(SNAPSHOT[SHARED].encode()).hexdigest()}
        envelope = ("<<<SHARED_CHANGE_REQUEST>>>\n" + json.dumps(payload)
                    + "\n<<<END SHARED_CHANGE_REQUEST>>>")
        result = parse(envelope)
        self.assertEqual(result.kind, "shared_request")
        self.assertEqual(result.request, payload)
        self.assertEqual(result.files, {})
        self.assertEqual(parse(envelope + "\n" + file_block(NEW, "x")).kind, "rejected")
        for change in ({"base_hash": "0" * 64}, {"path": EXISTING}, {"requirement_ids": []}):
            with self.subTest(change=change):
                invalid = dict(payload, **change)
                reply = "<<<SHARED_CHANGE_REQUEST>>>\n" + json.dumps(invalid) + "\n<<<END SHARED_CHANGE_REQUEST>>>"
                self.assertEqual(parse(reply).kind, "rejected")


if __name__ == "__main__":
    unittest.main()
