# v14 最终修复与改进报告：成品可用性防线与测试生成速度

日期：2026-09-29。分支：`v14`，审核对象：工作区未提交改动（`derived_pipeline.py`、`visual_requirements.py`、`main.py` +702 行等）。本报告只提出修复方案并给出证据，本轮**没有修改运行时代码**。行号按当前工作区核对，后续编辑以函数名定位。

## 1. 结论

1. **「一次语法/编码错误导致整个成品不可用」还没有真正堵住。** 生成期的检查是完整的，但几乎只把问题**报告**给下一轮模型，而不**拦截**写入。真正的最后防线是收尾时的 rehearsal：3 次修复，然后恢复到「最后一个经浏览器验证的提交」（LKG）。问题在于 full（derived）模式下，这个 LKG 几乎从不被记录；异常中止和收到 SIGTERM 时也完全不回滚。所以一旦最后几轮编辑把应用弄坏，或者 harness 在收尾前中止，交付的就是坏的代码，而且没有兜底。
2. **更好的方案**：把「每个提交都可启动」作为生成期不变量，配合一个随生成推进的 LKG 棘轮。一共五层：写入前解析、批次后启动探测、检查点浏览器检查、收尾 LKG 搜索、异常退出回滚。实测每批新增开销约 **0.5 秒**（后端启动探测约 0.1 s，未定义绑定检查约 0.2–0.6 s），远低于一次模型请求。
3. **测试生成慢的根因是推理 token，不是提示长度。** 测试类请求的输出里 70–90% 是推理 token，按约 58 token/s 输出，是请求耗时的主体。按阶段设置推理强度是收益最大、改动最小的提速手段。v14 的后台测试流水线另有 4 个实现缺陷，会让后台悄悄失效或看不到效果，需要先修。

## 2. 现有防线核查

| 层 | 位置 | 能拦住什么 | 发现错误后的行为 |
| --- | --- | --- | --- |
| 写入前（仅 FILE 协议） | `main.py:5007-5056` | 路由冲突、源码信封错误、整文件被注释替换、助手导入错误、前端 ESM 缺失导出、hook 返回键、原子回复的本地导入 | **拒绝整次回复**并回传证据 ✅ |
| 写入前 | 同上 | **JS/JSX 语法错误** | 不检查，直接 `write_files`（`main.py:5057`） ❌ |
| 写入后批次门 | `generation_checks.check_batch`（`:949`），由 `generation_batch_check` 调用（`main.py:7389`） | 后端改动文件 `node --check`（`:996`）、前端 `npm run build`（`:1007`，与后端语法检查合计 30 s 预算）、导入/导出图 | **只记为证据**，交给下一轮模型；只有 whole-app wave 会回滚本波（`main.py:10400`） ⚠️ |
| 写入后批次门 | `check_batch` `:958-960` | 后端 `require` 了不存在的模块、CommonJS 导出被覆盖 | 归入 `deferred`，只作提示，不算错误 ⚠️ |
| tool 模式结构化编辑 | `main.py:5215-5217` | 同批次门 | 同上，只记证据，不回滚本轮编辑 ⚠️ |
| 未定义标识符、TDZ | `undefined_bindings.cjs`，只在 `check_browser_health` 中调用（`main.py:5878`） | JSX 用了未导入的组件、未声明变量（渲染即白屏） | 只在运行测试或 rehearsal 时触发，生成期不跑 ⚠️ |
| 启动 + 浏览器 | `run_specs`、`measure_rehearsal_server`（`:5920`） | 构建失败、启动崩溃、页面报错/白屏 | 生成期在 derived 模式下几乎不运行（见 G1） |
| 收尾 rehearsal | `rehearsal()` → 最多 3 次修复 → `restore_startable_commit()`（`:12841`） | 同上 | 恢复到 `last_startable_sha`；没有这个值就原样交付 |
| 异常中止 / SIGTERM | `Flow.run` 的 `except`（`:13273`）、`main` 的 `KeyboardInterrupt`（`:13486`） | — | 只清理进程，**不做任何源码回滚** ❌ |

