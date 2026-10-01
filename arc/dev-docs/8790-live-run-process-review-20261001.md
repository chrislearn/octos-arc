# GitHub 进行中运行的失败原因与生产流程复核

对象：[8790a4b2c014](https://arc-bench.com/runs/8790a4b2c014)，v15.5 / qwen3.7-plus。日志冻结至 **2026-10-01 20:43:21 北京时间**（12:43:21 UTC）。仍在 Stage 2，第 8/47 个节点创建团队的第三轮工具修复；Stage 3 尚未评测。本文不是最终成绩，也未修改生产代码。

主要结论：前四个节点已经修复通过；目前未全通过，混合了真实功能缺失、内部测试错误、测试前置导航未就绪、代码生成控制状态残留和上游请求失败。最优先解决的是**节点验收的前置能力闭包与冻结测试审计**，随后修正重复上下文和成功纠正后的重试控制。增加时间、轮数或上下文不能单独消除这些原因。

## 每个已执行节点的结果

| 节点 | 各轮结果 | 原因和证据限度 |
| --- | --- | --- |
| 注册 REQ-1-1-1 | 2/3 → 3/3 | 首次失败在密码输入值。修复摘要说清空提交后的密码；File 中 RegisterPage 的错误分支确实清空两个密码字段。 |
| 登录 REQ-1-1-2 | 3/7 → 7/7 | 四例失败于 helpers.ts:44 的 Account menu。修复摘要指向 cookie/session；当前 File 显示后端设置 cookie、前端读取 /api/me。缺少修复前源码，不把摘要当作完整因果复现。 |
| 找回密码 REQ-1-1-3 | 0/2 → 0/2 → 2/2 | 首轮恢复 API 返回 500，accounts undefined；日志同时指出 CommonJS 导出被覆盖。导出修好后仍有 UI 断言失败，后续工具修复加入未登录布局和 Sign in 链接才通过。 |
| 退出登录 REQ-1-2 | 0/2 → 1/2 → 2/2 | 初次修改使旧范围 12/12 → 6/12。修好菜单后旧范围恢复；剩余用例卡在重复打开菜单，受控 Popover、导航时关闭后通过。File 可确认受控实现。 |
| 改密码 REQ-1-3 | 0/2 → 1/2，未验证 | 重复索取 auth.js 而终止实现；缺失入口导致两次 60 秒等待。修复后剩余失败为内部 OR 文本定位器歧义，harness 保留 unverified。 |
| 组织仓库 REQ-2-1-1 | 0/1 | 重复索取 organizations.js/App.jsx 后未完成生成。先在全局 Search 超时；File 中组织仓库页也只有占位文字，业务本身未实现。结构化修复 1004 秒遇到 HTTP 400 / proxy_error / unexpected EOF；fallback 195 秒超时，均未尝试写入。 |
| 创建组织 REQ-2-1-2 | 0/2 → 1/2 → 2/2 | 锚点失败经协议纠正成功，却再次 requote。后续 Owner 文本断言失败；拆开用户名、角色文本后通过。 |
| 创建团队 REQ-2-2-1 | 0/0 → 0/2 → 0/2，修复中 | 首次缺 Outlet 导入，修复回复又使用错误协议。纠正后先卡 spec-owner 登录；修好种子后，两例都卡 helpers.ts:64 的 Search，每例约 60 秒。12:41:21 开始第三轮工具修复。 |

12:41:21 最新通过回归是 **16/16，五个 spec**：注册、登录、找回密码、退出登录、创建组织。不含改密码、组织仓库、创建团队和后续未生成节点；不能解读为整套通过率。105 例是内部冻结测试，页面的 100 scenarios 也不是该内部用例数。

## P0 测试前置操作链未进入调度

云端 helpers.ts 的 organization() 先调用 repo()，后者从首页 Search 搜索仓库，再通过仓库内组织链接进入组织页。因此组织仓库和创建团队用例依赖：

首页 → 全局 Search → 仓库结果 → 仓库页 → 组织链接 → 组织页 → 当前功能

实际排序却是组织仓库第 6 个、创建团队第 8 个、全局搜索 REQ-3-1 第 13 个、仓库概览 REQ-3-3 第 15 个。冻结 case-plan 对上述用例只记录各自叶节点；创建团队声明依赖只有创建组织。topo_order 只读取原需求 dependencies，无法补足 helper 带来的依赖。

20:40:56 的团队两个真实失败均为 helpers.ts:64 的 Search fill；组织仓库也是同一位置。File 中 HomePage 只有 View Organizations，组织仓库页只有 Repository list 占位内容。这不是只相信模型“超出团队范围”的自述。团队目标动作尚未到达，不能据此判断创建 API 正确或错误；组织仓库则还有独立的真实功能缺失。

建议分别记录原需求依赖、helper 调用闭包、fixture 前置状态、公开入口能力。实现可以继续，验收及修复先判断前置链是否就绪；不就绪记 waiting_for_capability，并在前置能力完成后重测，不能算 pass 或遗忘。

可选方案：节点测试通过已有的公开组织入口进入，完整仓库搜索链保留在后续流程测试；或者先生成共享搜索/概览入口，再执行依赖它们的原用例。两者均保留业务断言、真实公开 UI 和完整流程覆盖，不能以私有 API 或硬编码产品路由绕开。仅补 metadata 而不接入调度也不足够。

approved_checkpoint_specs 虽检查声明依赖，但没有 helper 能力闭包；可信冻结套件跳过测试生成审计，也不会自动发现这里的遗漏。

## P0 改密码测试的歧义断言

冻结 REQ-1-3.spec.ts:17 用未限定范围的 getByText(/Current password is incorrect|Password confirmation does not match/) 调用 toBeVisible。用例同时提交错误当前密码和不匹配确认密码。

File 显示后端返回两个字段错误，前端显示两个独立 alert；原需求允许对应错误提示，但原定位器要求唯一元素，两个合法提示同时出现就报 strict mode violation。本地合成 DOM 用原表达式实际复现 **两个匹配、strict-mode 失败**；限定可见 alert、选择一个合法错误后通过。该探针不是云端完整应用复测。

当前 conflict 分支正确保留未验证，没有诱导删除合法错误。应离线审计并发布新测试身份，保持“其中一个或多个合法提示”的语义，随后仍执行原用例尾部的退出/旧密码登录检查。**原用例在歧义断言处提前结束，凭据不变的尾部检查尚未完成。** 不可把 1/2 直接改记为 2/2，或静默修改运行中的冻结套件。

## P1 生成与修复控制状态

**重复上下文恢复。** context_evidence 对同版本重复读取抛异常，防止无限循环是合理的；但 codegen_turn 的可纠正结果不含 needs_context_repeated，节点随后直接测试旧应用。改密码和组织仓库均走此路径。建议同一预算里转受限读取/编辑，或标记未实现并排队续作；保留写入保护。记录路径、版本和当前 prompt 是否实际包含完整源码，不能一概解释为 context window 不够。

**成功纠正后的冗余重试。** 锚点失败向累计 refused_paths 写入路径，成功纠正只清空本次 last_codegen_refused；node_cycle 仍用累计差集判断需要重试。真实 codegen_turn、mock 模型回复探针复现：outcome=applied、源码已写、当前 refused 为空，但调用层差集仍为 App.jsx。与 20:19:46 已写两文件、20:19:50 又 requote 的日志吻合。历史集合可补源码，但重试应使用本次仍未解决且版本匹配的状态。

**确定源码错误的修复次序。** Outlet 未定义已在 early check 发现，仍排入下批；CommonJS 导出丢失也仅为 warning。建议当前路径的确定错误先做小范围修复、编译/导出 smoke，再业务验收；动态导出和不确定跨模块状态不能机械变成硬拦截。repair_overwritten_route_exports 当前只有定义、没有调用，不算已接入的生产补修。

**传输失败恢复。** 组织仓库两个修复段都没有源码写入，node_repair_turn 返回 False 后 acceptance_loop 直接 break。节点 3000 秒上限与本轮 1200 秒 allowance 不同，不能说节点总预算必然耗尽。代理主要按 HTTP ≥500 重试，400 包装的 proxy_error/EOF 不走该分支。建议在无源改动且有预算时做有限传输恢复或排队重试；保留错误身份和可能发生用量的 unknown 状态，不无限重试。没有 request ledger，不能把 1004 秒全算成模型思考或某次请求等待。

**共享 UI 保护。** 退出登录曾破坏旧范围，现有 affected regression 发现并联合修复，这是有效机制。仍应减少 App.jsx 大范围替换，按 Layout、认证状态、公开页面边界编辑；初次实现纳入菜单关闭、再打开、导航及确认取消的状态转换证据。

建议顺序：前置能力准入和 oracle 冷运行审计 → 重复上下文恢复和历史拒绝状态 → 确定源码错误的小范围补修 → 有界传输恢复与共享 UI 状态保护。

## 当前生产版本的对应关系

本地 v15.5.zip 用生产 adapter_fingerprint 算出的指纹与线上一致：68b50e4a…e3989e，共 64 个 Python/blueprint 文件；ZIP SHA-256 为 7ecaf658…b23349。逐字比较部署包与当前同名文件，main.py、acceptance.py、quality_control.py、flow_policy.py、requirement_order.py 等一致；唯一不同的 Python 文件为 llm_proxy.py，当前差异主要为 GLM 推理配置及用量字段。本次使用 Qwen，不能据此声称 EOF 路径已改善。

上述调度、上下文恢复、历史拒绝状态和验收分支能反映当前核心生产实现。但整个工作区含额外开发脚本，其总指纹不相同。本文用该 ZIP 的 octos 内核离线导出了 **47 specs / 105 cases** 并验证本地冻结身份；相关测试与云端 File 内容一致，没有重写原测试。线上未提供内核摘要及完整套件 manifest；adapter 指纹不覆盖二进制，因此不能仅凭它证明线上内核及全部测试逐字同版。

当前已包含按 case 估算验收时间、测试 wall timeout 与启动故障区分、局部结果保留和可启动交付的收尾改进，不能直接套用旧报告的相应缺口。此次已确认的应用异常（500、Outlet 未定义）仍以 build/start 类摘要进入修复，后续可区分启动故障、业务请求异常、操作链前置缺失；不能把真实应用异常说成单纯测试超时。

## 证据和范围

- [线上日志与源码摘录](../diagnostics/8790a4b2c014-review-20261001/cloud-observations.json)：登录 Stdout/File DOM 观察后转录，不是原始完整 stdout。
- [冻结套件导出 receipt](../diagnostics/8790a4b2c014-review-20261001/export-receipt.json)：同指纹 ZIP 内核离线导出，官方/内部测试口径分开。
- [控制流探针](../diagnostics/8790a4b2c014-review-20261001/probe.py)、[结果](../diagnostics/8790a4b2c014-review-20261001/probe-results.json)：未调用模型，回复 mock，真实应用器和拒绝状态运行。
- [Playwright 定位器探针](../diagnostics/8790a4b2c014-review-20261001/oracle-probe.cjs)、[结果](../diagnostics/8790a4b2c014-review-20261001/oracle-probe-results.json)：合成两条 alert 的控制实验，不代表完整应用通过。

下载按钮等待 60 秒未取得完整项目 ZIP，因此通过 File DOM 检查 App.jsx、auth.js、organizations.js、sessions.js、server.js 及相关测试/helper。文件来自持续变化的单独读取，不能当作原子完整项目快照；没有云端 .arc 请求账本、每轮 prompt 或完整 trace。本文没有调用付费模型、暂停/取消云端、修改生产代码或冻结测试，也未重跑官方评测。
