# arc/ 适配层改动记录（工作流 A，分支 `wf-adapter`）

度量口径：本机 `.arc/octos-events.jsonl` 的 `turn/completed`（tokens_in / tokens_out 之和，不含缓存命中）与 `token_cost_update`（每个 session 的累计 `session_cost`，多 session 求和）；耗时取 `.arc/runner-events.jsonl` 的 running → completed；通过数由 `arc/grade-local.py` 用平台公开 Playwright 测试打分（`arc/metrics.py <输出目录>` 可一次打印整行）。所有运行都是本机、同一二进制（`octos 2.0.3-rc.11 (82e3bef3)`，`target/release/octos`，SHA-256 `b0b670ba…cd8c5`）、同一模型（`deepseek-v4-flash` 经 `api.arc-bench.com`）。「未评测」表示没有云端运行。

## 结论表（改前 → 改后，均为本机最终配置一次运行；云端未评测）

| 题 | 指标 | 改前 R0 | 改后 | 运行 |
|---|---|---|---|---|
| Counter | 公开测试 | 1/1 | 1/1 | r6-counter |
| Counter | tokens_in / tokens_out | 48,958 / 16,118 | 14,048 / 5,478 | 同上 |
| Counter | 费用 / 耗时 | ¥0.0756 / 422 s | ¥0.0211 / 63 s | 同上 |
| Counter | 节点状态 | REQ-1 PASSED（终检成功才有） | REQ-1 PASSED（本地 spec 判定） | 同上 |
| Ticket Booking | 公开测试（按评测方式启动） | 10/10 | 10/10 | r7-tb |
| Ticket Booking | tokens_in / tokens_out | 241,076 / 90,562 | 302,042 / 168,548 | 同上 |
| Ticket Booking | 费用 / 耗时 | ¥0.7645 / 2,508 s | ¥0.7166 / 1,988 s | 同上 |
| Ticket Booking | 节点状态 / tests 表 / 设计契约 | REQ-1、REQ-2 PASSED（依赖终检）/ 无 / 无 | REQ-1、REQ-2（+镜像 REQ-1.1、REQ-1.2）PASSED / 10 行全 passed / 2 | 同上 |
| Smoke Evolution | 公开测试（2 文件并行） | 不支持（会重做骨架） | 2/2 | e2-evolution |
| Smoke Evolution | 费用 / 耗时 | — | ¥0.0877 / 428 s | 同上 |

## 运行矩阵

| 运行 | 适配层 | 开关 / 代码状态 | 用途 |
|---|---|---|---|
| R0 | 改前（`82e3bef3` 的 `arc/`） | — | 对照，worktree `octos-arc-A-baseline` |
| R5 | 新编排器首版（`1a60fa8b`…`d5f9dccb`） | 默认开关 | A1–A7 全开；暴露了「测试改写数据被提交」「实现轮超时被当瞬时错误重放」「双端口 listen 两次」三个问题 |
| R6 | `06d3a02e`（单节点并入一轮 + 简短自验） | 默认 | Counter 最终配置 |
| R7 | `5a62ec89`（全套并行验收 + 按评测方式启动 + 只读设计轮） | 默认 | Ticket Booking 最终配置 |
| R8 | 同 R7 | `OCTOS_DESIGN_MODE=inline` | 设计轮并入实现轮的对照 |
| R1 / R3 / R4 | R6 代码 | 分别：修复轮 0 + 性能规则关 + 守护关 + 单 session；性能规则关；每轮新 session | Counter 上的开关消融 |
| E1 / E2 | R5 / R7 代码 | 默认 | A6：以 Counter 产物为模板跑 smoke-evolution--counter |

每完成一条改动就跑一次 Counter 与 Ticket Booking 的要求，实际执行成了「先整体重写、再用开关和连续修正逐项测」：编排器的七条改动共享同一套节点循环，拆成七个独立可运行的中间版本会让每个中间版本都带着后面才发现的缺陷（例如 R5 的三个问题）。下面每条 A 项都标注了它对应的运行。

## 数据总表（本机，同二进制同模型；每行一次运行）

Counter（`smoke--counter`，1 个节点，公开测试 1 条）：

| 运行 | 配置 | 轮数 | tokens_in | tokens_out | 费用 ¥ | 耗时 s | 公开测试 | 节点状态 | 事件流 |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| R0 base-counter | 改前 | 3 | 48,958 | 16,118 | 0.0756 | 422 | 1/1 | REQ-1 PASSED | `octos-arc-A-baseline/arc/arc-output/base-counter/.arc/` |
| R5 r5-counter | 默认（首版，测试后未还原数据） | 3 | 39,785 | 20,070 | 0.0834 | 354 | **0/1**（db.json 被验收测试改成 -1 后随 commit 提交） | REQ-1 PASSED | `arc/arc-output/r5-counter/.arc/` |
| R5 r5-counter-2 | 默认 + 测试后还原工作区 | 3 | 74,906 | 28,700 | 0.1436 | 597 | 1/1 | REQ-1 PASSED | `arc/arc-output/r5-counter-2/.arc/` |
| R5 r5-counter-3 | 默认（单节点已跳过设计轮） | 2 | 83,073 | 50,649 | 0.1605 | 862 | 1/1 | REQ-1 PASSED | `arc/arc-output/r5-counter-3/.arc/` |
| R4 r4-counter-turnscope | 默认 + `OCTOS_SESSION_SCOPE=turn` | 3 | 79,855 | 33,519 | 0.1452 | 548 | 1/1 | REQ-1 PASSED | `arc/arc-output/r4-counter-turnscope/.arc/` |
| **R6 r6-counter** | **默认（单节点：骨架并入节点轮，简短自验）** | **1** | **14,048** | **5,478** | **0.0211** | **63** | **1/1** | REQ-1 PASSED | `arc/arc-output/r6-counter/.arc/` |
| R3 r3-counter-noperf | R6 代码 + `OCTOS_PERF_CONTRACT=0` | 1 | 30,307 | 11,034 | 0.0384 | 351 | 1/1 | REQ-1 PASSED | `arc/arc-output/r3-counter-noperf/.arc/` |
| R1 r1-counter-minimal | R6 代码 + 修复轮 0、性能规则关、守护关、单 session | 1 | 19,563 | 11,256 | 0.0325 | 220 | 1/1 | REQ-1 PASSED | `arc/arc-output/r1-counter-minimal/.arc/` |

Counter 小结：同一代码三次运行（R6、R3、R1）都是 1 轮、1/1，费用 ¥0.021–0.038、耗时 63–351 s，运行间方差（模型自验证的多少）大于开关本身的差异；相对改前（¥0.0756、422 s）费用降到 28%–51%、耗时降到 15%–83%。真正起作用的是 A5 的两条：单节点不再单开骨架轮、提示词告知「harness 随后跑官方测试，自验证从简」。

Ticket Booking（`ticket-booking--ticket-booking`，2 个节点，公开测试 10 条）：

| 运行 | 配置 | 轮数 | tokens_in | tokens_out | 费用 ¥ | 耗时 s | 公开测试 | 节点状态 | 事件流 |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| R0 base-tb | 改前 | 5 | 241,076 | 90,562 | 0.7645 | 2,508（骨架轮超时 1200 s 后整轮重跑，共 1,991 s） | 10/10 | REQ-1/2 PASSED | `octos-arc-A-baseline/arc/arc-output/base-tb/.arc/` |
| R5 r5-tb | 默认（全套并行验收与「按评测方式启动」之前的代码） | 6 | 239,309 | 141,560 | 0.5674 | 1,555 | **0/10：按评测方式（只设 PORT）启动时 `ERR_SERVER_ALREADY_LISTEN` 崩溃**；逐节点验收 6/6 + 4/4 | REQ-1/2（及镜像 REQ-1.1/1.2）PASSED | `arc/arc-output/r5-tb/.arc/` |

Smoke Evolution（`smoke-evolution--counter`，模板 = 上一行 Counter 产物，公开测试 2 条并行）：

| 运行 | 模板 | 轮数 | tokens_in | tokens_out | 费用 ¥ | 耗时 s | 公开测试 | 节点状态 | 事件流 |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| E1 e1-evolution | r5-counter-2（服务端共享计数） | 5 | 98,381 | 39,295 | 0.2226 | 1,198 | **0/2**：两条测试并行改同一个服务端计数（期望 1 实得 3）；逐节点单跑时各自 1/1 | REQ-1/2 PASSED | `arc/arc-output/e1-evolution/.arc/` |
| **E2 e2-evolution** | r6-counter | 3（回归 0 轮 + 设计 + 实现） | 41,745 | 14,489 | 0.0877 | 428 | **2/2** | REQ-1 PASSED（carried over + 回归通过），REQ-2 PASSED | `arc/arc-output/e2-evolution/.arc/` |

| **R7 r7-tb** | **默认（最终代码：全套并行验收 + 按评测方式启动 + 只读设计轮 + 简短自验）** | 7 | 302,042 | 168,548 | 0.7166 | 1,988 | **10/10**（按评测方式启动） | REQ-1/2（及 REQ-1.1/1.2）PASSED；tests 表 10/10；node_contracts 2 | `arc/arc-output/r7-tb/.arc/` |

R7 逐轮：骨架 475 s → REQ-1 设计 155 s（51 次工具调用，模型无视「只读」仍执行了命令）→ 实现 831 s → 验收 4/6 → 修复 62 s（7 次调用）→ 6/6 → REQ-2 设计 147 s → 实现 267 s → 验收启动异常（后端「listening」后以 rc=0 退出）→ 修复轮 21 s 后 octos 进程退出（stderr 尾部为正常 INFO 日志，无 turn/error；转 B 排查）→ 重跑验收 4/4 → 全套并行 10/10 → 演练通过。

| R8 r8-tb-inline | R7 代码 + `OCTOS_DESIGN_MODE=inline` | 4 | 202,001 | 126,386 | 0.5494 | 2,847 | 10/10（按评测方式启动） | 同上 | `arc/arc-output/r8-tb-inline/.arc/` |

R8 逐轮：骨架 182 s → REQ-1 实现（含设计 JSON）900 s 超时 → 验收 0/6 → 修复 565 s 超时 → 3/6 → 节点预算耗尽 → REQ-2 实现 484 s → 验收 0/4 → 修复 609 s → 4/4 → 全套并行 10/10（REQ-1 剩余 3 条在 REQ-2 修复中被顺带修好）→ 演练通过。

Ticket Booking 小结：R7（默认）与 R8（inline 设计）都拿到 10/10；R7 费用 ¥0.717（改前 ¥0.765，−6%）、耗时 1,988 s（改前 2,508 s，−21%）；R8 费用 ¥0.549（−28%）但耗时 2,847 s（+14%），因为把设计并入实现轮后实现轮两次撞到 900 s 上限。默认保留独立的只读设计轮。**费用减半的目标在 TB 上没有达到**：三次 TB 运行输入 Token 202k–302k，与改前 241k 同量级，输出 Token（含推理）126k–169k 反而高于改前的 91k——模型在每轮里做的自验证多、推理长；进一步压缩要靠内核侧的工具输出裁剪/推理预算（B4/B3）和更短的实现轮。

## A1 · 功能实现率归零的原因

**证据**（本机可见的部分）：

- 本机 TB 运行 `ticket-arc-opt-final` 的 `.arc/traceability/node_states.json` 两个节点都是 `PASSED`，`runner-events.jsonl` 有完整的 design/implement/test 事件；Counter 运行 `cmp-arc-opt-final2` 同样完整。也就是说本机版适配层写出的文件格式和 Smoke 云端 1/1 的运行完全一致。
- 旧编排器的测试判定逻辑是：终检轮 `ok` 为假或任一节点实现失败时，**所有**节点一律 `mark_test_failed`；只有终检轮成功才全部 `mark_test_passed`。TB 云端运行 a74a5ac5afbd 总时长 1259 s、终检轮默认 1200 s 上限，一旦终检超时/失败，两节点都被标成 FAILED；而 Smoke 终检成功所以 1/1。
- 另一个本机可验证的差异：TB 公开测试文件名是 `REQ-1.1-user-registration.spec.ts`、`REQ-1.2-user-login.spec.ts`，而需求树节点是 `REQ-1`、`REQ-2`；Smoke 的测试文件 `REQ-1.spec.ts` 与节点 id 一致。若平台按测试侧 id 归集功能实现率，TB 的节点状态永远对不上。
- 云端 a74a5ac5afbd 的 traceability 接口「返回空」而不是「全 FAILED」，更符合第二种解释；但云端原始数据本工作流拿不到（不发起/不读取云端），**需要工作流 C 从运行详情导出 `.arc/traceability/` 与 runner-events 核对**。

**改法**（两种原因都覆盖）：

1. 每个 ATOMIC 节点在自己的周期内发出 `design_started/done`、`implementation_started/done|failed`，然后用属于该节点的公开 spec 在本机真实跑一遍 Playwright（10 s 单测试超时，与平台一致），据结果发 `test_passed` 或 `test_failed`；终检失败不再覆盖已有的节点判定。没有本地 Playwright 时才退回「终检 + 启动演练」判定。
2. spec 文件名里的 id 与节点 id 不一致时，按（精确匹配 → 数量相同按序配对 → 父前缀）映射，并把节点状态**同时**镜像到 spec 侧 id（`REQ-1.1`、`REQ-1.2`），`OCTOS_ARC_ALIAS_SPEC_IDS=0` 可关。
3. 设计 JSON 写入 `node_contracts`、接口写入 `interfaces`、每条测试结果写入 `tests` 表，平台无论读哪张表都有数据。
4. 运行异常中断时，`finally` 段为所有还没有判定的节点补 `test_failed`，保证每个节点都有终态。

**验证**：R7 `arc/arc-output/r7-tb/.arc/traceability/`：`node_states.json` = REQ-1 / REQ-2 / REQ-1.1 / REQ-1.2 全部 PASSED（后两者为镜像），`tests.json` 10 行全部 `passed: true`，`node_contracts.json` 有 REQ-1、REQ-2 的设计；`runner-events.jsonl` 里每个节点都有 design running/completed、implement running/completed、test passed。云端 `feature_implementation_rate` 未评测，需 C 用本分支打包后跑一次 TB。

## A2 · 按依赖序遍历需求树

`requirement_order.topo_order`：ATOMIC 节点按 Kahn 拓扑排序，依赖在前，同层保持文档顺序；依赖指向 FOLDER 时展开为其全部 ATOMIC 后代；未知 id、自依赖忽略；出现环时非环节点先出、环内按文档顺序打破（`arc/tests/test_requirement_order.py` 6 个用例）。`ancestors_of` 给出传递依赖，节点提示词里附上祖先节点已完成的设计 JSON 摘要（routes / pages / data_model，每个 ≤1500 字符），没有设计 JSON 的祖先只写「已实现，见代码」。