生成期的检查在「下一轮能修」的前提下是有效的。`diagnostics/local-qwen37-improve5-retry400-*` 的 github 与 sheet 中，3 次 vite 构建失败都在紧接着的下一轮就被修好。最近 4 次 sheet 运行（v13、v13.1、v13.3 首跑与续跑）的 85 次门检查全部没有错误。风险集中在**没有「下一轮」的时刻**：收尾阶段的修复、时间用尽、harness 异常。历史上的实际事故正是这一类：
- v9：后端 `seed.js` 启动崩溃；
- v10：误判为致命的路由检查使 rehearsal 失败，只能原样交付；
- v10.2：`api.js` 缺少导出导致前端构建失败，之后每一波都被推迟。

## 3. 缺口（按严重度）

**G1（P0）full/derived 模式下几乎从不记录 LKG。**
- `note_startable_commit` 唯一的调用点在 `run_specs` 里（`main.py:5757`）。
- 而 derived 模式在没有已批准用例时，`run_specs` 在构建之前就提前返回了（`:5731`）。
- 构建前复检 `pre_review_derived_system_check`（`:9535`）和收尾 rehearsal 都走 `measure_rehearsal_server`，成功后也**不记录** LKG。
- 以 v13.3 首跑为例：浏览器健康检查通过了 2 次，但没有任何可回滚的提交。如果收尾 rehearsal 失败，`restore_startable_commit()` 会直接返回 False，然后原样交付。
- v14 的检查点执行已批准用例后会偶尔记录 LKG，但这是附带效果，不能依赖。

**G2（P0）异常中止和 SIGTERM 没有回滚。** `Flow.run` 的 `except Exception` 和 `main()` 的 `KeyboardInterrupt` 分支只清理进程和写终止状态。harness 在编辑过程中崩溃（包括 v14 新增的后台线程、视觉代码引入的新异常面）或被平台终止时，工作区里写了一半的源码会被直接评分。

**G3（P1）语法错误先写入、后发现，而且结构化编辑不回滚。**
- FILE 协议的写入前门不做解析，一个括号不配对的 JSX 回复会被整体写入。
- tool 模式由内核直接写文件；请求上限耗尽时常常停在半截编辑。
- 批次门发现错误后只给下一轮证据；如果这正是最后一个节点或最后一次修复，就没有下一轮了。

**G4（P1）生成期不检查后端能否启动。**
- `node --check` 只查语法。`require` 缺失模块、`module.exports` 覆盖、`router.get(path, undefined)`、种子 JSON 解析失败、顶层 TypeError，都要等到启动时才暴露。
- 其中「缺失模块/导出」被刻意归入 `deferred`，理由是「后面的波次可能会生成它」。

**G5（P1）未定义标识符检查生成期不运行。** `undefined_bindings.cjs` 对前后端各只需 0.2–0.6 s。在 v13.3 首跑、续跑和两次 github 输出上实测全部 `passed`，没有误报。但它只在浏览器健康检查里运行。

**G6（P2）`restore_startable_commit` 遇到未提交文件就拒绝回滚**（`:12866`）。收尾时如果修复轮留下了未提交的改动，保护逻辑反而阻止了恢复，结果仍是原样交付。

**G7（P2）本地构建与评测环境依赖不一致。**
- `AppServer.build` 复用已有的 `node_modules`（`acceptance.py:1093-1127`），评测环境则按 `package.json` 全新安装。
- 源码导入了已装在 `node_modules` 里、却没有写进 `package.json` 的包时，本地能通过，评测会失败。
- 目前没有这项检查。我扫描了本地全部输出，暂未发现实例，所以这只是潜在风险。

