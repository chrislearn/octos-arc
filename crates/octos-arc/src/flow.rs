//! The harness main loop (`Flow` in `arc/main.py`): per node implement →
//! acceptance → repair ≤ K, commit on improvement, roll back on regression,
//! then the full parallel suite and the startup rehearsal.
//!
//! Tool-mode turns (a kernel session with file/shell tools) are not wired
//! yet: trees that need them, and codegen nodes whose repairs fall back to
//! tool mode, stop at the best state reached so far and say so in the log.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use std::time::{Duration, Instant};

use eyre::{Result, bail};
use regex::Regex;
use serde_json::{Value, json};

use crate::acceptance::{self, AcceptanceRunner, AppServer, RunSummary, SpecMap};
use crate::budget::{self, Global};
use crate::codegen::{self, CodegenInputs};
use crate::events::Events;
use crate::git::Git;
use crate::llm::{Completer, CompletionRequest};
use crate::plan::RunPlan;
use crate::policy::Policy;
use crate::prompts::Prompts;
use crate::run::RunnerSpec;
use crate::tree;

static DIGITS: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\d+").unwrap());
static TEST_ID: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[^A-Za-z0-9._-]+").unwrap());

fn tail(text: &str, n: usize) -> String {
    let count = text.chars().count();
    text.chars().skip(count.saturating_sub(n)).collect()
}

pub struct Flow {
    policy: Policy,
    prompts: Prompts,
    output_dir: PathBuf,
    req_dir: PathBuf,
    tests_dir: Option<PathBuf>,
    bundle_dir: Option<PathBuf>,
    web_port: u16,
    smoke_port: u16,
    events: Events,
    git: Git,
    llm: Box<dyn Completer>,
    tree: Value,
    ordered: Vec<Value>,
    node_ids: Vec<String>,
    folder_children: BTreeMap<String, Vec<String>>,
    plan: RunPlan,
    budget: Global,
    spec_map: SpecMap,
    all_specs: Vec<String>,
    extra_ports: Vec<u16>,
    runner: Option<AcceptanceRunner>,
    mem_limit: Option<u64>,
    private_playwright: Option<PathBuf>,
    test_verdict: BTreeMap<String, Option<bool>>,
    impl_failed: Vec<String>,
    pending_corrections: Vec<String>,
    codegen_blocked: bool,
    unchanged: BTreeSet<String>,
    probe_summaries: BTreeMap<String, RunSummary>,
}

/// How a node is rebuilt when round 0 passes nothing.
enum Rebuild {
    Codegen { codegen_prompt: String },
}

pub struct RunOutcome {
    pub failed_nodes: Vec<String>,
    pub aborted: Option<String>,
}

impl Flow {
    pub fn new(
        policy: Policy,
        prompts: Prompts,
        spec: &RunnerSpec,
        tree: Value,
        llm: Box<dyn Completer>,
        events: Events,
    ) -> Result<Self> {
        let ordered = tree::topo_order(&tree);
        if ordered.is_empty() {
            bail!("no ATOMIC requirement nodes found");
        }
        let node_ids: Vec<String> = ordered.iter().map(tree::node_id).collect();
        let output_dir = spec.output_dir.clone();
        let evolution = has_app(&output_dir);
        let unchanged = if evolution {
            tree::unchanged_node_ids(&ordered, &previous_requirement_records(&output_dir))
        } else {
            BTreeSet::new()
        };
        let nodes_to_implement = node_ids
            .iter()
            .filter(|id| !unchanged.contains(*id))
            .count();
        let plan = RunPlan::new(&policy, &tree, ordered.len(), nodes_to_implement, evolution)?;
        let budget = Global::new(plan.time_budget_seconds);
        let mut smoke_port = policy.ports.smoke_port;
        if smoke_port == spec.web_port {
            smoke_port += 1;
        }
        let tests_dir = spec.tests_dir.clone().filter(|d| d.is_dir());
        let (all_specs, spec_map, extra_ports) = match &tests_dir {
            Some(dir) => {
                let specs = acceptance::list_specs(dir);
                let map = acceptance::map_specs_to_nodes(&specs, &node_ids);
                let extra: Vec<u16> = if policy.ports.extra_port_contract {
                    acceptance::spec_base_ports(dir)
                        .into_iter()
                        .filter(|p| *p != spec.web_port)
                        .collect()
                } else {
                    Vec::new()
                };
                (specs, map, extra)
            }
            None => (
                Vec::new(),
                acceptance::map_specs_to_nodes(&[], &node_ids),
                Vec::new(),
            ),
        };
        let folder_children = tree::folder_descendants(&tree);
        Ok(Self {
            git: Git::new(&output_dir),
            policy,
            prompts,
            output_dir,
            req_dir: spec.requirement_path.clone(),
            tests_dir,
            bundle_dir: spec.bundle_dir.clone(),
            web_port: spec.web_port,
            smoke_port,
            events,
            llm,
            tree,
            ordered,
            node_ids,
            folder_children,
            plan,
            budget,
            spec_map,
            all_specs,
            extra_ports,
            runner: None,
            mem_limit: None,
            private_playwright: None,
            test_verdict: BTreeMap::new(),
            impl_failed: Vec::new(),
            pending_corrections: Vec::new(),
            codegen_blocked: false,
            unchanged,
            probe_summaries: BTreeMap::new(),
        })
    }

    // -- helpers ----------------------------------------------------------

    fn log(&mut self, line: impl AsRef<str>) {
        self.events.log(line);
    }

    fn mark(&mut self, kind: &str, node_id: &str, message: Option<&str>) {
        let (phase, status) = match kind {
            "design_started" => ("design", "running"),
            "design_done" => ("design", "completed"),
            "design_failed" => ("design", "failed"),
            "implementation_started" => ("implement", "running"),
            "implementation_done" => ("implement", "completed"),
            "implementation_failed" => ("implement", "failed"),
            "test_passed" => ("test", "passed"),
            "test_failed" => ("test", "failed"),
            other => panic!("unknown mark {other}"),
        };
        let aliases = if self.policy.acceptance.alias_spec_ids {
            self.spec_map.aliases_for(node_id)
        } else {
            Vec::new()
        };
        self.events
            .requirement_state(node_id, phase, status, message, &aliases);
    }

    fn has_app(&self) -> bool {
        has_app(&self.output_dir)
    }