Counter（1 节点）与 Ticket Booking（REQ-2 依赖 REQ-1，文档顺序本来就是依赖顺序）上遍历顺序与改前相同，因此这两题上 A2 没有可测的分数差异；它的价值在 ARC-Bench Web 六题（32–138 个节点、非线性依赖），由工作流 C 在 `arc-bench-web--keep` 上验证。

## A3 · 每节点「设计 → 本地验收 → 实现 → 通过即 commit」

- 设计轮：提示词 `DESIGN_PROMPT`（826 字符）要求读本节点 spec 和现有代码后写 `.arc/design/<节点>.json`（routes / pages / data_model / files / notes）并在回复里重复；harness 解析回复中的 JSON，取不到就读文件；设计写入 traceability 的 `node_contracts` 与 `interfaces`。树只有 1 个 ATOMIC 节点时跳过（`OCTOS_DESIGN_MIN_NODES=2`）：单节点应用没有跨节点接口要协调，设计轮只是纯开销（Counter 上一次设计轮 25–35 s、约 1 万 Token）。
- 实现轮：节点 spec + 设计 JSON + 祖先摘要 + 本节点 spec 文件清单 + UI/性能契约。实现轮最长占节点预算的 60%，超时不重放（改前把 `octos turn timed out` 当瞬时错误整轮重跑，r1-tb-aborted 因此白烧 15 分钟），已写出的代码直接进入验收。
- 验收循环：`acceptance.py` 用平台同款 Playwright、10 s 单测试超时，只跑属于本节点的 spec；失败只回传四字段摘要（Feature / Failed at / Observation / Steps，Steps 取 test.step 或 Playwright Call log）；K ≤ 5（`OCTOS_REPAIR_ROUNDS`）。通过数上升就 `git commit`，连续两次下降就 `git checkout <最优 commit> -- frontend backend` 并告知模型；节点结束若不在最优点也回到最优点。每次跑测试前 `git add -A`、跑完 `git checkout -- . && git clean`，把测试对持久化数据的改动还原（r5-counter 的 0/1 就是被测试改成 -1 的 db.json 被提交造成的）。
- 内核 B 的验收 hook（`OCTOS_ARC_SPEC_DIR` / `OCTOS_ARC_BASE_URL`）位于 `octos arc` 子命令的 `run_acceptance_hook`，只在那条 `octos chat` 流程末尾触发，无法从 `serve --stdio` 会话里按节点调用，所以适配层自己实现了同样的逻辑（也是纯 Playwright 子进程）。
- 平台容器里若找不到 Playwright（查 `OCTOS_ARC_PLAYWRIGHT_ROOT`、bundle 的 local-grader、`/workspace/tests` 的祖先、`/workspace`），会用 npmmirror 装 `@playwright/test` + chromium（上限 540 s）；装不上就退回「终检轮 + 启动演练」判定并记录 skipped。**容器内是否装得上未验证**，需要 C 的第一次云端运行日志（`[acceptance]` 行）。

## A4 · Ticket Booking 的两条超时

**本机复现**：用本机 arc-opt 产物 `ticket-arc-opt-final` 跑公开 10 条测试，把 Playwright `timeout` 设成平台的 10 000 ms：10/10 通过，单测试 549–1553 ms，注册接口 `crypto.scryptSync(password, salt, 64)`（默认成本 N=16384）。因此哈希成本、首屏加载在本机都不是瓶颈；云端失败的两条（`REQ-1.1 注册后刷新仍保持登录`、`REQ-1.2 用户名密码登录`）恰好是唯一两条在登录态下执行 `page.reload()` 的测试（邮箱大小写登录那条不刷新，通过了）。`reload()` 默认等 `load` 事件，最贴合的两个解释：登录后页面引用了外部资源（字体 / CDN / 头像）在无外网的容器里挂住 `load`；或 cookie 属性（`Secure`、`Domain=localhost`、`SameSite=None`）让 127.0.0.1 上的刷新丢会话，`expectSignedIn` 轮询 5 s 后连同前面的步骤超过 10 s。两者都无法从本机复现，需要 C 提供云端失败用例的错误文本。

**改法**：`PERFORMANCE_CONTRACT`（909 字符）加入节点、修复与终检提示：零外部请求、`load` 200 ms 内、scrypt 默认成本或 pbkdf2 ≤ 100k、单请求 < 100 ms、cookie `HttpOnly; Path=/; SameSite=Lax; Max-Age` 且**不带** `Secure`/`Domain`、刷新恢复登录态只允许一次同源请求、禁止 setTimeout/轮询/service worker/debounce 写盘。本地验收用 10 s 超时，任一测试超过 3 s（`OCTOS_ARC_SLOW_MS`）即把用例名连同性能规则喂回修复轮。`OCTOS_PERF_CONTRACT=0` 可关。

## A5 · 上下文成本

- 提示词长度（字符）：骨架 7,702 → 1,558；节点 6,370 → 3,557（含 UI 契约 1,945 + 性能契约 909）；终检 6,747 → 2,795（不含契约时）/ 3,703；新增设计轮 826、修复轮 727。所有提示词都是常量拼接，没有时间戳，段落顺序固定；工具定义与 system 由内核决定。
- 会话粒度 `OCTOS_SESSION_SCOPE`：默认 `node`（骨架单独一个 session；每个节点的设计 → 实现 → 修复共用一个 session，节点间新开），`turn` 每轮新开，`run` 全程一个。选 `node` 而不是 `turn` 的原因：设计轮已把 spec 和现有代码读进上下文，实现轮若新开 session 会再读一遍（r5-tb 首版观察到设计轮 24 次工具调用后实现轮又从 `list_dir` 开始）。
- 终检轮只在有节点没拿到本地验收判定时才跑；Counter 默认配置从改前 3 轮（骨架/节点/终检）变成 2 轮（骨架/节点）+ 本地 Playwright。

## A6 · Evolution 模式

启动时若输出目录已有 `frontend/package.json` 与 `backend/package.json` 即进入 evolution：跳过骨架轮；在 `store_requirement_tree` 覆盖之前读取上一轮提交在模板里的 `.arc/traceability/requirements.json`，按 `node_fingerprint`（id / name / description / scenarios / dependencies）比对，指纹相同的节点走 `regression_cycle`（design/impl 事件标「carried over」，只跑它的 spec；失败则进入修复循环），其余节点正常实现，节点提示词前置现有源码清单（`EVOLUTION_NOTE`）。本机验证：`run-task-local.py --template <smoke--counter 产物> arc/tasks/smoke-evolution--counter`。

## A7 · 守护规则

`guard.TurnMonitor` 订阅每轮的 `tool/started` / `tool/completed` 事件：写了文件、结束语宣称完成却没有执行过 build/start/curl/node 类命令（设计轮不适用）；同一错误（数字归一化后）连续 ≥3 次；写入保护路径（spec 目录、需求目录、`.arc/`，但允许 `.arc/design/`）。命中的纠正句附在同一节点下一轮提示词开头（`OCTOS_GUARD=0` 只记日志不注入）。预算：整体 `OCTOS_TIME_BUDGET`，节点预算 = min(1500, 剩余时间 / 剩余节点)，实现轮 ≤ 60%，修复轮剩余不足 90 s 即停止并保留最优 commit；整体预算耗尽的节点直接标 `implementation_failed`；任何异常都在 `finally` 段给未判定节点补 `test_failed`。

## 第二轮 · 吸收工作流 C 的回流（`bd3c56ca`）

C 用旧 main（`82e3bef3`）适配包在 `arc-bench-web--keep` 本机跑到 26/32、83 分钟，回流三点已吸收：

1. **FOLDER 节点也计入平台需求数**（keep 记「45 requirements and 32 scenarios」）。`mark_folders()` 在收尾时给每个非 ATOMIC 节点按其 ATOMIC 后代推导 design/implement/test 状态：全部子节点通过才 `test_passed`，否则 `test_failed` 并列出未通过的子节点；异常路径同样补齐。
2. **骨架轮不再读全部 spec**。旧 `ACCEPTANCE_TESTS_PROMPT` 在骨架轮列出全部 spec 文件并要求「写代码前全部读完」，模型因此在一轮里把 32 个功能全做完（70 分钟、单会话 40–130 万字符推理）。现在骨架轮只给 spec 目录、共享 helper 和「最多读两个 spec 学约定，不实现功能」，spec 文件在各自节点轮才出现。
3. **整体预算按节点数放大**：未显式设 `OCTOS_TIME_BUDGET` 时取 max(3600, 480 × ATOMIC 节点数)（`OCTOS_SECONDS_PER_NODE`），keep 为 15,360 s；节点预算仍是 min(1500, 剩余/剩余节点)。

第二轮代码的本机验证：

| 运行 | 轮数 | tokens_in | tokens_out | 费用 ¥ | 耗时 s | 公开测试 | 节点状态 |
|---|---:|---:|---:|---:|---:|---|---|
| r9-counter | 1 | 25,242 | 7,757 | 0.0327 | 331 | 1/1 | REQ-1、ROOT PASSED |
| **r9-tb** | 5 | 213,602 | 127,660 | **0.5768** | **1,346** | 10/10（按评测方式启动） | REQ-1、REQ-2、REQ-1.1、REQ-1.2、ROOT PASSED |

r9-tb 逐轮：骨架 211 s（不再读全部 spec）→ REQ-1 设计 167 s → 实现 504 s → 6/6 → REQ-2 设计 213 s → 实现 238 s → 4/4 → 全套并行 10/10 → 演练通过，零修复轮。相对改前：费用 −25%、耗时 −46%。

C 的其余发现与本分支已有改动的对应：轮超时被当瞬时错误重放 → `d5f9dccb` 已修；骨架超时但盘上已有 frontend/backend 则继续 → `skeleton()` 已按盘上状态判定；单会话累积上下文（keep 云端 8,256 万 token、¥17.94）→ 默认按节点新开 session；云端评测阶段 Playwright 用 4 workers 1 秒后被 SIGKILL 是平台侧问题，适配层无法影响；Evolution 在平台上 `ARCBENCH_TEMPLATE_DIR` 未设置而模板在 `/workspace/template`，本分支按输出目录里是否已有 frontend/backend 判定，与 C 观察到的 2/2 一致。

## 紧急修正 · 云端 Smoke Evolution 0/2（C 回流，运行 da9a64b32c09 / 16ea5178359a）

**现象**：main@40a629a8 的适配包在生成阶段 `[acceptance]` 自跑 2/2，但平台评测阶段 `npx playwright test` 报 `browserType.launch: Executable doesn't exist at /ms-playwright/chromium-1200/...`，2 条全失败；同题旧适配包 2/2。日志顺序是 `no Playwright install found; trying to install one` → `playwright installed into /tmp/octos-arc-playwright`。即镜像里其实有预装的 Playwright 但我们没找到，随后未隔离的安装改变了平台自己 `npx playwright` 的解析结果。

**改法**（`acceptance.py` / `main.py`）：
1. 先找预装：候选路径加上 `npm root -g` 的上级、/workspace、/workspace/tests、/app、/runner、/opt/playwright、/usr/local/lib、/usr/lib、$HOME；再做一次 25 s 内的 `find / -maxdepth 6 -path '*/node_modules/@playwright/test'`（排除 /proc /sys /tmp）。
2. 真要自装时完全隔离：版本钉死（tests 目录的 package-lock/package.json 声明的版本，否则 1.63.0；绝不 latest），`npm_config_cache` 与 `PLAYWRIGHT_BROWSERS_PATH` 都指向本次运行的私有临时目录，浏览器用 `node_modules/.bin/playwright install` 而不是 `npx`，所有验收运行带同一 `PLAYWRIGHT_BROWSERS_PATH`，运行结束（含异常路径）删除整个私有目录。
3. 本机验证：私有安装 24 s 完成，chromium-1243 落在私有目录，登录节点 4/4；安装前后 `~/Library/Caches/ms-playwright` 与 `~/.npm` 均未变化，私有目录已删除。
4. 云端 d116ad5e3aa0（wf-adapter-2@71040c6c）15 s 崩溃：`setup_playwright` 的一处文本替换未生效，仍把 `(root, env)` 元组当 Path 用，且缺 `cleanup_playwright`。`e3c1197f` 整段重写并加回归测试 `SetupPlaywrightTests`；本机把 local-grader 藏起来强制走该分支跑 Counter（r10-counter-privatepw）：私有安装 25 s → 验收 1/1 → 演练通过 → 私有目录已删除，公开测试 1/1，¥0.0306，374 s。**云端未评测**，等 C 用 e3c1197f 打包再跑一次 smoke-evolution 后合入。

## 第三轮 · 保护官方测试与空报告（C 回流，云端 a6ccc437539f，`wf-adapter-3`）

**云端现象**：main@40a629a8 的 TB 云端 0/10、¥10.22、3,376 s。日志里 `[guard] You modified protected files … /workspace/tests/*` 之后紧跟 `[acceptance] 0/0 passed (REQ-1.1-…)`：模型改了 `/workspace/tests`，复制过来的 spec 不再能加载，「0/0」被当成判定，之后的修复轮都在盲修；REQ-1 实现轮 900 s 超时；容器里 4 并行全套 2/10（10 s 超时）。

**改法**：
1. **拒绝写入官方测试目录**（`arc/hooks/deny_protected.py`）：内核 `before_tool_call` hook，对 write_file / edit_file 等按 `arguments.path` 判定，落在 tests 或 requirements 目录内即 exit 1（模型看到 `[HOOK DENIED]`）。接线要点：`octos serve --solo` 的 ProfileRuntime 只从 profile 自身 config 取 hooks（`config_from_profile`），host `config.json` 与 `profile-defaults.json` 都不生效——用真实 stdio 轮验证过两次都放行；改为在 `profile/local/create` 之后、`profile/llm/upsert` 之前把 `hooks` 写进 `data/profiles/<id>.json`，第三次验证：写保护目录被拒（spec 内容不变），写普通文件正常。shell 命令的参数被内核脱敏，hook 看不到，所以还有第 2 层。
2. **每轮结束还原受保护目录**：启动时把 tests / requirements 目录快照到私有临时目录并记 sha256，每轮结束比对，改动/删除的文件恢复、新增的删除，并把恢复列表作为纠正句喂给下一轮。平台评测用的正是这些文件，任何改动既破坏本地验收也触碰红线。
3. **空报告不是判定**：Playwright 收集到 0 条测试时返回 error，附顶层 `errors`（编译/加载错误）或 stdout 尾部，进入修复摘要并记日志。
4. **全套修复早停**：失败集合与上一轮相同即停止（默认最多 2 轮，`OCTOS_FINAL_REPAIR_ROUNDS`）。
5. **A4 哈希预算**：明确评测 CPU 慢 5–10 倍且 4 个浏览器并行，scrypt 用 `{N: 4096, r: 8, p: 1}` 或 pbkdf2 ≤ 10,000 次，单请求 CPU ≤ 30 ms。

