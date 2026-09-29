# v14 GitHub 任务运行诊断、改进方案与复核

日期：2026-09-30。范围：[ARC-Bench 运行 `2d7df7727ffd`](https://arc-bench.com/runs/2d7df7727ffd) 与本地 `v14` 分支工作区。代码核对基于当前 `b5afd987`；以下行号以本次核对时的文件为准，实施时以函数名定位。**本文只提出方案并复核，没有修改运行代码，也没有提交 Git。**

## 结论与证据边界

这次日志显示的首要问题是：派生行为测试的模型提案被**本地提示长度检查**反复挡住，导致模型请求没有发出，后台测试流水线虽然继续轮转，却没有为这些场景增加可审核的行为用例。与此同时，whole-app wave 因源码闭包超限而转交逐节点路径；首次 wave 的回滚后又发生一次请求不存在文件的上下文纠错。设计请求还花了 240 + 332 秒，分别因契约格式和 JSON 格式被拒。最终页面显示 **`Cancelled by user`**，评测阶段仍为 `Evaluation pending`；这不是代理崩溃或官方场景失败的证据，也没有最终分数。

首次写报告时运行仍在 Stage 2。取消后的最终页面显示历时 63 分 50 秒；最后一条可见生成日志为 2026-09-29 17:36:12 UTC，当时正在处理第 12/47 个原子节点 REQ-2-3 的第二次上下文请求。运行页标注 65 项需求、100 个官方场景；代理按依赖顺序处理 47 个原子节点。当前包标为 `v14.0`，因此本地工作区后续未打包的修改不能当作本次运行已有能力。`main.log` 同时写 stdout 和 stderr，同一消息出现两次不是两次模型调用。

| 运行页可见事实 | 代码对应位置 | 判断 |
| --- | --- | --- |
| 机械编译产生 71 个静态检查，含 7 个场景脚本、14 个入口脚本，45/47 个叶节点有 spec 文件 | `main.prepare_derived_tests`、`scenario_tests.compile_suite` | 这些是内部候选/诊断；文件数及 Playwright 加载检查通过数都不等于已批准行为覆盖 |
| 首批 8 个计划场景、后续 4/6/5 个场景批次反复出现 `insufficient_context`，对应批次报告 0 个新增有效脚本、0 个提案被拒 | `main.planned_derived_scenarios`、`augment_derived_tests`、`scenario_review.build_prompt` | **确定的本地跳过路径**，不是模型拒答，也不是 provider 5xx；`0 proposal rejected` 不能解释为提案质量好 |
| 设计首答 240 秒被记为 `invalid_contract`，格式重试 332 秒被记为 `invalid_json`；其后仍记录 55 routes、26 pages、23 collections，后续提示部分节点设计不完整 | `main.app_design`、`export_contracts` | 确定有两次无效回复和部分/恢复后的设计；拒绝文件内容未取得，不能猜具体 schema 字段 |
| wave 1 写入 6 个文件后早期检查发现 1 个问题并回滚；下一次回复索取已被回滚的 `frontend/src/shared/auth.js`，触发 `invalid_context_request`，再次纠错后写入 `auth.jsx` | `main.whole_app_waves`、`restore_app`、上下文请求校验 | 回滚后索取不存在路径是事实；`.js` 文件中 JSX 触发原构建错误是模型回复暗示，缺原始错误文本，仍属推断 |
| wave 3 的三个单叶源码闭包均超出 96,000/60,000 字符上限，剩余 41 个叶节点转交 node flow；汇总为 2 个 generated-unverified、45 个 deferred | `main.whole_app_waves` 的单叶回退与连续 3 次延后门 | 是既有安全回退，非系统崩溃；规模化生成受限，需要记录更具体的阻塞源 |
| 首个 `NEEDS_CONTEXT` 后，guard 恢复 `requirements/obligations.json`、`original.json` 两个文件，虽然该次模型没有写文件 | `main.snapshot_protected`、`prepare_build`、`quality_control.export_contracts` | 时间顺序和代码路径支持**内部写入触发保护恢复**；并发未知活动尚不能被排除 |
| 17:28 与 17:35 的测试批次连 `scenarios_in_batch=1` 的 REQ-4-1、REQ-4-2-1、REQ-4-2-2 都标 `insufficient_context`；两/三场景批次也继续超限 | `main.augment_derived_tests` 的预取和实际请求门 | 加强 P0 结论：仅把三场景降到一场景不足以解决；必须定位完整 prompt 的各分量 |
| REQ-2-2-2 首次 139 秒回复因 `incomplete_blocks` 被拒，100 秒的有界重试写入两个文件；REQ-2-3 用 142 秒读取 `App.jsx`，再用 143 秒请求 `repos.js`，取消时仍在第二次上下文回复途中 | `main.codegen_turn` 的完整块检查及 `NEEDS_CONTEXT` 流程 | 前者安全门和重试生效，后者暴露逐次索取已存在文件的时间成本；没有证据表明这些请求是非法循环 |
| 页面最终状态 `Cancelled by user`，Stage 3 仍为 `Evaluation pending`；日志未出现最终 rehearsal、批准测试运行、交付汇总或 5xx 终止错误 | 平台状态及生成日志末尾 | 不能把取消解释为代理超时/崩溃，也不能根据部分源码推断评分；取消原因只有平台状态标签，无用户操作细节 |

## 根因 1：全树需求原文在每个场景中重复，测试提案被本地丢弃（P0）

`main.planned_derived_scenarios` 为**每个** target 附同一个全树 `source_contracts` 字典；`scenario_review.build_prompt` 又在**每个** target 块中输出一份。接着 `main.augment_derived_tests` 在预取阶段和实际处理阶段都用 `len(prompt) > codegen_context_chars()` 判断，默认门槛 196,608 字符。超限时直接标 `insufficient_context` 并 `continue`，不会向模型发请求。首批三场景或两场景 chunk 越界；末尾 REQ-4 的单场景 chunk 也全部越界，证明批次缩小本身不足以消除问题。

我用仓库里的 `arc/tasks/hackathon--github/requirements.yaml` 作**静态重放**：47 个原子叶节点、87 个去重后的 `review_targets`；全树 65 项描述共 101,993 字符，序列化字典 103,109 字符。将相同字典注入前 1/2/3 个目标后，`build_prompt` 加当前 `TEST_QUALITY_GUIDANCE` 的长度分别是 **129,074 / 239,597 / 349,990 字符**，还**没有**加运行时 `phase_context`、义务和 API 契约。两目标已超默认门槛；一个目标在运行时仍可能因 phase 上下文、义务或设计内容超限。这是字符重放，不是实际 provider token 统计，也不能据此推算费用节省。运行日志与静态重放共同支持“重复全树描述是主要可定位膨胀项”，但不排除 phase 设计等第二个膨胀项。

**实施方案**：

1. 在 `planned_derived_scenarios` 中建立一次稳定的需求索引；每个 target 只附当前节点原文、祖先语境、按 `requirement_order.dependency_ids` 展开的明确依赖及其传递依赖。对 `dependency_literals` 等路径引用到的跨类别需求，按引用补入精确原文。不能只按同一类别切片，因为 enum、限制值和先决条件可能来自别的类别。
2. 让 prompt 可见的 `source_contracts` 与 `scenario_review.sourced_values` 的引文校验使用**同一份允许引用的原文索引**。如果某个 `source_values` 引文有依据但不在切片内，先从权威 YAML 扩展切片再检查；不降低引文长度、owner 或 exact quote 校验，不拿模型猜测补证据。
3. 保留稳定系统指令/DSL 前缀与固定顺序的来源块，避免无意义地改变缓存前缀。避免把同一来源字典逐 target 重复发送；共享来源可在一批中去重展示，但每条提案仍有明确归属。
4. 在发请求前精确测量完整 prompt，按 3→2→1 目标切分，不截断场景 GIVEN/WHEN/THEN、负向分支、义务和引文。单目标仍超限时，记录 `unverified_gap` 与组件字符数，优先查 phase 的 `requirements`、共享 `data_model`、设计路由，而不是盲目提高阈值或假报已审核。

**验收**：同一 YAML 固定重放里首批可发送的 chunk 数上升，`insufficient_context` 明显下降；跨类别依赖、文件夹依赖、枚举值引文、负向分支仍能通过原校验；无依据引文仍被拒。记录请求实际发送数、提示字符/输入 token、缓存命中 token、结构校验通过数、`approved_behavior`、执行及通过数，不能仅用 spec 文件数量证明覆盖。此项与现有[需求到测试 spec 改进报告](requirements-to-test-spec-improvement-review-20260930.md)的 P0 一致；本报告补充了本次运行的直接证据、字符重放和单目标仍超限的处理。

## 根因 2：保护快照早于内部契约导出（P0，小改动）

`Flow.run` 先调用 `snapshot_protected()`，随后 `prepare_build()` 触发 `app_design()`，而 `export_contracts()` 会写入 `output_dir/requirements/obligations.json` 与 `original.json`。本次 `ARCBENCH_TEMPLATE_DIR=<unset>`，日志里的目标正是 `/workspace/template/requirements`；第一次模型只返回 `NEEDS_CONTEXT`，却在下次文本轮开始时由 `restore_protected()` 把这两个文件恢复。这会丢失刚导出的内部元数据，并给出误导性的“模型改了受保护文件”信号。

**实施方案**：在 `prepare_build()` 完成内部契约写入后、开始生成和后台测试请求前，更新受保护目录的快照。更稳健的后续整理是将官方输入文件与运行中生成的元数据分目录或分别设保护策略。不得因此允许模型改写 `requirements.yaml` 或官方测试。

**验收**：模拟内部 `export_contracts` 写两个 JSON 后启动首次 `NEEDS_CONTEXT`，文件不被误恢复；随后模拟模型改动官方需求 YAML，仍被恢复并记录。检查设计原文、义务和后续测试生成实际读取的版本一致。

## 其他改进：按收益与证据强度排序

### P1：回滚后重建上下文，提前拦截确定性语法错误

首个 wave 写入后被构建门回滚，下一轮仍索取已不存在的 `auth.js`。应给后续请求附当前 `HEAD`/源码摘要与已存在路径的短清单，并清除或重新绑定被回滚版本的诊断、已写文件提示和上下文缓存；`invalid_context_request` 只应报告当前树。为 `.js` 中的 JSX、JSX/JSON 语法错误使用[最终修复报告](v14-final-repair-improvement-report-20260929.md)提出的写入前解析门 L0，避免 183 秒生成后才回滚。先用同一模型回复和回滚状态回放，证明不会再索取已删除路径、能立即给出准确扩展名与错误位置。**原始早期检查错误尚不可见，不能把 `.js`/JSX 当作已证实根因；不要为推断错误加入硬编码特殊规则。**

### P1：设计失败原因要可诊断，重试要有界

保留现有一次格式重试和部分设计回退，但在 `app_design` 指标中记录 schema 错误路径、JSON 解析位置、回复长度、覆盖缺口及重试耗时；机密内容和完整回复仍留在本地拒绝文件，不进普通 stdout。先按具体错误做确定性局部修复可行性判断，再决定是否消耗模型重试。验证在有缺口时 `design_readiness` 不会被“55 routes”等总数掩盖；任何自动修复都不能凭空补路由或改变需求约束。未读取拒绝原文前，不指定具体 prompt 改法。

### P2：wave 闭包可观测性与容量自适应

现有单叶闭包超限会安全转 node flow；记录 `missing_required` 的文件、各文件大小、prompt/source 分量和是否尝试过 `split_oversized_hub`，以判断应拆共享 hub、缩设计目录，还是允许更大上下文。当前自适应放宽要求所有可选实现路由和 fallback 都声明模型上下文容量，这是合理的保护。只有实际声明与 provider 返回证明有余量时才放大门槛；避免靠猜测容量让代理请求失败。验收看早期 wave 通过率、node-flow 回退率、构建通过率和最终行为覆盖，不以 wave 数本身为目标。

### P2：日志分别计“没发请求”和“提案被拒”

把场景状态至少拆成：本地超长跳过、模型请求已提交、回复收到、结构有效、独立审核批准、执行、通过/失败。`checked 45 changed spec file(s) in Playwright` 只表示候选文件可加载，不能显示为 45 个行为通过。保留 `full` 模式的独立审核和只在安全检查点执行已批准用例。这样能立即区分本次“0 个提案被拒但也没有发请求”的情形，与真正的引文/DSL 审核失败。

末尾还有一个具体误读风险：REQ-2-2-2 开始时 `specs=[]`，其派生场景此前为 `0/2`；代码写入后 `no_spec_feature_review` 仍打印“scenario/seed self-check found no deterministic gap”。该函数仅检查确定性源码/种子缺口，**没有**证明场景已获行为测试批准。日志应同时打印该节点的 `approved_behavior`、未验证场景数，并将此句明确限定为“静态源码检查未发现缺口”。

### P2：减少逐次 `NEEDS_CONTEXT` 的空转，并保留中断摘要

REQ-2-3 在取消前依次花 142 秒索取 `App.jsx`，143 秒索取 `repos.js`，两个回合都没有写代码。设计/路由索引可在提示预算允许时把已存在且最可能共改的入口文件一次性完整引用；预算不足则在首次上下文请求后，结合当前需求与依赖索引一次性提供同一闭包内的必要文件。保持现有源码引用和写保护规则，不为提速开放任意文件；用“每个成功写入前的上下文回合数”和提示/缓存 token 衡量，避免扩大提示反而变慢。两次 `NEEDS_CONTEXT` 都是合法请求，当前证据只支持效率优化，不支持认定死循环。

取消后页面没有代理生成的终止摘要或最终测量结果。若平台终止时给代理清理窗口，记录最后已提交节点、正在处理节点、未审核场景与最近的源码摘要，并按[最终修复报告](v14-final-repair-improvement-report-20260929.md)的异常恢复策略处理；若是立即强制杀进程，只能依赖已落盘的检查点与平台状态。**现有日志无法证明优雅清理代码失效，也不能要求取消运行继续评分。**

## 建议顺序与回放

1. 先修 P0 提示膨胀和 P0 快照时序；这两项有直接代码路径与本次日志证据，不依赖改变模型或并发策略。
2. 用本次 GitHub YAML、现有 Keep/Sheet YAML 做固定重放，比较裁剪前后每个 chunk 的完整 prompt 与引用集合；再用记录的回复检查 DSL/引文/审核结果无放宽。快照用隔离目录做写入与恶意改写两类回放。
3. 再处理回滚上下文、设计诊断、wave 指标和必要的上下文预取；最后用**相同任务、模型、预算、打包版本**的完整对照运行衡量真实覆盖和时间。本次被取消，没有最终评测分数。

## 复核记录

1. **事实复核：通过。** 再次刷新后页面明确标 `Cancelled by user`，末条可见日志在 17:36:12 UTC；取消时 REQ-2-3 第二次上下文回复仍在进行。先前的 `insufficient_context` 延伸到 REQ-4 单场景，REQ-2-2-2 的不完整块由一次有界重试恢复。没有把用户取消写成代理崩溃、官方测试失败或双倍模型请求。
2. **代码路径复核：通过。** 全树字典附到每个 target，prompt 每 target 重复输出，超门槛前置跳过模型调用；快照先于 `prepare_build`，`export_contracts` 后写受保护目录。两处均有明确修改点。静态重放重新计算为 129,074 / 239,597 / 349,990 字符（含 1,327 字符质量指导，不含 phase 上下文、义务和 API 契约），与默认 196,608 字符门槛比较成立。
3. **反证与保守性复核：已收紧。** 单目标静态提示未超限，运行时单目标仍超限说明 phase 上下文等也须测量；方案加入组件级仪表和单目标降级，不承诺仅裁剪来源就能解决所有批次。`.js`/JSX 仅列为推断，设计 schema 错误字段也不猜。REQ-2-3 的上下文请求没有非法循环证据；取消时没有终止摘要不能证明清理失败。whole-app 回退保留安全语义。
4. **信任与缓存复核：通过。** 来源只能来自 YAML，引用校验与展示同源；设计、视觉和候选测试不能独立授予行为通过；保持共享前缀与确定顺序，记录缓存 token 后再判断成本收益。未建议开放未声明模型容量或让未批准测试驱动修复。

**复核结论：方案可实施，优先级以“测试提案本地超限”和“保护快照时序”最高；实际覆盖、成本及评分收益仍须在代码落地后通过对照运行验证。**
