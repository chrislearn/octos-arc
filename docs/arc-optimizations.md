# ARC-Bench 内核优化记录

当前交付基线：`origin/main`（第一轮运行记录保留原始 `arc-opt` 证据）。所有数字均来自本机事件流、测试输出或 GitHub Actions 产物；评测分数与单元测试结果分开记录。

## 结论摘要

| 项目 | 改前 | 改后 | 证据 |
|---|---:|---:|---|
| stdio/solo `Reply OK` 输入 Token | 17,205 | 5,714 | `turn/completed`，`/private/tmp/arc-stdio-probe-events.jsonl` |
| stdio/solo 模型可见工具数 | 62 | 12 | serve 日志 `tool_count` |
| Counter 轮数 | 3 | 3 | 两个 `.arc/octos-events.jsonl` |
| Counter 输入 Token | 64,658 | 32,423 | 两个 `.arc/octos-events.jsonl`；改后使用最终 arm64 二进制的 `cmp-arc-opt-final2` |
| Counter 输出 Token | 20,337 | 16,558 | 两个 `.arc/octos-events.jsonl` |
| Counter 费用 | 0.01474648 | 0.09336362 | 两个 `.arc/octos-events.jsonl` 的 `token_cost_update` |
| Counter 耗时 | 667 秒 | 369 秒 | 两个 `.arc/runner-events.jsonl` 的 running/completed 时间 |
| Counter Playwright | 1/1 | 1/1 | 修正 `baseURL` 后的公开测试 |
| Ticket Booking 轮数 | 0 | 4（最终二进制） | 官方初次运行无完成回合；当前 arc-opt 运行含骨架、2 节点和最终检查 |
| Ticket Booking 输入 / 输出 Token | 0 / 0 | 243,149 / 126,310 | 两次 `.arc/octos-events.jsonl`；当前 arc-opt 使用 `ticket-arc-opt-final` |
| Ticket Booking 费用 | 无记录 | 0.99110494 | `token_cost_update` |
| Ticket Booking 耗时 | >10 分钟后中断 | 1,878 秒 | `runner-events.jsonl` 起止时间 |
| Ticket Booking Playwright | 未执行 | 10/10 | `grade-local.py` 公开测试 |

## 第二轮：工作流 B（P0-0、B1、B2、B3、B5）

本轮从 `origin/main` 的 `82e3bef3` 新建 `wf-kernel`，没有改动 `legacy`，也没有启用或复用上游发布工作流。

### P0-0：stdio/solo 默认 coding 工具面

该项已由第一轮合入的 `82e3bef3` 继承并复核：`serve --stdio --solo` 默认使用 coding 工具白名单，跳过 bundled app-skills/platform-skills；无 memory/goal 时不注入对应 snapshot，panes 树不进入模型上下文。实测为 5,714 input tokens、12 个工具，达到不超过 6,000 的目标。

### B1：Linux x86_64 手动发布

改动位置：`.github/workflows/arc-linux-release.yml`。