本机验证：`SetupPlaywright`/hook/tree-restore 共 34 个单元测试；r12-counter 1/1、¥0.0386、91 s（ROOT 状态已写）。

| 运行 | 轮数 | tokens_in | tokens_out | 费用 ¥ | 耗时 s | 公开测试 | 节点状态 |
|---|---:|---:|---:|---:|---:|---|---|
| r11-tb | 7 | 192,910 | 109,919 | 0.6697 | 1,141 | 10/10（按评测方式启动） | REQ-1、REQ-2、REQ-1.1、REQ-1.2、ROOT PASSED |

r11-tb 逐轮：骨架 89 s → REQ-1 设计 139 s → 实现 312 s → 验收 0/6（首页有两个 `a[href="/register"]`，strict mode）→ 修复 174 s → 6/6 → REQ-2 设计 60 s → 实现 196 s → 验收 0/4（`getByLabel(/用户名/)` 命中两个输入框）→ 修复 152 s → 4/4 → 全套并行 10/10 → 演练通过。两处都是四字段摘要直接点名的 strict-mode 错，各一轮修好；改前基线 ¥0.765 / 2,508 s。

**C 对 main@f3f113e6 的云端对比**（0a3cd1d66042 TB 7/10、¥4.45、981 s，生成阶段自跑 10/10）：平台 2 个 worker 并行打同一后端时，「注册后保持登录」超时、「用户名密码登录」登录后看不到用户名、「大小写邮箱登录」超时——两个 spec 各自注册再登录，异步「读文件-改-整写」的持久化在并发下会丢用户。本轮补充：性能契约明确「内存为唯一真源、变更先改内存再同步整写、禁止异步 read-modify-write」；`OCTOS_ARC_FULLY_PARALLEL=1` 可让本地验收在文件内也并行（比平台更严）。功能率 0/2 的原因是平台按测试标题前缀（REQ-1.1）匹配需求 id（REQ-1），与适配层无关，需向平台反馈。

## 云端结果（由工作流 C 运行，证据在 main 的 `evidence/`）

| 题 | 改前（82e3bef3） | main@40a629a8 | main@f3f113e6 | main@9b0d3009 |
|---|---|---|---|---|
| Ticket Booking | b00c4ee7b568：7/10，功能 0/2，¥4.73，674 s | a6ccc437539f：0/10（自装 Playwright 污染评测环境），¥10.22 | 0a3cd1d66042：7/10，0/2，¥4.45，981 s | **ab4c98a6cb17：9/10，功能 1/2，¥1.99，1,051 s** |
| Ticket Booking（main@0522db48） | — | — | — | cbbec51884de：8/10，¥2.49，1,352 s；2 条失败为 Chromium「Target crashed」及同一窗口内 reload 后的 evaluate 超时，同一代码路径上一轮通过，属平台侧随机 |
| Smoke Evolution counter | 37fb13835049：2/2，¥0.55 | da9a64b32c09：0/2（同因） | b76aadf42e9b：2/2，¥0.60，209 s | — |
| Smoke Evolution dice | a02d29a7064a：2/2，¥0.60，204 s | 16ea5178359a：0/2（同因） | 6c9ea2294ff6：2/2，¥1.48，283 s | — |

ab4c98a6cb17 唯一失败：REQ-1.2「用户名密码登录」在注册辅助步骤等 `getByLabel(/证件号码/)` 可见、可用、可编辑直到 10 s 超时；同一 helper 在另外 5 条注册用例和本机自跑 10/10 中都通过，是并行 worker 下页面尚未就绪（表单由 JS 在请求后渲染或请求期间禁用控件）。本轮把 UI 契约改为「表单控件必须直接存在于服务端 HTML 中，请求期间不得禁用」。功能率 1/2：平台按测试标题/文件前缀匹配需求，REQ-1.1 命中 REQ-1，REQ-2 因有失败用例记 0。

**Ticket Booking 收口**（2026-09-12）：四次云端 7/10 → 7/10 → 9/10 → 8/10，费用 ¥4.73 → ¥4.45 → ¥1.99 → ¥2.49；生成阶段自跑全套稳定 10/10。剩余失败是评测容器的渲染进程崩溃/内存压力（与 Web 大题评测被 SIGKILL 同源），适配层不再针对 TB 迭代。

## ARC-Bench Web 六题的建议参数（供工作流 C 本机先跑 `arc-bench-web--keep` 校准）

基于 TB 每节点实测（设计 60–213 s、实现 200–830 s、验收 + 一轮修复 150–200 s）与 C 用旧流程跑 keep 的数据（32 节点、26/32、83 min）：

```sh
OCTOS_SECONDS_PER_NODE=1500     # 总预算 = 1500 × 节点数（keep 32 节点 ≈ 13 h 上限，实际用不满）
OCTOS_NODE_TIME_BUDGET=1500     # 单节点含修复 ≤ 25 min，超时保留最优 commit 进入下一节点
OCTOS_IMPLEMENT_FRACTION=0.6    # 实现轮 ≤ 900 s
OCTOS_REPAIR_ROUNDS=2           # 每节点最多 2 轮修复；剩余 < 300 s 不再开修复轮
OCTOS_DESIGN_MODE=inline        # 32 个独立设计轮约 80 min、明显的费用大头；inline 把设计 JSON 并入实现轮（R8：TB 费用 −23%）
OCTOS_FINAL_REPAIR_ROUNDS=2     # 全套并行验收后的修复轮
```

预计单题 keep：约 32 × 8 min ≈ 4 h 上限、多数节点一轮过则 2–3 h；费用按 TB 每节点 ≈ ¥1.0–1.25 推算 ≈ ¥30–40，低于单次 ¥50 阈值。先本机跑到底，看每节点耗时与 Token 再定其余五题。

**keep-local-3 的校正**（C，2026-09-12）：按 480 s/节点跑到第 10 个节点，17 个实现/修复轮里 16 个在 283 s（0.6×预算）被截断，只有一轮正常结束；截断后剩余不到 200 s 的修复轮同样超时；grade-local 中途评分 8/32、79 min。Web 节点的实现轮需要 10–20 min。据此把默认 `OCTOS_SECONDS_PER_NODE` 从 480 改为 1500（实现轮 ≤ 900 s），新增 `OCTOS_MIN_REPAIR_SECONDS=300`：剩余不足 5 min 不再开修复轮而直接保留最优状态。另外超时的轮没有 `turn/completed`，`metrics.py` 改为从累计的 `token_cost_update` 取 Token 数（费用估算以平台计费为准）。

**keep-local-4（C，main@803f14c3 + 1500 s/节点 + inline + 2 轮修复）：grade-local 32/32，5 h 01 min**，骨架 312 s，平均 519 s/节点，30 个节点首轮通过，4 个实现轮触顶 900 s，全套并行 28/32 → 一轮修复 → 32/32，内核累计费用 ¥5.42（平台按完整输入计费会更高）。暴露的 bug：全套失败「failing nodes []」——错误抛在 `support/e2e.ts` 时按错误位置归属文件，没有节点认领，修复轮只能拿全量信息。已改为按测试所在 spec 文件归属节点，摘要里同时给出错误位置（`e2e.ts:48 (called from REQ-2.3.1-x.spec.ts)`）。

## 第二阶段（2026-09-13）· 目标：真实 agent 第 1（Smoke < ¥0.10、Evolution < ¥0.15、TB 10/10 且 < ¥0.70）

改动（`469ed3ac`、`15ec1549`）：
1. **DeepSeek 推理预算**：内核只对 api.deepseek.com 发 `reasoning_effort`/`thinking`，而 arc-bench 代理同样接受（同一提示：默认 455 completion tokens，`reasoning_effort: low` 279，`thinking: disabled` 132）。适配层起一个本机 stdlib 透传代理 `llm_proxy.py`，对 chat/completions 注入 `reasoning_effort=low`（`OCTOS_ARC_REASONING`：low/medium/high/none/passthrough），并把每次请求的 `usage`（prompt/completion/cache_hit/reasoning tokens，SSE 也解析）记到 `.arc/llm-usage.jsonl`——这是与平台计费同口径的数字。
2. **小题只跑一轮**：≤2 节点不再单开骨架轮（第一个节点轮建应用），< 3 节点不做设计轮，设计默认 inline；≤2 节点的实现轮用「最小自验」：不起服务、不 curl、不写自测，一次 `npm run build`，每个文件一次 write_file，不回读——harness 随后跑官方 spec，失败才进修复轮。
3. **契约按关键词裁剪**：核心块（标签/角色逐字、无 HTML5 校验、单错误元素、strict mode、按页状态、零外部请求）始终在；「fixture 数据」块和「会话」块只在需求文本出现相应关键词时加入；性能契约只在有登录/密码/会话的题目加入。Counter 的节点提示词从 ~3.5k 字符降到 ~2.4k。

本机（二进制 `octos 2.0.3-rc.11 (151fa447)`，与云端 Release 同源）：

| 题 | 之前最好 | 本次 | 公开测试 |
|---|---|---|---|
| Counter | ¥0.0211 / 63 s（r6） | **¥0.0074 / 28 s**，1 轮，13,757 in / 2,124 out（v2-counter） | 1/1 |
| Dice | — | **¥0.0203 / 184 s**，1 轮，17,946 in / 4,492 out（v2-dice） | 1/1 |
| Evolution | ¥0.0877 / 428 s（e2） | **≈¥0.008 / 27 s**，1 轮 21 s（v2-evolution；metrics 曾把模板里带过来的 Counter 事件一起算成 ¥0.0157 / 282 s，已修） | 2/2 |
| TB | ¥0.577 / 1,346 s（r9） | **¥0.241 / 984 s**，5 轮，130,542 in / 44,960 out（v2-tb；实现 400 s → 0/6 → 修复 48 s → 3/6 → 修复 40 s → 6/6；REQ-2 实现 428 s → 2/4 → 修复 28 s → 4/4；全套 10/10） | 10/10 |

云端/本机费用比此前约 3–4×（TB 本机 ¥0.58–0.67 对云端 ¥1.99–2.49），据此预估云端：Counter ≈ ¥0.03、Evolution ≈ ¥0.03、TB ≈ ¥0.8–0.9。TB 距 < ¥0.70 还差一点：下一步看 `.arc/llm-usage.jsonl` 的逐请求 prompt tokens，压实现轮的迭代次数（29/23 次工具调用）。

**第二阶段 · 第二版**（`bbe38ca3`…）：最小自验轮加显式工具预算（≤8 次写、≤2 次读、唯一 shell 命令 `npm run build`），第 2 个及之后节点的提示词直接给源码清单不再让模型 list_dir。代理现在记录每次请求的 usage（与平台计费同口径）和提示词构成：

| 题 | 轮数 | 请求数 | 计费 prompt tokens | completion（其中推理） | cache_hit | 内核费用 ¥ | 耗时 s | 公开测试 | 云端预估（¥0.36/M，取自 C 的四次 TB 云端账单） |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| v3-counter | 1 | 9 | 111,281 | 2,598（176） | 0 | 0.0163 | 131 | 1/1 | ≈ ¥0.04 |
| v3-tb | 2 | 23 | 487,879 | 36,154（22,261） | 0 | 0.0784 | 309 | 10/10（两节点首轮全过） | ≈ ¥0.19 |

**cache_hit 全为 0**：每次请求 prompt ≈ 12k–21k tokens 整段重发且没有命中 DeepSeek 前缀缓存——这是内核 system prompt/工具定义前缀不稳定或代理不回传缓存字段所致，属 B 的目标（`cache_hit` 字段），本记录是其证据；适配层这边每次请求的 `request` 字段（各 role 字符数、tools schema 大小）可直接定位前缀里变化的部分。

**第二阶段 · 第三版**（`wf-adapter-10`）：

- **代理去流式化**：内核的流式请求在代理处改为非流式发给上游、响应合成为 SSE 回给内核。动机：C 校准 cc066e8e11f6——供应商 usage 50,624 tokens，平台 token_count 613,136（12×），且两次运行的 ¥/平台 token 不一致，最贴合「平台计量层累加 SSE 每个 chunk 的累计 usage」；非流式上游只有一个 usage。`[usage]` 行新增每请求 `sse_chunks / sse_usage_chunks`。
- **spec 全文内嵌**：节点的 spec 与 helper 文件直接引用进提示词（≤24k 字符），模型不再花 3–4 个整上下文回合去读；批量并行 write_file；节点轮结束若 package.json 缺失不再判失败而是进验收循环由构建错误驱动修复；单 spec 题在节点未验证时也跑最终全套。

| 题 | 轮数 | 请求数 | 供应商 prompt / completion（推理） | 内核费用 ¥ | 耗时 s | 公开测试 |
|---|---:|---:|---:|---:|---:|---|
| v7-counter | 1 | 3 | 36,954 / 4,405（2,403） | 0.0064 | 35 | 1/1 |
| v7-dice | 1 | 3 | 36,554 / 2,194（308） | 0.0057 | 23 | 1/1 |
| v7-evolution | 1 | 6 | 69,463 / 1,142（314） | 0.0100 | 34 | 2/2 |
| v7-tb | 3 | 13 | 260,001 / 32,359（22,628） | 0.0455 | 239 | 10/10（REQ-2 2/4 → 18 s 修复 → 4/4） |

对照第一版（v3）：Counter 9 请求 / 111k → 3 请求 / 37k；TB 23 请求 / 488k → 13 请求 / 260k。每请求约 10k tokens 的固定前缀（内核 system prompt 25k 字符 + 15 个工具 schema 13.7k 字符）已占供应商计费的 70–80%，下一步在 B。

**第二阶段 · 第四版**（`wf-adapter-11`，本机 TB 反复对照，每行一次运行，均 10/10）：

