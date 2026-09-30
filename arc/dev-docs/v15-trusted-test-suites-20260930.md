# v15 可信测试套件直接驱动节点生成

当前修订：内嵌和项目生成套件统一使用 `derived-tests` 名称。完整源码保留 GitHub 104 项、Sheet 123 项测试；`INTEGRATION-*` 暂时不写入项目。项目只导出 GitHub 47 份 REQ spec / 98 项用例、Sheet 24 份 REQ spec / 72 项用例，计划、审核记录和哈希均对应实际导出文件。以下原始验证记录保留为历史证据。

`v15` 从当前 `v14` 的 `23e08b94` 切出，合并 worktree 提交 `06993281`，合并提交为 `67f45c3e`。独立 worktree 保留，后续流程修改在 `/home/chris/Works/octos-arc` 的 `v15` 完成。

## 使用

```bash
python3 arc/main.py /path/to/hackathon--sheet \
  --test-suite hackathon--sheet --trusted-tests --output-dir /path/to/output

OCTOS_ARC_TEST_SUITE=hackathon--github OCTOS_ARC_TRUSTED_TESTS=1 \
  python3 arc/main.py /path/to/hackathon--github
```

套件统一名称为 `hackathon--github` 与 `hackathon--sheet`。没有官方 spec 时，Python 调用新的 prompt 命令；`--trusted-tests` 可以显式请求这一步。命中后跳过在线 spec 流程，未命中或命令失败则走原有机械生成与审核流程。

Python 发出的调用形如：

```bash
octos arc generate-test-suite \
  --prompt 'Read the requirements in "/task/requirements.yaml". For task "hackathon--github", generate the complete Playwright test suite spec, shared business model, domain contracts, requirement constraints and test obligations. Return whether all generated tests and contracts are trusted.' \
  --output-dir /output/derived-tests \
  --requirements-sha256 <original-tree-fingerprint> \
  --exclude-integration
```

命令在内部固定解析 GitHub、Sheet 两个任务，不调用模型生成新文件内容。命中时提取已内嵌的整套 specs、fixtures、公共业务模型、领域契约和需求约束，返回 `success: true`、`generation: "embedded"`、`trusted: true`。该可信返回沿用已有的冻结文件、需求指纹和 review 绑定；可信表示测试与契约已源审查并冻结，不是应用通过了这些测试。

未命中内嵌任务时，命令退出码为 1，输出 `success: false`、`trusted: false`，不创建目标目录、不写入规格、不调用模型。Python 收到失败后继续原有机械 spec 生成和后续审查，不阻断任务。`octos arc tests` 保留为目录查询与直接提取工具，Python 的运行入口采用新的 prompt 命令。

## 运行流程

1. 加载原始 requirements；没有官方 spec 时，以读取 requirements 并生成测试的 prompt 调用 `octos arc generate-test-suite`。
2. octos 返回 `trusted: true` 后，加载 `app-design.json`、`domain-contracts.json`、`requirement-contracts.json`、`test-obligations.json`，不重新生成或复查这些模型。
3. 不启动 `LayeredTests` 的基础 spec 生成和复杂业务 spec 队列；跳过机械 spec 生成、在线 case review、spec 审计、完整性补生成、后台 spec 等待及生成结束后的 spec review 阶段。
4. 按依赖顺序，节点直接使用已加载的契约与业务约束生成代码，然后执行该节点的冻结测试与应用代码修复。可信模式每次生成一个节点，即使配置了 sibling batch 也不会先生成一组节点再等待测试。
5. 保留实际测试执行、应用修复、最后的整套回归与启动测量。失败不会通过修改冻结测试消除。

GitHub 的 47 个 ATOMIC 节点对应 47 份 spec / 98 个用例；Sheet 的 24 个 ATOMIC 节点对应 24 份 spec / 113 个用例。父层的公共入口与业务约束保留在各叶适用的共享模型和契约中。按用户要求，未添加新的节点覆盖硬校验。

修复了原有名称解析仅支持 `REQ-1.2` 的问题：Python 和 Rust 现在也支持 `REQ-1-2-1.spec.ts`，这些测试实际归属其 ATOMIC 节点，不再被截成 `REQ-1` 放进未分配的全局测试集合。

可信流程回归测试使用真实 Python coordinator 和 `node_cycle`，stub 模型与产品执行，验证 Sheet 24 个节点逐个进入 acceptance，以及所有 spec 生成和审计入口都未调用。这项验证是控制流测试；真实产品测量另行记录。

最终回归：Python 2178 项（2150 通过、28 项既有跳过）；Rust 133 项通过、1 项既有忽略；CLI 构建和实际 prompt 命令调用通过。验证命令和证据保存在 `v15-trusted-test-validation-20260930.json`，包含两个任务的可信返回及未命中时不写文件的实际 CLI 证据。

线上需部署包含新命令与内嵌套件的 Rust kernel，并使用 v15 Python bundle。旧内核命令失败时 Python 会走机械生成回退。本次只修改分支和构建验证，没有发布线上版本。
