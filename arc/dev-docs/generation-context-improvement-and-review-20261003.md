# Octos 生成阶段测试上下文检查与改进报告

日期：2026-10-03。范围：ARC 提交包的 Python Flow；代码基线为 `3747ef82` 加本次开始前工作区已有修改。本文记录历史证据、实施前方案复审、代码改进及实施后复审。

## 1. 结论与证据边界

当前 GitHub、Sheet 流程在应用代码生成前导出内置冻结测试，再按节点提供 spec、可达 helper 和 fixture。对当前 47 个 GitHub 节点及 24 个 Sheet 节点逐一重建首次生成提示词：71 个节点均有对应 spec，未发现 spec、可达 helper 或 fixture 缺失。因此不能把最近两次结果归因于“代码生成时没有测试”。动态任务使用分层测试时，生成阶段主要依据需求契约，业务 spec 在独立审核后冻结；这与两个内置任务的路径不同。

检查确认了三个改进点：工具模式的测试内联会因超限全部消失；跨前后端的源码选择缺少 HTTP 关系；Sheet 可点击选项的兼容性探针尚未接入自动流程。修复这些问题可以减少信息缺口，但本次没有重新调用模型生成完整应用，也没有新线上成绩，不能声称已提升 benchmark 分数。

线上参考：[GitHub f932fbf5cff1](https://arc-bench.com/runs/f932fbf5cff1)、[Sheet 8ff1885a8162](https://arc-bench.com/runs/8ff1885a8162)。本轮打开两页均得到 Request failed。Sheet 使用本机完整下载产物 `/home/chris/Downloads/8ff1885a8162-template/template`；GitHub 仅使用已有 13:50 CST 阶段报告，不把它当最终成绩。

完整逐节点数据：[改动前检查记录](/home/chris/Works/octos-arc/audit/generation-context-20261003/results.json)。该文件是离线重建记录，当前空应用提示词不代表历史运行中的完整应用源码。

## 2. 当前代码生成链路

`Flow.prepare_test_spec_source` 调用内核导出内置测试，然后采用冻结业务测试；`spec_bodies` 按节点读取完整 spec，再裁剪 helper 的可达声明；`node_cycle` 把这些内容送入 `codegen_implement_prompt`。工具模式使用 `tests_prompt_for`，默认 24,000 字符内联预算。codegen 默认总预算 196,608 字符，spec 至多占 60%；源码必须完整引用，缺失必需文件时进入补充上下文或工具路径。

| 当前任务 | 节点 | spec 与 helper 字符范围 | fixture 字符范围 | spec / helper / fixture 缺失 | 工具模式不内联 spec |
| --- | ---: | ---: | ---: | ---: | ---: |
| GitHub | 47 | 19,813–61,453 | 15,016–45,464 | 0 | 12 |
| Sheet | 24 | 5,545–45,402 | 1,352 | 0 | 10 |

工具模式的 `inline_spec_text` 在任意后续文件超限时返回空字符串，前面已经装入的 spec 也丢失；同时它使用全部共享 helper，而非 codegen 的可达声明。这会增加工具读取与上下文往返，不等于模型最终永远看不到文件。

## 3. 两次历史运行能证明什么

### 3.1 Sheet 的上下文与最终失败

历史 adapter 指纹与 `v17.1.zip` 精确一致。该运行记录了 31 次 implementation_context，最大 195,018 / 196,608 字符，6 次超过预算 90%。这是预算压力证据，不能据此认定 spec 被截断。日志保存路径、长度和哈希，未保存完整原始请求正文；历史 spec 传递判断结合已验证的 v17.1 源码链路重建，不等于逐请求原文核对。

context_recovery 共 11 条，其中 9 条提供源码、2 条因预算受阻；两次工具回退分别发生于 REQ-5-2-1 implement 和 REQ-2-1-2 repair1，记录的限制各为 8 次请求、240 秒。若干首次生成请求反复需要 `backend/lib/workbooks.js` 与 `backend/routes/workbooks.js`。REQ-5-2-1 请求六个现有后端文件，因为数据校验需要覆盖已有写入、导入、粘贴、撤销路径。这说明仅给当前 UI 与静态 import 闭包不足以说明写入所有权。

历史内部最终验收为 182 / 195；平台报告为 59 / 100、41 个 unexpected。按每个失败首条 waiting-for 操作分类：22 个先阻塞在可见 option 点击，10 个先阻塞在 Pivot Rows，9 个属于其他。此分类只描述首个阻塞操作，并不代表 32 个失败只有一个根因。

内置 Sheet helper 允许原生 select 的 selectOption；平台动作要求点击可见 option。二者存在交互覆盖差异。当前工作区已加入可见 option 和独立 label 的生成指导，本次保留它，不重复记作新修复。原始需求仍是行为依据，冻结测试不应改为照搬平台实现细节。

### 3.2 GitHub 的范围限制

已有阶段报告记录 33 / 47 节点、147 次 Playwright 检查和 49 次修复。此前已修正将基线失败误当新回归以及扩大历史测试范围的问题，本次不重复修改。缺少完整最终下载产物，不能给出 GitHub 最终得分或断言其失败由上下文导致。

## 4. 改进方案与实施前复审

| 问题 | 改动 | 验收标准 |
| --- | --- | --- |
| 工具模式超限全部清空 | 优先保留完整节点 spec；共享 helper 使用可达声明；过大 spec 仅在可确认顶层语句边界时提供完整测试用例，显式列出剩余读取路径 | 预算含标题与路径；不截断语句；不宣称部分内容为完整；磁盘测试字节不变 |
| 请求的后端所有者缺失 | 根据选中前端源码的实际 /api 请求，匹配直接注册的后端路由并跟随 import 闭包，优先引用候选源码 | 不按任务名硬编码；忽略外部 URL、动态不明路径；不强制装入整个 API 图，既有完整文件写入保护继续生效 |
| 兼容性诊断未自动执行 | Sheet 首次完整验收前自动运行独立、有限时的 option / label 探针；在隔离应用副本运行；记录独立 JSON 与质量摘要，保留预算不足状态 | 不修改验收数量、节点 verdict 或冻结 spec；不自动把兼容性假设当业务修复命令；探针随包发布 |

实施前复审结果：通过上述约束后可以实施。初始设想若强制把全部 helper 放入工具上下文，将再次挤出 spec，已否决；若根据控件名称猜后端文件，会给不相关源码提升优先级，已否决；若把兼容性结果合并为官方验收，将混淆证据，已否决。源码关系仍属于启发式选择，不能证明运行时注册或完整动态路由。实施中的进一步检查发现，完整 Sheet Editor 的跨 HTTP 依赖图额外达到 77,158 字符；因此最终方案把候选后端文件的排序提升到普通 import 关系之前，并保留已有必需源码的优先级，而非把整个图加入必需集合。

## 5. 实施与验证结果

改动涉及 [main.py](/home/chris/Works/octos-arc/arc/main.py)、[source_index.py](/home/chris/Works/octos-arc/arc/source_index.py)、新增 [compatibility_checks.py](/home/chris/Works/octos-arc/arc/compatibility_checks.py)、复用该模块的 [check_sheet_compat.py](/home/chris/Works/octos-arc/arc/check_sheet_compat.py) 和发布清单 [pack.sh](/home/chris/Works/octos-arc/arc/pack.sh)。README 已说明预算、独立证据、关闭选项与隔离范围。本次未改 Rust 内核、内置冻结测试、动态分层测试的审核规则，也未重编或替换 v18.0.zip。

### 5.1 提示词复查

| 指标 | 改动前 | 改动后 |
| --- | ---: | ---: |
| GitHub 工具模式含完整节点 spec | 35 / 47 | 45 / 47 |
| Sheet 工具模式含完整节点 spec | 14 / 24 | 22 / 24 |
| 两任务工具模式有节点测试内容 | 49 / 71 | 71 / 71 |
| 当前首次 codegen 含完整 spec 和 fixture | 71 / 71 | 71 / 71 |
| 工具内联超过 24,000 字符 | 未将标题计入上限 | 0 |

4 个只能部分内联的大 spec 为 GitHub REQ-1-1-1、REQ-4-4，以及 Sheet REQ-5-2-1、REQ-5-3-1。它们引用完整顶层测试用例，并明确要求读取文件里的剩余用例；不截断断言，不宣称全覆盖。两套导出测试树在检查前后逐文件哈希相同。见 [改动后逐节点记录](/home/chris/Works/octos-arc/audit/generation-context-20261003/after.json)。

在历史 Sheet 最终源码的 Editor 依赖图中，HTTP 关系发现 13 个额外后端候选文件，涵盖前述六个主动请求文件中的五个；seed 初始化模块不由这些 HTTP 请求推导，仍需其他证据。另做固定源码预算的排序对照，只用 24 个历史 spec 正文、不加入历史设计/保全契约/必需源码提升：60k、90k、120k 字符预算下，累计引用候选后端文件次数分别从 4→37、11→81、11→88。此计数包含不同节点重复引用同一文件，只验证排序效果；不是历史提示词复现，也不证明消除了实际 NEEDS_CONTEXT。见 [排序对照](/home/chris/Works/octos-arc/audit/generation-context-20261003/source-ranking-replay.json)。

### 5.2 浏览器与发布验证

对下载的原始高分 Sheet 包 8aa637d019a5 与本次低分包 8ff1885a8162，分别复制应用、安装依赖、构建并启动，再运行同一套四项兼容性探针。高分包 4/4 通过；低分包 0/4，前三项复现原生 option 不可见，第四项复现 Pivot Rows 标签链阻塞。低分并非通过修改测试变红；本次只把已有手动探针纳入自动流程。两个源应用前后 tree digest 一致。见 [浏览器复测](/home/chris/Works/octos-arc/audit/generation-context-20261003/compatibility-replay.json)。

发布验证在临时目录执行 `ARC_PACK_KERNEL=0 sh pack.sh`，检查 143 个归档条目、zip 完整性和新增文件与源文件一致。两项既有隔离发布测试也通过，包括脱离仓库导入和确认不打入冻结测试来源目录。没有覆盖原有提交包。

### 5.3 回归测试与失败基线

新增 [test_generation_context.py](/home/chris/Works/octos-arc/arc/tests/test_generation_context.py) 的 14 项测试覆盖超大 helper、完整用例边界、语句原始顺序、跨 helper 引用、HTTP 方法与参数、注释/外部 URL/未知 mount、API 排序、探针预算与任务准入、缺失浏览器、应用隔离、一次执行、过期证据不进入修复。

针对性回归 51 项全部通过；新增与发布检查组合 16 项全部通过；语法编译和 `git diff --check` 通过。全量 ARC 回归 2,418 项：2,381 通过、32 跳过、5 失败、0 error。全量运行后追加的“回调中的 method 不能改变 GET”边界测试属于上述最新针对性回归，未计入 2,418 项。

5 项失败均在本次开始时的 main.py 快照上单独重跑并复现，其他依赖保留原有工作区状态，因此没有新增全量失败。它们不是本次修复的通过项：

- `test_resumable_recovery.RecoveryControlTests.test_explicit_pass_limit_still_stops_after_one_noop`
- `test_token_optimization.PrefixAndCorrectionBudgetTests.test_all_critical_corrections_are_preserved_if_checkpoint_is_trimmed`
- `test_token_optimization.PrefixAndCorrectionBudgetTests.test_budget_render_reads_each_source_file_once`
- `test_token_optimization.TokenOptimizationTests.test_budget_includes_rules_corrections_headings_and_format`
- `test_token_optimization.TokenOptimizationTests.test_oversized_rewrite_evidence_switches_to_tools`

基线结果：[baseline-failures.json](/home/chris/Works/octos-arc/audit/generation-context-20261003/baseline-failures.json)。完整测试日志保存在 `/tmp/generation-context-tests-final.log`；最新针对性和发布日志为 `/tmp/generation-context-focused-tests.log`、`/tmp/generation-context-final-new-tests.log`。

## 6. 实施后复审

实施后复审完成；针对本次改动未发现未处理的阻塞问题。复审发现并修正了以下细节：

1. 部分测试引用必须保持顶层 setup 与保留用例的原始顺序，避免把后置初始化移动到前面。
2. 强制整个 HTTP 图会挤出源码预算，改为优先级选择，完整源码写入保护保持有效。
3. HTTP 方法只识别立即闭合调用的默认 GET 或 options 首个字面 method；回调、后续属性、动态 options 均留为未知候选，避免错误收窄所有者。
4. 新增第二条 zip 命令会使既有发布测试构建的临时副本缺文件；已将新增文件合并到原有唯一清单，两项发布测试恢复通过。
5. 兼容性观察按原始 source hash 绑定。修复后不会把旧失败继续送进提示词，质量摘要显式标记 stale；browser launch 失败、部分执行和不足四项收集都不能成为通过结论。

测试用例只作为上下文或独立诊断：冻结文件不变，compatibility 不进入节点 test_verdict、全套通过计数或行为权威判断。原有工作区改动保留，已有 option/label 指导与 GitHub 回归调度修复不被记作本次新增。

剩余限制：HTTP 选择不覆盖动态 URL、别名调用、router mount 或所有初始化/迁移路径；大 spec 的工具上下文仍需读取未引用部分。自动兼容性探针每次任务最多一次，源码后来变化时只标过期，避免无限复测；预算不足会记录延期。探针失败不会单独触发额外模型修复，只在当前源码对应的既有验收修复提示中提供需要核实的参考。因此需求验收全绿时，兼容性失败仍作为单独问题记录。Rust 直接运行路径不在本次 Python adapter 改进范围内。

本次没有进行完整模型生成 A/B 实验或重新提交线上评测。已验证的是上下文覆盖、源码选择与诊断执行，实际代码生成质量和平台分数仍需同条件线上对照；GitHub 的完整最终产物仍不可用。