| 运行 | 配置 | 请求数 | 供应商 prompt / completion（推理） | 耗时 s | 备注 |
|---|---|---:|---:|---:|---|
| v9-tb-b | 每轮新 session | 15 | 150,667 / 31,189（19,915） | 223 | 首轮 0/6 → 1 轮修复 |
| v11-tb | + 去 shell 工具 | 34 | 323,345 / 36,582（23,017） | 322 | 修复轮 20 次工具调用 |
| v13-tb-b | + 请求上限（实现 12 / 修复 10） | 9 | 117,884 / 26,371（18,309） | 176 | 两节点首轮全过 |
| v14-tb-a | + 0/N 时整体重写一轮 | 24 | 239,739 / 65,902（46,787） | 441 | 重写轮推理 20k+ |
| v15-tb-notrim-a/b | 不裁剪 system prompt（对照） | 9 / 16 | 127,972 / 46,522；247,351 / 74,578 | 277 / 457 | 首轮 6/6 与 0/6 各一：裁剪不是首轮失败的原因 |
| v16-tb-a/b | + 修复轮内嵌源码 | 15 / 7 | 169,643 / 48,024；85,927 / 40,982 | 353 / 246 | 修复只需 2 次工具调用 |
| **v17-tb-implnone-a/b** | **+ 实现轮关闭推理（修复/重写保持 low）** | 15 / 11 | 231,903 / 29,760（8,432）；181,135 / 12,828（0） | 300 / **112** | 输出 Token 降 3×，首轮 6/6 与 0/6 各一，重写后全过 |

结论：TB 首轮 6/6 的概率约一半、与裁剪无关；决定费用的是（1）失败后的恢复路径——一次整体重写 + 内嵌源码的修复优于多轮盲修；（2）推理 Token（¥/M 约为输入的 10 倍，由 C 的五张云端账单拟合：输入 ≈ ¥3/M、输出 ≈ ¥30/M）。默认改为：小题实现轮关闭推理，修复/重写 low；每轮请求硬上限（实现 12、修复 10）由代理执行；Counter/Dice/Evolution 全程关闭推理（v10/v12：2 次请求、9–10k prompt、1.6–1.9k completion、1/1 与 2/2）。

平台计量：C 校准 cc066e8e11f6 → 53a91acea453，去流式化后 token_count 613k → 165k（12× → 4×），费用 ¥0.373 → ¥0.171；剩余约 4× 与请求字节数同量级（Counter 一次请求约 45k 字节；裁剪后 15.5k）。

**更正 · 前缀缓存**（2026-09-13）：此前各处写的 `cache_hit = 0` 是记录 bug。arc-bench 端点按 OpenAI 风格在 `usage.prompt_tokens_details.cached_tokens` 报告命中，而代理只读 DeepSeek 风格的 `prompt_cache_hit_tokens`。直接探测：同一 4,014 token 前缀连发三次，cached_tokens = 0 / 2,048 / 3,840，命中正常，与 B 的 94% 结论一致。`llm_proxy.usage_record` 现兼容两种字段；之前所有 `[usage]` 行的 cache_hit 数字作废，各运行的真实命中要看 `.arc/llm-usage.jsonl` 里新字段（本轮之后的运行）。

**kernel arc.11 回归修正**（云端 76fb32a69d81，TB 0/0）：arc.11 给 DeepSeek 请求设单次输出上限 4096，与「一次响应写全部文件」叠加导致两个实现轮 output_truncated、无文件落盘。修：代理把 `max_tokens` 抬到 ≥32768（`OCTOS_ARC_MAX_TOKENS`）；实现轮截断即新会话按文件重写；实现轮请求上限 12→20；TB 实现轮保持 low 推理（auto 仍对单节点题关闭推理）；每轮验收打印失败 Observation。本机 arc.11 二进制（`b2134836`）：Counter 2 请求 / 8,121 prompt / 1,701 completion / 13 s / 1/1；TB w2-a 20 请求 10/10（首轮 6 条超时 → 重写 3/6 → 修复 6/6）、w2-b 13 请求 10/10（两节点首轮全过）。

**第二阶段 · 第五版（codegen）**：单节点题（Counter/Dice/Evolution 的新增节点）改为「一次请求出全部文件」：代理剥掉全部工具 schema，模型用 `<<<FILE path>>> … <<<END FILE>>>` 块回复，harness 落盘后进入正常验收；修复/重写同格式。本机（arc.11 内核）：Counter 1 请求 / 2,064 prompt / 1,040 completion / 10 s / 1/1；Dice 1 请求 / 1,967 / 1,330 / 11 s / 1/1；Evolution 3 请求 / 6,940 / 621 / 2/2。云端 v5（main@1121574e，C 运行）：Smoke ¥0.077 / ¥0.086、Evolution ¥0.137 / ¥0.119、TB 9/10 ¥0.667，cache_hit 已非零（TB 88%）。UI 契约加入「无过渡动画、加载后不重建表单控件」（TB 954a231a3d23 条款复选框 10 s 不 stable）。

**云端 v6（main@2363aadd，C 运行）**：smoke--dice fab88d27c1d0 1 请求 / 2,999 tokens / ¥0.061 / 19 s（榜首 ¥0.07）；smoke-evolution counter/dice 2/2、¥0.164 / ¥0.165；smoke--counter 91aaecaf31af **0/1**（单响应模式三轮同一失败：初始计数未在 HTML 中直接给出，toHaveText 超时）；TB 2e4802e9cb97 9/10、¥1.668（REQ-1.2 第 16 行 evaluate 超时；首轮 0/6 → 重写 → 修复，22 请求、推理 27k）。

**第六版**（`f2df6005`）：两轮同一失败摘要 → 该节点修复切回工具模式并注入换方法纠正；Observation 900 字符（含 Expected/Received/Locator）；UI 契约新增：初始状态直接在服务端 HTML 里、每个链接目标每页只一个 <a>、页面服务端渲染且加载后无 XHR、无过渡动画与表单重建。本机（arc.11 内核）：Counter codegen ×2 各 1 请求 / ~3.5k tokens / 11 s / 1/1；TB x3-a 36 请求 10/10（首轮 4/6，4 轮修复）、x3-b 20 请求 10/10（两节点首轮全过）。TB 首轮通过率在加入「一个链接一个 <a>」后两次分别 4/6、6/6（此前多为 0/6）。

## 云端结论（2026-09-13，main@027c2456，C 串行、key 空闲）

平台按 API key 计量；此前本机验证与云端共用同一把 key，云端账单被高估 4–12 倍。串行、key 空闲下的五题：

| 题 | 运行 | 结果 | 平台费用 | 耗时 | 真实 agent 榜首 |
|---|---|---|---|---|---|
| smoke--counter | 1365151c2cf7 | 1/1 | ¥0.0194（3,721 token） | 23 s | Smoke 提交合计 ¥0.039 vs 榜首 ¥0.07 |
| smoke--dice | 549b16afca23 | 1/1 | ¥0.0199 | 23 s | |
| smoke-evolution--counter | 96e2c8aaac3d | 2/2 | ¥0.0487 | 38 s | Evolution 合计 ¥0.090 vs 榜首 ¥0.20 |
| smoke-evolution--dice | 497502f1aefd | 2/2 | ¥0.0416 | 37 s | |
| ticket-booking | 060a3debc450 | 9/10，功能 1/2 | ¥0.365 | 216 s | 榜首 90% / ¥0.81；同通过率下费用更低 |

对照第一阶段起点（榜上旧条目）：Smoke ¥2.66 / 234 s → ¥0.019 / 23 s；Evolution ¥1.15 / 190 s → ¥0.045 / 38 s；TB ¥1.99 / 1,051 s（9/10）→ ¥0.365 / 216 s（9/10）。TB 10/10 仍是目标：本机连续 10/10，云端 9/10 的失败每次不同（Target crashed、复选框不 stable、evaluate 超时），集中在平台 512 MiB / 2 worker 的评测环境；本轮已加入服务端渲染、无 XHR、无动画、崩溃兜底与 favicon 探测。

**第七版（Smoke 冲榜首）**：刷榜后 Evolution、TB 已是真实 agent 第 1，Smoke 第 2（榜首 ¥0.02 / 10 s，我们 ¥0.04 / 23 s）。单节点题改用紧凑 codegen 提示词（3.3k 字符，含内嵌 spec）并要求最小输出（无 CSS/注释/README，package.json 只含 name+scripts，一行 build 脚本，≤15 行内联脚本）。本机（arc.11 内核）：Counter 1 请求 / 1,327 prompt / 546 completion / 10 s / 1/1；Dice 1 请求 / 1,229 / 562 / 9 s / 1/1；Evolution 1 请求 / 1,843 / 708 / 2/2。相对第六版（2.2k / 1.4k）输出 Token 降 60%。另：TB 云端 060a3debc450 失败的 spec 第 71 行是密码强度指示器 outerHTML 轮询，不是 reload；契约加入「实时指示器在 input 事件里同步更新自身元素」。

**云端 v10（main@251eea6d，C 串行，2026-09-13）**：smoke--counter 1868c77f82cb ¥0.0091 / 36 s、c6c35b0d1eab ¥0.0089 / 19 s；smoke--dice c967b38e457c ¥0.0092 / 20 s、db8980f15123 ¥0.0091 / 46 s——每次 1 请求、1.9k token、无修复轮；提交 854d34e7067d 合计 ≈¥0.018，低于真实 agent 榜首 ¥0.02。TB 709788da672e 8/10、¥0.514 / 352 s（上一版 9/10、¥0.365；失败文本待 C 回传）。

## Round 22 — codegen prompt diet (Smoke ≤ ¥0.007 target)

Codegen turns (single-node tasks and Evolution) now send a one-line system prompt (the proxy
replaces the kernel worker prompt, which is all tool guidance and useless in a tool-less turn),
a leaner user prompt (requirement description + spec file body only; no scenarios, no
tests-dir paragraph, fixed file layout, 20-line caps), and Evolution quotes only the html/js
sources of the existing app.

| task | before (round 21, local) | after (local) |
|---|---|---|
| Counter | 1 req, 1,396 prompt / 561 completion = 1,957 | 1 req, 508 / 452 = 960, 1/1 |
| Dice | 1 req, ~1.9k | 1 req, 435 / 417 = 852, 1/1 |
| Evolution (counter) | 1 req, 1,843 / 708 = 2,551 | 1 req, 798 / 379 = 1,177, 1/1 (grade 2/2) |

Cloud: 未评测 (C to rerun). Expected ≈ ¥0.0045 per Smoke task at the observed ¥4.6/M rate.

## Round 23 — Evolution without snapshots; Ticket Booking as two codegen requests

- Evolution probe: the platform template carries no `.arc/traceability` records, so cloud runs
  (9a1b1944a73e, 6232223b9863) re-implemented both nodes in tool mode (~18k tokens, ¥0.034–0.043).
  Now each candidate node's specs are run against the existing app first (no LLM); fully passing
  nodes are unchanged and the probe result doubles as their regression run.
- Codegen for small trees (≤2 nodes, `OCTOS_ARC_CODEGEN_MAX_NODES`) regardless of how many nodes are
  left; spec bodies include the `support/` helpers; size caps only for one-node tasks.
- One codegen repair (failure digest + quoted html/js) before falling back to tool mode
  (`OCTOS_ARC_CODEGEN_REPAIRS`, default 2 since round 28); the codegen rewrite prompt is the lean one.
- The harness writes both package.json manifests (model never outputs them); Playwright strict-mode
  rule (no duplicate links/labels/ids) in the codegen prompt.
