"""No-spec baseline oracles and the pre-code audit/correction lifecycle."""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from main import Flow
from derived_case_review import collect_cases, validate_review
from scenario_review import (authentication_invariants, behavior_test_titles, compile_reply,
                             grounded_behavior_test, review_targets, validate_proposal)
from scenario_tests import Fixtures, suite_fixtures


def login():
    return {"id": "AUTH", "name": "Password login", "type": "ATOMIC",
            "description": "Users sign in with a username and password via “Sign in”.",
            "scenarios": [{"name": "Login", "steps": [{"keyword": "GIVEN", "content":
                "The seeded data is account `alice`, email `alice@example.test`, password `Correct-pass-123!`."}]}]}


def proposal(target):
    account, password = target["invariant_credentials"]
    return {"id": target["id"], "title": target["title"], "signed_in": False, "confidence": 1,
            "steps": [{"op": "expect_sign_in_rejected", "target": account, "value": password}]}


class AuthenticationInvariantTests(unittest.TestCase):
    def test_required_password_login_gets_isolated_unknown_and_wrong_password_checks(self):
        node = login()
        fixtures = suite_fixtures([node])
        targets = authentication_invariants([node], fixtures)
        self.assertEqual([t["invariant_kind"] for t in targets], ["unregistered_account", "wrong_password"])
        scripts, dropped = compile_reply(json.dumps({"scenarios": [proposal(t) for t in targets]}), targets, fixtures)
        self.assertEqual(dropped, [])
        self.assertEqual(len(scripts["AUTH"]), 2)
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "AUTH.spec.ts").write_text("\n\n".join(scripts["AUTH"]))
            rows = collect_cases(directory, targets, {"AUTH"})
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertEqual(row["status"], "unreviewed")
                self.assertEqual(row["origin"], "baseline_invariant")
                self.assertIn("h.expectSignInRejected", row["case"])
                self.assertNotIn("h.signIn(", row["case"])
                self.assertNotIn("h.fillField(", row["case"])
                outcome = row["outcome"].split("THEN: ")[1]
                assertion = next(line.strip() for line in row["case"].splitlines() if "expectSignInRejected" in line)
                self.assertTrue(validate_review(row, {"status": "approved_behavior", "requirement_quote": outcome,
                                                     "test_quote": assertion, "reason": "Invalid credentials leave the session anonymous."}))

    def test_invariant_cannot_be_weakened_to_error_text_or_use_correct_credentials(self):
        node = login(); fixtures = suite_fixtures([node])
        target = authentication_invariants([node], fixtures)[1]
        bad = proposal(target)
        bad["steps"][0]["value"] = fixtures.password
        self.assertIsNone(validate_proposal(bad, target, fixtures))
        bad["steps"] = [{"op": "click", "target": "Sign in"}, {"op": "expect_visible", "target": "Sign in"}]
        self.assertIsNone(validate_proposal(bad, target, fixtures))
        source = validate_proposal(proposal(target), target, fixtures)
        title = target["title"] + " [model]"
        self.assertIn(title, behavior_test_titles(source))
        self.assertFalse(grounded_behavior_test(source.replace("Wrong-pass-", "Correct-pass-"), title, target))

    def test_non_authentication_passwordless_and_unseeded_products_do_not_get_invalid_baselines(self):
        self.assertEqual(authentication_invariants([{"id": "A", "description": "Edit a note"}], Fixtures()), [])
        node = login(); node["description"] += " Guest login without a password is permitted."
        self.assertEqual(authentication_invariants([node], Fixtures()), [])
        self.assertEqual(len(authentication_invariants([login()], Fixtures())), 1)

    def test_email_only_login_uses_valid_unknown_email_and_seeded_email(self):
        node = login(); node["description"] = "Users sign in with email and password."
        fixtures = suite_fixtures([node])
        targets = authentication_invariants([node], fixtures)
        self.assertEqual(targets[0]["invariant_credentials"][0], "$UNKNOWN_EMAIL")
        self.assertEqual(targets[1]["invariant_credentials"][0], fixtures.email)
        self.assertIsNotNone(validate_proposal(proposal(targets[0]), targets[0], fixtures))

    def test_baselines_exist_when_ai_is_disabled_and_remain_untrusted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flow = Flow(argparse.Namespace(web_port=3000), root, root)
            flow.metric = Mock()
            node = login()
            with patch.dict("os.environ", {"OCTOS_ARC_DERIVED_LLM": "0"}):
                self.assertTrue(flow.prepare_derived_tests([node]))
            source = (flow.derived_tests_dir / "AUTH.spec.ts").read_text()
            self.assertEqual(source.count("h.expectSignInRejected"), 2)
            titles = [t["title"] + " [script]" for t in flow.planned_derived_scenarios() if t.get("invariant_kind")]
            self.assertTrue(all(t in behavior_test_titles(source) for t in titles))
            self.assertTrue(all(not flow.trusted_derived_case("AUTH", t) for t in titles))