保留唯一的 ARC 专用 `workflow_dispatch` 工作流，不启用上游继承工作流。它按输入的精确 ref 构建 `x86_64-unknown-linux-gnu` runtime 和 bundled tools，生成 `octos-bundle-x86_64-unknown-linux-gnu.tar.gz`，并在 Release 中上传 bundle SHA-256、`octos` 二进制 SHA-256、源码提交、rustc 和版本信息。最终成功运行是 [34746031597](https://github.com/octos-org/octos-arc/actions/runs/34746031597)，创建了 [v2.0.3-rc.11-arc.10](https://github.com/octos-org/octos-arc/releases/tag/v2.0.3-rc.11-arc.10)。源码提交为 `ca337e4ff409144fa8e4469b4057371f4bca1d3f`，rustc 为 `1.98.0 (88d9e12ae 2026-08-18)`；bundle SHA-256 为 `68e10832f382a3f9b6cba3f142666b9ba3ffae30b072fa9808557cdbeda9027f`，`octos` SHA-256 为 `5e7a1b8b2cd3db40f0db290932f3b2e9909b4dd5c1adea29057873fc288b7753`。下载归档后用发布的 `bundle.sha256` 与 `octos.sha256` 均核验通过，并确认归档内 `octos` 是 Linux x86-64 ELF；`arc-runtime-lock.json.runtime_release` 已回填上述真实值。

### B2：DeepSeek 费用异常

改动位置：`crates/octos-llm/src/openai.rs`、`pricing.rs`、`crates/octos-core/src/ui_protocol.rs`、`crates/octos-cli/src/api/ui_protocol_transport.rs`。

OpenAI 兼容响应现在解析 DeepSeek 顶层 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`，并将其归一化为不重复计入的 input/cache-read 口径；DeepSeek cache hit 使用 0.1 的输入价格折扣。`turn/completed` 同时暴露 `cache_hit`，便于将计费数据与请求数据逐轮核对。新增 8 个 `octos-llm` cache/pricing 测试及 CLI 完成事件回归测试；尚未再次调用付费 ARC 任务，因此本轮没有声称线上费用下降，实际评测应标记为“未评测”。

本轮本地 Counter 运行 `wf-kernel-counter`（事件流：`/Users/mac/Desktop/octos-official-demo/arc-output/wf-kernel-counter/.arc/octos-events.jsonl`）为 3 轮、37,691 input、22,556 output、658,176 cache-hit tokens，累计费用 0.10373706；`grade-local.py` 公开测试为 1/1。费用异常修复的 provider 真实线上计费仍未评测，以上是新内核本地回归的可复核数据。

### B3：每轮与每节点预算

改动位置：`crates/octos-cli/src/config.rs`、`commands/gateway/gateway_runtime.rs`、`runtime/session.rs`；节点执行逻辑沿用 `crates/octos-arc/src/runner.rs` 的 `--node-budget-seconds` 和 `--node-token-budget`。

serve/stdio 会话新增可选 `[gateway].token_budget`，映射到 agent 的整轮总 Token 上限（包含缓存 Token）；`session_timeout_secs` 提供整轮时间上限。`octos arc` 仍按依赖拓扑逐节点设置 Token/时间预算，节点耗尽时记录 `skipped_budget`，保留此前完成的节点。Agent 的超限返回是失败结果，包含 `budget_exhausted`，不会被当成成功回合继续空转。配置解析和 session bootstrap 回归测试已通过。

### B5：容器实测

改动位置：`.github/workflows/arc-linux-release.yml`、`scripts/container-stdio-smoke.py`。

GitHub Actions Ubuntu runner 的最终运行 `34746031597` 通过了真实容器 smoke：使用 `python:3.13-slim-trixie`、`--security-opt=no-new-privileges`、`--cap-drop=ALL` 和 `--pids-limit=128`，只挂载 `octos` 二进制而不挂载 `octos-sandbox` helper。发布的 `arc-b5-container-smoke` artifact 报告 `container_marker=true`、`helper_absent=true`、`fixture_requests=2`、`turn_ok=true`、`reply=OK`、shell marker 为 `b5-sandbox-exec`、`sandbox_log=true`；滚动日志明确记录 `no sandbox backend found`、`shell commands run WITHOUT isolation` 和 `in_container=true`。这同时验证了 `serve --stdio --solo` 在无后端容器中的自动降级路径，而不是把普通容器执行结果当作沙箱隔离。

## P0-0：stdio/solo 提示与工具面瘦身

改动位置：`crates/octos-cli/src/commands/serve.rs`、`runtime/profile.rs`、`api/ui_protocol_transport.rs`。

`serve --stdio --solo` 启动时默认启用 coding profile，严格保留 12 个编码工具；bundled app-skills/platform-skills 不再自动 bootstrap。空 memory 不生成策略段或 `memory-snapshot`，无 active goal 不生成 `session-goal-snapshot`。panes 树仍只属于 `session/open` 的协议返回，不会追加到模型历史。

验证：CLI 单测 `p0_0_tests`、profile 白名单单测；真实 arm64 二进制用同一 API 配置和同一句 `Reply OK` 运行，得到 5,714 输入 Token、12 工具、成功回复 `OK`。

## P0-1：容器沙箱显式降级

改动位置：`crates/octos-agent/src/sandbox/mod.rs`。

启动时检测 `/.dockerenv` 及 docker/containerd/kubepods/podman/libpod cgroup 标记；容器中无可用隔离后端时记录明确 warning 并按容器策略降级，且不会把仅检测到的 Docker CLI 当成可用的嵌套隔离。探测函数保持纯函数便于测试。新增 dockerenv、cgroup、误判排除和 nested-Docker 降级测试；`sandbox::tests` 44/44 通过。

GitHub Actions Ubuntu runner 已完成上述验证（运行 `34746031597`，对应 artifact `arc-b5-container-smoke`）：容器内 `/.dockerenv` 存在，helper 缺失，fixture 驱动的 shell 命令成功执行，且 data-dir rolling log 捕获了明确的自动降级 warning。该结果覆盖了 P0-1 要求的容器事实与降级证据；本机仍未安装 Docker，因此没有把本机 Docker 当作验证来源。

## P0-2：上下文与 Token 控制

改动位置：`crates/octos-agent/src/compaction_tiered.rs`。

默认每条工具结果最多 8 KiB；完整 compaction pass 对超限结果保留头尾并加入截断标记，旧结果的 oversized-only pass 则替换为结构化一行摘要。过期、重复或不在工作集的结果仍折叠为结构化一行摘要，当前工作集文件读取保持可重读性。新增头尾保留、工作集保护和历史折叠测试。

Counter 事件流的输入 Token 从 64,658 降到 32,423；这是同一平台、最终 arm64 二进制一次成功运行的真实结果，不把它解释成仅由单个改动独立贡献的因果实验。该二进制的第一次 Counter 重跑因生成应用把 `data-testid` 与 JavaScript 的 `id` 查找混用而被公开测试判为 0/1；未修改生成应用，第二次运行 `cmp-arc-opt-final2` 由公开 grader 判定为 1/1。

Counter 的 arc-opt 费用高于官方这次记录（0.09336362 对 0.01474648）；费用字段按事件流原样保留，不能据此推断成本优化。Ticket Booking 的前两次 arc-opt 尝试在骨架首轮中断，当前最终二进制的 `ticket-arc-opt-final` 运行完成，公开测试为 10/10；官方 `grade-local.py` 原始脚本的 Playwright 配置缺少 `baseURL`，本地对照时仅临时补入 `baseURL: process.env.E2E_BASE_URL` 后执行公开测试，随后恢复了脚本。

## P0-3：推理模型空回合恢复

改动位置：`crates/octos-llm/src/context.rs`、`openai.rs`、`crates/octos-agent/src/agent/{detection,llm_call}.rs`。

DeepSeek V4 默认输出上限提高到 provider 级安全值；当 `finish_reason=length` 且无正文、无工具调用时，只重试一次，按配置降低 reasoning effort 或提高 max tokens；再次失败返回明确错误，不计为成功。新增判定与恢复策略测试。

## P1-4：流式失败自动回退

改动位置：`crates/octos-agent/src/agent/{detection,llm_call,mod}.rs`。

识别 SSE/streaming 不支持错误后，同一 session 记录 provider/model，后续请求直接走非流式路径；当前错误回合也自动回退一次。新增错误识别测试。Counter 运行期间平台请求成功，未再依赖适配层的 `OCTOS_DISABLE_STREAMING=1`。
即使当前 LLM 调用处于 FailFast 策略，明确的 SSE 不支持错误仍保留这一次非流式回退；其他传输错误继续按 FailFast 直接返回。该边界由单测覆盖。
provider/model 的 session key 使用不可歧义分隔符，避免 provider 或 model 名称含冒号时错误共享回退状态。

## P1-5：环境事实前置注入

改动位置：`crates/octos-arc/src/runner.rs`。

`octos arc` 每次 session 仅探测一次 node/npm/python、cwd、npm registry 连通性、容器标记和 sandbox 状态，并将短行事实加入稳定基础提示；生产路径同时对 cwd 和整段事实做字符上限保护，保持在 200 Token 量级以内。
单测用隔离的 node/npm/python3 fixture 验证版本、registry 连通性、容器标记和 200 Token 上限。

## P1-6：Playwright 验收 hook

改动位置：`crates/octos-arc/src/runner.rs`。

轮次结束的本地验证会发现显式目录或工作区内的 `*.spec.ts`，从项目及 spec 目录祖先查找 Playwright；存在时运行 `playwright test --reporter=line`，stdout/stderr 的失败断言以 `[hook]` 错误回传。没有 spec 或 Playwright 时记录 skipped 并继续。目录和基址可由 CLI 参数或 `OCTOS_ARC_SPEC_DIR`、`OCTOS_ARC_BASE_URL` 指定。单测用临时 spec 和 fake runner 验证了实际执行、基址注入及 passed/failed 证据记录。

## P2-7：按节点预算

改动位置：`crates/octos-arc/src/runner.rs`。

新增 `--node-budget-seconds`（默认 300）和 `--node-token-budget`（默认 20,000）。每次运行按依赖拓扑逐节点启动 coding turn：进程 deadline 绑定到当前节点，配置中的输出上限绑定到节点 Token 预算；超时或回合失败时记录 `skipped_budget`，继续后续节点并保留已完成部分。预算计划写入 `node-budgets.json`、报告并前置到 coding prompt。依赖排序和预算边界有单测。

## 构建与测试

构建命令：

```text
cargo build --locked -p octos-cli --no-default-features --features api
```

产物为 macOS arm64 Mach-O。`cargo fmt --all -- --check`、完整工作区 `cargo clippy --locked --all-targets -- -D warnings` 和完整工作区 `cargo test --locked` 均通过。当前相关 crate 的测试结果为：`octos-agent` 2,900 passed / 3 ignored，`octos-arc` 23 passed / 1 ignored，`octos-llm` 687 passed / 3 ignored，`octos-pipeline` 355 passed / 1 ignored，`octos-cli` 单元测试 3,680 passed / 10 ignored；工作区测试命令最终退出码为 0。此前本机无 Docker 时出现的 3 个环境相关失败已改为按 Docker 可用性断言，当前不再失败。

最终产物：`octos 2.0.3-rc.11 (a10521e4 2026-09-12)`；SHA-256 为 `4f7ec9437ec86aac0fad663fc5df94e395b537dad50138b5828732cc00e8cb09`，对应 `aarch64-apple-darwin` 和 Homebrew `rustc 1.98.0`。

`runtime_release` 已填入并核验 v2.0.3-rc.11-arc.10 的真实 Linux 产物；`build` 继续记录真实 macOS arm64 产物元数据。尚未创建新的 ARC 云端评测运行，因此线上 Counter 费用/分数仍应标记为“未评测”。

## 独立提交索引

每条优化都有至少一个独立的实现或回归提交，提交信息包含现象和改法：

| 优化 | 提交 |
|---|---|
| P0-0 | `840007d2` |
| P0-1 | `a422b473` |
| P0-2 | `f8cb7efb` |
| P0-3 | `7ccdab08` |
| P1-4 | `3a662235` |
| P1-5 | `9011052c` |
| P1-6 | `37d38bae` |
| P2-7 | `dc0f6be0` |

第二轮提交：B1 `e3bc8242` + `d12c15ad`；B2 `5e6ca223`；B3 `d9fba010`；B5 workflow/driver 修正经 PR #14、#15、#16、#17、#18、#21、#22、#23、#24 合入；最终 B5/Release 运行 `34746031597`，Release 提交为 `ca337e4f`。

## 第三阶段：工作流 B · 真实 agent 成本与缓存

本节对应目标书 2026-09-13 新增的第 7 节。实现已由 PR #31 squash 合入 main（`1de981aebe1915b8aeb9a6645b0fe91a63fb4d0a`）。本阶段没有修改 `legacy`，也没有把本地生成应用当作评测结果。

### 改动

- `crates/octos-cli/src/runtime/profile.rs`：stdio/solo 默认复用 coding 的 12 工具白名单，跳过 bundled app/platform skills；默认系统前缀使用紧凑 worker 指令，显式 system prompt 仍优先。
- `crates/octos-cli/src/runtime/session.rs`：DeepSeek ARC 会话默认 `reasoning_effort=low`，单次 completion 上限为 4,096；显式 profile/model/gateway 配置仍覆盖默认值。
- `crates/octos-llm/src/openai.rs`：ARC-Bench 的 OpenAI 兼容端点保留 DeepSeek V4 的 `reasoning_effort`/`thinking` 字段；其他未知自定义端点继续要求显式 model hints。
- `crates/octos-cli/src/api/context_manager.rs`：模型可见的单条工具输出默认上限为 8 KiB，保留头尾。AppUI 旧观测折叠的默认 rollout 已为 On，继续采用批量语义折叠。

### 真实本机对照

| 任务/请求 | 改前事件流 | 改后事件流 | input tokens | output tokens | cache_hit | 公开测试 |
|---|---|---|---:|---:|---:|---:|
| Counter（旧 8 KiB/8,192 上限） | `arc/arc-output/kernel-v2-baseline-counter/.arc/octos-events.jsonl` | `arc/arc-output/kernel-v2-final2-counter/.arc/octos-events.jsonl` | 20,627 → 21,614 | 8,300 → 6,950 | 235,520 → 186,624 | runner 通过；公开 grader 未重复 |
| Counter 首轮（同一流程） | 同上 | 同上首个 `turn/completed` | 20,627 → 15,674 | 8,300 → 4,262（−48.7%） | 235,520 → 110,336 | 工作流完成，测试结果以完整 runner 产物为准 |
| `Reply exactly OK.` | 官方证据 17,205、62 工具 | 新二进制直接 stdio/solo | 17,205 → 5,420 | — → 2 | — → 0（单轮） | OK |
| 同一 serve 会话第二次 `Reply exactly OK.` | — | 临时协议驱动器事件 | — | 2 | 5,120/5,420（约 94.5%） | OK |

同一 serve 会话的第二次请求采用 append-only 前缀，`turn/completed.cache_hit` 为 5,120；整段 prompt hash 随新增 transcript 改变，因此不能把整段 hash 当作“完全相同”，缓存命中字段才是本项证据。短请求的新二进制实测输入已低于 6,000；Counter 的全流程总量受模型是否额外发起需求回合影响，不能把首轮降幅误报为整题降幅。

Ticket Booking 的 8,192 上限版本曾运行到第二需求节点并被本地工具长尾中止，事件流保留在 `arc/arc-output/kernel-v2-lean-ticket/.arc/octos-events.jsonl`，不作为完成对照。4,096 上限版本已完成 6 个回合：`tokens_in=183,600`、`tokens_out=51,140`、`cache_hit=2,694,144`、费用 `0.13794452`，耗时 911 秒；对照基线为 7 个回合、`321,933/162,988`、`cache_hit=4,435,712`、费用 `0.25352586`、耗时 2,319 秒。官方公开 Playwright spec 重新执行为 10/10（使用 `grade-local.py` 的原始 spec，grader 进程清理采用等价的直接 runner 以避开 macOS 进程组权限错误）。

以上单元测试和本机 agent 运行均不等于 ARC-Bench 云端评测，云端成绩仍为“未评测”。

### 验证

已通过：

- `cargo fmt --all -- --check`；
- `openai::tests::deepseek_v4_thinking_style_downgraded_off_official_endpoint`；
- `runtime::profile::tests::stdio_lean_prompt_uses_compact_worker_instructions_but_honors_override`；
- `context_manager::tests::default_tool_output_policy_keeps_eight_kibibytes_for_model`；
- `cargo build --locked --release -p octos-cli --no-default-features --features api`。

本地 macOS arm64 产物为 `octos 2.0.3-rc.11 (08e10c05 2026-09-13)`，SHA-256：`a856afaf88c1967ad95ec2268259665085aa9a9ef6adb27aef0c29a6558488b1`；rustc 为 `1.98.0 (88d9e12ae 2026-08-18)`。对应 main 的 Linux Release 已由 workflow run `34752867215` 发布为 [v2.0.3-rc.11-arc.11](https://github.com/octos-org/octos-arc/releases/tag/v2.0.3-rc.11-arc.11)，源码提交为 `1de981aebe1915b8aeb9a6645b0fe91a63fb4d0a`，归档 SHA-256 为 `ec7fb4c1c9a4885d4a00d9e4bcd3e0c382779bf449ee0aa20c0bfc4062e59ab8`，解包 Linux `octos` SHA-256 为 `05f41672f0b5fef8c3936aa56b72f1add8525961a928668abb34849d4595124e`；下载地址已同步到 `arc-runtime-lock.json` 和 `arc/main.py`。

Release 后应由 C 使用新适配包重跑 Smoke Counter 与 Smoke Dice，并在日志确认 `2.0.3-rc.11`；本环境未提供跨会话 `send_to_session` 接口，因此对 C（`a63a5b17-2553-4c9d-9647-a5ae3b7d852c`）和 A（`04b003e2-ad06-4aa8-b56c-13c29a0d80c2`）的通知尚未实际发送，不能宣称云端已重跑。云端榜单成绩仍为“未评测”。

## 第四阶段：harness 收编（工作流 D，分支 `wf-kernel-harness`）

目标书：`GOAL-arc-rust-harness.md`（2026-09-14）。现状是策略层在 `arc/*.py`（4,386 行、约 60 个环境变量），Rust 的 `octos arc create/evolve` 与之重复且不在比赛路径上。本阶段把策略收进内核的 `octos arc run`，Python 只剩平台胶水；所有新路径放在 `OCTOS_ARC_ENGINE=rust` 开关后面，默认仍走 Python，直到第 4 节的对等验证全部通过。

### 现有 Python 策略 → Rust 模块 逐条对照表（草稿，随里程碑更新）

「来源」列是 `arc/` 里的唯一权威实现；「为什么存在」列引用 `arc/CHANGELOG.md` 的归因（云端运行编号）；「里程碑」列标注该条在哪个 PR 收编。M1 只做 codegen 闭环，tool 模式（stdio 驱动）在 M2。

#### tree.rs（← requirement_order.py、main.py 的树处理）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| T1 | 读 `requirements.yaml`/`.yml`，剥 `root`/`requirement` 包装，缺 `id` 即报错 | `main.load_requirement_tree` | 平台格式 | `tree::load` | M1 |
| T2 | ATOMIC 平铺：`type=ATOMIC` 或无子节点且非 FOLDER 的节点按文档序 | `requirement_order.flatten_atomic` | 未标类型的叶子也要实现 | `tree::flatten_atomic` | M1 |
| T3 | 依赖序遍历：依赖先出，同层保持文档序；依赖指向 FOLDER 时展开为其 ATOMIC 后代；未知 id、自依赖忽略；成环按文档序打破，保证终止且每节点恰一次 | `requirement_order.topo_order` | A2（ARC 论文消融：DFS 序 −16~−52 pp） | `tree::topo_order` | M1 |
| T4 | 传递祖先（按拓扑序返回）供提示词附祖先设计摘要 | `requirement_order.ancestors_of` | A2 | `tree::ancestors_of` | M1（提示词用在 M2） |
| T5 | 节点指纹 sha256(id/name/description/scenarios/dependencies)[:16] | `requirement_order.node_fingerprint` | A6 Evolution 差异 | `tree::node_fingerprint` | M1（M3 使用） |
| T6 | FOLDER → ATOMIC 后代映射；收尾时按子节点判定给 FOLDER 发 design/implement/test 事件 | `main.folder_descendants`、`Flow.mark_folders` | C 回流 1：平台把 FOLDER 也计入需求数（keep「45 requirements」） | `tree::folder_descendants` + `events` 里的 `folder_verdict` 事件，Python 翻译成 mark_* | M1 |
| T7 | 节点描述文本（ID/Name/Description/Scenarios/Depends on） | `main.describe_node` | 提示词 | `tree::describe_node` | M1 |
| T8 | 上一轮 `.arc/traceability/requirements.json` 与指纹比对得未变节点 | `main.previous_requirement_records`、`unchanged_node_ids` | A6 | `tree::unchanged_from_previous` | M3 |

#### plan.rs（← main.py 的模式判定）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| P1 | 节点数 ≤ `OCTOS_ARC_CODEGEN_MAX_NODES`(2) 且未被 `codegen_blocked` → 单请求 codegen；否则 tool 模式 | `Flow.codegen_mode` | 第五版/round 23：Counter 1 请求 872 token，TB 2 请求 | `plan::Mode::Codegen/Tools`，`policy.mode.codegen_max_nodes` | M1 |
| P2 | `OCTOS_VERIFY_MODE` auto/minimal/full；≤ `OCTOS_SMALL_TASK_NODES`(2) 用最小自验（无 shell、≤8 次写、≤2 次读） | `Flow.minimal_mode`、`verify_text` | 第二阶段 2、v11 | `plan::verify_mode` | M2 |
| P3 | 骨架轮只在 ≥ `OCTOS_SKELETON_MIN_NODES`(3) 或 `OCTOS_SKELETON_ALWAYS=1` | `Flow.run` | 第二阶段 2（小题只跑一轮） | `plan::wants_skeleton` | M2 |
| P4 | 设计轮：`OCTOS_DESIGN_TURN`、≥ `OCTOS_DESIGN_MIN_NODES`(3)、`OCTOS_DESIGN_MODE` inline/separate | `Flow.node_cycle` | A3、R7/R8（inline 省 23% 费用） | `plan::design_mode` | M2 |
| P5 | Evolution 判定 = 输出目录已有 frontend/package.json 与 backend/package.json | `Flow.has_app`、`run` | A6；C：平台不设 ARCBENCH_TEMPLATE_DIR | `plan::is_evolution` | M1（探测在 M3） |
| P6 | 推理档位 auto：待实现节点 ≤1 → none，否则 low；`OCTOS_ARC_IMPLEMENT_REASONING` 只作用于小题的首个实现轮 | `Flow.start_llm_proxy`、`turn` | 第二阶段 1、v17（输出 token 降 3×）、round 23（TB none 首轮 2/6） | `plan::reasoning_for(turn_kind)` → `llm::ReasoningMode` | M1 |
| P7 | 按需求关键词裁剪契约块：session（login/password/…）、data（seed/option/…）；性能契约只在有会话的题 | `Flow.classify_tree`、`ui_contract`、`perf_text` | 第二阶段 3（Counter 提示词 3.5k→2.4k） | `plan::ContractFlags`，规则写进策略文件 `[prompts.keywords]` | M2 |
| P8 | 总预算未显式设置时 = max(3600, 1500 × 节点数) | `Flow.run` | C 回流 3、keep-local-3（480 s/节点截断 16/17 轮） | `budget::global_budget` | M1（预算细节 M2） |

#### codegen.rs（← codegen.py、main.py 的 codegen 路径）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| C1 | `<<<FILE path>>>…<<<END FILE>>>` 解析：路径归一、禁绝对/`..`、去掉包住正文的 ``` 围栏、同路径后者胜 | `codegen.parse_file_blocks` | 第五版 | `codegen::parse_file_blocks` | M1 |
| C2 | HTML 无 charset 时注入 `<meta charset="utf-8">` | `codegen.ensure_charset` | round 28（s5/s10：中文定位器全失败） | `codegen::ensure_charset` | M1 |
| C3 | 整块被 JSON 转义（`\n` 字面）时还原 | `codegen.unescape_flattened` | round 28（s12） | `codegen::unescape_flattened` | M1 |
| C4 | 部分转义的 JS 只在 `node --check` 由失败变通过时改写 | `codegen.repair_flattened_js` | round 28 | `codegen::repair_flattened_js` | M1 |
| C5 | 服务端实现 `<!--NAV-->` 时删除页面里重复的静态 login/register/logout 链接 | `codegen.dedupe_nav_links` | round 28（s2/s3/s15 strict mode） | `codegen::dedupe_nav_links` | M1 |
| C6 | 落盘（建目录、按后缀套用 C2–C4） | `codegen.write_files` | — | `codegen::write_files` | M1 |
| C7 | harness 写死两个 package.json：build 复制 src→dist 并生成无扩展名页面副本；backend `"type":"commonjs"` | `main.CODEGEN_MANIFESTS`、`write_codegen_manifests` | round 26（3e425ce2ebf6 ESM 崩溃）、round 28（s8 `/register` 404） | `codegen::write_manifests` | M1 |
| C8 | 一行 system prompt 替换内核 worker 提示 | `main.CODEGEN_SYSTEM` + `llm_proxy.replace_system_prompt` | round 22 | 直接构造 messages（无工具） | M1 |
| C9 | 紧凑用户提示：需求描述 + spec 全文（含 support helper）+ 固定文件布局 + 规则 + 尺寸规则（单节点 ≤20 行；多节点 NAV/cookie/校验/可见盒/无 HTML5 校验机制） | `main.CODEGEN_PROMPT`、`CODEGEN_SIZE_SMALL/FULL`、`spec_bodies` | round 22/23/27/28 | `arc/prompts/codegen-*.md`，`codegen::implement_prompt` | M1 |
| C10 | spec 默认端口 ≠ PORT 时附双端口契约句（`ARC_EXTRA_PORTS`） | `Flow.codegen_ports_clause`、`main.spec_base_ports` | round 24（3f0124e82113/784402a777c2 0/10） | `acceptance::spec_base_ports` + `codegen::ports_clause` | M1 |
| C11 | Evolution codegen：提示改为「保留现有应用、完整输出改动文件」并内嵌现有 html/js（≤30k 字符） | `Flow.node_cycle` | round 22/23 | `codegen::evolution_prompt` | M1 |
| C12 | codegen 修复：REPAIR_PROMPT + 失败摘要 + 内嵌源码 + 「每个改动文件完整输出」 | `Flow.acceptance_loop` | round 23、v16 | `codegen::repair_prompt` | M1 |
| C13 | 0/N 时一次整体重写（原提示 + 失败 + 内嵌源码） | `Flow.node_cycle.rebuild_prompt`、`OCTOS_ARC_REWRITE_ON_ZERO` | v14/round 23 | `codegen::rewrite_prompt` | M1 |
| C14 | 连续两轮失败摘要（数字归一化后）相同 → 该节点切 tool 模式并注入「换方法」纠正；≥ `OCTOS_ARC_CODEGEN_REPAIRS`(2) 轮仍失败 → tool 模式；`codegen_blocked` 每节点重置 | `Flow.acceptance_loop`、`node_cycle` | 91aaecaf31af、5747e6bcf530、round 23/28 | `loop::CodegenGate` | M1（切换本身 M1；tool 模式落地 M2） |
| C15 | codegen 轮请求上限 3 | `OCTOS_ARC_CODEGEN_REQUESTS` | v13 | `policy.requests.codegen`；单请求无工具，只用于瞬时错误重试上限 | M1 |

#### acceptance.rs（← acceptance.py）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| A1 | spec 文件名前缀 `REQ-x.y` 提取 | `acceptance.spec_node_id` | A1 | `acceptance::spec_node_id` | M1 |
| A2 | spec→节点映射：精确 id → 数量相同按数字序配对 → 父前缀；其余进回归集；别名表 | `acceptance.map_specs_to_nodes` | A1（TB 的 REQ-1.1/1.2 对 REQ-1/2） | `acceptance::map_specs_to_nodes` | M1 |
| A3 | 节点状态镜像到 spec 侧别名 id | `Flow.mark`、`OCTOS_ARC_ALIAS_SPEC_IDS` | A1 | 事件带 `aliases`，Python 翻译时镜像 | M1 |
| A4 | 测试目录定位：ARCBENCH_TESTS_DIR → /workspace/tests → 随包 public-tests（按根名） | `main.locate_acceptance_tests` | A3 | 留在 Python 胶水，经 runner-spec.json 传入 | M1 |
| A5 | 扫描 spec 里 `http://127.0.0.1:PORT` 得默认端口 | `main.spec_base_ports` | round 24 | `acceptance::spec_base_ports` | M1 |
| A6 | Playwright JSON 报告折叠：每 spec 一条结果；错误位置在 helper 时按 spec 文件归属 | `acceptance.summarize_report` | keep-local-4（failing nodes []） | `acceptance::summarize_report` | M1 |
| A7 | 四字段失败摘要（Feature / Failed at / Observation ≤900 字符 / Steps ≤8，超时标注，Call log 兜底） | `acceptance.failure_summaries` | A3、第六版（缺 Expected/Received） | `acceptance::failure_summaries` | M1 |
| A8 | 失败按 spec 文件 basename 归属节点 | `acceptance.nodes_for_failures` | keep-local-4 | `acceptance::nodes_for_failures` | M1（全套用在 M2） |
| A9 | 慢测试阈值 `OCTOS_ARC_SLOW_MS`(3000) → 修复提示附性能规则 | `RunSummary.slow`、`Flow.acceptance_loop` | A4 | `acceptance::RunSummary::slow` | M1 |
| A10 | 先找预装 Playwright：`OCTOS_ARC_PLAYWRIGHT_ROOT`、bundle/local-grader、tests 目录及祖先、/workspace、/app、/runner、/opt/playwright、/ms-playwright、$HOME、`npm root -g` 上级、/usr/local/lib…，再 `find / -maxdepth 6` 25 s | `playwright_candidates`、`find_playwright_root`、`find_playwright_by_search` | 紧急修正（da9a64b32c09：自装污染了平台的 npx 解析） | `acceptance::find_playwright` | M1 |
| A11 | 自装完全隔离：版本钉死（tests 的 lock/package.json，否则 1.63.0；绝不 latest）、私有 npm cache 与 PLAYWRIGHT_BROWSERS_PATH、npmmirror、540 s 上限、结束删除 | `playwright_version_hint`、`isolated_install_env`、`ensure_playwright`、`cleanup_playwright` | 紧急修正、d116ad5e3aa0 | `acceptance::private_install` | M1 |
| A12 | cgroup 内存上限 → worker 数 = min(请求数, 上限/700 MiB)，至少 1 | `container_memory_limit`、`workers_for_memory` | 29c840566f36（512 MiB、4 worker OOM） | `acceptance::workers_for_memory` | M1（M4 复核） |
| A13 | 构建：有依赖且无 node_modules 才 `npm install`；先 mkdir dist；`npm run build` 600 s | `AppServer.build` | c17bc1b44d26（dist 不存在） | `acceptance::AppServer::build` | M1 |
| A14 | 启动：`PORT`=smoke 端口，非 grader-like 时 `ARC_EXTRA_PORTS=0`；45 s 内等端口；启动即探测 | `AppServer.start` | R5 双端口 listen 两次 | `acceptance::AppServer::start` | M1 |
| A15 | 健壮性探测 `/favicon.ico`、未知路径、未知 API 必须有响应且进程活着 | `robustness_probe` | f9f0026819f1（ENOENT 杀进程，8 条 ECONNREFUSED） | `acceptance::robustness_probe` | M1 |
| A16 | grader-like 启动时 spec 默认端口也必须被绑定 | `AppServer.extra_ports_bound` | 3f0124e82113 | `acceptance::extra_ports_bound` | M1 |
| A17 | 停止：killpg SIGKILL、释放 smoke 端口、只杀 cwd 在项目内的额外端口监听者 | `AppServer.stop`、`free_port`、`free_owned_ports` | 运行主机共享 | `acceptance::AppServer::stop` | M1 |
| A18 | 把 tests 复制到 Playwright 根下的私有工作目录，写 config（timeout 10 s、retries 0、fullyParallel 开关、workers、json reporter、expect/action 4 s、navigation 6 s） | `AcceptanceRunner._prepare` | A3（10 s 与平台一致；子超时让失败带定位器） | `acceptance::Runner::prepare` | M1 |
| A19 | 运行：E2E_BASE_URL、CI=1、NODE_PATH、900 s 墙钟；被杀（rc<0/"Killed"）不是判定；收集到 0 条测试是错误不是 0/0 | `AcceptanceRunner.run` | 29c840566f36（OOM）、a6ccc437539f（0/0 盲修） | `acceptance::Runner::run` | M1 |
| A20 | 跑测试前 `git add -A`，跑完 `git checkout -- . && git clean -fdq -e node_modules -e dist -- frontend backend` 还原测试写坏的持久化数据 | `snapshot_worktree`、`restore_worktree` | r5-counter（db.json 被改成 -1 后提交） | `acceptance::with_worktree_snapshot` | M1 |
| A21 | 受保护目录（tests、requirements）快照 + sha256，每轮结束比对还原并把恢复清单作为纠正句 | `tree_digest`、`restore_tree`、`Flow.snapshot_protected/restore_protected` | 第三轮（a6ccc437539f 模型改了 /workspace/tests） | `guard::ProtectedTrees` | M2（codegen 轮不写盘，M1 不需要） |

#### loop.rs（← main.py 主循环）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| L1 | 节点预算 = min(`OCTOS_NODE_TIME_BUDGET`, max(240, 剩余/剩余节点数))；实现轮 ≤ min(`OCTOS_NODE_TIMEOUT`, 0.6×节点预算) | `Flow.node_cycle` | A7、keep-local-3 | `budget::NodeBudget` | M1 |
| L2 | 实现 → 验收循环：round 0 直接验收；通过即 commit 返回 True；通过数上升 commit 并记最优 sha；连续两次下降回滚到最优并注入纠正；两次无提升即停；`attempt == K` 停；剩余 < `OCTOS_MIN_REPAIR_SECONDS`(300) 不开修复轮；结束时不在最优点则回到最优点 | `Flow.acceptance_loop` | A3、f9f0026819f1（4/6↔3/6 振荡）、keep-local-3 | `loop::acceptance_loop` | M1 |
| L3 | 基础设施错误（构建/启动失败）作为「app startup」失败摘要进修复轮；测试进程被杀则无判定 | `Flow.acceptance_loop` | 29c840566f36 | 同上 | M1 |
| L4 | 修复前把 frontend/src 与 backend 源码快照到 `.arc/codegen/<node>-r<n>/` | `Flow.snapshot_sources` | round 27（27de75de0cd0 首轮代码不可追溯） | `loop::snapshot_sources` | M1 |
| L5 | 实现轮结束但缺 package.json 不判失败，进验收循环由构建错误驱动 | `Flow.node_cycle` | v6-counter | `loop::node_cycle` | M1 |
| L6 | 实现轮超时：保留盘上文件交验收；不当瞬时错误重放 | `Flow.node_cycle`、`OctosDriver._transient` | d5f9dccb（r1-tb 白烧 15 分钟） | `llm::is_transient` 排除自身超时 | M1 |
| L7 | 输出被 max_tokens 截断且未落盘 → 新会话按文件重写一次 | `Flow.node_cycle` | 76fb32a69d81 | `loop::node_cycle`（codegen：截断即视为失败进修复） | M1（tool 版 M2） |
| L8 | 单 spec 题在节点已判定时跳过全套；否则全套并行（grader-like、按内存定 worker）、失败按节点分组、同一失败集合即停、≤ `OCTOS_FINAL_REPAIR_ROUNDS`(2)、启动失败 = 全部节点失败、被杀保留逐节点判定 | `Flow.final_acceptance` | R7、第三轮 4、29c840566f36 | `loop::final_acceptance` | M1（单/双 spec 路径）+ M2（修复轮 tool 模式） |
| L9 | 启动演练 3 次（grader-like build+start），失败则 REHEARSAL_REPAIR_PROMPT | `Flow.rehearsal` | R0 | `loop::rehearsal` | M1（演练）/ M2（修复轮） |
| L10 | 骨架轮：≤4 次尝试、无 frontend/backend 时 nudge ≤2；只读 helper 与至多两个 spec | `Flow.skeleton`、`tests_prompt_for(skeleton=True)` | C 回流 2（keep 骨架轮 70 分钟） | `loop::skeleton` | M2 |
| L11 | 无本地判定的节点走终检轮 + 演练判定 | `Flow.run` | A1 | `loop::final_check` | M2 |
| L12 | 每节点提交（implement / accepted / repair n / keep best）、终态提交 | `Flow.commit`、`restore_app` | A3 | `git.rs` | M1 |
| L13 | smoke 端口 = `OCTOS_SMOKE_PORT`(3100)≠web_port；轮内 `PORT`=smoke；watchdog 每 5 s 杀掉自己进程对评测端口的绑定 | `Flow.__init__`、`_port_watchdog` | R0（runner 见到评测端口被占即终止） | `reap::PortWatchdog` | M4（codegen 路径不起服务，M1 不需要） |
| L14 | 收尾：残留进程清理、把嵌套一层的 app 提到根、释放评测端口、写 preview-ready.json | `_reap_stray_processes`、`_postflight_structure_check`、`_free_web_port`、`write_preview_ready` | 0764e8d77c54、R0 | `reap.rs`（M4）；preview-ready 留在 Python 胶水 | M1/M4 |
| L15 | 异常路径：未判定节点补 test_failed、FOLDER 补齐、run_failed，退出码 0 | `Flow.run` except | A1-4 | `run::execute` 的错误路径 + 事件 | M1 |

#### budget.rs（← guard.py 的预算部分 + P2-7）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| B1 | 总时间预算、剩余时间、耗尽后节点直接 implementation_failed | `Flow.remaining/time_up`、`run` | A7 | `budget::Global` | M1 |
| B2 | 每轮请求硬上限（实现 20 / 修复 10 / codegen 3），超限剥工具并要求收尾 | `llm_proxy.enforce_turn_budget`、`Flow.turn` | v13（20 次调用的修复轮） | tool 模式：内核会话 `max_iterations`；codegen：重试上限 | M1（codegen）/ M2 |
| B3 | 全局 Token 与回合上限、超限降级为「每节点一次实现 + 一次全套」 | 目标书新增（P2-7 的 `--node-token-budget`） | keep ¥57 | `budget::Guardrails` | M4 |

#### llm.rs（← llm_proxy.py；做进 octos-llm 的 provider 配置）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| M1 | DeepSeek 推理注入：none → `thinking:{type:disabled}`；low/medium/high → `reasoning_effort` + `thinking:enabled`；非 deepseek 模型不动 | `llm_proxy.inject_reasoning` | 第二阶段 1（455→279→132 completion tokens） | `ChatConfig.reasoning_effort` + `ReasoningStyle::EffortAndThinkingToggle`（`api.arc-bench.com` 已被 `openai.rs` 识别） | M1 |
| M2 | `max_tokens` 下限 32768（内核 arc.11 stdio 会话默认 4096） | `llm_proxy.ensure_max_tokens` | 76fb32a69d81（两个实现轮截断） | `ChatConfig.max_tokens = policy.reasoning.max_tokens_min` | M1（tool 模式经 profile `gateway.max_output_tokens` M2） |
| M3 | 去流式：上游一次 JSON 响应 | `llm_proxy.destream_request/to_sse` | cc066e8e11f6（平台把 SSE 逐 chunk usage 累加 12×） | codegen 直接 `chat()` 非流式；tool 模式会话 `OCTOS_DISABLE_STREAMING=1` | M1 |
| M4 | 每请求用量记账：prompt/completion/reasoning/total、cache hit（DeepSeek 与 OpenAI 两种字段）、耗时、请求/响应字节、消息形状 → `.arc/llm-usage.jsonl` | `llm_proxy.usage_record`、`request_shape` | 更正·前缀缓存、cc066e8e11f6 | `llm::UsageLedger`（同字段名，`metrics.py` 直接可读） | M1 |
| M5 | 裁掉与 ARC 无关的 system prompt 段与 6 个工具 schema | `llm_proxy.trim_request`、`DROP_SECTIONS/DROP_TOOLS` | v4；v15 证明与首轮成败无关 | tool 模式用内核 stdio/solo 精简 profile（B 第三阶段），不再代理裁剪 | M2 |
| M6 | 最小自验轮剥掉 shell 工具 | `extra_drop_tools`、`OCTOS_ARC_DROP_SHELL` | v11（无 shell 修复轮仍 41 次调用） | 会话 profile 的工具 deny 列表 | M2 |
| M7 | 瞬时错误重试 3 次（30 s、60 s），自身超时不重放 | `OctosDriver._run_with_retries/_transient` | d5f9dccb | `llm::call_with_retries` | M1 |
| M8 | 启动前原始 chat 探测，等代理恢复最多 10 分钟 | `main.probe_endpoint` | 平台代理抖动 | `llm::probe` | M1 |
| M9 | 请求体转储（调试） | `OCTOS_ARC_PROXY_DUMP` | 前缀分析 | `policy.debug.dump_requests` | M1 |

#### driver.rs（← octos_stdio.py、main.py 的 OctosDriver；tool 模式）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| D1 | 起 `octos serve --stdio --solo --data-dir … --danger-full-access`，NDJSON JSON-RPC：`profile/local/create`（唯一 id）→ 把 hooks 写进 profile 文件 → `profile/llm/upsert` → `session/open` → `turn/start` → 收 `message/delta`、自动批准 `approval/requested`、`turn/completed`/`turn/error` | `OctosStdioSession` | A5、第三轮 1（hooks 只从 profile 自身 config 生效） | `driver::StdioSession`（同一可执行文件 `current_exe()`） | M2 |
| D2 | 会话粒度 `OCTOS_SESSION_SCOPE` turn/node/run（默认 turn） | `OctosDriver` | v8-tb（node 粒度 49 请求 1.1M prompt） | `policy.session.scope` | M2 |
| D3 | 30 s 心跳日志（runner 杀静默进程）；`octos chat` 回退 | `_run_with_heartbeat`、`run_octos` | 平台 | 事件流心跳 | M2 |
| D4 | 全部通知写 `.arc/octos-events.jsonl`；`[arc-mod]` 标记转发 | `_log_event` | metrics.py 口径 | `events.rs` 镜像 turn/completed | M1（codegen 也写）/ M2 |
| D5 | 内核环境：provider 判定与 key 环境变量、config.json（sandbox allow_network、memory refresh 关、`gateway.max_output_tokens` 65536、deepseek `reasoning_effort` low、hooks）、`OCTOS_DISABLE_STREAMING=1`、`OCTOS_DANGER_FULL_ACCESS=1`、npmmirror | `main.build_octos_env`、`write_profile_defaults` | 平台代理拒绝 SSE、容器即沙箱、npmjs 慢 | Python 胶水只留环境变量；内核侧 profile 由 driver.rs 写 | M2 |
| D6 | 二进制定位与下载（gh-proxy 镜像、12 次、curl --http1.1） | `find_octos`、`_download_octos` | 平台到 GitHub 的 HTTP/2 流被杀 | 留在 Python 胶水，M5 加 SHA-256 校验 | M5 |

#### guard.rs（← guard.py、main.py 的保护）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| G1 | 轮内监视：写了文件、结束语宣称完成却没跑 build/start/curl；同一错误连续 ≥3；写保护路径（允许 .arc/design/）；纠正句注入下一轮 | `guard.TurnMonitor`、`OCTOS_GUARD` | A7 | `guard::TurnMonitor`（订阅 driver 事件） | M2 |
| G2 | `before_tool_call` hook 拒绝写 tests/requirements（写进 profile config） | `main.protected_hooks`、`hooks/deny_protected.py` | 第三轮 1 | 内核内置 hook（不再需要 Python 脚本） | M2 |
| G3 | harness 纠正句：同一失败两次、两次下降已回滚、改了官方文件已还原、缺 package.json、实现轮超时、截断重写、并行不干扰、演进回归 | 散布在 `Flow` | 各云端归因 | `arc/prompts/corrections.md`（按键引用） | M1（codegen 用到的）/ M2 |

#### events.rs（← metrics.py、arcbench_agent_runtime 的调用点）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| E1 | 节点事件 design/implement/test 的 started/done/failed（含别名镜像）、FOLDER 推导、run started/completed/failed | `Flow.mark`、`mark_folders`、`events.mark_run_*` | A1 | 内核写 `.arc/octos-arc-events.jsonl` 并在 stdout 逐行输出 `@@arc-event {…}`；Python 翻译成 `mark_*` | M1 |
| E2 | 每条测试结果写 tests 表；设计 JSON 写 node_contracts/interfaces | `Flow.record_tests`、`save_design` | A1-3 | `test_result`、`design` 事件，Python 翻译 | M1 / M2 |
| E3 | 每次 commit 触发 commit_history 刷新信号 | `GitClient.commit` | 平台 UI | `commit` 事件 | M1 |
| E4 | `[usage] provider totals` 收尾行 | `Flow.log_usage_summary` | 平台不导出 .arc 时也有账 | `usage_total` 事件 + 日志行 | M1 |
| E5 | metrics.py 口径（turn/completed、token_cost_update、llm-usage、runner-events、local-grade） | `metrics.py` | 本机对照 | 内核镜像 turn/completed 与 llm-usage 记录，脚本不改 | M1 |

#### reap.rs（← main.py 的进程回收）

| # | Python 策略 | 来源 | 为什么存在 | Rust | 里程碑 |
|---|---|---|---|---|---|
| R1 | 收尾/异常时：打印 free -m、cgroup memory.*、ps 按 RSS 前 20；杀 chrom/headless_shell/playwright/octos serve/node/npm（排除自身与父进程） | `_reap_stray_processes` | 0764e8d77c54、e60fb3545eae（评测阶段 4 worker 1 秒被 Killed） | `reap::sweep(tag)`，并按目标书改为每节点结束回收 frontend/backend 目录下残留的 node/Chromium | M4 |
| R2 | 评测端口 watchdog | `_port_watchdog` | R0 | `reap::PortWatchdog` | M4 |

#### 策略文件 `arc/arc-policy.toml`（← 约 60 个环境变量）

全部 `OCTOS_*` / `OCTOS_ARC_*` 开关映射为有默认值、有注释的字段，环境变量仍可覆盖（命令行 > 环境变量 > 策略文件 > 内置默认）。字段清单与对应环境变量见 `arc/arc-policy.toml` 的注释；`policy::tests` 逐字段断言默认值与 Python 一致、环境变量覆盖生效。留在 Python 胶水的变量：`ARCBENCH_*`（平台输入）、`OCTOS_BIN`、`OCTOS_CACHE_DIR`、`OCTOS_RELEASE_URL`、`OCTOS_ARC_ENGINE`。

#### 提示词 `arc/prompts/*.md`

`policy.txt` 与 Python 里的全部模板（APP_SKELETON / NODE / DESIGN / REPAIR / FINAL_CHECK / REHEARSAL / UI_CONTRACT 三块 / PERFORMANCE / ARCHITECTURE / VERIFY 两种 / PORT_RULES / ACCEPTANCE_TESTS / codegen 四段 / 纠正句）逐字搬到 `arc/prompts/`，占位符用 `{name}`。M1 只有 codegen 段进入运行路径；其余在 M2 接入 tool 模式时使用，但文件在 M1 就位，便于对照。

### M1：tree + codegen + acceptance 最小闭环（PR 待编号）

**改动位置**：`crates/octos-arc/src/{policy,prompts,tree,plan,codegen,acceptance,llm,events,git,budget,flow,run,envs}.rs`（新增），`runner.rs`（`octos arc` 增加 `run` 子命令，原 create/evolve 形式不变），`crates/octos-cli/src/commands/mod.rs`（接线），`crates/octos-llm/src/openai.rs`（`OpenAIProvider::with_chat_timeout`：非流式请求原来固定 300 s 超时，整应用单响应生成需要更长），`arc/arc-policy.toml` 与 `arc/prompts/*.md`（策略与提示词，运行时读取），`arc/rust_engine.py`（胶水，仅在 `OCTOS_ARC_ENGINE=rust` 时由 `main.py` 转入），`arc/pack.sh`（打包新增文件），`.gitignore`（`*.md` 全局忽略规则对 `arc/prompts/` 例外）。

**命令**：`octos arc run --spec <output>/.arc/runner-spec.json --policy arc/arc-policy.toml [--dry-run] [--set key=value]`。runner-spec.json 由胶水写出（requirement_path、output_dir、web_port、tests_dir、bundle_dir、model 路由；key 只从环境变量读）。内核把事件写到 `.arc/octos-arc-events.jsonl` 并在 stdout 逐行输出 `@@arc-event {…}`，胶水实时翻译成 ARC 的 `mark_*`、tests 表与 commit 刷新信号；`.arc/llm-usage.jsonl` 与 `.arc/octos-events.jsonl`（turn/completed 与 token_cost_update 镜像）保持 `metrics.py` 口径不变。

**M1 覆盖范围**：对照表中标 M1 的条目全部落地；tool 模式（stdio 驱动、骨架/设计/终检轮、全套修复轮、演练修复轮、守护）在 M2。codegen 修复两轮后或同一失败连续两次时，Python 会切到 tool 模式，M1 在该点保留最优状态并在日志写明；Smoke 两题不触发该路径。`loop.rs` 在 Rust 里叫 `flow.rs`（`loop` 是关键字）。

**通用性自查（0.1 节）**：本 PR 没有含任务名或 REQ 编号的条件分支。相对 Python 逐字搬运的提示词，改写成通用形式的有：UI 契约里「(username, city, date)」「one "Register" link, one "Login" link」「the count is initially 0」「password-strength meters, counters, previews」分别改为「a user name, a chosen option, a date」「specs locate links by href」「a value shown on load」「any live indicator derived from what the user is typing」；性能契约里 scryptSync 的具体参数改为「每请求 CPU 预算 30 ms，选满足预算的哈希参数」；codegen 多节点规则里的 TB 链接文本改为「按 spec 复制导航文本与 href」；契约关键词表去掉「nationalit / 车次 / train」（只对订票类题目有意义），保留 seed/published/fixture/option/select/dropdown/选项/下拉/预置。所有阈值（K=5、codegen 修复 2、慢测试 3 s、10 s 单测超时、700 MiB/worker、32768 max_tokens、1500 s/节点）都来自策略文件且与 Python 默认一致，从容器事实（cgroup）、spec 文本（默认端口）或验收输出（失败摘要）推导。

**M1 对等验证（本机，2026-09-14，同一二进制 `target/release/octos` = main@ea503546 + 本分支，同一模型 `deepseek-v4-flash` 经 `api.arc-bench.com`，`run-task-local.py` 默认配置，`grade-local.py` 公开测试打分；每行一次运行，`billed` 取 `.arc/llm-usage.jsonl`，即平台计费同口径的供应商 usage）**

| 运行 | 路径 | 请求数 | prompt tokens | completion tokens | 耗时 s | 公开测试 | 节点状态 |
|---|---|---:|---:|---:|---:|---|---|
| py-counter-1 | Python | 1 | 509 | 327 | 11 | 1/1 | REQ-1、ROOT PASSED |
| py-counter-2 | Python | 1 | 509 | 349 | 9 | 1/1 | 同上 |
| py-counter-3 | Python | 1 | 509 | 309 | 9 | 1/1 | 同上 |
| py-counter-4 | Python | 1 | 509 | 357 | 9 | 1/1 | 同上 |
| py-counter-dump | Python | 2（首轮 0/1，一次重写） | 1,541 | 409 | 19 | 1/1 | 同上 |
| rs-counter-1 | Rust | 1 | 510 | 374 | 12 | 1/1 | 同上 |
| rs-counter-2 | Rust | 2（首轮 0/1：按钮无脚本，一次重写） | 1,555 | 415 | 21 | 1/1 | 同上 |
| rs-counter-3 | Rust | 1 | 510 | 342 | 11 | 1/1 | 同上 |
| rs-counter-4 | Rust | 1 | 510 | 361 | 12 | 1/1 | 同上 |
| rs-counter-dump | Rust | 1 | 510 | 374 | 13 | 1/1 | 同上 |
| py-dice-1 | Python | 1 | 436 | 307 | 8 | 1/1 | 同上 |
| py-dice-2 | Python | 1 | 436 | 304 | 9 | 1/1 | 同上 |
| rs-dice-1 | Rust | 1 | 437 | 327 | 11 | 1/1 | 同上 |
| rs-dice-2 | Rust | 1 | 437 | 315 | 11 | 1/1 | 同上 |

- 通过率：14/14 次运行公开测试 1/1，节点状态与 FOLDER 状态与 Python 路径一致。
- 请求数：两条路径各有 1 次首轮 0/1（模型采样：Rust 那次首轮的 `index.html` 按钮没有脚本；Python 那次是 `py-counter-dump`），都由「0/N 时一次重写」修好；其余运行都是 1 次请求。
- Token：单请求运行的 prompt 差 1 token（510 对 509、437 对 436）。用 `OCTOS_ARC_PROXY_DUMP=1` 抓的 Python 侧请求体与 Rust 侧逐字段比对：model、`max_tokens: 32768`、`temperature: 0.0`、`stream: false`、`thinking: {type: disabled}`、system 消息完全一致，user 消息只差末尾一个换行（内核会话对回合输入做 trim，Rust 侧原样保留了模板末尾的换行）。已改为同样 trim（见下一行的复测）。completion 是采样波动：Counter 单请求均值 Python 335.5、Rust 362.8（+8.1%），Dice 305.5 对 321（+5.1%）；单请求总 token Counter 844.5 对 872.8（+3.3%）、Dice 741.5 对 758（+2.2%），都在 ≤10% 内。
- `metrics.py` 的 cost 列两条路径估价表不同（Python 路径由内核会话按 deepseek-chat 价估，Rust 路径的账本按 `octos-llm` 的 deepseek-v4 价估），对照以 token 为准；平台计费以其 meter 为准。
- 云端未评测（M5 前不请求云端运行）。
- trim 之后复测（同一二进制重新编译）：rs-counter-5 1 请求 / 509 prompt / 343 completion / 1/1；rs-dice-3 1 请求 / 436 / 309 / 1/1——prompt 与 Python 路径逐 token 相同。