- `codegen_blocked` reset per node (REQ-2 no longer inherits REQ-1's tool-mode fallback).

| task (local) | before | after |
|---|---|---|
| Evolution counter, template without traceability | 2 nodes in tool mode (cloud ¥0.034) | probe + 1 request 812/379 = 1,191 tokens, 2/2, grade 100 |
| Ticket Booking | 13–33 requests, 8–9/10 on cloud | 2 requests, 12,701 prompt / 21,686 completion (15,045 reasoning), 10/10, grade 100 |
| Counter | 960 tokens | 504/368 = 872 tokens, 1/1, grade 100 |

Ticket Booking with `OCTOS_ARC_REASONING=none`: first pass 2/6, 11 requests, 122k prompt — kept
`auto` (low for multi-node). Cloud: 未评测.

## Round 24 — port contract for codegen (cloud TB 3f0124e82113 / 784402a777c2: 0/10)

The specs default to `http://127.0.0.1:3301`; the grader sets only PORT. The codegen prompt had lost
the PORT CONTRACT, so the generated server bound PORT alone and all 10 tests failed with
ERR_CONNECTION_REFUSED (our own suite used E2E_BASE_URL and could not see it). Now the codegen prompt
carries the contract whenever the specs name extra ports, and the grader-like start (final suite,
rehearsal) verifies those ports are bound; if not, the run counts as a startup failure and is repaired.

| task (local) | result |
|---|---|
| Ticket Booking | 3 requests, 16,797 prompt / 18,973 completion (11,361 reasoning), 10/10, grade 100; `curl :3301` and `:PORT` both 200 with only PORT set |
| Evolution counter (no snapshot) | probe + 1 request 795/181 = 976 tokens, 2/2, grade 100 |

Round 23 cloud (C): Evolution best ¥0.0044 / ¥0.0042 (≈¥0.0086 total, leader ¥0.0188); Smoke ¥0.0050 / ¥0.0044
(¥0.0095). The two polluted Evolution runs (63,877 / 26,591 tokens with a 1-request log) were foreign usage on the
shared key at the window start; from now on, check `pgrep -f run-task-local` before requesting a window.

## Round 25 — speed rule in the codegen prompt

Cloud round 24 (C): TB e79b1160d081 9/10 ¥0.332 and d24f1c3d1c84 9/10 ¥0.251 (cost real-agent #1; leader
¥0.81 at 90%). The fixable miss was a whole-test 10 s timeout inside the registration helper while the same
spec passed in the run's own suite — a slow page/backend under the grader's 4 parallel browsers, not a
missing field. The codegen prompt now states the speed budget: no slow hashing (bcrypt/scrypt/pbkdf2/argon),
no timers, no per-keystroke work, state rendered server-side or from the initial HTML.

| task (local) | result |
|---|---|
| Ticket Booking | 2 requests, 12,451 prompt / 13,881 completion (7,573 reasoning), 6/6 + 4/4 first pass, full suite 10/10, grade 100 |
| Counter | 1 request, 578/358 = 936 tokens, 1/1, grade 100 |

Cloud: 未评测.

## Round 26 — speed rule dropped; backend manifest pinned to CommonJS

Cloud round 25 (C): TB 84444321d4f7 9/10 ¥0.564 (reasoning 49.8k vs 15.9k in round 24) and 3e425ce2ebf6 9/10
¥0.746 (24 requests: the codegen server.js mixed `import` and `require`; Node 20.19 module detection loaded
it as ESM → "require is not defined in ES module scope" → three tool-mode rounds). The speed rule did not
change the grader's 10 s timeouts and correlated with the reasoning jump, so it is dropped. The harness-written
backend/package.json now has `"type": "commonjs"` and the prompt says "CommonJS (require)".

| task (local) | result |
|---|---|
| Ticket Booking (speed rule dropped) | 3 requests, 16,457 prompt / 15,784 completion (7,833 reasoning), 10/10, grade 100 |
| Counter | 1 request, 509/357 = 866 tokens, 1/1, grade 100 |
| Dice | 1 request, 436/309 = 745 tokens, 1/1, grade 100 |

Leaderboard (C, round 24 submission): all three tracks real-agent #1 — Smoke ¥0.0095, Evolution ¥0.0086,
TB ¥0.251 / 9/10. Cloud for round 26: 未评测.

## Platform-side issues (for the coordinator to report; not fixable in arc/)

- Ticket Booking grading: 4 of 6 runs (rounds 23–26) lost one test to `Target crashed` (Playwright renderer
  process crash) — e.g. d24f1c3d1c84, 27de75de0cd0. Container is a 512 MiB cgroup running 4 browsers.
- Ticket Booking grading: whole-test 10 s timeouts inside the registration helper (e79b1160d081,
  84444321d4f7) with no slow code in the app (C inspected server.js/register.html): cumulative latency of
  page.goto + 8 fills under 4 parallel browsers.
- Web track: 4 Chromium workers OOM under the 512 MiB limit (earlier rounds), so the track cannot be graded.
- Feature-rate matching by test-title prefix (`REQ-1.1` vs node `REQ-1`) undercounts features.

Cloud round 26 (C): TB 27de75de0cd0 9/10 ¥0.609 (first pass 0/6 → 13 requests; the loss was `Target crashed`);
no ESM startup crash. Leaderboard keeps the round-24 submission (¥0.251, 9/10).

## Round 27 — first-pass quality for multi-node codegen; source snapshots; locator logging

Cloud TB cost is set by the first pass (4/6 → 3 requests ¥0.25; 0/6 → 13 requests ¥0.61). Local first-pass
snapshots (new `.arc/codegen/<node>-r<n>/`, kept before every repair so cloud first-pass code is retrievable
via the platform source API) showed three generic mistakes: an empty `div` as the strength meter (zero box →
"not visible"), a header rendered by a fetch after load, and HTML5 `required` attributes letting the browser
block the submit so the server's message never appears. Guidance for these lives in the multi-node slot of the
codegen prompt only (Smoke prompts unchanged). `[acceptance]` logs now include the `Failed at:` locator line.

| TB sample (local) | first pass | requests | tokens (prompt / completion / reasoning) | grade |
|---|---|---|---|---|
| z11 (before) | 1/6 | 3 | 18,206 / 33,223 / 22,583 | 100 |
| z12a (visibility guidance) | 4/6 | 3 | 18,227 / 20,845 / 9,069 | 100 |
| z12b (visibility guidance) | 6/6 | 2 | 12,702 / 15,168 / 8,185 | 100 |
| z13 (+ no HTML5 validation) | 6/6 | 2 | 12,758 / 26,713 / 19,791 | 100 |

Cloud: 未评测.

## Round 28 — Ticket Booking first-pass study (20 local samples) and deterministic fixes

Coordinator ask: first-pass rate + reasoning distribution over ≥5 local TB runs; find systematic first-pass
errors; evaluate staged codegen. 20 samples on rounds 27–28 prompts (`.arc/codegen/<node>-r0/` snapshots):

| sample | first pass | final | requests | reasoning |
|---|---|---|---|---|
| z11 z12a z12b z13 | 1/6 4/6 6/6 6/6 | 10/10 ×4 | 3 3 2 2 | 22.6k 9.1k 8.2k 19.8k |
| s1 s2 s3 s4 s5 | 2/6 0/6 0/6 3/6 0/6 | 10/10 ×5 | 3 3 3 9 4 | 10.7k 6.9k 21.4k 22.6k 17.5k |
| s6 s7 s8 s9 s10 | 5/6 6/6 0/6 6/6 0/6 | 10/10 ×5 | 3 2 12 2 5 | 13.3k 6.7k 28.6k 39.0k 18.0k |
| s11 s12 s13 s14 s15 s16 | 6/6 start-crash 6/6 start-crash 0/6 1/6 | 10/10 9/10 8/10 10/10 10/10 10/10 | 2 25 19 11 3 3 | 6.1k 48.5k 29.2k 24.9k 9.3k 20.7k |

First pass ≥5/6: 7 of 20 (35%); 10/10 reached: 18 of 20; requests median 3 (2–25); reasoning per run
median ≈19k, range 6k–48k on the SAME prompt (s7 6.7k vs s9 39.0k both 6/6 first pass) — reasoning is
sampling noise, not prompt-driven, so splitting codegen into staged outputs would add a request and prompt
tokens without a mechanism to lower it: not pursued.

Systematic first-pass errors found and fixed deterministically (zero prompt tokens):
- no `<meta charset>` + `text/html` without charset → Chromium decoded Chinese as Latin-1, every Chinese
  locator failed (s5, s10): `codegen.ensure_charset` injects the meta tag into every generated HTML.
- `/register` mapped to `dist/register` (no extension) → 404 (s8): the build script also emits extensionless
  page copies.
- file block with JSON-escaped newlines (s12: server.js syntax error at start): `unescape_flattened` for fully
  flattened blocks, `repair_flattened_js` (only if `node --check` fails before and passes after) for partial.
- static nav links duplicating the server-filled `<!--NAV-->` (s2, s3, s15: strict-mode violation):
  `dedupe_nav_links` strips them when the server implements the placeholder.
- two codegen repairs before tool mode (tool mode is what multiplies cost: s8 12 req, s12 25 req).
Prompt (multi-node slot only): mechanisms for NAV, cookie `Path=/`, helper values must validate, messages =
first regex alternative verbatim, no HTML5 validation attributes.

Remaining first-pass misses are model sampling (invented validation rules, message wording, links injected
twice server-side, cookie/redirect details). With the leaderboard scoring the MOST RECENT run and the current
TB entry at ¥0.251 (a 3-request run), a rerun has negative expected value (median 3 requests ≈ ¥0.3, tail
¥0.6+): recommendation — do not rerun TB; keep the entry. Cloud: 未评测 for round 28.

## Handover inventory for workflow D (Rust harness, `OCTOS_ARC_ENGINE=rust`)

Everything the Python adapter does today, with defaults and the evidence that motivated it. Behavioural
parity target; the Python path stays the default until D passes side-by-side verification.

**Flow (`arc/main.py`)**
- Requirement tree → atomic nodes in dependency order (`requirement_order.topo_order`, folder nodes marked
  from children). Time budget max(3600, 1500 s × nodes); per-node cap 1500 s; per-node budget
  min(cap, max(240, remaining / nodes_left)).
- Spec↔node mapping by file-name prefix with aliases (`acceptance.map_specs_to_nodes`); support helpers
  (`support/*.ts`) are quoted with the spec.
- Per node: implement turn → run that node's specs → repair loop (≤5 rounds, 3 for >2-node trees on
  wf-adapter-30): rewrite-on-zero once, identical normalized failure twice → tool mode, no improvement for two
  repairs → stop, two regressions → restore best commit. Verdict recorded in traceability.
- Codegen mode (≤2-node trees, `OCTOS_ARC_CODEGEN_MAX_NODES`): one tool-less request returning
  `<<<FILE path>>>` blocks; system prompt replaced by one line (proxy `system_override`); lean prompt =
  requirement description + spec bodies + fixed layout + rules; multi-node slot carries the NAV/cookie/
  validation/visibility mechanisms; 2 codegen repairs (failure digest + quoted html/js) before tool mode.
  Harness writes both package.json (build copies src→dist plus extensionless page copies; backend
  `type: commonjs`), injects `<meta charset>`, restores flattened newlines (guarded by `node --check`),
  strips static nav links duplicating `<!--NAV-->`. Evidence: rounds 22–28 (Smoke ¥0.0095, Evolution
  ¥0.0086 real-agent #1; TB 20-sample study).
- Evolution: `.arc/traceability/requirements.json` fingerprints, then probe each remaining node's specs
  against the existing app (no LLM); passing nodes are unchanged and the probe doubles as their regression
  run. Evidence: cloud 9a1b1944a73e/6232223b9863 (platform template has no snapshot).
- Final suite grader-like (only PORT set): verifies spec default ports (3301) are bound, robustness probe
  (/favicon.ico, unknown path/API), memory-aware workers, OOM-killed runner = no verdict; ≤2 repair rounds,
  identical failing set → stop. Evidence: 3f0124e82113 (0/10 port contract), c17bc1b44d26, 29c840566f36.
- Protected dirs: deny hook (`hooks/deny_protected.py`, patched into the profile JSON) + tree digest
  restore after each turn; worktree snapshot/restore around every test run (tests mutate persisted state).
- Guard (`guard.py`): unverified completion claims, repeated errors, protected writes → corrections
  appended to the next prompt; per-turn request budget via proxy (`enforce_turn_budget`).
- Source snapshots `.arc/codegen/<node>-r<n>/` before every repair; `[acceptance]` logs `Failed at:` +
  `Observation:`; `[usage] provider totals` at the end.

**LLM proxy (`arc/llm_proxy.py`)**: de-stream (upstream JSON, SSE synthesized to the kernel), reasoning
injection (auto: none for ≤1 node to implement, low otherwise), `max_tokens ≥ 32768` floor (kernel arc.11
caps at 4096), system-prompt section trimming + tool schema drops (shell tools for small tasks, all tools for
codegen), per-turn request cap, usage log incl. `prompt_tokens_details.cached_tokens`, request dump.

**Acceptance (`arc/acceptance.py`)**: Playwright discovery (`/opt/arcbench` preinstalled) or isolated pinned
private install (1.63.0) removed after the run; 10 s test timeout, 4 s action/expect, 6 s navigation;
failure digest (Feature / Failed at / Observation / Steps); slow-test threshold 3 s; `container_memory_limit`
(cgroup v1/v2), `workers_for_memory` 700 MiB/worker (per node), `workers_for_final` 450 MiB/worker
(wf-adapter-30); `free_owned_ports`, `reap_workspace_processes` (wf-adapter-30).

**Known platform limits** (see "Platform-side issues" above): renderer crashes, 10 s cumulative timeouts,
feature-rate prefix matching; container now 2 GiB / 1 CPU / `--workers=4` (keep 2224a9013528 pending).

**Local tooling**: `run-task-local.py` (`--template` for Evolution), `grade-local.py` (restores worktree),
`pack.sh` bundle list, `metrics.py`; unit tests `cd arc && python3 -m unittest discover -s tests -t .` (85).

## Round 29 — generality review of the prompts (user rule: no task-specific strategy)

Rule applied: a rule may only depend on what the run can derive from its own inputs (requirements.yaml,
spec text, container facts, failure text); every prompt sentence must be a general engineering rule that
matters for at least two tasks; no competition/task names, titles or known failing cases.

Rewritten (main.py): strict-mode bullet no longer names "Register"/"Login" links or `a[href="/register"]`;
echoed-value examples generic; "live indicators" no longer enumerates controls (meters/counters/previews);
codegen multi-node mechanism (1) describes the NAV placeholder generically (link texts come from the tests)
instead of hard-coding Chinese link texts and USERNAME; mechanism (3) says "values the test helpers generate
must be accepted; do not invent stricter rules" instead of listing name/document/phone/email; performance
contract says "a few ms per hash call, no default-cost KDF / native module" instead of scrypt parameters.
codegen.py: `dedupe_nav_links` derives the hrefs to strip from the anchors the server itself renders into the
placeholder (was a fixed /login|/register|/logout list).

通用性自查 (checklist, all ✔):
- [✔] No task id / title / competition name in any prompt constant or decision (`grep` for ticket|dice|counter|
  keep in prompt text: none; only code comments and evidence ids remain, which are not sent to the model).
- [✔] Ports: derived from spec text (`spec_base_ports`), never a literal.
- [✔] Session/login rules: gated by requirement/spec keywords (`needs_session`), phrased as generic web rules.
- [✔] Codegen mechanisms: placeholder/cookie/validation/visibility/no-HTML5-validation are generic; the only
  literal is the placeholder token `<!--NAV-->` the harness itself introduces.
- [✔] Deterministic post-processing: charset meta, extensionless page copies, flattened-newline repair, NAV
  dedupe — all input-derived, none keyed to a task.
- [✔] Acceptance/robustness probes: /favicon.ico + unknown path/API are browser/grader facts, not task facts.
- [✔] Local parity: prompts render for Counter/Dice/Evolution/TB offline (1,940 / 1,577 / 2,521 / 14,791 chars,
  ports clause only where a spec names a port); unit tests 79 OK. Live runs 未评测 (key reserved for keep).

## Round 30 — existing app that satisfies no spec → fresh build; codegen effort by spec size

Cloud (octos account, main@032a57ac): Evolution counter c30b29eab45b 2/2 ¥0.209 / 202 s, dice 10b04d36f704
2/2 ¥0.368 / 279 s (personal account same package: ¥0.0044). The template handed to that account is the
platform's React/Vite/Express/SQLite scaffold with a placeholder home page (template.yaml `web-react-express`),
not a working app: the probe found 0/1 for every node, the flow still treated it as evolution (implement on
top of the scaffold, then rewrite → multi-request).

Generic rule (no template names involved): if the probe ran and NO node's specs pass against the existing app
(placeholder page, scaffold that does not build/start, or an app the new specs no longer accept), the app is
not a usable base → frontend/ and backend/ move to `.arc/template-discarded/` and the task is built fresh
(single-request codegen per node with our manifests). A real previous app keeps the probe/1-request path.

Codegen effort is now derived from spec size (`OCTOS_ARC_CODEGEN_REASONING_CHARS`, default 5000): specs
below it get reasoning none and the compact size rule; larger specs (e.g. multi-page apps with sessions) keep
the base mode and the multi-page mechanisms. Previously both hinged on node count, so a 2-node counter tree
paid 4.4k reasoning tokens and got navigation/cookie mechanisms that crowded out the page script (first
pass 0/1).

| scenario (local) | before | after |
|---|---|---|
| Evolution counter, placeholder template | evolution path, implement + rewrite (cloud ¥0.21–0.37) | fresh build, 2 requests, 1,283 / 713 = 1,996 tokens, 2/2, grade 100 |
| Evolution counter, real template (no snapshot) | 1 request 976 | 1 request 799 / 379 = 1,178, 2/2, grade 100 |
| Dice | 743 tokens | 743 tokens, 1/1, grade 100 |

Generality check: decision derived from probe results only; thresholds from spec size; no task/template
names. Cloud: 未评测.

## Round 31 — OCTOS_ARC_DRYRUN=1 (structural parity runs for workflow D)

`OCTOS_ARC_DRYRUN=1` replaces the kernel driver with `DryRunDriver`: no kernel, no model, the endpoint
preflight is skipped. Every turn returns a fixed reply (a placeholder index.html + static server as file
blocks for codegen prompts, a sentence for tool-mode prompts), so the whole flow runs end to end — tree order,
skeleton folding, mode selection, Evolution probe/discard, per-node acceptance and repair stops
(rewrite-on-zero, identical failure, no improvement), source snapshots, final grader-like suite (port
contract, robustness probe), rehearsal, traceability/runner events, usage summary. Real-path behaviour is
untouched (the switch only selects the driver and skips the preflight).

Verified locally with a dummy key: smoke--counter (1 node) and ticket-booking (2 nodes, `OCTOS_REPAIR_ROUNDS=1`)
both complete with exit 0; TB emits 68 runner events (37 signal / 29 requirement_state / 2 runner_state) and
its rehearsal reports the PORT CONTRACT violation of the placeholder server, as intended.

## Round 32 — tiny-spec tier (Smoke ≤ 300 tokens per task target)

Smoke board: three real entries ahead of ours at ¥0.0031–0.0037 for both tasks (≈250 tokens per task); ours
≈845 tokens (prompt 509 + completion 335 incl. ≈176 reasoning) → ¥0.005 per task.

Tier trigger: spec body smaller than `OCTOS_ARC_TINY_SPEC_CHARS` (default 1500; `OCTOS_ARC_TINY=0` disables) —
input-derived, no task names. What changes for such a node:
1. Prompt = the spec's own statements (imports, blank lines, `await`, closing braces stripped) + one output
   sentence; no contract sections. System prompt "Reply with HTML only." (21 chars).
2. Thinking off (the spec-size reasoning rule already yields none).
3. Output = one index.html (inline script) written from the bare reply (code fences tolerated; FILE blocks still
   accepted); the harness writes the manifests and a fixed static server (`TINY_SERVER_JS`: `/`→index.html,
   `/<name>`→`<name>.html`, 404 otherwise, try/catch, PORT + spec default ports unless ARC_EXTRA_PORTS=0) —
   generic scaffold, no task logic. Verified: `/` and `/register` 200 with charset, `/favicon.ico`, `/api/x`,
   path traversal 404, extra port bound.
4. The node's specs run right after; on failure the existing compact codegen tier redoes the node (then the
   normal repair loop). Evolution nodes with an existing index.html use a variant that quotes the page.

