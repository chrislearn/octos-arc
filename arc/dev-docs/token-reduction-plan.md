# 少 token 完成 ARC-Bench：调查、核查与方案（2026-09-17）

本文是一次调查的结论，不是规范。每条数字标明来源：**实测**（本机跑出来的）、**记录**（CHANGELOG
里的云端/本机运行）、**推算**（由前两者算出）。没有标的就是推测。

## 1. 现状

### 1.1 榜单（2026-09-17 拉取，账号 `chrislearn`）

| 赛道 | chrislearn | 同一代码的 `octos` 账号 | 对手上限 |
|---|---|---|---|
| smoke | 7/37，¥0.01 | 4/37，¥0.003927 | ¥0.003099（第 2；第 1 是 ¥0.000072、0s，疑似不生成） |
| smoke-evolution | 6/24，¥0.01 | 4/24，¥0.005496 | ¥0.004617（第 3） |
| ticket-booking | 5/45，¥0.23 | 3/45，¥0.17 | 前两名 0% 功能率或 ¥0.000423 |
| arc-bench-web | 未上榜 | 未上榜 | 第 3 名 59% / ¥111 |

两条推论：
- chrislearn 的提交是旧包（同题费用是 octos 账号的 2.5 倍）。**不改代码重交**就能挪名次。
- Web 赛道我们云端跑过 `2b6406557024`：46/66 = 69.7%，¥47.99（记录）。进榜即第 3 名量级，费用是现第 3 名的 43%。
  **Web 是提交问题，不是优化问题。**

### 1.2 Token 去向（记录：keep `2224a9013528`，tool 模式，Round 35 之前）

1,152 请求，28.05M prompt（91% 缓存命中）+ 0.76M completion，¥16.58。按拟合价（¥2/M 输入、¥0.2/M
命中、¥7.5/M 输出）拆：未命中输入 ≈¥5、命中 ≈¥5、输出 ≈¥5.7 —— 三份各占三分之一。

平均 **24,350 prompt token/请求**（推算）。一次 tool 模式 turn 的固定开销（实测，见 §3.3）在适配层
trim 之后 ≈2,190 token，所以 **~22,000 token/请求是对话历史**。

### 1.3 smoke 实测（本机 `arc-output/try1`，2026-09-16）

prompt 495 + completion 380 = **875 token**。与 Round 32 记的「≈845」一致；Round 33/34 声称的「≈260」
**从未在实测中出现**。原因：`tiny_turn` 把整个需求 JSON（含每条 GIVEN/WHEN/THEN，与 spec 内容重复）和
spec 文件都发了（1,836 字符）；输出 1,444 字符含 doctype/head/`<style>`/注释/空行 —— 因为
`prompts/tiny-prompt.md` 现在写的是 "including required styling"，Round 33 那条「no CSS」在 PR #100
通用性审查里被删了。这道题的需求原文是 "No styling or layout is required"。

## 2. 已做（commit 见 git log）

- **P1 · 后端按区域拆模块**：契约改为 `server.js` 只做静态服务与路由分发，新增路由进
  `backend/routes/<area>.js`；`relevant_sources` 只把后端入口排第一（入口名从 start 脚本读）。
  把每节点「完整返回改动文件」的输出从 O(N²) 变成 O(N)。**未用模型评测**。
- **自带内核**：`pack.sh` 把 `target/release/octos` strip 后打成包内 `bin/octos`，校验 ELF 是 Linux
  x86_64；`find_octos()` 补回 `zipfile` 解压丢掉的可执行位。36M 包，上传上限未确认。
  **云端第一次用它就卡死**（`e70711133d37`）：本机 glibc 2.43 编的内核要求 GLIBC_2.43，平台加载不了。
  现在 `pack_kernel.py` 按官方 release 的上限（GLIBC_2.39）拒绝这类构建、退回下载路径；本机构建的内核
  要上云得走 CI release 或固定 glibc 目标。见 CHANGELOG 同日条目。
- `DryRunDriver.without_tools()`：修好之后 codegen 树的 dry run 才能走完（之前第一个节点就 abort）。

## 3. 核查：调查过程中说错或需要修正的

诚实记下来，免得后面的人踩同一个坑。

1. **`relevant_sources` 的排序改动今天是行为等价的。** `codegen_context_fits` 要求整个应用放进
   `OCTOS_ARC_CODEGEN_CONTEXT_CHARS`（90,000）减 spec 之后的预算，通过时整个应用必然放得下，省略分支
   在 implement 路径上取不到。实测（spec 8,000 字符）：应用 60k → codegen；85k / 200k → **tool 模式**。
   keep 云端产物 86k 字符，**其后段节点早就在走 tool 模式**。Round 35「每节点单请求」对任何长过 ~82k
   的应用都不成立。这就是 §5 选 P1b 的原因。
2. **内核「轮内不裁剪工具结果」的说法是错的。** `compaction_tiered.rs` 每次迭代清掉 >8 KiB 的工具
   结果（`DEFAULT_TIER1_MAX_SIZE_BYTES_PER_RESULT`），固定最近 K 个文件的读取不被清（#2131 pin），并对
   同一文件+范围的重复读取去重。在 ARC 里失效的只是**按用户轮龄**的 stale 清理（ARC 每 session 一条
   user 消息，`DEFAULT_TIER1_MAX_AGE_TURNS = 5` 永远到不了）。我先前引用的 `prune_tool_results()`
   是另一个默认关闭（`workspace_policy.rs:94` 为 `None`）的机制，引错了。所以 22k/请求的历史来自
   <8 KiB 的小结果、被 pin 的工作集、以及 assistant 自己的 tool_call 消息 —— 内核侧的杠杆比我说的小，
   而且没量过。