**G8（P2）门检查的错误文本截断方式不对。** `check_batch` 用的是 `(stdout+stderr)[-2500:]`（`:972`）。vite 的真正错误（文件:行:列）在堆栈之前，长输出时会被截掉。`AppServer._run` 已有 `startup_error_digest`，应该复用。

## 4. 更好的方案：「可启动不变量 + LKG 棘轮」

核心原则：**成品永远等于最近一个被验证可启动的提交，再加上之后被验证无害的增量。** 在生成期就维持这个不变量，而不是把风险攒到收尾时一次性处理。

### L0 写入前解析（毫秒级，只拦截确定的错误）
- 新增 `parse_check.cjs`，用前端已安装的 `@babel/parser`（`undefined_bindings.cjs` 已依赖它），对回复中每个 `.js/.jsx/.mjs/.cjs/.ts/.tsx` 做完整解析；后端 CommonJS 文件额外在临时路径上跑 `node --check`；`.json` 用 `json.loads` 校验。
- FILE 协议：解析失败就拒绝整次回复，把 `文件:行:列 + 消息` 回传给模型，结果类型为 `syntax_contract`，与现有的 `export_contract` 一致。
- 结构化编辑：可选方案是在 octos 的 `before_tool_call` 钩子里对 `write_file/edit_file` 的结果内容做同样的解析，失败则拒绝该工具调用（退出码 1），模型在同一轮内就能修正。该钩子已支持 argv 调用和环境清洗。
- 只拦截「解析失败」这种确定性错误，不拦截风格或推测性问题，避免重演 v10 的误判致命。

### L1 批次后启动探测（每批约 0.5 s）
在 `check_batch` 之后追加以下检查：
- **后端启动探测**：临时端口 + 临时 `ARC_DATA_DIR` + `ARC_EXTRA_PORTS=0`，运行 `node <server entry>`，最多等 10 s 监听；然后 `GET /`，要求 200 且在 SPA 模式下返回 HTML，再选 1–3 个设计文档中不带参数的 GET API，要求非 5xx；最后结束进程组。在 v13.3 首跑产物上实测，0.10 s 就开始监听，全部探测 0.11 s。
- **绑定检查**：前后端各运行一次 `undefined_bindings.cjs`，`failed` 视为确定错误。
- **依赖声明检查**：扫描裸模块导入（排除 node 内置模块），与各自 `package.json` 的依赖做比对（对应 G7）。

判定规则：
- 全部通过，且前端构建已真实执行（不是 `deferred`）时，**推进 LKG**，即提交并记录 sha。
- 若上一个状态可启动，本批让它不可启动了，就判为「启动回退」：
  - wave 路径：扩展现有的 `wave_rollback`，把启动回退也纳入回滚条件；
  - 顺序路径：先给一次带精确 stderr 的限时修复轮（复用 `node_repair_turn` 的预算规则）；仍失败就把本节点改动的文件恢复到节点开始前的提交，节点标为 `implemented_unverified/deferred`，交给后续检查点和收尾处理。这与现有的 `incomplete_node_rollback` 语义一致。
- 「缺失模块」这一类暂时保留 `deferred` 的宽容：只要缺失的路径出现在设计文档计划中、但尚未生成的文件列表里，就不回滚本批，**只是不推进 LKG**。

### L2 检查点浏览器检查（约 3 s）
在 wave 结束、每 K 个顺序节点（默认 4）、`pre_review_derived_system_check` 和每次 rehearsal 成功时，运行 `check_browser_health`；通过就把 **browser-LKG** 记录为「已验证渲染」的更强回滚点。`note_startable_commit` 要改为不依赖 `run_specs` 的暂存状态，而是用 `git status --porcelain -- frontend backend` 为空加 `HEAD` 来判定（对应 G1）。