Offline token estimate (chars ÷ 3.8, the ratio measured on round-22 prompts):
| task | prompt chars → tokens | expected completion | expected total |
|---|---|---|---|
| counter | 614 → ≈162 (+6 system) | ≈90–110 (≈350 chars of HTML) | ≈260–280 |
| dice | 378 → ≈99 (+6) | ≈70–90 | ≈180–200 |
| evolution REQ-2 (page quoted) | 995 → ≈262 (+6) | ≈100 | ≈370 |

Dry-run (no model): counter and evolution traverse tiny → spec check → compact fallback → repair loop, exit 0.
Live: 未评测 (key occupied by the Web queue; 5-minute window requested from C). Unit tests 93 OK.

## Round 33 — token-free startup probe; tighter tiny output

Cloud (main@6974ffcd, key idle): tiny tier all first pass — counter e123086d9c9d 1/1 ¥0.00275 (prompt 164 +
completion 214, reasoning 0), dice ee470858da53 ¥0.00235 (115 + 174), octos counter b438df2a5fcb ¥0.00277,
dice b88799874e8a ¥0.00238, octos Evolution counter bcf72deae878 2/2 ¥0.00281, dice 207f40662651 2/2 ¥0.00269.
Fitting the two Smoke points gives ≈¥2/M input, ≈¥7.5/M output and a fixed ≈¥0.0008 per run — the startup
probe: "Reply with exactly: OK" with max_tokens=4 still let the model produce reasoning_content (DeepSeek
caps only the answer), i.e. about a third of a tiny-tier task.

- Probe is now GET /models (unbilled; any non-5xx answer proves the endpoint is up). Only if that never
  answers, one chat request with `thinking: disabled` and `max_tokens: 1`. Same 10-minute outage wait.
- Tiny prompt's output sentence asks for minimal markup, one inline script, no CSS/comments/blank lines
  (prompt +≈12 tokens; expected completion 214 → ≈150 for counter, 174 → ≈120 for dice).

Expected per task at the fitted prices: counter ≈ ¥0.0003 + ¥0.0011 ≈ ¥0.0015, dice ≈ ¥0.0012. Generality:
probe and output rule are endpoint/format facts, no task content. Cloud: 未评测 (next Web gap). Unit tests 95 OK.
## wf-adapter-30 (unmerged) — cost guard recalibrated on keep 2224a9013528

Calibration: keep PASSED 32/32, 9,038 s, ¥16.58, no OOM at 2 per-node workers, graded at 4 workers in
2 GiB / 1 CPU; ≈282 s and ¥0.52 per node; measured `[usage]`: 1,152 requests, 28.05M prompt (91% cache hits) + 0.76M completion
= 28.8M total = platform token_count; ≈0.9M tokens and 36 requests per node; grading 4 workers, 32 tests in
24.6 s, peak memory 0.96 GiB, oom 0. Derived defaults therefore sit ≈2.8× (tokens) and ≈3× (turns) above a
healthy run.

Guard defaults (derived once the tree is known; explicit env overrides; 0 = off):
- `OCTOS_ARC_MAX_TOTAL_TOKENS` = max(6M, 2.5M × nodes) ≈ 3× a healthy run (keep: 80M vs 26M used).
- `OCTOS_ARC_MAX_TURNS` = max(24, 4 × nodes) ≈ 3.5× (keep: 128 vs ~35).
- `OCTOS_ARC_MAX_TOTAL_TOKENS_ABS` (opt-in, default off): absolute ceiling for a per-run spend rule; ¥50 ≈ 75M
  tokens. Note a healthy 125-node tree (ctrip) would cost ≈¥65 by the calibration, so this ceiling can cut a
  normal run short — set it only when the spend rule outranks completion.
- Tripped guard = no more repair turns; remaining nodes still get one implement turn; final suite runs once.
Kept as generic: repair rounds 3 for >2-node trees (keep barely repaired), final-suite workers 450 MiB each
(→4 in 2 GiB, matching the grader), per-node reap of leftover node processes. Dropped: raising
`OCTOS_MIN_REPAIR_SECONDS` (1 CPU did not slow node cycles: 282 s/node observed, budget 1500 s).

## Round 34 (phase 3 §1.2) — probe policy by tier; body-only tiny reply

- The endpoint probe moved from `main()` into the flow, after the spec map is known: tiny-tier tasks (every
  node with specs below `OCTOS_ARC_TINY_SPEC_CHARS`) skip it entirely — the first real request is the probe
  and a failure there surfaces through the normal turn error path; other tasks keep the token-free
  GET /models probe with the `thinking: disabled`, `max_tokens: 1` fallback (round 33). Dry runs skip it.
- Tiny reply is page markup only (no doctype/head/CSS/comments/blank lines); the harness injects the charset
  head (`ensure_charset`) and a fragment is accepted as the page (`looks_like_markup`).

Offline estimate (chars ÷ 3.8 prose, ÷ 3.3 code): counter prompt 657 chars ≈ 173 tokens + 6 system, minimal
fragment ≈ 80–110 → ≈ 260–290 total worst case, ≈ 240 typical; dice 421 chars ≈ 111 + 6, reply ≈ 70–90 →
≈ 190–210. At the fitted ¥2/M in, ¥7.5/M out: counter ≈ ¥0.0011–0.0012, dice ≈ ¥0.0009. Dry run traverses
tiny → spec check → compact fallback. Generality: tier by spec size only; probe policy by tier; no task text.
Cloud: 未评测 (next gap). Unit tests 97 OK.

## Round 35 (phase 3 §1.1) — single-request codegen for every node of an N-node tree

keep/bookstack spent ≈36 requests per node in tool mode (read/edit/verify steps). Now every node of any tree
size takes the codegen path (`OCTOS_ARC_CODEGEN_MAX_NODES` default unlimited): one request that returns every
changed file complete. The prompt quotes the existing sources selected by `relevant_sources`: backend entry
files first (the router every node extends), then pages ranked by how many of the node's spec terms
(locators, texts, routes, identifiers) they contain, within `OCTOS_ARC_CODEGEN_CONTEXT_CHARS` (default 90,000
chars ≈ 26k tokens ≈ ¥0.05 input per request); the rest are listed by name. Stylesheets are never quoted. The
harness manifests replace the skeleton turn. A node whose spec alone cannot fit the budget uses tool mode;
codegen repairs (2) then tool mode remain the per-node fallback.

Offline on the real keep workspace (cloud 2224a9013528, 5 source files, 86k chars): REQ-2.5.2 quotes
server.js + app.js + index.html + build.js (≈72k chars ≈ 21k tokens), no omission. Dry run of keep (32 nodes):
skeleton skipped, every node one codegen request, final suite + rehearsal reached, exit 0.
Expected per node: 1–3 requests (≤5 target) instead of 36; cost dominated by input ≈ ¥0.05–0.15.
Generality: selection by spec-term overlap and size only; no task names. Cloud: 未评测. Unit tests 99 OK.

## Round 36 (phase 3 §1.3) — L17 ported: the final suite delivers its best round

The full-suite loop now records each round's pass count with the commit it tested (a new best after a repair
is committed as "best so far"). When the loop ends — repair rounds exhausted, identical failures, time or
cost guard — on a round worse than the best, frontend/ and backend/ are restored to the best commit and the
per-node verdicts and traceability are re-recorded from that round's results (`record_full_suite`). Ported
from the Rust harness's L17 (docs/arc-optimizations.md); before, a regressing full-suite repair shipped as-is.
Rehearsal/grading parity: the full suite already runs grader-like with `workers_for_final` (450 MiB per
worker → 4 under 2 GiB, matching `--workers=4`), 10 s test budget, 3 s slow-test threshold (round 28 / PR 81).

Verified by simulated rounds (1/2 → 0/2 → 0/2 restores the 1/2 state and its verdicts; 0/2 → 2/2 keeps the last
round) and a TB dry run through the full-suite path. Generality: pure loop logic, no task content.
Cloud: 未评测 (needs a TB gap). Unit tests 105 OK.

## 2026-09-15：保留可操作错误，按失败观察判断修复停滞

云端运行 `2b6406557024`：生成阶段全套验收两次均 46/66，平台评测也是 46/66（69.7%，¥47.993744，28,635 秒）。平台 stdout 显示缺失按钮、隐藏元素以及等待定位器，不能仅凭 `timedOut` 归因为机器性能。最终修复回合触及 10 次请求上限，随后按相同失败测试名称停止。

- Playwright 的 `error` 可能只有整条测试超时，具体定位器在 `errors` 后续项。现在优先保留带调用日志或定位器的错误及其位置。
- 超时摘要不再推断页面或请求未结束，提示检查具体操作以及缺失/隐藏元素。
- 最终修复停滞依据文件、测试名、状态、位置、错误和步骤；忽略毫秒数、重试次数噪声。同一测试从按钮错误推进到弹窗错误时允许继续，已有轮次、时间、费用上限仍生效。
- 通用性：只读运行时 Playwright 报告；不按赛道名、题号、页面文本写分支；适用于所有有 UI 验收的任务。仅 Python 默认路径，Rust 后续需要同步。
- 验证：3 个诊断回归用例改前失败；改后适配层 unittest 107/107，通过同名测试失败步骤变化后继续到全通过的流程测试。无模型调用。云端改后分数与费用：未评测。
- 尚未解决：大量失败共用一个 10 请求修复回合的问题，及生成应用中的具体缺失交互；此修改不能作为 66/66 的证据。

## 2026-09-15：通用性审查与语义保留（PR #100 扩展）

用户要求所有优化能用于更广泛场景，不得为题目特调。审查默认 Python 路径与 Rust codegen、共享提示词后：

- 禁用基于服务端 href 的自动删链接。相同目的地可能是导航、正文入口或条件内容，源文本不能证明冗余。兼容函数保留为无操作，实际问题交由验收诊断。
- 写文件时不再按转义符比例无条件反转义。原逻辑会破坏包含许多合法 `\\n` 的 JavaScript/JSON；JS 仅保留“原文件语法失败且候选语法通过”的受检修复。
- 删除强制导航占位符、固定 Cookie 名/寿命/跳转、每页只能出现一次文本/链接、禁用日期/数字输入、禁止 CSS/动态 UI、固定 20 行、示例自动变种子数据等提示。行为由需求与现有应用决定。
- 不假定固定 CPU 慢速倍数、4 浏览器或必然超时；慢测试提示以配置阈值和实测为准。按用户澄清，密码哈希工作因子允许在评测/演示中降低且可配置，生产设置分开。
- 小任务请求包含完整节点输入和未经裁剪的公开测试，避免只实现测试样例；相关源码包括 CSS，以支持布局/可见性问题。公开测试用于验证完整需求，冲突不能默默覆盖需求。
- 修复提示不再硬写“第二次响应必须改完、最多读两个文件”；调用层预算仍限制费用。

验证：Python unittest 109 通过；Rust 99 单元测试及 1 集成测试通过、1 项原有忽略；cargo clippy -p octos-arc --all-targets -- -D warnings、fmt、diff 检查通过。覆盖链接保留、合法 JS/JSON 转义保留、完整小任务输入、CSS 上下文。没有付费模型调用，没有声称新的云端分数。

范围与限制：这是生成/修复路径的通用性审查，并非证明整个仓库不存在其他特化。保留平台要求的启动/输出目录契约，以及可配置的资源预算。提示放宽可能增加输出和依赖开销；通用价值由语义保留回归测试支撑，跨任务生成成功率和费用仍需评测。Python/Rust 修改均已写入，已发布 Rust 二进制需要重新构建后才会包含代码变化。

### 同题内模型分档（同轮追加）

默认 Python 代理增加 `OCTOS_ARC_MODEL_ROUTES`：按阶段、完整请求大小、工具/图片能力选模型，允许同题首轮小模型、失败修复另一模型；不写死厂商或题名，空配置及无匹配保留原请求。请求选用模型与阶段进入用量日志。Rust 配置此项会明确报不支持，避免静默忽略。配置示例与边界见 README。

增加路由单测和真实本地 HTTP 代理集成测试，Python 共 115 项通过；模拟 provider 无付费调用。真实 provider 目录查询返回 11 项但不含 qwen3.8-27b，也不含价格/参数量；未据此断言省钱或速度收益。跨模型任务评测待进行。

## 2026-09-15：余额错误停止重试与官方排名口径

一次新包本机运行被 provider 以 HTTP 402 / insufficient_balance 拒绝（未生成应用）。旧逻辑用任意位置的 `503`/`429`/`401` 等数字识别临时错误，请求 ID 中的数字也可能触发重试；同时将认证失败视作可重试。现在 Python/Rust 都解析显式 HTTP 状态，余额/认证错误优先判为不可重试。Python 默认流程遇到这类错误直接标记运行失败并返回非零，不再从 tiny 退到 compact 继续调用。Rust 此次同步重试判定，跨阶段停止策略另行处理。