class AuditCorrectionTests(unittest.TestCase):
    def test_preparation_orders_generation_audit_correction_reaudit_and_adoption(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, _, _ = self.setup_flow(Path(folder))
            order = []
            flow.augment_derived_tests = Mock(side_effect=lambda nodes: order.append("generate"))
            flow.review_derived_cases = Mock(side_effect=lambda ids, **kwargs: order.append("audit"))
            flow.correct_derived_cases = Mock(side_effect=lambda ids: order.append("correct") or {"A"})
            flow.adopt_derived_specs = Mock(side_effect=lambda ids: order.append("adopt"))
            with patch.dict("os.environ", {"OCTOS_ARC_DERIVED_LLM": "1", "OCTOS_ARC_DRYRUN": "0",
                                           "OCTOS_ARC_DERIVED_CASE_CORRECTION_REQUESTS": "2"}):
                flow.prepare_derived_spec_batch(flow.derived_nodes)
            self.assertEqual(order, ["generate", "audit", "correct", "audit", "adopt"])
            self.assertEqual(flow.review_derived_cases.call_args_list[0].kwargs, {"reserve_requests": 1})

    def setup_flow(self, root):
        flow = Flow(argparse.Namespace(web_port=3000), root, root)
        flow.derived_tests_dir = root / "tests"; flow.derived_tests_dir.mkdir()
        flow.tests_dir = flow.derived_tests_dir; flow.derived_as_specs = True
        node = {"id": "A", "name": "Create", "description": "A created record shows “Done” after “Create”.",
                "scenarios": [{"name": "Create", "steps": [
                    {"keyword": "WHEN", "content": "Click “Create”."},
                    {"keyword": "THEN", "content": "A created record shows “Done”."}]}]}
        flow.derived_nodes = [node]; flow.derived_case_reviews = {}
        flow.metric = Mock(); flow.snapshot_protected = Mock()
        flow.wound_down = Mock(return_value=False); flow.review_budget_spent = Mock(return_value=False)
        flow.remaining = Mock(return_value=5000); flow.final_phase_reserve = Mock(return_value=0)
        target = review_targets([node], Fixtures(), include_all=True)[0]
        initial = {"confidence": 1, "steps": [{"op": "click", "target": "Create"},
                                               {"op": "expect_visible", "target": "Done"}]}
        path = flow.derived_tests_dir / "A.spec.ts"
        path.write_text(validate_proposal(initial, target, Fixtures()))
        return flow, target, path

    def test_audit_feedback_regenerates_then_reaudits_the_new_version(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, target, path = self.setup_flow(Path(folder))
            original = path.read_text()
            def turn(prompt, allowance, label, **kwargs):
                if "audit correction" in label:
                    self.assertIn("verify persistence", prompt)
                    return True, json.dumps({"scenarios": [{"id": target["id"], "confidence": 1,
                        "steps": [{"op": "click", "target": "Create"}, {"op": "reload"},
                                  {"op": "expect_visible", "target": "Done"}]}]})
                shown = json.loads(prompt.split("\nCases: ")[1])
                return True, json.dumps([{ "id": row["id"],
                    "status": "approved_behavior" if "page.reload" in row["case"] else "needs_correction",
                    "requirement_quote": "A created record shows “Done”.",
                    "test_quote": "await h.expectTextsVisible(page, ['Done']);",
                    "reason": "verify persistence after reload"} for row in shown])
            flow.text_turn = Mock(side_effect=turn)
            flow.review_derived_cases({"A"}, reserve_requests=1)
            self.assertFalse(flow.trusted_derived_case("A", target["title"] + " [model]"))
            self.assertEqual(flow.correct_derived_cases({"A"}), {"A"})
            self.assertIn("page.reload", path.read_text())
            self.assertEqual(path.read_text().count("test("), 1)
            self.assertEqual((flow.derived_tests_dir / "review/before-correction-1-A.ts").read_text(), original)
            self.assertFalse(flow.trusted_derived_case("A", target["title"] + " [model]"))
            flow.review_derived_cases({"A"})
            self.assertTrue(flow.trusted_derived_case("A", target["title"] + " [model]"))
            path.write_text(path.read_text() + "// changed\n")
            self.assertFalse(flow.trusted_derived_case("A", target["title"] + " [model]"))

    def test_rejected_correction_keeps_original_and_budget_exhaustion_uses_no_model(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, target, path = self.setup_flow(Path(folder))
            flow.derived_case_reviews[("A", target["title"] + " [model]")] = {
                "node_id": "A", "scenario_id": target["id"], "status": "needs_correction", "reason": "bad oracle"}
            original = path.read_text()
            flow.text_turn = Mock(return_value=(True, '{"scenarios": [{"id":"S1","confidence":1,"steps":[{"op":"shell"}]}]}'))
            self.assertEqual(flow.correct_derived_cases({"A"}), set())
            self.assertEqual(path.read_text(), original)
            flow.text_turn.reset_mock()
            self.assertEqual(flow.correct_derived_cases({"A"}), set())
            flow.text_turn.assert_not_called()  # one correction round per scenario
            path.write_text(path.read_text() + "// sibling spec changed\n")
            self.assertEqual(flow.correct_derived_cases({"A"}), set())
            flow.text_turn.assert_not_called()  # a file version change does not reset the limit
            flow.derived_case_review_requests = 6
            flow.text_turn.reset_mock()
            self.assertEqual(flow.correct_derived_cases({"A"}), set())
            flow.text_turn.assert_not_called()

    def test_case_audit_batches_same_phase_and_retries_only_missing_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, _, _ = self.setup_flow(Path(folder))
            rows = [{"id": f"case-{index}", "node_id": "A", "title": f"Case {index}",
                     "status": "unreviewed", "requirement": "A created record shows Done.",
                     "case": "await page.click('Create');", "outcome": "A created record shows Done."}
                    for index in range(3)]
            flow.codegen_context_chars = Mock(return_value=1000000)
            shown_batches = []

            def audit(prompt, *_args, **_kwargs):
                shown = json.loads(prompt.split("\nCases: ")[1])
                shown_batches.append([item["id"] for item in shown])
                if len(shown_batches) == 1:
                    shown = shown[:2]  # model omitted one case in a valid batch
                return True, json.dumps([{"id": item["id"], "status": "needs_correction",
                                          "reason": "Missing state assertion"} for item in shown])

            flow.text_turn = Mock(side_effect=audit)
            with patch("main.collect_cases", return_value=rows), \
                    patch.dict("os.environ", {"OCTOS_ARC_DERIVED_CASE_REVIEW_BATCH": "3"}):
                flow.review_derived_cases({"A"})
            self.assertEqual(shown_batches, [["case-0", "case-1", "case-2"], ["case-2"]])
            self.assertEqual(flow.derived_case_review_requests, 2)
            self.assertTrue(all(row["status"] == "needs_correction" for row in rows))

    def test_case_audit_splits_oversized_batch_before_model_call(self):
        with tempfile.TemporaryDirectory() as folder:
            flow, _, _ = self.setup_flow(Path(folder))
            rows = [{"id": f"case-{index}", "node_id": "A", "title": f"Case {index}",
                     "status": "unreviewed", "requirement": "A created record shows Done.",
                     "case": "await page.click('Create');", "outcome": "A created record shows Done."}
                    for index in range(3)]
            flow.codegen_context_chars = Mock(side_effect=[1, 1000000, 1000000])
            shown_batches = []

            def audit(prompt, *_args, **_kwargs):
                shown = json.loads(prompt.split("\nCases: ")[1])
                shown_batches.append([item["id"] for item in shown])
                return True, json.dumps([{"id": item["id"], "status": "needs_correction",
                                          "reason": "Missing state assertion"} for item in shown])

            flow.text_turn = Mock(side_effect=audit)
            with patch("main.collect_cases", return_value=rows), \
                    patch.dict("os.environ", {"OCTOS_ARC_DERIVED_CASE_REVIEW_BATCH": "3"}):
                flow.review_derived_cases({"A"})
            self.assertEqual(shown_batches, [["case-0"], ["case-1", "case-2"]])
            self.assertEqual(flow.derived_case_review_requests, 2)


if __name__ == "__main__":
    unittest.main()
