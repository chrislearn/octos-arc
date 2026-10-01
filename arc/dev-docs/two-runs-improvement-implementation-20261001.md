# 两个运行后续改进：方案、复审与实施记录

后续：[整体复核及补测期限/耗时缓存边界修正](overall-review-20261001.md)。本文保留该轮实施记录，后续验证以整体复核的最终源码和日志为准。

依据：[最新运行复核](two-runs-latest-review-20261001.md)。本轮只修改可复现的适配器控制流，不干预正在运行的旧任务。

## 实施方案与实施前复审

1. **验收预留窗口**：保留实际完整验收（包括失败但已完整测量）的范围、spec 摘要、worker 和墙钟耗时。再次测量相同范围时用近期耗时加余量，未知范围用现有按用例/显式 timeout 的估算。每轮同时预留本节点和当前受影响回归；不能根据 0/0、部分执行或启动失败缩小窗口。停止准入时保留真实失败/未知状态。
2. **共用修复 deadline**：在快照/提示构建、可选 rewrite、codegen 纠正、工具 fallback 和无写入续跑期间临时收紧节点 deadline，测量前恢复。所有段共享同一个绝对截止时间；即使失败/异常退出也恢复，不能给后续测量继承较短 deadline。全任务和节点硬预算保持有效。
3. **上下文恢复**：仅当提示确实包含完整的当前磁盘源码时去重。过期源码或 outline 不算已提供。`needs_context` 和 `needs_context_repeated` 均可在剩余时间/请求允许且没有部分写入时最多进入一次工具恢复；不把容量不足当格式错误重新整文件生成。工具恢复仍受结构化工具开关、零额度、保护文件和原调用限制。

复审调整：动态窗口是准入估算，不保证任意新回归都能在该窗口完成；因此不声称消除所有超时。只缓存完整测量的耗时，spec 内容、worker、所选用例或 grader 环境改变就失效；不持久化源码或模型请求正文。回归范围不能从未验证节点扩大为“全通过”。rewrite 失败后的普通修复也不得重新拿一份完整时间额度。已有源码上下文要按内容核对，不能只凭文件名标题判定已读。

暂不接入无调用的导出机械修复、不调整模型/请求上限、不自动拆分云端 Editor。Sheet 保存失败断言的现有并行改动保持，本轮不覆写冻结测试。

## 验收与实施后复审要求

- 可控时钟复现 1039 秒剩余时间：修复结束后仍有节点和已受影响回归的测量窗口。
- 快照/提示构建、无写入 rewrite 后 fallback、工具续写、异常及取消均不能扩大 deadline；测量和下一节点不继承修复截止时间。
- 未知范围按显式 case timeout 估算；部分测量不训练更短窗口；spec/worker 变化失效。
- 已引用当前源码不重复追加；过期/outline 保留正常请求。大文件超容量后工具恢复可以真实改磁盘；请求/时间耗尽、工具关闭或部分写入不恢复。
- 运行相关控制流回归及全量 Python 回归，检查打包仍含受改模块。复审与结果在完成后追加。

## 已实施的代码改进

- `main.py` 的 `run_specs` 收集最近 64 次完整测量。相同范围使用最近五次耗时最大值 × 1.25 + 15 秒，最少 30 秒；否则使用现有 `measurement_seconds` 按 case/timeout 估算。失败但完整测量可用于估算；部分执行、加载/运行时未知、0/0、异常不能训练更短窗口。通过 `measurement_case_scope` 区分分层/生成用例的 inclusion、exclusion 与 active 数量，并恢复读取前的分层选择状态。
- `acceptance_loop` 先扣全任务最终阶段预留，再扣目标验收及已受影响回归的测量窗口。相关回归实际执行联合范围，因此预留也包含再次运行目标 spec。`node_repair_window` 指标记录可用时间、测量时间、修复时间及是否准入。
- `repair_control.py` 的 `repair_deadline` 临时收紧原节点期限；快照、提示构建、rewrite、codegen、工具恢复及无写入续跑共享此期限。正常、`continue`、`break`、异常退出均恢复原期限；`codegen_turn` 也取当前节点剩余时间，不能借全任务余量绕过该限制。
- `quality_control.py` 对完整文件标题后的正文核对当前磁盘内容。大文件放不下和重复读同版本两种结果均有一次工具恢复出口，最多 240 秒/8 请求，还会取原调用剩余额度；无时间、零请求、工具关闭及部分写入均不进入该出口。
- 新增 `test_two_run_repair_windows.py` 的 17 项回归；旧 `test_codegen.py` 的三个裸 `Flow` 夹具补全任务预算，`test_main_helpers.py` 的修复准入夹具补全测量预留模拟。原有回滚、修复轮数、工具切换和角色冲突断言保持。

