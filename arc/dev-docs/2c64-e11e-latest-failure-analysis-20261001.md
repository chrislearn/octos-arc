# 最新云端失败与取消运行复核（2026-10-01）

复核运行：[Sheet 2c6418d39ccd](https://arc-bench.com/runs/2c6418d39ccd)、[GitHub e11e610bb3ca](https://arc-bench.com/runs/e11e610bb3ca)。检查了登录网页的最终 Stdout、下载的最终源码、Sheet 的两个较早下载快照，并用当前适配器独立复现。网页日志时间为 UTC；北京时间加 8 小时。

两次云端都使用 **v15.3 / qwen3.7-plus**，日志记录适配器指纹 `d18dea950e25e8d90535102c5fbd7da1fefe2017aaeea079fa59ec60953c8264`。当前主工作区 HEAD 为 `e386b9dd`，已包含上次 worktree 合并；云端这两次运行没有使用这些新修改。以下分别标注旧运行表现和当前仍存在的缺口。

## 结论

Sheet 的直接失败链是：Pivot 生成未完成 → 缺失菜单导致多个用例逐个等待 60 秒 → 900 秒整批超时丢失局部结果 → 被误归类为启动故障 → 启动修复改了无关代码 → 全量验收再次超时 → 适配器以退出码 1 报告未完成验证。GitHub 是用户取消，停止时尚在第 27/47 个节点的第二轮修复；最终源码仍能复现筛选竞态和文件提交验证竞态。

当前修改改善了工具预算、源码范围、验证隔离和重构回滚，但**尚未解决超时分类、局部结果保留、普通修复的路由注册保护，以及快速交互与保存完成的验证**。不能用开发回归全绿证明这几项业务问题已经解决。

## Sheet：失败原因和修复引入的问题

1. **Pivot 实际没有实现。** 04:17:35 模型请求 `backend/routes/workbooks-worksheets.js` 和 `backend/lib/workbooks.js`；旧适配器报告无法完整引用，停止实现后直接测试旧应用。最终源码没有 `Create pivot table` 菜单和创建/聚合/刷新 Pivot 的完整处理路径。后面的删除工作表代码虽检查 `pivot_state`，不代表 Pivot 功能存在。
2. **用例数与整批时间上限不匹配。** `REQ-5-3-1.spec.ts` 有 16 个用例，各自 `test.setTimeout(60_000)`，单 worker。缺失菜单使每个用例都可能等待 60 秒；仅这些失败等待就可达 960 秒，还未计初始化。当前 `main.py:6455` 仍按 `max(900, 30 * len(specs))` 给整批预算，单 spec 仍只有 900 秒。单节点剩余预算的钳制无法解决按 spec 数估算而忽略 case 数的问题。
3. **超时丢掉已经完成的失败证据。** 当前 `acceptance.py:1555` 捕获 `TimeoutExpired` 后直接返回只有 error 的 `RunSummary`。本次用最终下载源码、冻结原测试、独立数据目录、240 秒调用上限复现，得到 `0/0 / playwright run exceeded 235s`，但磁盘已有 **3 个完成的单例 trace**；三个都在等待 `Create pivot table` 菜单时耗尽 60 秒。这证明 0/0 并不表示测试没开始，也不证明应用启动失败。局部结果只能做诊断，未执行完的完整范围仍须标为 unknown。
4. **误分类导致无关修复。** 04:32:40、04:54:54 日志将 `playwright run exceeded 900s` 标为 `Failed at: build/start`。04:39:54、05:02:32、05:23:03 浏览器健康检查均通过，却继续启动修复。当前 `acceptance_loop` 仍把通用 `summary.error` 放进 `_unresolved_startup_error`，并生成“app startup / npm run build -> npm start”的失败提示。
5. **启动修复重新引入重复注册。** 较早 04:49 下载的 `workbooks.js` 明确注明三个同目录模块由 `server.js` 自动加载。05:02:21 修复把它改成再次调用三个模块。最终真实运行时路由表为 **40 条注册、20 条 duplicate 冲突**。重复注册是在第一次超时之后产生的附加缺陷；Express 当前执行先注册的处理器，不能据此把初始 900 秒超时归因于它。当前“拆大文件”专用流程检查真实路由签名，但普通 codegen、tool、启动修复没有共用同样的提交门槛，常规验收把这些冲突当 warning。
6. **用删功能尝试修复超时。** 05:22:48 启动修复删除拖选回调里的 `saveSelection(...)`，保留内存中的 `setSelectedRange`。最终文件与较早快照的 diff 确认了删除。现有 `RangeSelector` 没有依赖回调的循环 effect，不能支持“通过删持久化解决 React 无限循环”的解释；应恢复持久化语义后独立检查拖选、刷新与切换工作表。本次没有把末尾 34/35 的单个回归直接归因于这行，云端下载不含对应验收报告。
7. **恢复提示只证明 build/start。** 05:38:08 日志称“build/start recovered”；当前 `recover_deferred_startup` 只做 build/start，通过后会清空测试超时字符串。控制探针也复现了这一点，未提供任何业务测试结果。继续生成后续节点可以是合理决策，但“启动恢复”和“超时根因/功能已修复”必须分别记录。`node_cycle` 的 deadline 作用域结束后，外部 sequential/deferred recovery 也不自动继承该节点的剩余预算，需要单独共享恢复总预算。

收尾时 05:45:26 旧通过范围为 **34/35（18 个 spec）**；06:00:31 全套又超时，没有完整 verdict；06:00:42 启动演练通过。日志没有 Python aborted traceback，收尾正常输出工作区和清理信息；结合 `Flow.run` 在仍有未验证节点时返回 1 的代码，符合“未完成验证导致退出 1”的路径。平台 Stage 3 未启动评测，因此页面的 0.0 **不能当成实际 0/72**。后置 cgroup 日志 OOM/oom_kill 均为 0，不能把失败说成内存杀进程。

## GitHub：取消前还存在什么问题

网页状态为 **Cancelled by user / Evaluation pending**，不是应用主动崩溃。最后日志到 06:01:41：REQ-5-1-1 第二轮修复已运行 450 秒。停止时仅启动到第 27/47 个节点，后面 20 个节点尚未走到；其功能缺失不能全算作“修复失效”。心跳只能证明修复进程尚在运行，下载包不含工具逐请求流水，无法从心跳判断当时是在阅读、等待模型还是编辑。

- **前一节点文件创建反复修错。** REQ-4-4 从 1/3 改到 2/3，再保持 2/3；第四轮耗时 1199 秒后无有效改动，恢复最佳状态。最终本地仍为 2/3。
- **当前 Issues 节点修复无进展。** 实现后 0/1，第一轮花 768 秒后仍 0/1；模型称 Open/Closed 清理关键词后应通过，但 harness 没有证实它。随后“identical failure twice”切换工具模式，停止前没有第二轮完成的验收结果。

本次对下载的最终源码复现两个具体原因：

1. **Closed 状态被后续输入覆盖。** `Issues.jsx` 的 `updateFilter` 从当前 render 捕获的 `searchParams` 拷贝参数。测试点 Closed 后立即 fill，React 路由尚未提交新 render，输入处理器仍用旧参数。trace 中最后请求实际为 `.../issues?state=open&q=Legacy+welcome+text`，所以后端按 Open 返回空列表。这是前端状态更新竞态；不是关键词过滤算法或 fixture 中没有 Closed issue。清空关键词没有修正原子更新问题，也可能违背组合过滤要求。
2. **编辑草稿被误当保存结果。** `getByText('Persisted file contents').first()` 能匹配仍可见的编辑 textarea，因此 `h.persisted` 的第一次断言在提交完成前通过并马上 reload。trace 中 POST commits 为 201，后续 GET 有被取消的 `-1`，没有文件查看 API；刷新后留在仓库首页，只显示新文件链接和提交记录。模型此前把 React `setFileName('')` 当作立即改变 async handler 的闭包值，误判了导航原因。保存已发生，最终展示流程和测试的保存完成条件存在竞态。

为确认原因，只在 diagnostics 副本中做两项控制修改：筛选用同步 ref 更新参数并由同一更新函数处理状态链接；提交 pending 时隐藏编辑表单，保留其 state 供错误时恢复，避免草稿满足保存断言。**原下载源码、冻结测试、fixtures 与主适配器未修改。**

| 范围 | 最终下载源码 | 诊断控制副本 |
| --- | ---: | ---: |
| Issues 1 例 + 文件创建 3 例 | 2/4 | 4/4 |
| 云端此前通过的 37 例 + 上述 4 例 | 39/41 | 41/41 |

41 例配对使用完全相同的冻结范围摘要 `6d566bf73c252c12b2e27f69d75173e0a8b2e6aa2db646daceedafdb562d8412`，独立数据目录；控制副本未丢失原有通过用例。单独四例与扩展 41 例均验证了控制修改，仍**不代表 98 例全套成功，也不证明当前适配器会自动生成这些修改**。

## 当前工作区的缺口与改进顺序

| 优先级 | 当前状态 | 下一步与验证条件 |
| --- | --- | --- |
| P0 | 超时丢局部结果，并误送 startup repair；仍存在 | 区分 build、server、browser、test load、case timeout、wall timeout；逐例增量落盘完成事件。未知结果不能算 pass，但保留缺失控件与已完成失败。以本次 16-case 原样本验证：超时后保留单例证据，禁止据此改入口。 |
| P1 | 整批预算按 spec 数估算；仍存在 | 用冻结 case roster、单例 timeout、worker 与实测耗时准入；剩余预算不足时分片测量，保持原用例和身份，全范围未完成仍标 unknown。先识别缺失菜单，再决定实现，避免重复跑 15 分钟。 |
| P1 | 普通修复可破坏 loader/路由注册；专用重构保护不足以覆盖 | 普通、启动及 tool 写入统一记录真实 loader 和注册签名；新 duplicate、literal shadow、丢路由须拒绝并原子回滚。用早期 20 路由到最终 40 路由的真实提案做回归，保留合法重构。 |
| P1 | 保存/导航/过滤竞态；开发回归没有证明生成端解决 | 把最终 trace 的最后变更请求、路由提交和可见容器纳入诊断；持久化 oracle 应证明保存完成、匹配读取视图，快速过滤须原子保留 state/q/label。先冻结原成绩，再独立审计 oracle。用本次 39/41→41/41 配对做验收，随后扩展全量。 |
| P1 | 无证据删持久化、启动修复外层预算未统一；仍有缺口 | 启动修复只能编辑与已确认故障相关的最小范围，保护先前功能和数据写入契约；包括恢复分支的统一 deadline。恢复指标分别记 startup、功能结果和未知 case，不用 smoke 替代业务验收。 |
| P2 | 独立 24000 字符的 preservation 分区仍可能溢出 | 已合入源码闭包与 native 读取恢复，旧 Pivot 整文件拒绝路径有改善；契约分区和 fixture 依赖闭包仍需单独处理。单纯增大 196608 总字符预算不会解除另一分区上限。先记录缺失内容，再比较 262144 总预算及分区配额；字符不等于 token。 |
| P2 | 末轮默认 0，收尾消息仍称允许下一种方案 | 记录实际可执行轮数，停止时明确原因；在可测量的同源应用上比较 0/1/2 轮。预算充裕不应先消耗在重复超时和错误类别的修复上。 |

上次合并已经解决的范围：每次验证私有数据、所属进程组清理、同轮共享请求上限、上一段预算耗尽标记阻塞新轮、started/completed 区分、native 编辑范围与记忆、专用大文件重构的异常回滚及覆盖检查。本次发现的上述缺口不应混同为这些改动全部无效。

## 证据与限制

本次没有调用 Qwen 追加生成请求，没有修改主适配器或重新打包；使用 Playwright 对最终云端下载源码做隔离复现和控制实验。原 v15.3 完整本地 Qwen 基线继续独立运行，不与本次云端快照混用成绩。

- 原始下载 SHA 与路径：[Sheet 三次下载记录](../diagnostics/2c64-e11e-20261001/sheet-downloads.json)、[GitHub 最终下载记录](../diagnostics/2c64-e11e-20261001/e11e610bb3ca/download.json)。两个 final ZIP 都不含 `.arc` 内部日志/指标；网页关键 Stdout 的观察单独记录，没有声称已下载完整内部日志。
- 本地配对及 Pivot 局部证据：[reproduction-evidence.json](../diagnostics/2c64-e11e-20261001/reproduction-evidence.json)。包含 source/scope 摘要、原 41 例结果及控制 41 例结果，Pivot 已完成单例错误与 trace 路径。
- [GitHub 真实 trace 请求摘录](../diagnostics/2c64-e11e-20261001/e11e610bb3ca/trace-network-events.json)、[诊断副本 patch](../diagnostics/2c64-e11e-20261001/e11e610bb3ca/controlled-candidate.patch)。
- [Sheet 最终真实路由表](../diagnostics/2c64-e11e-20261001/2c6418d39ccd/route-table-final.json)、[当前恢复分类控制探针](../diagnostics/2c64-e11e-20261001/current-recovery-probe.json)。探针的健康构建/启动为 stub，验证的是控制流，不能代替真实业务测试。
- [云端关键日志观察](../diagnostics/2c64-e11e-20261001/cloud-observations.json)。

结论复核：Pivot 菜单缺失有源码、实际快照及三个超时 trace 一致支持；重复注册有前后源码和真实路由表支持；GitHub 两处竞态有实际网络 trace、两次原样失败和同冻结测试的控制验证支持。未取得云端末尾 34/35 的详细报告，不指定该单个回归的根因；未把取消后缺失的后续节点、0.0 展示值、残留僵尸或模型自述当作测试成绩。

## 用户复核后的交付收尾补修

用户指出：验收时间不足应停止修改并提交现有成品，不能直接以生成失败结束。复查确认，旧 `Flow.run` 虽保留最终文件，并且启动演练通过，仍因某些节点非 True 而发出全局 `run_failed`、返回 1；平台失败原因明确引用了该非零退出码。这里把生成交付和业务验证混成一个判定，属于收尾策略缺陷。该 Sheet 运行触及的是 900 秒单次验收上限，日志的总预算为 36000 秒；不能说总时间或费用已经耗尽。

本次将正常收尾修改为：启动演练通过即可正常交付、返回 0；若业务未完整验证，completed 消息明确写 `runnable application delivered; local verification incomplete`。节点 False/None、质量报告及全套 unknown 均保留，未将测试改成通过。确认无法启动或程序异常仍报失败。原版本 ZIP 与独立 Qwen 基线未改动。

回归通过真实 `Flow.run` 协调流程和真实 `final_acceptance` 的超时分支，覆盖 False/None 结果保留及确认启动失败的负例。生成、产品执行被 stub，没有调用模型。对旧 HEAD 的 `Flow.run` 回放相同新增测试，两个超时场景真实出现 `1 != 0`；补修后嵌入套件相关 19 项回归通过。完整回归结果见 [交付补修验证证据](../diagnostics/delivery-finalization-20261001/verification.json)。尚未重新上传到云端，不能声称已经观察到平台 Stage 3 成功开始。

补修完整开发回归：**2280 项、28 项跳过、失败/错误 0，90.170 秒**。原分析草稿字节保留，测试产生的根工作区 metrics 已备份并恢复，原 `v15.3.zip` 的 SHA-256 未改变。