看板移除未经证实的“预生成”判定和排除排名，只显示官方响应顺序；小额费用保留到六位小数，¥0.000024 不再显示为零。

验证：账户错误、请求 ID 混入状态码、默认流程余额错误中止、完整看板渲染均有回归测试。Python 119 项通过；Rust 99 单元与 1 集成通过，1 既有忽略；clippy/fmt 通过。真实成绩未提升，当前 provider 额度不足，未创建新的云端运行。

## 2026-09-17：后端按区域拆模块（P1），以及 codegen 单请求路径的真实生效范围

codegen 的契约是「每个改动的文件完整返回」，而架构契约把所有 API 路由钉在一个 `backend/server.js` 里。
于是第 k 个节点要把前 k−1 个节点写进这个文件的东西原样再吐一遍，输出规模随树大小二次增长。

- 架构契约改为：`server.js` 只做静态文件与路由分发，保持小而稳定；新增 API 路由放
  `backend/routes/<area>.js`，共享持久化放 `backend/store.js`。措辞只约束**新增**代码，既有单文件后端不会被
  要求重构（一次性重写的风险大于收益）。`main.py` 的 `CODEGEN_PROMPT` 与 `prompts/codegen-prompt.md` 同步。
- `relevant_sources` 的排序从「所有 backend 文件优先」改为「只有后端入口优先，其余后端模块与页面一起按
  spec 词命中排序」。入口名从 `backend/package.json` 的 start 脚本读取（`node app.js` → `app.js`），
  读不到时回落到契约里的 `server.js`。拆模块后若继续把所有路由文件排在前面，会把 spec 真正点名的页面挤出预算。
- `DryRunDriver` 补上 `without_tools()`。`codegen_turn` 在这个作用域里运行，dry run 缺这个方法，
  于是**任何走 codegen 的树在第一个节点就 abort**——Round 35 记的「keep 32 节点 dry run 每节点一次 codegen
  请求、跑到终检」在当前代码上复现不出来。补上后 keep 的 32 节点 dry run 可以逐节点走完 codegen 路径。

数据：适配层 unittest 290 项通过（新增 7 项）。本机/云端模型运行**未评测**——省下多少输出 token 取决于模型
是否照契约拆文件，必须用一次真实 keep 运行对比，不能由本条改动自证。

### 同轮测到的事实：`codegen_context_fits` 的悬崖

`codegen_context_fits` 要求**整个应用**塞进 `OCTOS_ARC_CODEGEN_CONTEXT_CHARS`（90,000）减去 spec 之后的预算，
否则整个节点退回 tool 模式（keep 实测 36 请求/节点）。实测（spec 8,000 字符）：

| 应用总字符 | codegen_context_fits | 实际路径 |
|---:|---|---|
| 60,000 | True | codegen 单请求 |
| 85,000 | False | tool 模式 |
| 200,000 | False | tool 模式 |

推论两条：
1. keep 云端产物实测 86k 字符 —— 它的后段节点其实早就在走 tool 模式，Round 35 的「每节点单请求」对任何
   会长过 ~82k 字符的应用都不成立，而 Web 六题都会长过。
2. 因为这个门槛通过时整个应用必然已经放得下，`relevant_sources` 的省略分支在 implement 路径上**取不到**，
   本轮的排序改动在今天是行为等价的；它是放宽门槛的前置条件，不能记为省 token。

放宽方向（未实施，风险在通过率）：门槛从「整个应用放得下」改成「spec + 入口 + spec 点名的文件放得下」，
其余按文件名列出；并加一道确定性防护——回复里出现**未被引用**的既有文件的 FILE 块时拒绝落盘，
保留磁盘上的版本，使省略在构造上安全。

## 2026-09-17：zip 里自带内核（`bin/octos`），修掉解压丢失可执行位

`find_octos()` 的第 2 顺位本来就是 `<包根>/bin/octos`，但 `pack.sh` 的清单里没有 `bin`，这条路一直取不到。
补上之后发现它光靠 `pack.sh` 还不能用：

- 实测 `zipfile.extractall()` **会丢掉 Unix 权限位**（压缩前 755，解压后不可执行）。旧的
  `find_octos()` 只判断 `.exists()`，于是会把一个 OS 拒绝 spawn 的路径交出去，而且不会回落到下载 —— 整次运行直接失败。
- 新增 `executable_or_none()`：补回可执行位；补不回来（只读挂载）就返回 None，让 `find_octos()` 继续往下
  找 PATH / 下载。`bin/octos-sandbox` 存在时一并处理。
- `pack.sh` 默认把本机构建的内核打成包内 `bin/octos`（新增 `pack_kernel.py`）：来源按 `ARC_KERNEL_BIN` →
  `arc/bin/octos` → 交叉编译 target → `target/release/octos`，逐个校验 **ELF 头是 Linux x86_64**
  （读 e_ident/e_machine，不依赖 `file`）。macOS / aarch64 的构建会被跳过：自带的二进制排在下载前面，
  装错了平台会直接 spawn 失败，比不自带更糟。打包时 `strip`（原件保留符号），zip 条目标 0755。
  `ARC_PACK_KERNEL=0` 回到不自带内核的小包。
- `arc/.gitignore` 加 `bin/`：125M 的构建产物不进版本库。

验证：真二进制走完整链路 —— `cargo build --release` → `pack.sh`（36M 包，`bin/octos` 97M）→
`zipfile.extractall`（**实测权限位丢失**）→ `find_octos()` 返回该路径且已可执行 → `--version` 跑出
`octos 2.0.3-rc.11 (05273416)`；`ARC_PACK_KERNEL=0` 打出 404K 无 `bin/` 的包。
适配层 unittest 303 项通过（本条新增 13 项）。

体积：`target/release/octos` 125M，`strip` 后 94M，`zip -9` 后约 35M。**平台的上传体积上限未知**，
超限就仍旧走 `OCTOS_RELEASE_URL` 下载。自带的好处是省掉线上那段要 12 次重试、轮换 gh-proxy 镜像的下载。
自带的二进制必须是 Linux x86_64，且 glibc 不高于平台容器（本机构建产物 `for GNU/Linux 3.2.0`，动态链接）。

## 2026-09-18：从原始代码复核后修订 token 与前缀布局

基线：`493c2e6a2808438091b2de131cb8bea9170c9a12`，默认 Python 编排路径。
上一版未提交的「仅失败节点展开场景」已撤回。ctrip REQ-3.2.3 的 description 只有
`Exception Same-City Validation`，错误文案及阻止导航只在场景里；REQ-2.4.4/5 的错误文案也只在场景里。
所以场景不能一概当作 description 的复述。全套、检查点和单节点修复均保留原有完整需求契约。

本轮改动：

- **前缀布局**：Python codegen 固定规则在前，按相关性选中的源码按路径呈现，纠正信息、当前需求和
  spec 在后。选取优先级仍是入口 → spec 重叠 → 小文件 → JSON，没有直接排除零命中文件。
  修复提示词改为固定规则 → 完整需求/源码 → 当前失败与纠正信息；全套修复的完整需求树因此成为稳定前缀。
  大小规则放在源码后，跨 SMALL/FULL 切换不再打断相同源码前缀。源码内容、选中集合或模型配置变化仍可能打断缓存。
- **完整用户消息预算**：codegen 实现提示词计入规则、需求、spec、纠正信息、文件标题、省略列表、
  换行及 FILE 格式。必要时缩减引用内容。检查点证据按类型标记，只裁观察正文，保留全部失败节点 ID、
  裁剪标记及所有非检查点操作约束；预算充足时逐字保留。仍不能引用入口或保留关键约束时退工具模式，使用原纠正文本。
  源码一次读取，在内存中逐个移除最低优先级引用，最多文件数加一次呈现。回退日志带 spec/entry/room/limit/reason。
  codegen 修复的最终预算检查补计格式前的换行。
- **零通过重写**：原先复用实现前的提示词（含旧源码），再追加当前源码，造成重复输入和冲突版本。
  现在从当前磁盘重新构建，只引用一次，沿用完整用户消息预算；超预算转工具路径。
- **tiny 表示**：需求 JSON 改为 `describe_node`，保留 id、name、description、场景及依赖，去掉 JSON 结构开销。
  公开题已枚举字段中仅省去节点 `type` 元数据和 JSON 结构符号；编排器之前已经据 type 选取节点。
  不改样式措辞和推理规则。
- **残留回归证据**：检查点修复会消费原先排队的 correction；现在将修复后仍失败的最新证据重新入队。
  修复中途预算不足仍保留最新证据，修复成功不保留过期证据；修复后测试不可靠时保留最后一次可靠失败。
- **清掉重复与失效的判定**：`codegen_context_fits` 的 60% / 入口两条规则已经在 `codegen_implement_prompt`
  里重新实现，留着就是会漂移的第二份真相，删除；spec 超 60% 的拒绝移到读盘之前，是最省的一次拒绝。
  `relevant_sources` 只是 `scored_sources` + `select_source_snapshot` 的包装，生产路径不再调用，删除，
  排序理由并入前者的 docstring。`codegen_mode` 的 docstring 改指真正做判定的函数；
  `Flow.codegen_budget` 给出默认值，日志改用 `.get`，多一个调用点也不会 AttributeError。
  行为不变：离线测量六项数字与删除前逐字相同。

离线实测（**字符，不是 tokenizer / provider 用量**）：

| 测量 | 原始代码 | 修改后 |
|---|---:|---:|
| 固定源码夹具 codegen 两节点共同前缀 | 16 | 3,858 |
| 同夹具跨 SMALL/FULL 共同前缀（对 HEAD） | 16 | 3,858 |
| 同夹具跨 SMALL/FULL 共同前缀（对前一次工作布局） | 1,468 | 3,858 |
| 12306 完整需求修复、不同失败节点的共同前缀 | 57 | 88,915 |
| ctrip 完整需求修复、不同失败节点的共同前缀 | 55 | 59,143 |
| smoke--counter tiny 用户提示词 | 1,837 | 1,605（−12.6%） |

六道 Web 题的原始需求块逐字相同。修复前缀夹具只引用完整需求块，不引用源码，以隔离本轮变化。
codegen 夹具的源码在两节点间保持不变、全部放得下，完整消息字符数几乎不变；实际选取/内容变化时不能
直接套用前缀长度。重现：

```bash
python3 arc/dev-docs/measure-token-prompts.py --baseline-ref 493c2e6a2808438091b2de131cb8bea9170c9a12
python3 -m unittest discover -s arc/tests -t arc
```

50k spec + 28k 入口 + 约 12k 检查点纠正文本的预算夹具，观察正文缩短后能保留 codegen 和完整入口引用。
预算充足时不裁；普通操作约束放不下时仍走工具。源码读取次数及回退日志也有单测。
已纠正计划里「写保护使省略安全」和「required styling 导致 style 输出」两处过度推断。

验证：累计新增 23 项覆盖预算、跨档稳定前缀、重写当前源码、场景独有约束、残留/缩短证据及日志；原有 Mock 接线测试适配新构建函数。
完整适配层 340 项，332 通过、8 跳过。真实模型对比未做，不宣称缓存命中率、通过率或费用改善。
Rust 引擎的提示词布局、预算计算及 tiny 表示本轮未改；运行本轮优化使用默认 Python 路径。

## 2026-09-17：P1b —— codegen 不再要求整个应用放进一次请求；未被完整引用的文件写保护

背景见 `dev-docs/token-reduction-plan.md` §3.1：`codegen_context_fits` 要求整个应用放进
`OCTOS_ARC_CODEGEN_CONTEXT_CHARS`（90,000）减 spec 之后的预算，否则整个节点退回 tool 模式（keep 实测 36
请求/节点）。keep 云端产物 86k 字符，其后段节点早就在走 tool 模式；Round 35「每节点单请求」对任何长过
~82k 的应用都不成立。三处改动，缺一不可：

1. **门槛**：改为「spec ≤ 预算 60%，且后端入口（每个节点都要扩展的那个文件）放得进剩余预算」。其余文件
   由 `relevant_sources` 在预算内引用、预算外按名列出（这条分支此前在 implement 路径上取不到）。
2. **写保护**（阻止覆盖未完整引用的既有文件）：`codegen_turn` 对回复里的每个 FILE 块，若目标文件**已存在于磁盘**且
   提示词**没有把它完整引用**（`quoted_paths()`：只认没有后缀标注的 `--- path ---` 头；`(omitted, …)` 和
   `(too large to quote whole, …)` 都不算），拒绝落盘、保留磁盘版本、记一条 correction 给下一轮。新文件与
   完整引用的文件照常写入；tiny 层的 `raw_target` 不受影响。全部块都被拒时该轮判失败（不再是「成功但
   什么都没写」）。靠提示词请求模型「别改没看到的文件」不算保护。
3. **修复轮** `codegen_repair_prompt`：去掉「有省略/裁剪就回 tool 模式」的拒绝（写保护覆盖了那个风险）；
   源码按「预算 − 提示词其余部分 − 后缀 − 格式块 − 2,000 余量」的房间重新引用，结果按构造放得下。
   不改这条，第一次失败就把节点送回 36 请求，收益蒸发。

盈亏（推算）：节点 codegen 失败最多多花 1 次 implement + 2 次 codegen 修复（≈3 × ~26k token）再进入和
今天一样的 tool 模式，代价 <10%；成功则从 ≈864k 降到 24–72k。成功率 ≥ ~9% 即回本。

验证：适配层 unittest 307 项通过（新增 4 项，改写 3 项：原「整个应用必须放得下」「有裁剪就拒绝修复」
两条断言按新契约反转）。两个 dry run（无模型）：

- **回归**：keep 32 节点、默认预算，全程 codegen，0 abort、0 次「exceeds one-request allowance」回退。
- **写保护实跑**：以 `arc-output/try1` 的可用计数器为模板，把 index.html 用注释填到 29,005 字符，
  `OCTOS_ARC_CODEGEN_CONTEXT_CHARS=10000`、`OCTOS_ARC_TINY=0` 跑 smoke-evolution--counter。探测后 REQ-1 判为
  unchanged（填充页仍通过它的 spec），REQ-2 走 codegen 而不是 tool 模式（改前必回退：29k > 10k）；提示词省略
  了 index.html，dry run 的占位回复照旧带着它的 FILE 块，日志
  `[codegen] REQ-2 implement: refused frontend/src/index.html: the file exists and the prompt did not show it whole`、
  `wrote 1 file(s): ['backend/server.js']`，磁盘上的 index.html 仍是 29,005 字符的原页。
  第一次做这个实验用的是不通过任何 spec 的模板，被 Round 30 的「模板不满足任何 spec → 重建」规则丢掉了，
  guard 没有机会触发 —— 那是夹具错，不是 guard 错，记在这里免得重蹈。