    fn remaining(&self) -> f64 {
        self.budget.remaining()
    }

    fn time_up(&self) -> bool {
        self.budget.time_up()
    }

    fn corrections_text(&mut self) -> String {
        if self.pending_corrections.is_empty() {
            return String::new();
        }
        let items: Vec<String> = self
            .pending_corrections
            .drain(..)
            .map(|c| format!("- {c}"))
            .collect();
        self.prompts
            .render("corrections-header", &[("items", &items.join("\n"))])
            .unwrap_or_default()
    }

    fn perf_text(&self) -> String {
        if self.policy.prompts.perf_contract && self.plan.needs_session {
            self.prompts.get("performance-contract").to_string()
        } else {
            String::new()
        }
    }

    fn sources_text(&self) -> String {
        let limit = self.policy.prompts.inline_source_chars;
        if limit == 0 {
            return String::new();
        }
        format!(
            "{}\n",
            codegen::inline_sources(&self.prompts, &self.output_dir, limit, false)
        )
    }

    fn codegen_mode(&self) -> bool {
        self.plan.codegen && !self.codegen_blocked
    }

    fn correction(&self, key: &str, vars: &[(&str, &str)]) -> String {
        self.prompts
            .correction(key, vars)
            .unwrap_or_else(|_| key.to_string())
    }

    /// Just the spec file contents for a node (codegen prompts): the node's
    /// specs, then every helper file.
    fn spec_bodies(&self, node_id: &str) -> String {
        let Some(tests_dir) = &self.tests_dir else {
            return "(none)".into();
        };
        let mut files: Vec<String> = self.spec_map.specs_for(node_id).to_vec();
        for helper in acceptance::support_files(tests_dir) {
            if !files.contains(&helper) {
                files.push(helper);
            }
        }
        let mut parts = Vec::new();
        for rel in &files {
            let Ok(text) = std::fs::read_to_string(tests_dir.join(rel)) else {
                continue;
            };
            let text = text.trim();
            parts.push(if files.len() == 1 {
                text.to_string()
            } else {
                format!("--- {rel} ---\n{text}")
            });
        }
        if parts.is_empty() {
            "(none)".into()
        } else {
            parts.join("\n")
        }
    }

    // -- acceptance -------------------------------------------------------

    /// Prefer the Playwright already on the machine (the runner image ships
    /// one). A private install is the last resort and never touches shared
    /// state: own npm cache, own browser dir, pinned version, removed at exit.
    fn setup_playwright(&mut self) {
        let Some(tests_dir) = self.tests_dir.clone() else {
            return;
        };
        let mut notes = Vec::new();
        let explicit = (!self.policy.acceptance.playwright_root.is_empty())
            .then(|| PathBuf::from(&self.policy.acceptance.playwright_root));
        let candidates = acceptance::playwright_candidates(
            explicit.as_deref(),
            self.bundle_dir.as_deref(),
            Some(&tests_dir),
            &self.output_dir,
        );
        let mut root = acceptance::find_playwright_root(&candidates);
        if root.is_none() {
            root = acceptance::find_playwright_by_search(&mut notes, 6, Duration::from_secs(25));
        }
        let mut env_extra = Vec::new();
        if root.is_none() && self.policy.acceptance.install_playwright {
            let version = acceptance::playwright_version_hint(
                Some(&tests_dir),
                &self.policy.acceptance.playwright_fallback_version,
            );
            notes.push(format!("[acceptance] no preinstalled Playwright found; private install of @playwright/test@{version}"));
            let private =
                std::env::temp_dir().join(format!("octos-arc-playwright-{}", std::process::id()));
            self.private_playwright = Some(private.clone());
            if let Some((found, extra)) = acceptance::ensure_playwright(
                &private,
                &mut notes,
                Duration::from_secs(self.policy.acceptance.install_timeout_seconds),
                &version,
            ) {
                root = Some(found);
                env_extra = extra;
            }
        }
        for note in notes {
            self.log(note);
        }
        let Some(root) = root else {
            self.log(
                "[acceptance] Playwright unavailable; nodes will be judged by the final check only",
            );
            return;
        };
        let limit = acceptance::container_memory_limit();
        self.mem_limit = limit;
        let workers = acceptance::workers_for_memory(
            limit,
            self.policy.acceptance.workers,
            self.policy.acceptance.memory_per_worker_mib,
        );
        let work_dir = acceptance::acceptance_work_dir(&root);
        self.runner = Some(AcceptanceRunner {
            root: root.clone(),
            tests_dir: tests_dir.clone(),
            work_dir,
            timeout_ms: self.policy.acceptance.test_timeout_ms,
            workers,
            fully_parallel: self.policy.acceptance.fully_parallel,
            env_extra,
            wall_timeout: Duration::from_secs(self.policy.acceptance.run_wall_timeout_seconds),
        });
        let limit_text = limit
            .map(|l| format!(" (container memory limit {} MiB)", l / (1024 * 1024)))
            .unwrap_or_default();
        self.log(format!(
            "[acceptance] using Playwright at {}; workers={workers}{limit_text}",
            root.display()
        ));
    }

    fn cleanup_playwright(&mut self) {
        if let Some(private) = self.private_playwright.take()
            && private.exists()
        {
            let _ = std::fs::remove_dir_all(&private);
            self.log(format!(
                "[acceptance] removed private Playwright install {}",
                private.display()
            ));
        }
    }

    fn app_server(&self, grader_like: bool) -> AppServer {
        let mut server = AppServer::new(
            &self.output_dir,
            self.smoke_port,
            grader_like,
            self.extra_ports.clone(),
        );
        server.build_timeout = Duration::from_secs(self.policy.acceptance.build_timeout_seconds);
        server.start_wait = Duration::from_secs(self.policy.acceptance.start_wait_seconds);
        server
    }