### L3 收尾 LKG 搜索
- rehearsal 失败时，恢复顺序依次为：browser-LKG → 启动 LKG → 在最近 N 个（默认 6 个）生成提交里**从新到旧**逐个测量构建+启动，每个约 5–20 s，受剩余预算约束。
- 恢复前先把脏工作区提交成一个 `wip` 提交，而不是拒绝回滚（对应 G6）。
- 恢复后，被丢弃提交所对应的节点，其状态标为 `test_unverified`，并注明原因。
- `final_rehearsal_reserve()` 至少要留出一次 LKG 恢复加复测的时间。

### L4 异常与终止兜底（对应 G2）
- `Flow.run` 的 `except` 分支和 `main()` 的 `KeyboardInterrupt`/`fatal` 分支加入 `emergency_restore()`：
  - 如果当前源码摘要等于最后验证过的摘要，什么都不做；
  - 否则在 ≤20 s 内做一次 L1 探测（不跑浏览器）；失败且有 LKG 时，先保存 `wip` 再恢复 LKG。
- SIGTERM 时间很紧时，只在「当前已有未解决的确定错误」时才不经测量直接恢复 LKG，其余情况保留当前源码。
- 结果写入 `terminal-state.json`。

### 成本与收益
- L0 加 L1 每批约 0.5–1 s；按首跑 116 次实现请求计算，总计约 1–2 分钟。
- L2 每次约 3 s。
- 收益：把「0 分成品」的概率从「依赖收尾那 3 次修复」降为「最坏交付上一个可启动版本」。这对评分是严格占优的：功能少一些，但能用，好过功能多却打不开。

## 5. 测试生成速度与 v14 后台流水线

### 5.1 慢的根因（续跑 `llm-usage.jsonl`）

| 请求 | 耗时中位数 | 输出 token | 其中推理 | 输出速率 |
| --- | ---: | ---: | ---: | ---: |
| 代码实现（首跑 116 次） | 13 s | 641 | 181 | — |
| 义务提取 | 84 s | 6,677 | 4,408 | 58/s |
| 义务独立审核 | 193 s | 11,318 | **8,192（触顶）** | 58/s |
| 场景生成（26 次） | 101 s | 5,842 | 4,575 | 58/s |
| 用例独立审核 | 83 s | 4,571 | 4,114 | 58/s |

首个 token 在 2–3 s 内返回，输入长度不是瓶颈。串行跑时，一个 3 叶节点批次约 830 s，全树 8–10 批。

### 5.2 提速方案
- **S1 按阶段设置推理强度（收益最大）。**
  - 生成类（义务提取、场景生成）关闭思考：它们的产出之后还要经过确定性编译和独立审核。
  - 审核类用 `thinking_budget` 限在约 2k。
  - 实现方式：在 `turn_reasoning_for_model`（`llm_proxy.py:290`）按标签分流，加环境变量开关。
  - 必须先用同一批提示回放，比较拒绝率、批准率和误批准数（误批准必须为 0）再定默认值。
  - 粗估：场景生成 100 s → 25–30 s，用例审核 80 s → 40 s，义务审核 190 s → 80–90 s。
- **S2** 义务审核只返回「ID + 判定 + 引文编号」，原文由程序回填，沿用 B1 的做法。
- **S3** 代码侧空闲时（Playwright 检查点、构建、启动修复期间），后台并发放宽到 2。
- **S4** 用 B2 的拒绝分类数据挑出最常见的一类，优先做确定性预修正，减少整次重试。