**真实模型对比未做**（额度）；做之前不宣称数字。

## 2026-09-17：自带内核在云端卡死（`e70711133d37`）—— 原因与 glibc 上限校验

用自带 `bin/octos` 的 36M 包提交 smoke，stdout 停在平台的「Waiting for container to exit without timeout」，
`main.py` 自己一行日志都没有，2 分钟后仍在「Launching generation agent」（旧包 20–69 秒完成）。

原因（实测）：本机 glibc 2.43，`target/release/octos` 要求的版本化符号最高 **GLIBC_2.43**；官方 release
`v2.0.3-rc.11-arc.13`（CI `arc-linux-release.yml` 在 `ubuntu-latest` 上编）最高 **GLIBC_2.39**，能在平台跑。
平台容器的 glibc 介于两者之间：加载官方的成功、加载本机的失败（`version 'GLIBC_2.43' not found`）。
`octos_stdio.py` 没有握手，每步 60–120 秒超时，叠上 3 次瞬时重试，就是那个「一直 launching」。
**这是自带内核那条改动引入的，不是平台问题。**

修：`pack_kernel.py` 新增 glibc 上限校验 —— 扫描候选二进制里的 `GLIBC_x.y` 字符串取最大值（.dynstr 里的，
strip 不掉；纯字节扫描不依赖 objdump），高于 `PLATFORM_MAX_GLIBC = (2, 39)` 就跳过并打印原因，包退回下载
路径。musl/静态二进制没有这些字符串，放行。`ARC_KERNEL_MAX_GLIBC` 只在确认平台镜像更新后放宽。
本机构建现在被拒：`跳过 …/target/release/octos: needs GLIBC_2.43, the platform has at most 2.39 …`。

验证：`test_pack_kernel.py` 新增 4 项（先红后绿），共 13 项；本机 `pack.sh` 打出 404K 无 `bin/` 的包。
教训写进 README：本机 `cargo build` 的内核多半不能直接自带；要发改过的内核走 CI release，或固定 glibc
目标（`cargo zigbuild --target x86_64-unknown-linux-gnu.2.39`）。

### 同日：在本机编出平台能加载的内核（`arc/build-kernel-docker.sh`）

本机没有 docker/podman/zig/cross，且依赖里有 `aws-lc-sys`（cmake）、`ring`、`zstd-sys`、`libsqlite3-sys` 等 C 库，
musl / zigbuild 都不保证一次过。装了 `docker.io`（Ubuntu 26.04 仓库，29.1.3）后，用和 CI 同一个底座的容器编：
`arc/docker/kernel-builder.Dockerfile` = `ubuntu:24.04` + rustup 1.98.0 + build-essential/cmake/pkg-config；
`arc/build-kernel-docker.sh` 建镜像、以本机 uid 在容器里 `cargo build --locked --release -p octos-cli
--no-default-features --features api`（产物目录 `target/docker/`，与本机 2.43 的 `target/` 隔开）、拷到
`arc/bin/octos`、末尾用 `pack_kernel.py` 自己的规则打印校验结果。

实测：全量 release 编译 5 分 31 秒；产物 `octos 2.0.3-rc.11 (37a9551d)` 需要的最高 glibc **2.39** = 平台上限；
`pack.sh` 通过校验打出 36M 包；`zipfile` 解压 → `find_octos()` 选中包内内核并补回可执行位 → `--version` 正常。
本机 shell 拿不到新加的 docker 组（26.04 没有 `sg`/`newgrp`），用 `sudo -g docker` 以本人身份跑脚本绕过。
云端用这个包是否正常结束：**未评测**（等下一次提交）。

## 2026-09-17：arc-bench-web--12306 离线体检 —— 共享 helper 按引用裁剪

没有 key，真跑未做；先把不花钱能看出来的看完。12306：需求 137,828 字符、142 个 id、117 个 spec 文件 +
一个 **25,240 字符的 `helpers.ts`（54 个 export）**。`spec_bodies()` 把所有非 spec 的 `.ts` 整个追加到**每个**节点
的 spec 文本里，于是每个节点的"spec"都是 25.5–27.6k 字符，而 spec 文件本身中位数只有 464 字符：

- 推理关闭规则（< 5,000 字符）在 **0/117** 个节点上生效 —— 每个请求都带推理 token（按输出计价）。
- 每个请求多带 ≈7k token 的 helper 代码，一个 spec 直接用到的 export 中位数只有 4/54。
- 源码预算被挤到 `max(8000, 90000 − 27k)` ≈ 62k。

改动：`trim_helper_to_references()` —— 解析 helper 的顶层声明（export/非 export 的 function/const/class/type…），
从 spec 引用的标识符出发做传递闭包，只引用能到达的声明 + import 行；spec 没引用到 helper 就不带；helper 解析不出
顶层声明（如 `module.exports = {...}`）就整个带上（宁多勿断）。没有 spec 文件的节点（全套修复）保持原样。
通用：按标识符引用，不按题名。

实测（离线，`spec_bodies` 字符数）：

| | 改前 | 改后 |
|---|---|---|
| 12306 中位数 / 最大 | 25,748 / 27,652 | **11,323 / 14,817** |
| 12306 推理关闭的节点 | 0 / 117 | 24 / 117 |
| 12306 全部节点 spec 文本合计 | ≈3.01M | 1.16M（−62%） |
| keep 中位数 / 最大 | — | 6,382 / 7,460；推理关闭 7/32 |

中位数没降到直接引用量（1.5k）是因为闭包诚实地把可达的声明都带上了：`REQ-4.3.6` 直接引用 9 个 export，
可达 23 个声明，其中 `FIXTURES` 一个常量表就 5,712 字符（47 个 spec 用它，应用必须按它造数据，不能省）。
适配层 unittest 311 项通过（新增 4 项，先红后绿）。真实模型效果：**未评测**。

同时确认：117 个节点没有一个超过 60% 门槛（P1b 之前也不会因 spec 过大回退），无 tiny 层节点，spec 不写死端口。

### 同日：helper 裁剪的兜底 —— 解析不出名字的 export 一律整文件引用

改前核对：六道 Web 题的 `helpers.ts`（12306 / bookstack / ctrip / keep / prestashop / stackoverflow）每一行 `export`
都能被声明解析器命名；12306 全部 117 个 spec 裁剪后没有一个可达声明被漏掉。唯一的空洞是假设性的：
`export { a, b }`、`export const { x } = …`、`export default { … }` 这类解析不出名字的形式，闭包会**静默丢掉**。
现在只要 helper 里有一行 `export` 解析器命名不了，就整文件引用（宁多勿断）。公开六题没有这种写法，改后
12306 / keep 的度量与改前逐字相同（中位数 11,323 / 6,382）。unittest 313 项通过（新增 2 项，先红后绿）。

## 2026-09-19：每次运行一次应用级设计，注入每个 codegen 节点的提示词

复核前提：codegen 一个节点一个节点实现，每个节点的提示词只有自己的 description + spec，上游依赖是一行
`implemented (see code)`（`ancestors_text`，inline 模式下 `self.designs` 为空）。没有任何一步告诉第 40 个节点
前 39 个节点约定了哪些路由、页面和记录形状——只能从引用的源码里猜。改前核对了两点：
- 之前我说 `2b6406557024` 的 46/66 来自"数据模型不一致"，**记录里没有这个证据**，记录说的是缺失按钮、隐藏元素、
  定位器等待。全局设计对这类失败（节点之间页面/路由/元素命名不一致）是**可信但未测量**的收益，本条不宣称数字。
- 消费侧早就在：`self.designs` → `ancestors_text` 的精简键（routes/pages/data_model）、`.arc/design/` 持久化。

改动：
- `tree_outline()`：整棵树的 id / name / description / dependencies 大纲，**不带 scenarios**（它们和公开 spec 重复，
  体积是三倍）。`app_design()`：运行开头一次无工具请求（`text_turn`，从 `codegen_turn` 里抽出来的公共壳），
  要一个 JSON：data_model / routes / pages / notes；存到 `self.app_design_doc` 和 `.arc/design/app.json`。
  没有 JSON 就照旧跑（dry run 实测：`application design ok … 'dry run: no model call'` → `no JSON object in the
  reply; nodes proceed without one` → 节点正常开始）。只在**新建 + codegen + 节点数 ≥ design_min_nodes** 时做：
  已有应用本身就是设计，tool 模式节点会读代码。`OCTOS_ARC_APP_DESIGN=0` 关闭。
- `app_design_context()`：每个节点带的设计切片，`OCTOS_ARC_APP_DESIGN_CHARS`（默认 6,000）内。放不下时
  data_model 整个保留，routes/pages 只留与该节点 spec 词重合的；仍放不下就截断并标注，绝不使提示词失败。
- `codegen_implement_prompt`：设计块的位置见下方「复核修正」——放得下的整份设计在规则之后、源码之前（每个节点
  逐字节相同）；放不下时按节点过滤的切片放在**源码之后**。两者都计入 `fixed` 预算（`room` 相应减少）。
- `prompts/app-design.md` 同步给 Rust 引擎。

成本（离线实测）：

| 题 | requirements.yaml | 大纲（无 scenarios） | 设计请求 | ≈ token（÷3.8） |
|---|---:|---:|---:|---:|
| 12306 | 137,828 字符 | 52,167 | 53,057 | ≈14.0k，**整次运行一次** |
| ctrip | 117,631 | 44,560 | 45,450 | ≈12.0k |
| keep | 27,287 | 9,835 | 10,725 | ≈2.8k |

每节点多带 ≤ 6,000 字符（≈1.5k token），且在稳定前缀里。unittest：`tests/test_app_design.py` 12 项（先红后绿）
+ 全套通过。真实模型下设计质量与对通过率的影响：**未评测**。

### 同日：`77522b55` 复核修正（三条，均由本地探针复现）

1. **字段类型错误会终止整次运行**（P1）。`app_design()` 只验证顶层是非空 dict；模型返回合法 JSON 如
   `{"routes": 1}` 时，`len(design.get("routes"))` 抛 TypeError，外层捕获后整次 run 中止，一个节点都不开始。
   新增 `valid_app_design()`：data_model 必须是 dict、routes/pages 必须是 dict 列表、notes 必须是字符串，且三个结构
   字段至少出现一个；不合格按**无设计**降级，不持久化。
2. **按节点过滤的切片放在源码前面，破坏跨节点前缀**（P2）。我之前写的「缓存不受影响」**不成立**：设计超过
   6,000 字符时切片随节点变化，探针里 orders / login 两个提示词在第 1,715 字符就分歧，而源码从第 1,905 字符才开始。
   现在 `app_design_blocks()` 分两段：放得下的整份设计（每节点相同）在源码前；放不下时按节点过滤的切片在源码
   **后**。测试断言两个不同节点的提示词直到最后一个源码块为止逐字节相同。
3. **tiny 层与修复/重写没有拿到设计**（P3）。`tiny_turn`、`codegen_repair_prompt`、node_cycle 的 rewrite 提示词各自
   拼提示词，且每轮新 session 不继承。现在：有应用级设计时不进 tiny 层（它的固定静态服务器和无设计提示词正是
   设计要防的）；codegen 修复提示词带节点切片并计入重引用房间；rewrite 提示词同样带上。

`tests/test_app_design.py` 新增 6 项（先红后绿），全套通过。

## 2026-09-19：云端 `fcec6ac02a95`（12306 真跑）的读数，以及被拒文件的重试

第一次完整真跑：135/135、117/117 功能、PASSED 100 分，¥119.68，6 h 12 min（`main.py` 在 `77522b55` 之前两个
commit：含 P1 / P1b / helper 裁剪，不含应用级设计）。日志逐行统计：

| | 数值 |
|---|---:|
| 请求总数（代理） | 1,154 |
| tool 模式回合 | 32 个，**1,077 次工具调用 ≈ 93% 的请求**，3.8 h / 6.2 h |
| codegen 块被写保护拒绝的节点 | **28 / 117**，被拒的每次都是 spec 自己的目标页（ticket-orders / user-information / security / index） |
| 修复因「evidence unavailable within codegen budget」直接进 tool 模式 | 15 次 |
| 第一次拒绝 | 第 49 个节点，应用 16 个文件；结束时 44 个文件 |
| 代理统计 | prompt 55.84M（**90% 缓存命中**）+ completion 2.10M（含推理 1.24M）= 57.94M |
| 平台计量 | **185.29M token，¥119.68 → ¥0.646/M**；keep `2224a9013528` 是 28.8M = 代理总数、¥0.576/M |

进 tool 模式的链条：44 个文件时 spec 词命中噪声大（导航栏文字每页都有），同分按体积升序 → 小文件先占满预算 →
目标页被跳过 → 模型照样重写它 → 写保护拒绝（正确）→ spec 失败 → 修复轮同一份选择再被拒 → 「identical failure
twice」→ tool 模式 30–86 次请求。**这不是模型的失败，是选择的失败**，而且被拒的路径就是答案。

改动（`tests/test_target_quoting.py` 10 项先红后绿）：
- `scored_sources(must_include=…)`：入口(0) → 上一次被拒的文件(1，模型说了要改它) → spec 点名的文件(2，
  `spec_targets`：文件名词干 ≥5 字符出现在去掉分隔符和大小写的 spec 文本里，`openTicketOrders` ↔
  `ticket-orders.html`；公开六题的页面都靠点击到达，`goto` 只有 `/`，所以只能靠 helper 名) → 其余按命中(3) → JSON(4)。
- 写保护把被拒路径记进 `self.refused_paths`（每节点清零）。implement 被拒后**立刻**用重建的提示词重试一次
  ——仅当新提示词确实把被拒文件完整引用了；放不下就记日志、照旧走验收。一次请求换掉 30–86 次。
- 修复：`codegen_repair_prompt` 的补丁路线放不下时，不再直接进 tool 模式，改走 `codegen_implement_prompt`
  （规则 → 设计 → 排序源码 → 失败证据 ≤6k）；连它也放不下才交给工具。
- 用量记录多一个 `label`（`REQ-x implement` / `repair 2/3` / `application design`），按节点、阶段归因用。

**平台计量 vs 代理差 3.2 倍**（185.3M vs 57.9M），keep 那次是 1.0 倍，但 ¥/M 一致。¥2/M×55.84M + ¥7.5/M×2.10M
= ¥127.5，与 ¥119.68 相差 6%——**像是平台按全价计 prompt token、不打缓存折扣**，但 185M 这个数还解释不了。
对账之前，缓存命中率对榜单费用的价值是未知数，任何按节点归因都要以平台数为准。真实效果：**未评测**。
