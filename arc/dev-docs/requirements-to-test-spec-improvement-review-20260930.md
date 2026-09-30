# 从 requirements.yaml 生成测试 spec：改进报告与复审

日期：2026-09-30。性质：方案与实施复审。前半部分保留实施前的分析与建议；末尾记录本次代码实施及验证。本地核对基于 `b1313d50` 及当前未提交工作区；行号以函数名为准。上游核对基于 [arc-bench `ddc7e40e`](https://github.com/code-philia/arc-bench/tree/ddc7e40e4a715eadfd309a333b0da785192886e7) 和 [ARC 编译器 `a119f22f`](https://github.com/code-philia/agentic-requirement-compiler/tree/a119f22fc09391ec5924b44217c0373a02724cca)。

## 结论

上游没有公开的、可直接移植的「YAML 机械生成高质量 Playwright spec」实现。arc-bench 发布的是需求与配套测试，并用[审计脚本](https://github.com/code-philia/arc-bench/blob/ddc7e40e4a715eadfd309a333b0da785192886e7/scripts/audit-benchmark-tests.js)检查二者的对应关系；它不生成测试。ARC 编译器则在接口设计之后，用模型代理按场景生成测试，并保留需求—接口—测试的映射，见[生成器](https://github.com/code-philia/agentic-requirement-compiler/blob/a119f22fc09391ec5924b44217c0373a02724cca/src/agents/test_generator.py)和[提示词](https://github.com/code-philia/agentic-requirement-compiler/blob/a119f22fc09391ec5924b44217c0373a02724cca/src/agents/context/prompts/test_generator.py)。因此，上游最适合借鉴的是**覆盖契约与质量门槛**；行为路径仍需要模型或人工解释需求。

我们的无官方 spec 流程已具备机械编译、AI 提案、确定性 DSL 校验、独立审核、哈希绑定和场景覆盖账本，见 `main.py` 的 `prepare_derived_tests`、`planned_derived_scenarios`、`prepare_derived_spec_batch`、`derived_scenario_coverage`。本报告只针对该流程提出三个增量改动；官方 spec 的运行路径不在改动范围内。

## 证据与现状

| 发现 | 上游证据 | 本地现状 | 判断 |
| --- | --- | --- | --- |
| 每个原子需求和场景都可追溯到测试 | arc-bench 审计要求原子需求对应 spec 文件，测试标题与 YAML 场景名称、顺序一致 | `scenario_review.review_targets` 建稳定场景目标；`main.py.derived_scenario_coverage` 记录缺口和分支；一场景允许多个独立 case | 复用审计原则，不照搬「一文件一场景标题」格式 |
| 测试根据接口和场景生成 | ARC `TestGenerator` 读取当前节点的接口契约；GIVEN/WHEN/THEN 对应准备、动作、断言 | `main.py.phase_design_for_tests` 已将按 phase 过滤的设计放进 `phase_contexts`；`scenario_review.build_prompt` 已注入场景、依赖、义务、声明的 API | 先前认为「尚未传接口契约」不准确；无需再加一层同类设计上下文 |
| 行为断言比可达检查更强 | ARC 提示要求运行真实流程并断言结果；arc-bench 测试以可观察行为为中心 | `scenario_tests._compile_scenario` 跳过负向 THEN 分句；`behavior_test_titles` 将 reach/entry 排除；独立审核只批准有证据的行为用例 | 机械产物的**分支完整度标记**仍可改进；未发现它绕过现有审核的证据 |
| 测试不应依赖实现捷径 | arc-bench 审计禁止 spec 直接访问内部 API、浏览器存储、内部 URL 等 | 我们的 DSL 允许有声明依据的响应观察，并有 harness reset；`proposal_problems` 和独立审核限制断言来源 | 只能移植有范围的审计规则，不能复制上游禁用正则 |

本地可定位依据：`arc/scenario_tests.py` 的 `_compile_scenario`、`compile_leaf`；`arc/scenario_review.py` 的 `build_prompt`、`behavior_test_titles`、`proposal_problems`；`arc/derived_case_review.py` 的 `collect_cases`、`validate_review`；`arc/main.py` 的 `phase_design_for_tests`、`planned_derived_scenarios`、`write_derived_coverage`。

## 建议实施

### P0：去除 AI 提示中重复的全树需求描述

`main.planned_derived_scenarios` 当前把**全需求树**的 `id → description` 字典放入每个 target 的 `source_contracts`，`scenario_review.build_prompt` 又对批次中的每个 target 输出一遍。按本地三份 YAML 的描述字符数估算：Keep 6,839 字符 × 32 场景，12306 39,243 × 135，Sheet 30,961 × 100。乘积只表示构造目标时的重复上界，**不是实际发送 token 或成本**；批次大小和上下文门槛会限制实际请求。它仍说明长提示的一个可定位来源，并可能挤占单批场景与义务的上下文空间。

保留当前需求原文、祖先语境、明确依赖、声明的 API、义务原文和当前 phase 设计；把 `source_contracts` 缩到当前节点及其直接依赖，跨依赖的值只按 `dependency_literals`/`source_values` 的引用补入。先比较裁剪前后的需求 ID、GIVEN/WHEN/THEN、负向分支、精确字面量和可解析提案；缺任何必要证据就回退原提示。尤其要回放跨分类依赖和从别的需求引用枚举值的场景。此项与已有 v14 B2 的「设计按 phase 裁剪」互补，不重复裁剪设计或代码生成提示。

### P1：把机械用例的覆盖范围标到每个结果分句

`_compile_scenario` 目前发现负向 THEN 后只增加计数并跳过断言。如果同一场景另有正向可见文本，`compile_leaf` 仍可能产出 `[script]`；其脚本验证了正向片段，却没有验证拒绝后状态未变化。现有 `missing_negative_contracts` 会在总覆盖账本中指出一些缺口，且独立审核阻止未获批测试驱动修复；这里尚无误批准实例。机械阶段的 `mechanical=behavior` 与脚本存在本身没有表达「只覆盖了部分结果」，容易让进度与诊断读者误判机械覆盖程度。

建议先产出仅由 YAML 推导的场景结果清单：每个 THEN 分句记录原文、分支类别、机械动作/断言是否可生成、不能生成的原因及对应测试标题。机械脚本可保留已证明的正向部分，但不得凭其存在将整个场景视为完整覆盖；负向结果继续进入现有 AI 规划与独立审核。清单是编译信息，不是新的行为预言机，也不改变 `approved_behavior` 的准入条件。

改动点：`scenario_tests._compile_scenario`、`compile_leaf`、`main.prepare_derived_tests` 的指标，以及现有 `derived_scenario_coverage` 的结果分句汇总。验收样例：纯负向、正负混合、状态未变、重新加载后仍未变；机械脚本只能为实际断言过的分句记账，未审核脚本不能驱动代码修复。先用已有单测和固定输出回放验证，不需要为报告运行真实模型。

### P1：适配 arc-bench 的静态审计为生成套件预检

在现有审核前后加只读预检：每个 YAML 场景都有稳定状态；每个生成用例都能映射到一个场景或显式标记为基础不变量；标题中的需求 ID 与文件归属一致；不存在重复标题或失去归属的用例。对行为用例继续要求动作之后有与 THEN 对应的断言。采用现有 `review_targets`、`collect_cases` 和覆盖账本，不另建一套状态来源。

上游审计的内部 API 禁令不能原样复制：`resetState` 是 harness 隔离，声明的 API 响应观察可作为补充证据。审计应拒绝**未在需求或已校验契约中声明的内部路径、存储访问、DOM 实现选择**，并要求 API 观察不能替代要求用户可见结果的场景断言。审计失败只隔离对应候选并记录理由，不能改写需求、自动删断言或把整个应用判失败。

### 不直接复用的内容

- 不复制 arc-bench 的官方测试或各应用 `helpers.ts` 作为派生测试模板：它们是评测答案的一部分，而且按应用专门编写，不能证明通用 YAML 编译能力。
- 不替换现有 DSL/审核流水线为上游 `TestGenerator`：两者都依赖模型，移植会重复已有能力并扩大回归面。
- 不要求所有原子节点在 AI 预算不足时强行产出可运行 spec；缺口要明示为 `missing/unverified`，不能制造只有入口断言的「伪覆盖」。

## 验收与度量

实施顺序为提示裁剪（P0）→ 机械分句标记（P1）→ 静态审计（P1）。每一步先用固定 YAML 和既有模型回复回放，再做相同任务、模型、路由、预算的对照运行。至少分别记录：场景总数、完整/部分/缺失结果分句、`approved_behavior`、`approved_smoke_only`、未审核、隔离、实际执行与通过数；另记负向分支覆盖、提案拒绝原因、提示字符数、提供方输入及缓存 token、墙钟。不得用生成文件数或脚本通过数替代需求覆盖。误批准必须为零；是否提高真实覆盖、降低成本和改善官方成绩需由运行结果判断。

## 复审记录

1. **事实复审：通过。** 上游 `audit-benchmark-tests.js` 仅审计现成测试；ARC `test_generator.py` 调用模型代理写测试。报告没有声称官方测试是自动生成的，也没有把官方测试质量归因于某种未公开方法。
2. **本地能力复审：已纠偏。** 当前代码已有按 phase 裁剪的设计上下文、场景覆盖账本、负向合同检查和独立审核；它们不是待新增功能。P0 只处理重复的全树描述，P1 补机械阶段的分句记账和静态映射缺口。没有发现机械负向分句缺失绕过审核的实例，因此将它排在 P1。
3. **信任边界复审：通过。** YAML 决定预期行为；设计只辅助导航；机械候选、模型提案和测试执行均不自行取得批准。`full` 模式仍须经过独立审核。官方测试仅用于独立评测，不进入生成提示。
4. **收益复审：待实测。** 字符乘积是静态重复量估算，不能当实际 token 节省。设计阶段未进行模型调用或 ARC-Bench 评分，故不宣称质量或成本已改善。

**复审结论：方案可作为小步实施依据；优先落实全树提示裁剪。** 裁剪必须先通过需求证据等价检查；静态审计必须保留 harness 重置与有来源的 API 观察这两类例外。

## 本次实施与复审

| 项目 | 实施结果 | 复审结论 |
| --- | --- | --- |
| P0 提示裁剪 | `source_contracts_for_tests` 仅保留当前节点、祖先、显式依赖（含文件夹依赖的原子后代及传递依赖）；`build_prompt` 在同一批次只输出一次描述，并逐场景列出可引用 ID | 依赖和原文引用仍由 `sourced_values` 校验；其他场景的描述不再自动作为引用来源。已用传递依赖与批次重复样例测试。真实模型提案的等价性仍需同预算回放验证 |
| P1 机械分句账本 | 生成 `derived-tests/mechanical-outcomes.json`；每个 `THEN` 及其后 `AND/BUT` 分句记 `candidate` 或 `needs_ai`、理由与保留的脚本标题；覆盖汇总分别统计两类 | `candidate` 还须有保留脚本、对应动作和字面量断言；负向与无可靠字面量的分句保持 `needs_ai`。该账本不构成批准或通过 |
| P1 静态预检 | 审核时写 `derived-tests/review/static-audit.json`；重复/无归属标题、直接页面导航/API 请求、存储与实现选择器标成无效候选，缺文件/空文件记为缺口 | 预检逐用例隔离，已有批准不能覆盖新发现的静态无效状态；`h.resetState` 与 `h.watchResponse` 保留。语义正确性仍由独立审核判定 |

对三份固定需求树按**每个原子节点收到的描述字符数之和**做纯静态核对：Keep 从 218,848 降到 35,462（减少 83.8%），12306 从 4,591,431 降到 470,245（减少 89.8%），Sheet 从 743,064 降到 202,349（减少 72.8%）。这不是实际批次提示长度，更不是模型输入 token 或费用；批次共享去重带来的额外节省也未计入。

修复过一次兼容性回归：机械账本最初放在 `review/`，提前创建目录影响现有流程测试；现放在派生套件根目录，由审核阶段自行创建 `review/`。另同步了覆盖总计结构的固定断言。定向测试通过；全量单测运行 `2081` 项，其中 `27` 项跳过（`PYTHONPATH=arc:arc/tests .venv/bin/python -m unittest discover -s arc/tests -q`）。

**剩余限制：** 静态扫描按生成用例的文本做预检，不能证明断言对应需求，也不能识别所有间接内部调用。机械 `candidate` 只是分句级诊断，不代表完整场景覆盖、独立审核批准或 ARC-Bench 得分提升。后续需要用固定需求与相同模型预算的回放比较实际输入 token、提案通过率、获批行为覆盖和误批准数。

## 两份 v14 运行报告的复核与吸收（第二轮）

复核来源：[GitHub 运行诊断](v14-github-run-2d7df7727ffd-improvement-review-20260930.md)与[Sheet 停止快照报告](v14-sheet-run-76dd683eb2b8-improvement-report-20260930.md)。两份报告都把在线运行记为用户取消、评测未完成；本轮未取得这两次在线运行的原始私有指标，因此把其中的日志数字视为报告给出的历史观察，不把它们当作当前代码的效果。已重新下载 [Sheet 在线运行](https://arc-bench.com/runs/76dd683eb2b8) 的停止产物，其 YAML SHA-256 `9cddf67be50748106289ed158648629a6c50c30a490d0eda5bd570c557440b96` 与本地任务完全相同；产物仍缺引擎提交标识，不能证明引擎逐字同版。

| 运行报告的问题 | 当前代码复核 | 吸收后的处理 |
| --- | --- | --- |
| GitHub：测试提案在本地 `insufficient_context`，连单场景也可能超限 | 第一轮只裁剪了 `source_contracts`；`augment_derived_tests` 仍把整类 `requirements` 和设计片段放进每个批次 | 本轮把 phase 上下文缩到当前批次节点，按完整提示长度拆分 3→2→1，不截断场景、依赖引文或义务；单场景仍超限时保留 `insufficient_context` 并记录来源、phase、质量指导字符数。请求前的提示与实际发送提示复用同一字符串 |
| GitHub：内部契约导出发生在保护快照之后，下一轮可能恢复掉导出文件 | `run` 中首次 `snapshot_protected` 的确早于 `prepare_build`；`app_design` 会调用 `export_contracts` 写入 `requirements/original.json`、`obligations.json` | `prepare_build` 后刷新保护快照；固定回放证明内部导出保留，随后对 YAML 和导出 JSON 的擅自改写仍被恢复 |
| Sheet：私有候选与公开 spec 状态脱节，日志里的 `validated script` 易被误读为批准 | 当前 `poll_background_specs` 已按共享输入过期、局部 spec 冲突分别处理，`close_background_specs` 有有界排空；历史零合入的确切原因仍未知 | 不重复实现后台队列。新增 `requested`、`response_received`、`candidate_validated` 阶段指标，在 `spec-handoff.json` 明列候选覆盖、获批用例、获批场景和未验证场景；用只读 `derived_run_trace.py` 定时抓取公开套件、审核账本、内部指标和执行状态，复盘每批去向 |
| Sheet：取消时留下不可启动的应用源码；GitHub：回滚后索取不存在的文件 | 现有批次检查、回滚和交付检查点处理应用生成，但两份旧运行没有提供可归因到某次写入的完整前像/检查日志 | 纳入跨流程风险清单；不把 `.js`/JSX 推断或坏树写入时刻当作已证实根因。要另用固定坏回复和中断注入验证写入协议及恢复点，避免在测试生成改动里放宽应用语法门 |
| Sheet：Z/AA 列边界 | 是该次生成应用的具体业务缺陷，CSV 完整列序的要求来自 Sheet YAML | 在本地 Sheet 回放中记录宽表边界是否被测试覆盖；通用 YAML→spec 引擎不硬编码表格列号规则 |

两份报告其余设计格式诊断、wave 源码闭包、`NEEDS_CONTEXT` 预取、取消摘要属于应用生成或平台中断链路；当前证据只足以列为后续定向回放项，不能用测试提示裁剪的静态收益推断它们已经改善。现有独立审核与已批准用例准入门槛保持不变。

第二轮固定输入的**无模型**提示重放：GitHub YAML 有 47 个原子节点、87 个去重场景；Sheet YAML 有 24 个原子节点、58 个去重场景。按每 3 场景顺序组批、仅含已裁剪需求来源和质量指导（不含运行时义务、设计与视觉上下文），Github 的 29 批全部低于 196,608 字符、最大 77,139；Sheet 的 20 批全部低于该上限、最大 60,556。此数值证明静态来源膨胀已大幅下降，**不证明真实运行的每批都能发送**；真实 phase、义务、路由和模型预算须由后续本地运行记录。

### Sheet 本地确定性回放与数据状态

在 `arc/arc-output/v14-sheet-derived-replay-20260930/` 用 SHA-256 为 `9cddf67be5074810…` 的 Sheet YAML 运行机械编译、交接状态计算、静态用例审核和 Playwright `--list` 加载检查。24 个原子节点都生成 spec；24/24 文件加载成功，编译约 0.335 秒、加载约 0.99 秒。结果账本有 576 个分句，全部 `needs_ai`；58 个场景的候选行为覆盖为 0。静态审核无映射或内部捷径问题，24 个用例均为 `approved_smoke_only`，获批行为用例 0，未执行应用行为测试。

首次回放曾把 4 个标题形如 `[reach] 控件名` 的用例记为 `needs_correction`；复核发现 `collect_cases` 只识别以 `[reach]` 结尾的标题，现已修正并以 24/24 smoke 分类重放通过。详细状态保存在该输出目录的 `.arc/local-replay.json`、`.arc/derived-trace-final.json`、`derived-tests/mechanical-outcomes.json` 和 `derived-tests/review/cases.json`。`derived_run_trace.py <输出目录> --watch --out <jsonl>` 可在完整本地运行时定时保存同一组状态。

这次是**不调用模型的流水线与加载验证**。进程环境没有模型 API 凭据，不能从 0 个行为脚本推断 AI 生成失败、独立审核表现或官方得分；完整 Sheet 生成与执行回放仍需可用的本地 API 配置，并应另记模型、路由、预算和源码版本。

### 在线停止快照的本地执行与过程数据

重新从运行页下载的 `project.zip` SHA-256 为 `91b99140f8a14f4fe900847902b9817a5e0d0fdcb5066b11d2c3679b40cfb761`。原样解包于 `arc/arc-output/v14-sheet-stop-snapshot-76dd683eb2b8-20260930/template/`；原样的 24 个派生 spec 在 Playwright `--list` 中全部加载（约 0.925 秒），但 `backend/routes/workbooks.js:812` 的重复片段使 `node --check` 报 `SyntaxError: missing ) after argument list`，应用无法原样启动。这与 Sheet 报告的主要停机缺陷相符。

为执行**该快照已有的测试**，另建 `diagnostic-app/` 副本，仅删除 `workbooks.js` 的重复语法片段；原始 `template/` 保持不动。副本中所有后端 JS 的 `node --check`、前端锁定依赖安装和 `npm run build` 通过，根页面 HTTP 200。以副本服务为目标运行原样 24 个派生测试，4 工作进程约 55.006 秒结束：**4 通过、20 失败、0 加载错误、0 超时杀进程**。通过的恰好是 4 个 `[reach]` 可达性用例；20 个 `[entry]` 失败中，11 个找不到名为 `Worksheet grid` 的 `grid`，5 个预置 A1 应为 `Item` 却见 `Region`，4 个预置 A1 应为 `2` 却未匹配。后两组需结合共享测试状态和页面实现进一步定位，不能仅凭此判定各需求功能缺失。4 个通过也只是 smoke，不是 58 个行为场景获批或通过。快照仍为 24 个 `candidate`、58 个场景目标零获批行为覆盖；没有官方评分。

诊断过程每 10 秒取一次状态，6 个采样点中服务根页面均为 HTTP 200，前 5 次执行报告未完成，第 6 次已完成。对应原始加载结果、逐用例状态、失败摘要及时间线分别保存在 `snapshot-tests.json`、`diagnostic-execution.json`、`diagnostic-timeline.jsonl`；另有 `snapshot-trace.json` 汇总停止时的 24 个候选节点与 58 个未覆盖场景。副本的唯一语法改动见 `diagnostic-syntax-fix.txt`。这些文件都在上述停止快照输出目录。应用服务已在测试完成后关闭。此执行用来定位停机快照与旧 smoke 套件的状态，**不能**当成新引擎生成质量或正式 ARC-Bench 评测。

这组数据把后续优化重点进一步收窄：优先验证后台批次从候选到合入的每一步与中断持久化，再用同模型、同预算的新运行衡量获批行为覆盖；页面入口 smoke 需去掉不由需求保证的固定 A1 值或控件命名，避免 20 个同源断言把进度误读成 20 个独立功能失败。不得在通用引擎里为本次应用硬编码工作表选择器或单元格内容。

第二轮全量单测运行 `2085` 项，其中 `27` 项跳过，其余通过；随后针对最后的追踪汇总补充做了定向回归。`derived_run_trace.py` 按实际 `llm-usage.jsonl` 的 `label` 聚合提供方 token，并汇总提案最终无效的原因类别；套件标记的解析树哈希与 YAML 文件字节哈希分开标注，避免把两种口径误判为输入漂移。