3. **Round 35 的 dry run 记录复现不出来**（见 §2 第三条）；Round 33/34 的 token 估算没有实测支撑（§1.3）。
4. 第一次榜单解读用的是 `octos` 账号，不是 `chrislearn`（§1.1 已更正）。

## 3.3 内核一次 tool 模式 turn 的线上载荷（实测：真二进制 + 本地假 provider，生产路径）

| | 字节/字符 |
|---|---:|
| 请求总字节 | 21,154 |
| system prompt | 7,422 |
| 15 个工具 schema | 13,715（`spawn` 一个 4,806） |
| 实际内容 | 17 |
| 适配层 `trim_request` 之后 | 8,322（system 2,451；9 个工具 5,603） |

固定开销已经被适配层代理砍掉 60%；内核里再删是干净，不是新省。**但 `rust_engine.py` 不走这个代理**
（只 import 了 `configured_model_routes`），切 `OCTOS_ARC_ENGINE=rust` 会静默失去每请求 ≈3,377 token
的裁剪。切引擎前先量。

## 4. 方案清单（按收益 / 风险）

| # | 改动 | 层 | 预期 | 风险 | 怎么验 |
|---|---|---|---|---|---|
| P0 | 用当前包重交 smoke / evolution / TB；Web 首次提交 | 无 | 名次直接挪 | 无 | 榜单 |
| **P1b** | 放宽 `codegen_context_fits` + 未引用文件写保护 + 修复轮同样放宽 | 适配层 | 大树的节点从 36 请求 → 1–3 | 中：省略了模型需要的文件 → 多一次修复 | keep 本机对比 |
| P2 | codegen 提示词：源码按路径固定序放前，需求放最后 | 适配层 | 输入命中缓存，费用 −60~80%；token 数不变 | 中：需求挪到末尾对指令遵循的影响 | 先离线量前缀重合度 |
| P3 | 只引用命中 >0 的文件 + 入口 | 适配层 | 后期节点输入 −40% | 中 | 与 P1b 合并考虑 |
| P4 | 修复轮按目标文件分组，一组一请求 | 适配层 | 解决 20 个失败挤 10 请求；输入减少 | 低 | 2b64 的失败列表回放 |
| T1 | tiny 层：需求只发 description，不发与 spec 重复的 scenarios；样式「按需求」 | 适配层 | smoke 875 → ~400 token，¥0.0039 → ~¥0.0017，够到第 2 | 低 | 本机 smoke |
| K4 | deepseek `reasoning_effort` implement 轮改 none | 配置 | 输出（含推理）下降 | 低 | 本机 TB 对比通过率 |
| K3 | Rust 引擎接上 trim 代理 | 适配层 | 只在切引擎时有意义 | 低 | §3.3 的测法 |
| K1 | 内核：量 tier-1 之后历史里还剩什么，再决定 | 内核 | 未知 | 中 | 先量 |

## 5. 本轮选 P1b 的理由与设计

**理由**：Web 六题占 token 的 99.9%；其中 tool 模式回退是最大单项（36 请求 × 24k token ≈ 864k
token/节点）；而 §3.1 证明这个回退在 keep 量级就已经发生。P1b 从源头不进 tool 模式，且是 Python
改动，不需要重编内核。

**盈亏**（推算）：一个节点若 codegen 失败，最多多花 1 次 implement + 2 次 codegen 修复 ≈ 3 × ~26k
token 再进入和今天一样的 tool 模式，代价 <10%；若成功，从 864k 降到 24–72k。**成功率 ≥ ~9% 即回本。**

**设计**（三处，缺一不可）：
1. 门槛 `codegen_context_fits`：从「整个应用放得下」改为「spec 放得下 60% 且后端入口放得下」。
   `relevant_sources` 本来就会在预算内引用、预算外列名。
2. **写保护**（让省略在构造上安全）：codegen 回复里的 FILE 块，若目标文件**已存在于磁盘**且**未被完整
   引用**到提示词里（省略、或只引用了片段的 "too large to quote whole"），拒绝落盘、保留磁盘版本、
   记一条 correction 给下一轮。新文件与被引用文件照常写入；tiny 层的 `raw_target` 不受影响。
   靠提示词请求模型「别改没看到的文件」不算保护。
3. 修复轮 `codegen_repair_prompt` 去掉「有省略就回 tool 模式」的拒绝 —— 有了写保护，它和 implement
   同样安全；不改这条，第一次失败就把节点送回 36 请求，收益蒸发。

**不做的**：不改 `relevant_sources` 的排序规则（入口 → 命中数 → 小文件优先，已经合理）；不动 tool 模式。

**验证**：unittest 先红后绿；keep dry run 走通；`OCTOS_ARC_CODEGEN_CONTEXT_CHARS` 缩小到让 dry run
的占位应用超预算，确认节点仍走 codegen 且写保护有日志。**真实模型对比留待有额度时做**，做之前不宣称
数字。

**结果（2026-09-17，已提交）**：unittest 307 通过。keep 32 节点回归 dry run 0 abort、0 次 tool 模式回退。
写保护实跑（29k 页 + 10k 预算 + evolution 模板）：REQ-2 走 codegen，占位回复对被省略页面的 FILE 块被拒，
原页完整保留，日志见 CHANGELOG 同日条目。夹具教训：模板必须至少通过一个 spec，否则 Round 30 规则会先把它
丢掉，guard 没机会触发。

**下一步（未做）**：有额度时用 keep 做一次真实对比 —— 记录 请求数/节点、prompt/completion token、
通过数，和 `2224a9013528`（36 请求/节点、28.8M）并排放。那之前 P1/P1b 都只是「应该省」。
