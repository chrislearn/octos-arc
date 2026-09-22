import json
import unittest

from llm_proxy import BUDGET_NOTICE, WRITE_DECISION_NOTICE, destream_request, enforce_turn_budget, ensure_max_tokens, force_write_decision, inject_reasoning, request_shape, to_sse, trim_request, trim_system_prompt, usage_record


class InjectTests(unittest.TestCase):
    def test_qwen37_plus_uses_explicit_enable_thinking(self):
        for model in ('qwen3.7-plus', 'qwen3.7-plus-2026-05-26', 'provider/qwen3.7-plus'):
            body = json.dumps({'model': model, 'messages': [], 'thinking': {'type': 'enabled'},
                               'reasoning_effort': 'high'}).encode()
            for mode in ('none', 'off', 'disabled'):
                out = json.loads(inject_reasoning(body, mode))
                self.assertIs(out['enable_thinking'], False)
                self.assertNotIn('thinking', out)
                self.assertNotIn('reasoning_effort', out)
            self.assertTrue(json.loads(inject_reasoning(body, 'low'))['enable_thinking'])
            self.assertEqual(inject_reasoning(body, 'passthrough'), body)

    def test_should_add_low_effort_and_thinking_for_deepseek(self):
        out = json.loads(inject_reasoning(json.dumps({"model": "deepseek-v4-flash", "messages": []}).encode(), "low"))
        self.assertEqual(out["reasoning_effort"], "low")
        self.assertEqual(out["thinking"], {"type": "enabled"})

    def test_should_disable_thinking_for_none(self):
        out = json.loads(inject_reasoning(json.dumps({"model": "deepseek-v4-flash", "messages": [], "reasoning_effort": "high"}).encode(), "none"))
        self.assertEqual(out["thinking"], {"type": "disabled"})
        self.assertNotIn("reasoning_effort", out)

    def test_disabled_mode_overrides_kernel_enabled_default(self):
        body = json.dumps({"model": "deepseek-v4-flash", "messages": [],
                           "thinking": {"type": "enabled"}, "reasoning_effort": "high"}).encode()
        for mode in ("none", "off", "disabled"):
            out = json.loads(inject_reasoning(body, mode))
            self.assertEqual(out["thinking"], {"type": "disabled"})
            self.assertNotIn("reasoning_effort", out)

    def test_explicit_enabled_mode_can_override_disabled_kernel_default(self):
        body = json.dumps({"model": "deepseek-v4-flash", "messages": [],
                           "thinking": {"type": "disabled"}, "reasoning_effort": "none"}).encode()
        out = json.loads(inject_reasoning(body, "low"))
        self.assertEqual(out["thinking"], {"type": "enabled"})
        self.assertEqual(out["reasoning_effort"], "low")

    def test_should_leave_other_models_and_non_chat_bodies_alone(self):
        body = json.dumps({"model": "gpt-5", "messages": []}).encode()
        self.assertEqual(inject_reasoning(body, "low"), body)
        self.assertEqual(inject_reasoning(b"not json", "low"), b"not json")
        self.assertEqual(inject_reasoning(json.dumps({"model": "deepseek-v4-flash", "input": "x"}).encode(), "low"),
                         json.dumps({"model": "deepseek-v4-flash", "input": "x"}).encode())

    def test_should_respect_client_set_fields(self):
        out = json.loads(inject_reasoning(json.dumps({"model": "deepseek-v4-flash", "messages": [], "reasoning_effort": "high"}).encode(), "low"))
        self.assertEqual(out["reasoning_effort"], "high")


class UsageTests(unittest.TestCase):
    def test_should_extract_billing_fields(self):
        payload = json.dumps({"usage": {"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 64,
                                        "completion_tokens_details": {"reasoning_tokens": 5}}}).encode()
        rec = usage_record(payload, 123, "low")
        self.assertEqual((rec["prompt_tokens"], rec["completion_tokens"], rec["prompt_cache_hit_tokens"], rec["reasoning_tokens"]), (100, 20, 64, 5))

    def test_should_return_none_without_usage(self):
        self.assertIsNone(usage_record(b'{"choices": []}', 1, "low"))
        self.assertIsNone(usage_record(b"garbage", 1, "low"))


