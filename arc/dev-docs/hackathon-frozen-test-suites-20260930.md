# Hackathon 内嵌冻结测试套件

本分支基于 `a54685fb`，独立 worktree 为 `/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc`，分支为 `codex/hackathon-frozen-specs`。不修改 `/home/chris/Works/octos-arc` 的文件。

## 入口与名称

统一名称采用已有 ARC task ID：`hackathon--github`、`hackathon--sheet`。

Python 入口支持：

```bash
python3 arc/main.py /path/to/hackathon--sheet --test-suite hackathon--sheet --output-dir /path/to/output
OCTOS_ARC_TEST_SUITE=hackathon--github python3 arc/main.py /path/to/hackathon--github
```

显式名称匹配到内嵌套件时优先采用它。未知名称沿用现有官方测试/需求派生流程。不指定名称时，现有官方 public-tests 优先；没有官方测试时，按原始 requirements 根标题和整棵树的 SHA256 自动匹配。自动匹配遇到 requirements 变化时沿用派生流程；显式选择已知套件而 requirements 不同则报错，防止把错误任务的测试当作冻结测试。

GitHub 根标题为 `GitHub Collaboration Platform Core Requirements`，Sheet 为 `Core Requirements for an Online Spreadsheet Data Workspace`。指纹计算使用整棵原始树的 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(',', ':'))`，包括 atomic prose、scenario 与继承入口契约。Python 在 seed reconciliation 前保留原树；Rust 同样逐层排序 JSON 键。

Rust 入口：

```bash
octos arc tests --list
octos arc tests --name hackathon--sheet --output-dir /new/suite/directory --requirements-sha256 <catalogue fingerprint>
```

Python 调用实际 octos 提取到 `<output>/.arc/frozen-tests/<task-id>`，不会复制仓库中的 TS 文件。`rust-embed` 的 `debug-embed` 确保 debug 与 release 都从二进制读取完整文件。注册表、规格、helpers、fixtures、原始 YAML、review 和 README 一起内嵌。Rust 在写盘前校验所有字节与 review；暂存目录在同一文件系统中一次 rename 发布，完全相同的已有目录可重复使用，已修改目录不会覆盖或拼接。

## 设计与冻结

源 requirements 与下载目录中的两份 YAML 一致。GitHub 有 47 个 ATOMIC 节点/98 个用例，Sheet 有 24 个 ATOMIC 节点/113 个用例，共 71 份 spec、211 个用例。逐条审查完整 atomic description、ROOT role matrix、继承页面/字段/状态契约，再生成一个 atomic 节点一个 spec 文件。部分 Sheet scenario 是泛化或损坏的模板，按更明确的 atomic 正文解释，不从无内容模板编造路径和业务。

Sheet 设计由并行 subagent 完成，主线程再复核。所有测试经业务原文 review 后冻结；`review.json` 逐 case 记录需求全文、来源、review 状态和 spec 文件哈希，`suite-origin.json` 记录全文件哈希与需求指纹。冻结指的是本次运行中不重新生成、不允许模型改写规格；source review 不代表已经在真实产品上运行通过，也不是 ARC 官方 spec 或官方评分。

`fixtures.json` 是公开初始数据契约，不指定私有 seed/reset API 或产品 URL。GitHub 每个可变测试独占一套组织/仓库记录，账户的 role grant 明确区分 Read/Triage/Write/Maintain/Admin，团队层级不隐式传播权限。公共组织也有独立私有仓库用于验证访客不可发现。commit 有可读 parent 和过去时间；PR diff、merge 与保护规则以实际 branch 文件和当前 compare commit 为准。Sheet 除保留的 Q3 Sales 入口数据外，通过公开 UI 创建独立空 workbook，覆盖坐标、公式栏原文、复制/剪切相对引用、结构规则移动、CSV、sort/filter/pivot 与 undo/redo。

生成提示词显式标注 reviewed/frozen/internal，并要求读取 fixtures 和 README、实现完整 requirements。两种引擎直接使用这些 specs，不进入在线派生 spec 的生成/review 队列。保护目录仍走既有写入拒绝与快照恢复；Python 执行前对比提取时留存的 manifest，Rust 执行前对比编译进二进制的全部文件。Python 首次提取还核对 Rust receipt 中的 manifest 哈希，修改规格后重算本地哈希也不能替换冻结记录。Playwright observer 只注入 staging 副本，原套件保持完整。

共享业务模型同时内嵌 `app-design.json`、`domain-contracts.json`、`requirement-contracts.json`、`test-obligations.json` 和 `business-review.json`。沿用现有 app-design schema 的 `data_model/domain_contracts/contracts/commands`，GitHub 16 个实体，Sheet 9 个实体；公共身份、权限、输入原文/显示值、原子 effects/rejection、状态转移和持久化相互对应。确定性 requirement contracts 保留全部 scenario 原文，源约束 ledger 保留 1667/339 条逐叶适用的 atomic/ancestor 源条款。ledger 是源约束目录，不声称每个条款已经有可执行 case witness。

Python 把模型加载为 `app_design_doc`，把契约和 ledger 直接加载进现有上下文，并把惯用读取副本写到 `.arc/design`；冻结原件仍是 authority。已匹配冻结套件的 `app_design` 不调用模型重新生成。为避免完整源条款文档在每个节点挤满 prompt，Python 携带共享身份与当前节点的完整合同，Rust 同样注入当前节点模型，完整文件保留在已保护的套件目录。

复现规格与冻结记录：

```bash
python3 arc/build_frozen_tests.py
# 先完成业务源审查与 TS/Playwright 检查，再记录冻结：
python3 arc/audit_frozen_tests.py --freeze
python3 arc/audit_frozen_tests.py
```

修改 recipe/helper 后必须重新审查、冻结并重编译 Rust；不允许只更新 review 标记来掩盖产品或测试问题。

## 验证与上线

已完成：

- Python 集成/业务契约相关 214 个测试通过。
- Rust octos-arc 全量单元测试 132 个通过，1 个原有测试忽略。
- 最终 211 个业务用例通过严格 TypeScript 编译和 Playwright test discovery；30 处静态 clipboard 字面量经 TS AST 检查，没有错误的字面 `\\t`/`\\n`。
- 主线程 7 项真实 Chromium helper 自测通过；Sheet subagent 的额外 7 项 helper 自测通过。
- 实际 CLI 二进制提取两个套件、重复使用、冻结文件篡改恢复、业务模型直接加载、Playwright observer staging 均通过，未调用生成模型。
- 将 worktree 的 `arc/frozen-tests` 暂时移走，在 `/tmp` 用最终二进制执行上述链路仍通过；随后立即恢复源目录，确认提取字节来自 Rust 二进制。
- Python bundle 中包含 `frozen_suites.py`，三个相关入口的 zip 内源代码可编译；TS 套件只随 Rust 内核携带。

完整验证计数、命令、需求指纹、二进制哈希和两个套件的提取证据保存在同目录 `hackathon-frozen-validation-20260930.json`。

基础设施验证与真实产品的 runtime pass 分开记录；`runtime_status` 始终是 `not_run_against_product`，直到实际执行产生独立证据。

`arc/pack.sh` 已加入 `frozen_suites.py`；规格字节只由 Rust kernel 携带。线上必须发布/打包包含本分支的 kernel，再使用相应 Python bundle。旧 kernel 自动模式可回到原流程，显式 suite 选择则提示重建内核，不能把旧版本描述成已内嵌。保留 pack_kernel 的 Linux x86_64/glibc 平台兼容校验；本机生成的验证二进制不是线上兼容性证明。

额外修复：原基线 codegen-prompt 的 `{items:[...]}` 被模板渲染器误当作变量，会阻断代码生成。此分支改为转义 `{{items:[...]}}`，渲染后的提示词仍显示原文字面内容。
