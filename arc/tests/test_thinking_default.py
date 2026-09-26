"""Low reasoning remains enabled across task sizes and turn phases."""
import argparse
import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main as m


class ThinkingDefaultTests(unittest.TestCase):
    def test_medium_default_is_reserved_for_generated_tests_and_design(self):
        for model in ("qwen3.7-plus", "glm-5.3-flash"):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as tmp, patch.dict(
                    os.environ, {"MODEL": model}, clear=True):
                root = Path(tmp)
                flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
                proxy = Mock(mode="medium", no_tools=False, extra_drop_tools=set(),
                             turn_budget=8, turn_requests=0, no_action_exhausted=False,
                             hard_budget_exhausted=False, base_url="http://127.0.0.1:9999/v1")
                flow.llm_proxy = proxy
                flow.base_reasoning_mode = "medium"
                flow.protected_prefixes = lambda: []
                flow.restore_protected = lambda: []
                flow.driver = SimpleNamespace(run=Mock(return_value=(True, "done")), progress_deadline=None)
                for label, expected in (("derived scenario review", "medium"),
                                        ("derived case independent review", "medium"),
                                        ("application design", "medium"),
                                        ("whole application implement", "low"),
                                        ("A repair", "low")):
                    flow.turn("prompt", 60, label, expect_verification=False)
                    self.assertEqual(proxy.mode, expected, label)
        with patch.dict(os.environ, {"MODEL": "qwen3.7-plus", "OCTOS_ARC_REASONING": "medium"}, clear=True):
            self.assertEqual(m.turn_reasoning_for_model("qwen3.7-plus", "A implement"), "medium")

    def test_no_action_circuit_marks_turn_incomplete_even_if_kernel_reports_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = m.Flow(argparse.Namespace(web_port=3000), root, root)
            proxy = Mock(mode="medium", no_tools=False, extra_drop_tools=set(),
                         turn_budget=8, turn_requests=2, no_action_exhausted=True,
                         hard_budget_exhausted=False, base_url="http://127.0.0.1:9999/v1")
            flow.llm_proxy = proxy
            flow.base_reasoning_mode = "medium"
            flow.protected_prefixes = lambda: []
            flow.restore_protected = lambda: []
            flow.driver = SimpleNamespace(run=Mock(return_value=(True, "done")), progress_deadline=None)
            ok, reason = flow.turn("implement", 60, "A implement", expect_verification=False)
            self.assertFalse(ok)
            self.assertIn("local_no_action_limit", reason)

    def test_whole_app_generation_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            flow = m.Flow(argparse.Namespace(web_port=3000), Path(tmp), Path(tmp))
            flow.codegen_turn = Mock()
            self.assertFalse(flow.whole_app_codegen({}, []))
            flow.codegen_turn.assert_not_called()

    def test_default_proxy_mode_is_low_for_every_task_size_and_turn_phase(self):
        for nodes in (1, 32, 138):
            with self.subTest(nodes=nodes), tempfile.TemporaryDirectory() as tmp, patch.dict(
                    os.environ, {"OPENAI_BASE_URL": "https://provider.invalid/v1",
                                 "OCTOS_ARC_MODEL_ROUTES": ""}, clear=True):
                flow = m.Flow(argparse.Namespace(web_port=3000), Path(tmp), Path(tmp))
                flow.nodes_to_implement = nodes
                proxy = Mock(mode="low", base_url="http://127.0.0.1:9999/v1", no_tools=False,
                             extra_drop_tools=set(), turn_budget=0, turn_requests=0)
                proxy.start.return_value = proxy
                proxy.enable_edit_preflight.return_value = tmp
                with patch("main.LlmProxy", return_value=proxy) as factory:
                    flow.start_llm_proxy()
                self.assertEqual(factory.call_args.args[1], "low")
                self.assertEqual(flow.base_reasoning_mode, "low")
                for size in (0, 1000, 20000):
                    self.assertIsNone(flow.codegen_reasoning(size))
                flow.protected_prefixes = lambda: []
                flow.restore_protected = lambda: []
                flow.driver = SimpleNamespace(run=Mock(return_value=(True, "done")))
                for label in ("whole application design", "whole application implement", "R repair", "R rewrite"):
                    flow.turn("prompt", 60, label, expect_verification=False)
                    self.assertEqual(proxy.mode, "low")

    def test_explicit_auto_and_low_remain_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mode, nodes, expected in (("auto", 1, "none"), ("auto", 32, "low"), ("low", 1, "low")):
                with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://provider.invalid/v1",
                                            "OCTOS_ARC_REASONING": mode, "OCTOS_ARC_MODEL_ROUTES": ""}):
                    flow = m.Flow(argparse.Namespace(web_port=3000), Path(tmp), Path(tmp))
                    flow.nodes_to_implement = nodes
                    proxy = Mock(base_url="http://127.0.0.1:9999/v1")
                    proxy.start.return_value = proxy
                    proxy.enable_edit_preflight.return_value = tmp
                    with patch("main.LlmProxy", return_value=proxy) as factory:
                        flow.start_llm_proxy()
                    self.assertEqual(factory.call_args.args[1], expected)

    def test_gateway_and_bundled_policy_also_default_to_low(self):
        policy = tomllib.loads((m.BUNDLE_DIR / "arc-policy.toml").read_text())
        self.assertEqual(policy["reasoning"]["mode"], "low")
        for provider in ("openai", "deepseek"):
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                    "OCTOS_PROVIDER": provider, "OPENAI_BASE_URL": "http://localhost/v1"}, clear=True):
                m.build_octos_env(Path(tmp))
                config = json.loads((Path(tmp) / "config.json").read_text())
                self.assertEqual(config["gateway"]["reasoning_effort"], "low")

    def test_glm53_flash_defaults_medium_and_explicit_low_wins(self):
        for override, expected in ((None, "medium"), ("low", "low"), ("high", "high")):
            environment = {"MODEL": "glm-5.3-flash", "OPENAI_BASE_URL": "http://localhost/v1"}
            if override is not None:
                environment["OCTOS_ARC_REASONING"] = override
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, environment, clear=True):
                m.build_octos_env(Path(tmp))
                config = json.loads((Path(tmp) / "config.json").read_text())
                self.assertEqual(config["gateway"]["reasoning_effort"], expected)
                flow = m.Flow(argparse.Namespace(web_port=3000), Path(tmp), Path(tmp))
                proxy = Mock(base_url="http://127.0.0.1:9999/v1")
                proxy.start.return_value = proxy
                proxy.enable_edit_preflight.return_value = tmp
                with patch("main.LlmProxy", return_value=proxy) as factory:
                    flow.start_llm_proxy()
                self.assertEqual(factory.call_args.args[1], expected)

    def test_qwen37_plus_defaults_medium_and_explicit_setting_wins(self):
        for model in ("qwen3.7-plus", "provider/qwen3.7-plus-2026-05-26"):
            for override, expected in ((None, "medium"), ("low", "low"), ("none", "none")):
                environment = {"MODEL": model, "OPENAI_BASE_URL": "http://localhost/v1"}
                if override is not None:
                    environment["OCTOS_ARC_REASONING"] = override
                with self.subTest(model=model, override=override), tempfile.TemporaryDirectory() as tmp, patch.dict(
                        os.environ, environment, clear=True):
                    m.build_octos_env(Path(tmp))
                    config = json.loads((Path(tmp) / "config.json").read_text())
                    self.assertEqual(config["gateway"]["reasoning_effort"], expected)
                    flow = m.Flow(argparse.Namespace(web_port=3000), Path(tmp), Path(tmp))
                    proxy = Mock(base_url="http://127.0.0.1:9999/v1")
                    proxy.start.return_value = proxy
                    proxy.enable_edit_preflight.return_value = tmp
                    with patch("main.LlmProxy", return_value=proxy) as factory:
                        flow.start_llm_proxy()
                    self.assertEqual(factory.call_args.args[1], expected)