### 5.3 v14 实现缺陷（必须先修）
- **R1（P0）** 所有 `derived …` 标签在 `phase_for_label()` 中都映射为 `implement`，后台 worker 的用量又被并入主日志，而 `check_background_code_health` 只按 `phase == 'implement'` 过滤。结果是测试请求被当成代码请求，要么误触发暂停，要么掩盖真实退化。修法：排除 `parallel_spec_worker` 行以及 `derived`/`visual` 标签。
- **R2（P0）** 暂停和 `stale_input` 都会调用 `close(0)` 永久关停流水线，与方案中「空闲/收尾时恢复、只丢弃过期批次」的写法不一致。
- **R3（P1）** `close_background_specs` 会丢弃在途批次的结果（请求照样计费），后置审核随后又重做同一批节点。应给在途批次一个有上限的等待，或者先 poll 再决定。
- **R4（P1）** 私有 `Flow.metric` 写在临时目录，清理时删除。后台的 B2 拒绝分类、审核决策、引文重审指标全部丢失。应改为经队列转发，并标注 `source='background'`。
- **R5（P2）** 真实的多阶段链没有测试覆盖：`test_start_background…` 把 `prepare_derived_spec_batch` 换成了空函数。应补一个用脚本化 `text_turn` 的端到端测试。
- 次要：后台批次不会向平台补发 `design_done` 生命周期事件；需确认私有批次不会改动 `capabilities.json`/`suite-origin.json`；`R_tail` 用的是单次请求的 p90，而不是整个批次。

## 6. 实施顺序与验收

| 优先级 | 项目 | 离线验收（TDD，`should_<expected>_when_<condition>`） |
| --- | --- | --- |
| P0 | G1 在 rehearsal、pre-review 和 L2 检查点记录 LKG；G6 先 wip 后回滚 | 只做 rehearsal 成功的 derived 运行也会有 `last_startable_sha`；脏工作区加失败 rehearsal 时能恢复到 LKG |
| P0 | G2/L4 异常与终止兜底 | 模拟一次编辑中途抛异常：当前树不可启动时恢复 LKG；当前树可启动时保持不动；SIGTERM 路径 ≤20 s |
| P0 | R1、R2 | 混合日志（代码 + 测试行）不触发暂停；单个过期批次只丢弃该批次 |
| P1 | L0 写入前解析（FILE 协议） | 括号不配对的 JSX、坏 JSON、坏 CommonJS 都被整次拒绝，并带 `文件:行:列`；合法的 JSX/ESM/CJS 不被误拒 |
| P1 | L1 启动探测 + 绑定 + 依赖声明；顺序路径的启动回退回滚 | 构造「`require` 缺失模块」「`router.get(path, undefined)`」「坏种子 JSON」「未导入的组件」「未声明依赖」各一例，都能在当批被发现；计划中的缺失模块不回滚，只是不推进 LKG |
| P1 | L3 收尾 LKG 搜索；G8 使用 `startup_error_digest` | 最近 3 个提交都坏、第 4 个好时交付第 4 个；搜索受预算约束 |
| P1 | R3、R4、S1 回放 | 在途批次结果被收取；后台指标出现在主 `flow-metrics.jsonl`；S1 回放报告 |
| P2 | 结构化编辑的 `before_tool_call` 解析钩子；S2–S4；R5 | 钩子拒绝坏写入，模型在同一轮内重试；端到端流水线测试 |

每一步都要跑 `unittest discover` 全量测试，并按 `pack.sh` 检查新文件（如 `parse_check.cjs`）是否已加入显式打包清单。之后在同一任务、同一模型、同一预算下做对照运行。最终验收指标：
- 收尾 rehearsal 失败次数，以及通过 LKG 恢复的次数；
- 被丢弃的节点数；
- 每批门检查的额外耗时；
- 测试阶段的推理 token 和墙钟时间；
- 首个已批准用例的出现时间。

## 7. 未验证事项

- L1 探测的耗时只在 sheet 产物上测过；使用 SQLite 或长启动逻辑的后端可能需要调大 10 s 上限。
- `before_tool_call` 钩子能否拿到 `edit_file` 的完整结果内容，需要核对 octos 钩子的负载格式。
- S1 的质量影响只能靠回放和真实运行确认。关闭思考后的误批准数必须为 0，否则只对生成类阶段启用。
- 云端评测环境的安装方式（`npm install` 还是 `npm ci`、是否带 dev 依赖）以平台实际行为为准；G7 的检查按「必须声明」这一更严格的口径实现。