class SseTests(unittest.TestCase):
    def test_should_read_usage_from_last_sse_chunk_and_request_include_usage(self):
        sse = b'data: {"choices":[{"delta":{"content":"O"}}]}\n\ndata: {"choices":[],"usage":{"prompt_tokens":9,"completion_tokens":3}}\n\ndata: [DONE]\n'
        rec = usage_record(sse, 5, "low")
        self.assertEqual((rec["prompt_tokens"], rec["completion_tokens"]), (9, 3))
        out = json.loads(inject_reasoning(json.dumps({"model": "deepseek-v4-flash", "messages": [], "stream": True}).encode(), "low"))
        self.assertEqual(out["stream_options"], {"include_usage": True})


class ShapeTests(unittest.TestCase):
    def test_should_count_chars_per_role_and_tools(self):
        body = json.dumps({"model": "x", "messages": [{"role": "system", "content": "abc"}, {"role": "user", "content": "de"},
                                                       {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]}],
                           "tools": [{"type": "function", "function": {"name": "f"}}]}).encode()
        shape = request_shape(body)
        self.assertEqual((shape["messages"], shape["tools"], shape["system_chars"], shape["user_chars"]), (3, 1, 3, 2))
        self.assertGreater(shape["assistant_chars"], 0)


class DestreamTests(unittest.TestCase):
    def test_should_turn_streaming_request_into_json_and_back_into_sse(self):
        body, was = destream_request(json.dumps({"model": "m", "messages": [], "stream": True, "stream_options": {"include_usage": True}}).encode())
        self.assertTrue(was)
        self.assertEqual(json.loads(body)["stream"], False)
        self.assertNotIn("stream_options", json.loads(body))
        _, was2 = destream_request(json.dumps({"model": "m", "messages": []}).encode())
        self.assertFalse(was2)
        resp = json.dumps({"id": "x", "created": 1, "model": "m", "choices": [{"index": 0, "finish_reason": "tool_calls",
                           "message": {"role": "assistant", "content": None, "reasoning_content": "hm",
                                       "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "write_file", "arguments": "{}"}}]}}],
                           "usage": {"prompt_tokens": 5, "completion_tokens": 2}}).encode()
        sse = to_sse(resp).decode()
        chunks = [json.loads(l[5:]) for l in sse.splitlines() if l.startswith("data:") and l != "data: [DONE]"]
        self.assertEqual(chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"], "write_file")
        self.assertEqual(chunks[0]["choices"][0]["delta"]["tool_calls"][0]["index"], 0)
        self.assertEqual(chunks[1]["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(chunks[2]["usage"]["prompt_tokens"], 5)
        self.assertTrue(sse.endswith("data: [DONE]\n\n"))
        rec = usage_record(resp, 1, "low")
        self.assertEqual(rec["sse_chunks"], 0)


class TrimTests(unittest.TestCase):
    SYS = ("You are Octos.\n\n## Formatting Rules\nkeep f\n\n## Research & Search Rules\ndrop r\n### sub\ndrop too\n\n"
           "## Coding And Shell Rules\nkeep c\n### Output shape\nkeep o\n\n## Active Skills\n\n# Cron Scheduling\ndrop\n## Actions\ndrop\n"
           "# Skill Store\ndrop\n\n## Tool use discipline\nkeep t\n")

    def test_should_drop_listed_sections_including_subsections_and_skill_block(self):
        out = trim_system_prompt(self.SYS)
        for kept in ("You are Octos.", "## Formatting Rules", "keep f", "## Coding And Shell Rules", "keep c", "keep o", "## Tool use discipline", "keep t"):
            self.assertIn(kept, out)
        for dropped in ("Research", "drop r", "drop too", "Cron Scheduling", "Skill Store", "## Actions"):
            self.assertNotIn(dropped, out)

    def test_should_leave_unknown_prompts_untouched(self):
        self.assertEqual(trim_system_prompt("plain text\n## Something else\nbody"), "plain text\n## Something else\nbody")

    def test_should_remove_unused_tools_and_keep_coding_tools(self):
        body = json.dumps({"model": "m", "messages": [{"role": "system", "content": self.SYS}, {"role": "user", "content": "x"}],
                           "tools": [{"type": "function", "function": {"name": n}} for n in ("spawn", "bash", "write_file", "update_plan", "read_file")]}).encode()
        out = json.loads(trim_request(body))
        self.assertEqual([t["function"]["name"] for t in out["tools"]], ["bash", "write_file", "read_file"])
        self.assertNotIn("Research", out["messages"][0]["content"])
        self.assertEqual(out["messages"][1]["content"], "x")


class ExtraDropTests(unittest.TestCase):
    def test_should_drop_extra_tools_on_top_of_defaults(self):
        body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "x"}],
                           "tools": [{"type": "function", "function": {"name": n}} for n in ("bash", "write_file", "spawn", "shell")]}).encode()
        from llm_proxy import DROP_TOOLS
        out = json.loads(trim_request(body, DROP_TOOLS | {"bash", "shell"}))
        self.assertEqual([t["function"]["name"] for t in out["tools"]], ["write_file"])


class TurnBudgetTests(unittest.TestCase):
    def test_should_strip_tools_and_append_notice_once_budget_is_used(self):
        body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "x"}], "tools": [{"type": "function", "function": {"name": "bash"}}]}).encode()
        self.assertIs(enforce_turn_budget(body, 3, 6), body)
        self.assertIs(enforce_turn_budget(body, 99, 0), body)
        out = json.loads(enforce_turn_budget(body, 6, 6))
        self.assertNotIn("tools", out)
        self.assertEqual(out["messages"][-1], {"role": "user", "content": BUDGET_NOTICE})
        again = json.loads(enforce_turn_budget(json.dumps(out).encode(), 7, 6))
        self.assertEqual(sum(1 for m in again["messages"] if m.get("content") == BUDGET_NOTICE), 1)

    def test_should_close_read_tools_late_in_a_no_write_structured_turn(self):
        tools = [{"type": "function", "function": {"name": name}}
                 for name in ("read_file", "grep", "edit_file", "write_file")]
        body = json.dumps({"messages": [
            {"role": "assistant", "tool_calls": [{"id": "r1", "function": {
                "name": "read_file", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "r1", "content": "source"},
        ], "tools": tools}).encode()
        out = json.loads(force_write_decision(body, used=6, budget=8, elapsed=20))
        self.assertEqual([t["function"]["name"] for t in out["tools"]], ["edit_file", "write_file"])
        self.assertEqual(out["messages"][-1]["content"], WRITE_DECISION_NOTICE)

    def test_should_keep_reads_before_threshold_or_after_a_write_attempt(self):
        tools = [{"type": "function", "function": {"name": name}}
                 for name in ("read_file", "edit_file")]
        early = json.dumps({"messages": [], "tools": tools}).encode()
        self.assertIs(force_write_decision(early, used=3, budget=8, elapsed=20), early)
        written = json.dumps({"messages": [{"role": "assistant", "tool_calls": [{"id": "w", "function": {
            "name": "edit_file", "arguments": "{}"}}]}], "tools": tools}).encode()
        self.assertIs(force_write_decision(written, used=7, budget=8, elapsed=999), written)


class MaxTokensTests(unittest.TestCase):
    def test_should_raise_small_or_missing_max_tokens_and_keep_large(self):
        small = json.dumps({"model": "m", "messages": [], "max_tokens": 4096}).encode()
        self.assertEqual(json.loads(ensure_max_tokens(small, 32768))["max_tokens"], 32768)
        missing = json.dumps({"model": "m", "messages": []}).encode()
        self.assertEqual(json.loads(ensure_max_tokens(missing, 32768))["max_tokens"], 32768)
        large = json.dumps({"model": "m", "messages": [], "max_tokens": 65536}).encode()
        self.assertIs(ensure_max_tokens(large, 32768), large)
        self.assertIs(ensure_max_tokens(small, 0), small)


class CachedTokensTests(unittest.TestCase):
    def test_should_read_openai_style_cached_tokens(self):
        payload = json.dumps({"usage": {"prompt_tokens": 4014, "completion_tokens": 2,
                                        "prompt_tokens_details": {"cached_tokens": 3840}}}).encode()
        self.assertEqual(usage_record(payload, 1, "low")["prompt_cache_hit_tokens"], 3840)


class SystemOverrideTests(unittest.TestCase):
    def test_should_replace_all_system_messages_with_one(self):
        from llm_proxy import replace_system_prompt
        body = json.dumps({"model": "m", "messages": [{"role": "system", "content": "long"}, {"role": "system", "content": "more"}, {"role": "user", "content": "u"}]}).encode()
        out = json.loads(replace_system_prompt(body, "short"))
        self.assertEqual([m["role"] for m in out["messages"]], ["system", "user"])
        self.assertEqual(out["messages"][0]["content"], "short")