## 实施后复审与修正

首轮全量回归发现 10 项错误。九项来自上述旧夹具未设置真实 `Flow` 所需预算或新增方法仍返回 `Mock`。另一项暴露本次增加早期上下文路径登记后的实际状态残留：上下文已供给、补丁成功写入，仍留下待读取路径，使 `_node_repair_turn` 继续工具修复。已在提供证据后清空待请求状态，保留原有 `test_node_context_retry_requotes_then_applies_under_the_existing_guard` 验证补丁落盘且没有额外工具调用。

复审进一步补强耗时兼容性：仅按 spec 文件摘要不足以区分相同文件里的部分/完整验收，因此补上实际选择的用例身份及 grader 环境。新增用例证明短的部分验收记录不能用于扩大后的范围；读取选择状态不改变原分层执行选择。记录不改变测试选择、通过条件或修复请求上限。

可控时钟验证结果：剩余 1039 秒时，目标测量 100 秒 + 联合回归 200 秒先预留；快照消耗 17 秒后，修复最多取得 722 秒。随后恢复原节点期限，真实 `acceptance_loop` 完成两次测量，时钟恰到原节点截止。另一项走真实 `node_repair_turn`/`_node_repair_turn`，codegen 消耗 200 秒、第一次工具消耗 300 秒、无写入续跑最多取得余下 422 秒，仍留 100 秒验收额度。rewrite 无写入后的工具修复以及全任务最终预留不足也有覆盖。

这些是调度控制流复现，模型与测量执行器由确定性夹具替代，编辑真实临时磁盘文件；没有调用付费模型，不能据此声称线上吞吐或官方通过率提高。原始失败日志保留，复审修正后的最终结果单独存放。

## 验证与交付边界

- 相关回归：`env PYTHONPATH=arc:arc/tests python3 -m unittest test_two_run_repair_windows test_codegen test_diagnostic_repairs test_main_helpers test_8790_improvements test_codegen_recovery test_joint_regression_repair test_unknown_verdict test_repair_speed_controls`：394 项，392 通过、2 跳过，3.709 秒。[最终日志](../diagnostics/two-runs-improvements-20261001/targeted-tests-final.log)。
- 全量 Python 回归：`env PYTHONPATH=arc:arc/tests python3 -m unittest discover -s arc/tests`：2354 项，2324 通过、30 跳过，99.983 秒。[最终日志](../diagnostics/two-runs-improvements-20261001/python-full-tests-final.log)。本轮仅修改 Python 控制流，未新增 Rust/浏览器业务逻辑改动，因此未重跑上一轮已通过的 Rust 和浏览器专项检查。
- Python 编译检查及 `git diff --check` 通过。
- 在隔离临时目录运行实际 `pack.sh`，`ARC_PACK_KERNEL=0`；逐字节确认包内 `main.py`、`quality_control.py`、`repair_control.py`、`frozen_setup.py` 与当前工作区一致。[打包核验](../diagnostics/two-runs-improvements-20261001/package-check.json)。该包只验证适配器源码打包，未发布或替换云端内核。

已针对两个运行证据中的“修复后没有测量机会”和上下文出口遗漏实施改进；它们不直接修复云端 Editor 的复制/剪切/撤销实现、未实现的 Search 或 teams HTTP 500。验收预留仍是估算，新补丁导致耗时突增或产生此前未知回归时可能超时。分层尚不允许的范围按源码估算，不因此变成可验收范围。

这两个旧进程不会热更新到本地代码。生产效果需要新版本运行验证；本轮没有重启、取消、部署、发布或新建付费运行。Sheet 冻结保存失败测试及其他已有改动未被本轮覆写。