    /// Build, start, run the specs, then undo whatever the test run mutated
    /// (a persisted counter at -1 would otherwise be committed as the seed).
    /// `grader_like` starts the backend with only PORT set, as the platform does.
    fn run_specs(
        &mut self,
        specs: &[String],
        workers: Option<u32>,
        grader_like: bool,
    ) -> RunSummary {
        self.git.snapshot_worktree();
        let started = Instant::now();
        let mut server = self.app_server(grader_like);
        let summary = match server.build().or_else(|| server.start()) {
            Some(error) => RunSummary::error(error),
            None => match &self.runner {
                Some(runner) => runner.run(
                    specs,
                    &format!("http://127.0.0.1:{}", self.smoke_port),
                    workers,
                ),
                None => RunSummary::error("no Playwright runner"),
            },
        };
        server.stop();
        self.git.restore_worktree();
        if summary.error.is_none() {
            self.log(format!(
                "[acceptance] {}/{} passed in {}s ({})",
                summary.passed,
                summary.total,
                started.elapsed().as_secs(),
                specs.join(", ")
            ));
        } else if let Some(error) = &summary.error
            && error.starts_with("Playwright collected 0 tests")
        {
            self.log(format!("[acceptance] {}", tail(error, 300)));
        }
        summary
    }

    fn record_tests(&mut self, node_id: &str, summary: &RunSummary) {
        for r in &summary.results {
            let test_id: String = TEST_ID
                .replace_all(&r.title, "-")
                .chars()
                .take(120)
                .collect();
            self.events.emit(
                "test_result",
                json!({"node_id": node_id, "test_id": test_id, "title": r.title, "file": r.file, "ok": r.ok, "type": "e2e"}),
            );
        }
    }

    fn failures_of(&self, summary: &RunSummary) -> String {
        acceptance::failure_summaries(summary, 8, 900, self.policy.acceptance.test_timeout_ms)
    }

    fn startup_failure_digest(&self, error: &str, grader: bool) -> String {
        let limited: String = error.chars().take(if grader { 700 } else { 600 }).collect();
        self.prompts
            .render(
                if grader {
                    "startup-failure-grader"
                } else {
                    "startup-failure"
                },
                &[("error", &limited)],
            )
            .unwrap_or_else(|_| format!("- Feature: app startup\n  Observation: {limited}"))
    }

    // -- turns ------------------------------------------------------------

    /// Run a tool-less turn; parse and write the file blocks from the reply.
    /// Returns (ok, text) like the Python `codegen_turn`.
    fn codegen_turn(&mut self, prompt: &str, timeout: Duration, label: &str) -> (bool, String) {
        let user = codegen::with_format(&self.prompts, prompt);
        let mode = self.plan.reasoning_for(label);
        let started = Instant::now();
        let request = CompletionRequest {
            label,
            system: self.prompts.get("codegen-system"),
            user: &user,
            mode,
            timeout: timeout.max(Duration::from_secs(60)),
        };
        let result = self.llm.complete(&request);
        let (ok, text) = match result {
            Ok(completion) => {
                self.events.emit(
                    "usage",
                    json!({"label": label, "mode": mode.label(), "elapsed_ms": completion.elapsed_ms, "attempts": completion.attempts,
                        "prompt_tokens": u64::from(completion.usage.input_tokens) + u64::from(completion.usage.cache_read_tokens),
                        "completion_tokens": completion.usage.output_tokens, "reasoning_tokens": completion.usage.reasoning_tokens,
                        "cache_hit_tokens": completion.usage.cache_read_tokens, "truncated": completion.truncated}),
                );
                let files = codegen::parse_file_blocks(&completion.text);
                if files.is_empty() {
                    if completion.truncated {
                        (
                            false,
                            "output truncated by the model's max_tokens; no complete file block"
                                .to_string(),
                        )
                    } else {
                        self.log(format!("[codegen] {label}: reply contained no file blocks"));
                        (
                            false,
                            "codegen reply contained no <<<FILE>>> blocks".to_string(),
                        )
                    }
                } else {
                    match codegen::write_files(&self.output_dir, &files) {
                        Ok(written) => {
                            let shown: Vec<&String> = written.iter().take(8).collect();
                            self.log(format!(
                                "[codegen] {label}: wrote {} file(s): {shown:?}",
                                written.len()
                            ));
                            let deduped = codegen::dedupe_nav_links(&self.output_dir);
                            if !deduped.is_empty() {
                                self.log(format!("[codegen] {label}: removed static nav links duplicating the NAV placeholder in {deduped:?}"));
                            }
                            if completion.truncated {
                                self.log(format!("[codegen] {label}: reply was truncated by max_tokens; testing the files that arrived"));
                            }
                            (true, completion.text)
                        }
                        Err(error) => (false, format!("could not write files: {error}")),
                    }
                }
            }
            Err(error) => (false, format!("{error:#}")),
        };
        self.log(format!(
            "[flow] {label} {} in {}s: {:?}",
            if ok { "ok" } else { "FAILED" },
            started.elapsed().as_secs(),
            tail(&text, 240)
        ));
        (ok, text)
    }

