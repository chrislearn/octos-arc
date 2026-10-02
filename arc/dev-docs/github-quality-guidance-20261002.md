# GitHub 生成质量修复（v15，2026-10-02）

本次修改针对 ARC run `8ffb73bb2a39` 暴露的基础数据和行为分岔风险。它是对生成器的改进；没有在该历史 run 上重跑官方测试，不能把本地 derived-tests 通过数当成线上通过率。

## 生成时完整交付场景前提

`fixture_delivery.py` 解析公开测试 helper 的场景 ID（如 `h.fixtureRepo('file-create')`），并以当前节点的 `case-plan.json` 补全计算表达式无法静态解析的 ID。所选记录包括仓库、组织、账号，以及显式授权/成员关系的依赖闭包和反向引用。名字按完整边界匹配，避免把 `active-old` 与 `active` 混淆。

此前 v15 已有依赖闭包，但未解析这些 helper ID；超出内联额度时只交付文件路径，文本生成模型无法从路径读取必需数据。现在 `OCTOS_ARC_FIXTURE_CONTEXT_CHARS` 是选择精简上下文的软偏好：保留选中闭包的完整 JSON。最终生成 prompt 的硬预算仍然生效，必要输入过大时走原有工具生成回退；不会截断权限或文件内容。冻结 fixture 缺失/损坏会明确报错。

需求的精确、原子规则优先于截图和概括文字；权限按每项操作定义，不假设角色能力累加。公用记录的 ID 和所有权要一致，不能通过重复初始化覆盖已有修改。

## 新增节点引导测试

保留 v15 现有节点测试、integration 对节点的上下文覆盖、引导场景、`setup_requires` 调度和生成/修复机制。新增 5 个公开 UI 场景：

1. 搜索基础 fixture 仓库及其声明的所有者，提前暴露共享数据缺失。
2. 将已存在的 release 分支设为默认分支，刷新后仍保留，main 文件不变。
3. 编辑文件产生真实提交；历史修订保留原始内容。
4. Write 创建 Issue 和评论，Maintain 指派/关闭/重开，Read 看到保存后的状态且没有修改入口。
5. 发布一位 reviewer 当前 head 的待提交评论，其他人的草稿继续私有。

变更型场景使用各自独立的仓库 fixture，通过公开 UI 和刷新检验持久化；不依赖私有重置 API。GitHub 冻结 review revision 更新为 6。内部共 116 个案例；按 v15 既有策略导出 47 个节点 spec / 110 个案例（内部 6 个 integration 案例不导出）。Sheet 未修改。

## 验证和发布边界

Python 回归覆盖 fixture 选择、真实生成 prompt 硬预算、冻结审核/导出和原有修复机制；Rust 测试验证嵌入测试树。新增 5 个浏览器场景已在修复后的独立控制应用上通过，用于验证测试可执行性；它不是一次新的 v15 模型生成应用验证，也不表示全部 110 个导出案例通过。

冻结 spec 被 Rust 内核编译嵌入，修改 Python 或 spec 文件后必须重建内核并一起打包。使用 `sh arc/build-kernel-docker.sh` 构建 Linux x86_64 / GLIBC <= 2.39 内核，再执行 `sh arc/pack.sh`；提交包需包含 `fixture_delivery.py` 和该版本的 `bin/octos`。