    /// Copy the app sources the next repair will overwrite into
    /// `.arc/codegen/<node>-r<attempt>/` (the platform keeps the workspace but
    /// not our git history).
    fn snapshot_sources(&mut self, node_id: &str, attempt: u32) {
        let dest = self
            .output_dir
            .join(".arc/codegen")
            .join(format!("{node_id}-r{attempt}"));
        let _ = std::fs::remove_dir_all(&dest);
        let mut count = 0;
        for rel in ["frontend/src", "backend"] {
            let src = self.output_dir.join(rel);
            if !src.is_dir() {
                continue;
            }
            let mut stack = vec![src.clone()];
            while let Some(dir) = stack.pop() {
                let Ok(entries) = std::fs::read_dir(&dir) else {
                    continue;
                };
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_dir() {
                        if entry.file_name() != "node_modules" {
                            stack.push(path);
                        }
                        continue;
                    }
                    let keep = path
                        .extension()
                        .and_then(|e| e.to_str())
                        .is_some_and(|e| matches!(e, "html" | "js" | "json" | "css"));
                    if !keep {
                        continue;
                    }
                    let target = dest.join(path.strip_prefix(&self.output_dir).unwrap_or(&path));
                    if let Some(parent) = target.parent() {
                        let _ = std::fs::create_dir_all(parent);
                    }
                    if std::fs::copy(&path, &target).is_ok() {
                        count += 1;
                    }
                }
            }
        }
        self.log(format!("[flow] {node_id}: {count} source file(s) snapshotted to .arc/codegen/{node_id}-r{attempt}"));
    }

    fn restore_app(&mut self, sha: &str) {
        self.git.restore_app(sha);
        self.log(format!(
            "[flow] restored frontend/ and backend/ to best commit {}",
            &sha[..sha.len().min(8)]
        ));
    }

    fn commit(&mut self, message: &str) {
        match self.git.commit(message) {
            Ok(true) => {
                let sha = self.git.head().unwrap_or_default();
                self.events
                    .emit("commit", json!({"message": message, "sha": sha}));
            }
            Ok(false) => {}
            Err(error) => self.log(format!("[git] commit failed: {error}")),
        }
    }

    /// Returns Some(true/false) for a real verdict, None when no local run
    /// happened. `rebuild` yields a full re-implementation prompt; it is used
    /// once when round 0 passes nothing — rewriting beats patching a
    /// structurally broken first attempt.
    fn acceptance_loop(
        &mut self,
        node_id: &str,
        specs: &[String],
        deadline: Instant,
        rebuild: Option<Rebuild>,
    ) -> Option<bool> {
        if self.runner.is_none() || specs.is_empty() {
            return None;
        }
        let repair_rounds = self.policy.repair.rounds;
        let mut best_passed: i64 = -1;
        let mut best_sha = self.git.head();
        let mut regressions = 0u32;
        let mut stalls = 0u32;
        let mut rewrite_used = false;
        let mut previous_failures: Option<String> = None;
        self.codegen_blocked = false;
        for attempt in 0..=repair_rounds {
            let mut summary = self.run_specs(specs, None, false);
            if summary.error.is_some() && summary.killed {
                self.log(format!(
                    "[acceptance] {node_id}: test runner killed ({}); no verdict from this round",
                    tail(summary.error.as_deref().unwrap_or(""), 120)
                ));
                return None;
            }
            let (passed, failures) = if let Some(error) = summary.error.clone() {
                self.log(format!(
                    "[acceptance] {node_id} infrastructure error: {}",
                    error.chars().take(300).collect::<String>()
                ));
                let digest = self.startup_failure_digest(&error, false);
                summary = RunSummary {
                    passed: 0,
                    total: specs.len().max(1),
                    ..Default::default()
                };
                (0usize, digest)
            } else {
                self.record_tests(node_id, &summary);
                (summary.passed, self.failures_of(&summary))
            };
            self.log(format!(
                "[acceptance] {node_id} round {attempt}: {passed}/{}",
                summary.total
            ));
            let normalized = DIGITS.replace_all(&failures, "#").into_owned();
            if !normalized.is_empty() && previous_failures.as_deref() == Some(normalized.as_str()) {
                self.codegen_blocked = true;
                let correction = self.correction("identical_failure", &[]);
                self.pending_corrections.push(correction);
                self.log(format!(
                    "[flow] {node_id}: identical failure twice; switching repairs to tool mode"
                ));
            }
            previous_failures = Some(normalized);
            if attempt >= self.policy.repair.codegen_repairs
                && passed < summary.total
                && self.codegen_mode()
            {
                // Repeated codegen repairs re-emit the same files; one cheap codegen repair is allowed, then tools.
                self.codegen_blocked = true;
                self.log(format!("[flow] {node_id}: codegen attempt {attempt} still failing; repairs use tool mode"));
            }
            for line in failures.lines() {
                let trimmed = line.trim();
                if trimmed.starts_with("Failed at:") || trimmed.starts_with("Observation:") {
                    let squashed: String = trimmed.split_whitespace().collect::<Vec<_>>().join(" ");
                    self.log(format!(
                        "[acceptance]   {}",
                        squashed.chars().take(360).collect::<String>()
                    ));
                }
            }
            if summary.total > 0 && passed == summary.total {
                self.commit(&format!(
                    "{node_id} (accepted): {passed}/{} acceptance tests pass",
                    summary.total
                ));
                return Some(true);
            }
            let passed_i = passed as i64;
            if passed_i > best_passed {
                if best_passed >= 0 {
                    self.commit(&format!(
                        "{node_id} (repair {attempt}): {passed}/{} pass",
                        summary.total
                    ));
                }
                best_passed = passed_i;
                best_sha = self.git.head();
                regressions = 0;
                stalls = 0;
            } else if passed_i == best_passed && attempt > 0 {
                stalls += 1;
                if stalls >= self.policy.repair.stall_limit {
                    self.log(format!(
                        "[flow] {node_id}: no improvement for two repairs; keeping the best state"
                    ));
                    break;
                }
            } else if passed_i < best_passed {
                regressions += 1;
                if regressions >= self.policy.repair.regression_limit
                    && let Some(sha) = best_sha.clone()
                {
                    self.restore_app(&sha);
                    let correction = self.correction(
                        "regressions_restored",
                        &[
                            ("best", &best_passed.to_string()),
                            ("total", &summary.total.to_string()),
                        ],
                    );
                    self.pending_corrections.push(correction);
                    regressions = 0;
                }
            }
            if attempt == repair_rounds {
                break;
            }
            let left = deadline
                .saturating_duration_since(Instant::now())
                .as_secs_f64();
            if left < self.policy.budget.min_repair_seconds as f64 || self.time_up() {
                self.log(format!(
                    "[flow] {node_id}: {left:.0}s left, below the {}s a repair needs; keeping the best state",
                    self.policy.budget.min_repair_seconds
                ));
                break;
            }
            self.snapshot_sources(node_id, attempt);
            let slow = summary.slow(self.policy.acceptance.slow_ms);
            let slow_text = if slow.is_empty() {
                String::new()
            } else {
                let perf = self.perf_text();
                self.prompts
                    .render(
                        "slow-tests",
                        &[("slow", &slow.join("; ")), ("performance", &perf)],
                    )
                    .unwrap_or_default()
            };
            let turn_timeout =
                Duration::from_secs_f64(left.min(self.policy.budget.node_timeout_seconds as f64));
            if passed == 0
                && !rewrite_used
                && self.policy.repair.rewrite_on_zero
                && let Some(Rebuild::Codegen { codegen_prompt }) = &rebuild
            {
                rewrite_used = true;
                self.log(format!(
                    "[flow] {node_id}: nothing passed; one full rewrite turn instead of a patch"
                ));
                if self.codegen_mode() {
                    let failures_text = if failures.is_empty() {
                        "(no detail)".to_string()
                    } else {
                        failures.clone()
                    };
                    match codegen::rewrite_prompt(
                        &self.prompts,
                        codegen_prompt,
                        &failures_text,
                        &self.output_dir,
                        self.policy.prompts.codegen_source_chars,
                    ) {
                        Ok(prompt) => {
                            self.codegen_turn(
                                &prompt,
                                turn_timeout,
                                &format!("{node_id} rewrite (repair {})", attempt + 1),
                            );
                        }
                        Err(error) => self.log(format!(
                            "[flow] {node_id}: could not build the rewrite prompt: {error}"
                        )),
                    }
                    continue;
                }
                self.log(format!("[flow] {node_id}: rewrite needs tool mode, which octos arc run does not drive yet; keeping the best state"));
                break;
            }
            if !self.codegen_mode() {
                self.log(format!("[flow] {node_id}: repairs need tool mode, which octos arc run does not drive yet; keeping the best state"));
                break;
            }
            let corrections = self.corrections_text();
            let sources = self.sources_text();
            let port_rules = self
                .prompts
                .render(
                    "port-rules",
                    &[
                        ("smoke", &self.smoke_port.to_string()),
                        ("port", &self.web_port.to_string()),
                    ],
                )
                .unwrap_or_default();
            let failures_text = if failures.is_empty() {
                "(no detail)".to_string()
            } else {
                failures.clone()
            };
            let prompt = self.prompts.render(
                "repair",
                &[
                    ("node_id", node_id),
                    ("passed", &passed.to_string()),
                    ("total", &summary.total.to_string()),
                    ("failures", &failures_text),
                    ("corrections", &corrections),
                    ("slow", &slow_text),
                    ("sources", &sources),
                    ("port_rules", &port_rules),
                ],
            );
            match prompt {
                Ok(prompt) => {
                    let prompt = format!("{prompt}{}", self.prompts.get("codegen-repair-suffix"));
                    self.codegen_turn(
                        &prompt,
                        turn_timeout,
                        &format!("{node_id} repair {}/{repair_rounds}", attempt + 1),
                    );
                }
                Err(error) => self.log(format!(
                    "[flow] {node_id}: could not build the repair prompt: {error}"
                )),
            }
        }
        if best_passed > 0
            && let Some(sha) = best_sha
            && self.git.head().as_deref() != Some(sha.as_str())
        {
            self.restore_app(&sha);
            self.commit(&format!(
                "{node_id}: keep best acceptance state {best_passed}"
            ));
        }
        Some(false)
    }

    // -- per node ---------------------------------------------------------

    fn node_cycle(&mut self, node: &Value, index: usize, total: usize) {
        let node_id = tree::node_id(node);
        let specs: Vec<String> = self.spec_map.specs_for(&node_id).to_vec();
        self.codegen_blocked = false;
        let nodes_left = total - index + 1;
        let node_budget = budget::node_budget_seconds(
            self.policy.budget.node_time_budget_seconds,
            self.policy.budget.node_time_floor_seconds,
            self.remaining(),
            nodes_left,
        );
        let deadline = Instant::now() + Duration::from_secs_f64(node_budget.max(1.0));
        self.log(format!("[flow] node {index}/{total} {node_id} starting (budget {node_budget:.0}s, specs={specs:?})"));

        self.mark("design_started", &node_id, None);
        let design_wanted = self.plan.design_enabled;
        let inline_design = design_wanted && self.plan.design_inline;
        if design_wanted && !inline_design {
            self.log(format!("[flow] {node_id}: separate design turns need tool mode, which octos arc run does not drive yet"));
        }
        if !inline_design {
            self.mark(
                "design_done",
                &node_id,
                Some("design folded into the implementation prompt"),
            );
        }

        self.mark("implementation_started", &node_id, None);
        if !self.codegen_mode() {
            let message = "tool-mode implementation is not available in octos arc run yet; nothing was generated";
            self.log(format!("[flow] {node_id}: {message}"));
            self.mark("implementation_failed", &node_id, Some(message));
            self.impl_failed.push(node_id);
            return;
        }
        let description = node
            .get("description")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim()
            .to_string();
        let spec_text = self.spec_bodies(&node_id);
        let existing = self.has_app();
        let compact = {
            let inputs = CodegenInputs {
                node_id: &node_id,
                description: &description,
                spec: &spec_text,
                web_port: self.web_port,
                extra_ports: &self.extra_ports,
                n_nodes: self.plan.n_nodes,
                existing_app: existing.then_some(self.output_dir.as_path()),
                existing_app_chars: self.policy.prompts.codegen_source_chars,
            };
            match codegen::implement_prompt(&self.prompts, &inputs) {
                Ok(prompt) => prompt,
                Err(error) => {
                    let message = format!("could not build the codegen prompt: {error}");
                    self.mark("implementation_failed", &node_id, Some(&message));
                    self.impl_failed.push(node_id);
                    return;
                }
            }
        };
        match codegen::write_manifests(&self.output_dir) {
            Ok(written) if !written.is_empty() => {
                self.log(format!("[codegen] wrote manifests {written:?}"))
            }
            Ok(_) => {}
            Err(error) => self.log(format!("[codegen] could not write manifests: {error}")),
        }
        let implement_timeout = (self.policy.budget.node_timeout_seconds as f64)
            .min(self.policy.budget.implement_fraction * node_budget)
            .min(
                deadline
                    .saturating_duration_since(Instant::now())
                    .as_secs_f64(),
            );
        let (ok, text) = self.codegen_turn(
            &compact,
            Duration::from_secs_f64(implement_timeout.max(1.0)),
            &format!("{node_id} implement"),
        );
        let timed_out = !ok && text.to_lowercase().contains("timed out");
        if ok && !self.has_app() {
            self.log(format!("[flow] {node_id}: app layout incomplete after the turn; acceptance loop will drive the repair"));
            let correction = self.correction("layout_incomplete", &[]);
            self.pending_corrections.push(correction);
        }
        if !ok && !timed_out {
            self.mark("implementation_failed", &node_id, Some(&tail(&text, 500)));
            self.impl_failed.push(node_id);
            return;
        }
        if timed_out {
            self.log(format!("[flow] {node_id}: implement turn hit its {implement_timeout:.0}s cap; testing what exists"));
            let correction = self.correction("implement_timed_out", &[]);
            self.pending_corrections.push(correction);
        }
        if inline_design {
            self.mark(
                "design_done",
                &node_id,
                Some("design folded into the implementation turn (no JSON file)"),
            );
        }
        let done_message = if ok {
            tail(&text, 500)
        } else {
            "implement turn timed out; partial code".to_string()
        };
        self.mark("implementation_done", &node_id, Some(&done_message));
        let name = node.get("name").and_then(Value::as_str).unwrap_or("");
        self.commit(&format!("{node_id} (implement): {name}"));

        let verdict = self.acceptance_loop(
            &node_id,
            &specs,
            deadline,
            Some(Rebuild::Codegen {
                codegen_prompt: compact,
            }),
        );
        self.test_verdict.insert(node_id.clone(), verdict);
        match verdict {
            Some(true) => {
                let message = format!("{} acceptance spec file(s) pass locally", specs.len());
                self.mark("test_passed", &node_id, Some(&message));
            }
            Some(false) => self.mark(
                "test_failed",
                &node_id,
                Some("acceptance specs still failing after repair rounds"),
            ),
            None => {}
        }
    }

    /// Evolution probe: run each candidate node's specs against the existing
    /// app (no model); nodes that fully pass need no implementation turn.
    fn already_passing_nodes(&mut self, candidates: &[String]) -> BTreeSet<String> {
        let mut out = BTreeSet::new();
        for node_id in candidates {
            let specs: Vec<String> = self.spec_map.specs_for(node_id).to_vec();
            if specs.is_empty() {
                continue;
            }
            let summary = self.run_specs(&specs, None, false);
            if summary.error.is_some() || summary.total == 0 {
                continue;
            }
            self.log(format!(
                "[acceptance] probe {node_id}: {}/{} against the existing app",
                summary.passed, summary.total
            ));
            if summary.all_passed() {
                out.insert(node_id.clone());
                self.probe_summaries.insert(node_id.clone(), summary);
            }
        }
        out
    }

    /// Evolution: unchanged node — carry the design/impl over, re-run its specs.
    fn regression_cycle(&mut self, node: &Value) {
        let node_id = tree::node_id(node);
        let specs: Vec<String> = self.spec_map.specs_for(&node_id).to_vec();
        self.mark("design_started", &node_id, None);
        self.mark(
            "design_done",
            &node_id,
            Some("unchanged since the previous requirement version; carried over"),
        );
        self.mark("implementation_started", &node_id, None);
        self.mark(
            "implementation_done",
            &node_id,
            Some("carried over from the template application"),
        );
        let mut verdict = None;
        if self.runner.is_some() && !specs.is_empty() {
            let summary = match self.probe_summaries.remove(&node_id) {
                Some(summary) => summary,
                None => self.run_specs(&specs, None, false),
            };
            if let Some(error) = &summary.error {
                self.log(format!(
                    "[acceptance] regression {node_id} infrastructure error: {}",
                    error.chars().take(300).collect::<String>()
                ));
            } else {
                self.record_tests(&node_id, &summary);
                verdict = Some(summary.all_passed());
                self.log(format!(
                    "[acceptance] regression {node_id}: {}/{}",
                    summary.passed, summary.total
                ));
                if verdict == Some(false) {
                    let seconds = budget::node_budget_seconds(
                        self.policy.budget.node_time_budget_seconds,
                        self.policy.budget.node_time_floor_seconds,
                        self.remaining(),
                        2,
                    );
                    let deadline = Instant::now() + Duration::from_secs_f64(seconds.max(1.0));
                    let correction = self.correction("evolution_regression", &[]);
                    self.pending_corrections.push(correction);
                    verdict = self.acceptance_loop(&node_id, &specs, deadline, None);
                }
            }
        }
        self.test_verdict.insert(node_id.clone(), verdict);
        match verdict {
            Some(true) => self.mark(
                "test_passed",
                &node_id,
                Some("regression specs pass locally"),
            ),
            Some(false) => self.mark(
                "test_failed",
                &node_id,
                Some("regression specs fail after repair rounds"),
            ),
            None => {}
        }
    }

    /// Run EVERY spec file together, files in parallel, like the grader does.
    /// Per-node runs cannot see cross-node interference through shared server
    /// state; this pass can. The repair rounds after a failing suite need
    /// tool mode (not wired yet), so this pass records the verdicts of one
    /// grader-like round.
    fn final_acceptance(&mut self) {
        if self.runner.is_none() || self.tests_dir.is_none() {
            return;
        }
        let all_specs = self.all_specs.clone();
        let mut unverified: Vec<String> = self
            .test_verdict
            .iter()
            .filter(|(_, v)| **v != Some(true))
            .map(|(n, _)| n.clone())
            .collect();
        if unverified.is_empty() {
            unverified = self
                .node_ids
                .iter()
                .filter(|n| {
                    !self.spec_map.specs_for(n).is_empty() && !self.test_verdict.contains_key(*n)
                })
                .cloned()
                .collect();
        }
        if all_specs.len() < 2 && unverified.is_empty() {
            return; // single spec already judged by the node run
        }
        let workers = acceptance::workers_for_memory(
            self.mem_limit,
            self.policy.acceptance.final_workers,
            self.policy.acceptance.memory_per_worker_mib,
        );
        let summary = self.run_specs(&all_specs, Some(workers), true);
        if summary.error.is_some() && summary.killed {
            self.log(format!(
                "[acceptance] full suite could not run ({}); keeping per-node verdicts",
                tail(summary.error.as_deref().unwrap_or(""), 120)
            ));
            return;
        }
        let (grouped, summary) = if let Some(error) = summary.error.clone() {
            // The app does not even start the way the grader starts it: every node fails.
            self.log(format!(
                "[acceptance] full suite (grader-like start) failed: {}",
                error.chars().take(300).collect::<String>()
            ));
            for node_id in self.node_ids.clone() {
                self.test_verdict.insert(node_id, Some(false));
            }
            let mut grouped: BTreeMap<Option<String>, Vec<acceptance::TestOutcome>> =
                BTreeMap::new();
            grouped.insert(None, Vec::new());
            (
                grouped,
                RunSummary {
                    passed: 0,
                    total: all_specs.len(),
                    ..Default::default()
                },
            )
        } else {
            (
                acceptance::nodes_for_failures(&summary.results, &self.spec_map),
                summary,
            )
        };
        let failing_nodes: Vec<String> = grouped.keys().flatten().cloned().collect();
        let failing_text = if !failing_nodes.is_empty() {
            format!("{failing_nodes:?}")
        } else if grouped.contains_key(&None) && summary.results.is_empty() {
            "all".to_string()
        } else {
            "[]".to_string()
        };
        self.log(format!(
            "[acceptance] full suite round 0: {}/{}; failing nodes {failing_text}",
            summary.passed, summary.total
        ));
        if !summary.results.is_empty() {
            for node_id in self.node_ids.clone() {
                let specs = self.spec_map.specs_for(&node_id).to_vec();
                if specs.is_empty() {
                    continue;
                }
                let names: BTreeSet<String> = specs
                    .iter()
                    .filter_map(|p| {
                        Path::new(p)
                            .file_name()
                            .map(|n| n.to_string_lossy().into_owned())
                    })
                    .collect();
                let subset: Vec<acceptance::TestOutcome> = summary
                    .results
                    .iter()
                    .filter(|r| names.contains(&r.file))
                    .cloned()
                    .collect();
                self.record_tests(&node_id, &RunSummary::from_results(subset));
                self.test_verdict.insert(
                    node_id.clone(),
                    Some(!grouped.contains_key(&Some(node_id.clone()))),
                );
            }
        }
        if grouped.is_empty() {
            self.commit(&format!(
                "chore: full acceptance suite {}/{} pass (parallel)",
                summary.passed, summary.total
            ));
            return;
        }
        let failures = {
            let flat: Vec<acceptance::TestOutcome> = grouped.values().flatten().cloned().collect();
            self.failures_of(&RunSummary::from_results(flat))
        };
        for line in failures
            .lines()
            .filter(|l| l.trim().starts_with("Failed at:") || l.trim().starts_with("Observation:"))
        {
            let squashed: String = line.split_whitespace().collect::<Vec<_>>().join(" ");
            self.log(format!(
                "[acceptance]   {}",
                squashed.chars().take(360).collect::<String>()
            ));
        }
        self.log("[acceptance] full-suite repairs need tool mode, which octos arc run does not drive yet; keeping the verdicts");
    }

    /// Build and start exactly like the grader (only PORT set). A failure
    /// would go to a repair turn, which needs tool mode (not wired yet), so
    /// one attempt decides.
    fn rehearsal(&mut self) -> bool {
        self.log(format!(
            "[rehearsal] startup rehearsal 1/1 (smoke port {}, grader-like env)",
            self.smoke_port
        ));
        let mut server = self.app_server(true);
        let error = server.build().or_else(|| server.start());
        server.stop();
        match error {
            None => {
                self.log("[rehearsal] app builds and starts cleanly");
                true
            }
            Some(error) => {
                self.log(format!(
                    "[rehearsal] FAILED: {}",
                    error
                        .lines()
                        .next()
                        .unwrap_or("")
                        .chars()
                        .take(200)
                        .collect::<String>()
                ));
                self.log("[rehearsal] repair turns need tool mode, which octos arc run does not drive yet; submitting as-is");
                false
            }
        }
    }

    /// The platform counts FOLDER nodes as requirements too; derive their
    /// state from their atomic descendants.
    fn mark_folders(&mut self) {
        let folders = self.folder_children.clone();
        for (folder_id, leaves) in folders {
            if leaves.is_empty() {
                continue;
            }
            let verdicts: Vec<Option<bool>> = leaves
                .iter()
                .map(|l| self.test_verdict.get(l).copied().flatten())
                .collect();
            self.events
                .requirement_state(&folder_id, "design", "running", None, &[]);
            self.events.requirement_state(
                &folder_id,
                "design",
                "completed",
                Some(&format!("{} atomic children designed", leaves.len())),
                &[],
            );
            self.events
                .requirement_state(&folder_id, "implement", "running", None, &[]);
            let any_failed = leaves.iter().any(|l| self.impl_failed.contains(l));
            if verdicts.iter().all(|v| v.is_some()) || any_failed {
                let done: Vec<&String> = leaves
                    .iter()
                    .filter(|l| !self.impl_failed.contains(l))
                    .collect();
                if done.is_empty() {
                    self.events.requirement_state(
                        &folder_id,
                        "implement",
                        "failed",
                        Some("no atomic child implemented"),
                        &[],
                    );
                } else {
                    self.events.requirement_state(
                        &folder_id,
                        "implement",
                        "completed",
                        Some(&format!(
                            "{}/{} atomic children implemented",
                            done.len(),
                            leaves.len()
                        )),
                        &[],
                    );
                }
            }
            if verdicts.iter().all(|v| *v == Some(true)) {
                self.events.requirement_state(
                    &folder_id,
                    "test",
                    "passed",
                    Some(&format!("all {} atomic children pass", leaves.len())),
                    &[],
                );
            } else {
                let failing: Vec<&String> = leaves
                    .iter()
                    .zip(&verdicts)
                    .filter(|(_, v)| **v != Some(true))
                    .map(|(l, _)| l)
                    .collect();
                let names: Vec<&str> = failing.iter().map(|s| s.as_str()).collect();
                self.events.requirement_state(
                    &folder_id,
                    "test",
                    "failed",
                    Some(&format!("children not verified: {}", names.join(", "))),
                    &[],
                );
            }
        }
    }

    // -- run --------------------------------------------------------------

    pub fn run(&mut self) -> RunOutcome {
        self.events.emit(
            "run_started",
            json!({"nodes": self.node_ids, "time_budget_seconds": self.plan.time_budget_seconds, "codegen": self.plan.codegen,
                "evolution": self.plan.evolution, "web_port": self.web_port, "smoke_port": self.smoke_port,
                "reasoning": self.plan.base_reasoning.label(), "tests_dir": self.tests_dir}),
        );
        let outcome = self.run_inner();
        match outcome {
            Ok(()) => {
                for node_id in self.node_ids.clone() {
                    match self.test_verdict.get(&node_id).copied().flatten() {
                        Some(true) => self.mark(
                            "test_passed",
                            &node_id,
                            Some("acceptance specs pass (node run and full parallel suite)"),
                        ),
                        Some(false) => {
                            self.mark("test_failed", &node_id, Some("acceptance specs failing"))
                        }
                        None => {}
                    }
                }
                self.mark_folders();
                let failed: Vec<String> = self
                    .node_ids
                    .iter()
                    .filter(|n| self.test_verdict.get(*n).copied().flatten() != Some(true))
                    .cloned()
                    .collect();
                let message = if failed.is_empty() {
                    "all requirement nodes implemented and verified".to_string()
                } else {
                    format!("completed; nodes not verified: {}", failed.join(", "))
                };
                self.finish("run_completed", &message);
                RunOutcome {
                    failed_nodes: failed,
                    aborted: None,
                }
            }
            Err(error) => {
                let text = format!("{error:#}");
                self.log(format!("[flow] aborted: {text}"));
                for node_id in self.node_ids.clone() {
                    if !self.test_verdict.contains_key(&node_id) {
                        self.mark(
                            "test_failed",
                            &node_id,
                            Some(&format!(
                                "run aborted: {}",
                                text.chars().take(200).collect::<String>()
                            )),
                        );
                        self.test_verdict.insert(node_id, Some(false));
                    }
                }
                self.mark_folders();
                self.finish("run_failed", &text.chars().take(1000).collect::<String>());
                RunOutcome {
                    failed_nodes: self.node_ids.clone(),
                    aborted: Some(text),
                }
            }
        }
    }

    fn finish(&mut self, kind: &str, message: &str) {
        self.cleanup_playwright();
        let totals = self.llm.totals();
        self.log(format!("[usage] provider totals: {totals}"));
        self.events.emit("usage_total", totals);
        self.events.emit(
            kind,
            json!({"message": message, "elapsed_s": self.budget.elapsed().as_secs()}),
        );
    }

    fn run_inner(&mut self) -> Result<()> {
        let ids = self.node_ids.clone();
        self.log(format!(
            "[flow] {} atomic nodes in dependency order: {ids:?}; time budget {}s",
            ids.len(),
            self.plan.time_budget_seconds
        ));
        if self.plan.evolution {
            let to_implement: Vec<&String> = ids
                .iter()
                .filter(|i| !self.unchanged.contains(*i))
                .collect();
            self.log(format!(
                "[flow] evolution mode: existing app detected; unchanged nodes {:?}, to implement {to_implement:?}",
                self.unchanged
            ));
        }
        match self.tests_dir.clone() {
            Some(dir) => {
                let mapping: BTreeMap<&String, &Vec<String>> = self
                    .spec_map
                    .by_node
                    .iter()
                    .filter(|(_, v)| !v.is_empty())
                    .collect();
                self.log(format!(
                    "[tests] {} spec files at {}; mapping {mapping:?}; aliases {:?}",
                    self.all_specs.len(),
                    dir.display(),
                    self.spec_map.aliases
                ));
            }
            None => {
                self.log("[tests] no acceptance specs found; building from requirement text only")
            }
        }
        self.git.ensure_repo()?;
        self.setup_playwright();
        if self.plan.evolution && self.runner.is_some() {
            // The platform's template app carries no traceability records, so fingerprints cannot tell
            // what is new. A node whose specs already pass against the existing app is unchanged.
            let candidates: Vec<String> = ids
                .iter()
                .filter(|i| !self.unchanged.contains(*i))
                .cloned()
                .collect();
            let passing = self.already_passing_nodes(&candidates);
            self.unchanged.extend(passing);
            let to_implement: Vec<String> = ids
                .iter()
                .filter(|i| !self.unchanged.contains(*i))
                .cloned()
                .collect();
            self.plan
                .set_nodes_to_implement(&self.policy.clone(), to_implement.len())?;
            self.log(format!(
                "[flow] evolution mode after probing the existing app: unchanged {:?}, to implement {to_implement:?}",
                self.unchanged
            ));
        }
        let patience = Duration::from_secs(self.policy.reasoning.probe_patience_seconds);
        for line in self.llm.probe(patience) {
            self.log(line);
        }
        if self.plan.wants_skeleton && !self.plan.codegen {
            bail!(
                "this tree needs the skeleton and tool-mode turns, which octos arc run does not drive yet"
            );
        }
        let total = self.ordered.len();
        let ordered = self.ordered.clone();
        for (index, node) in ordered.iter().enumerate() {
            let node_id = tree::node_id(node);
            if self.time_up() {
                self.log(format!("[flow] time budget exhausted; skipping {node_id}"));
                self.mark("implementation_started", &node_id, None);
                self.mark(
                    "implementation_failed",
                    &node_id,
                    Some("skipped: time budget exhausted"),
                );
                self.impl_failed.push(node_id);
                continue;
            }
            if self.unchanged.contains(&node_id) {
                self.regression_cycle(node);
            } else {
                self.node_cycle(node, index + 1, total);
            }
        }
        if !self.time_up() {
            self.final_acceptance();
        }
        let undecided: Vec<String> = ids
            .iter()
            .filter(|i| {
                self.test_verdict.get(*i).copied().flatten().is_none()
                    && !self.impl_failed.contains(*i)
            })
            .cloned()
            .collect();
        let rehearsed = self.rehearsal();
        if !undecided.is_empty() {
            self.log(format!("[flow] nodes without a local verdict: {undecided:?}; the final check turn needs tool mode, so the rehearsal decides"));
        }
        for node_id in undecided {
            if rehearsed {
                self.mark(
                    "test_passed",
                    &node_id,
                    Some("startup rehearsal passed (no local spec verdict)"),
                );
            } else {
                self.mark(
                    "test_failed",
                    &node_id,
                    Some("no local spec verdict and the startup rehearsal failed"),
                );
            }
            self.test_verdict.insert(node_id, Some(rehearsed));
        }
        let _ = &self.req_dir;
        let _ = &self.tree;
        Ok(())
    }
}

pub fn has_app(output_dir: &Path) -> bool {
    output_dir.join("frontend/package.json").is_file()
        && output_dir.join("backend/package.json").is_file()
}

/// The previous run's requirement table (committed with the template).
fn previous_requirement_records(output_dir: &Path) -> BTreeMap<String, Value> {
    let path = output_dir.join(".arc/traceability/requirements.json");
    let Ok(text) = std::fs::read_to_string(path) else {
        return BTreeMap::new();
    };
    let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&text) else {
        return BTreeMap::new();
    };
    map.into_iter().filter(|(_, v)| v.is_object()).collect()
}
