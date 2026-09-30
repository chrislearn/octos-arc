# hackathon-test2 手工恢复与 derived-tests 复审（2026-10-01）

按用户最新授权直接修复现有两个项目；本轮没有调用 `.test_data` 模型。原生成终态、原 REQ 文件、最初验收报告和 trace 保留在各项目 audit 中。旧失败的生成终态描述历史生成结果，当前恢复成绩以 recovery 的独立测量为准。

| 项目 | 原生成最终成绩 | 本轮同版 REQ 验证 | 强化版 REQ 验证 |
| --- | --- | --- | --- |
| GitHub | 68/98 | 98/98（前一源码版本，对照） | 99/99（最终源码） |
| Sheet | 61/72 | 72/72 | 72/72 |

两项目均使用原内置 blueprint 的 collection/store/request/server/build 核心。Sheet 已提交 `ed7fbf591021e57906d8f3a91d219359671fd20d`。GitHub 已提交 `8e93a932db3b59cadfc40ae999b0f4a6f439c45f`。Octos 源测试修改已提交 `a56bab32`，同步回当前 checkout 后 Python 21/21 再次通过。

## 确认的测试缺陷与修正

1. Sheet 的 `values` helper 将整格 DOM 文本当作值，包含下拉按钮的 `▼`，因此合法的 `Closed` 被判断为 `Closed▼`。现在读取单元格内容时排除控件/装饰文字，仍精确比较其余内容；下拉按钮、选项和实际编辑拒绝仍单独验证。
2. GitHub 的 `h.text` 可以匹配填写后的 textarea。在评论和新文件提交后，第一次反馈断言会提前通过，随后 reload 抢在持久化/导航前，既可能假通过，也可能误报保存失败。现在排除 input、textarea 和 editable 内容，等待真正的公开结果。
3. 没有删除正确的业务用例，没有 skip/only/fixme；Fork 的 button 角色、全部字段错误、PR/current-commit 保护与持久化断言均有原需求依据，修正位置是实现。

新增/加强指导：注册账号经 email 登录、reload、独立会话 username 登录；过滤保留表头与控件；行列修改后从首页打开同一工作簿与 URL；修改校验限值保持完整规则范围；pivot 纠错成功清除旧错误。登录指导属于 REQ-1-1-2，并注明此前 REQ-1-1-1，首注册节点保持独立。

## 实现修正与代码复核

Sheet：正则坐标解构、多字母列计算、过滤保留表头、pivot 失败在活动编辑区显示并成功时清错、重开校验规则按原 range 保存/删除。两个操作 seed 现在为正常持久工作簿，首页重新打开保留同一记录，移除每次点击创建新记录的 factory 入口。

GitHub：注册原生邮箱校验阻挡应用错误集合、取消退出时的菜单遮挡、Fork 角色、缺失 seed 关联闭包、团队/组织成员实际创建流程、Issue metadata、目录与 Code search、commit/diff、ready/reviewer/PR 创建的 collection 副本写回、review 公开反馈。Merge 从只有按钮变成真正重新校验并在一次 collection 事务中写 merge commit、base head 与 PR 终态；独立保护要求、当前有效审批、Request changes、冲突和失败零写入均额外检查。代码复审补充团队 creator/createdAt 持久化、组织/团队标题、合并确认条件状态、Fork 失败保留表单、Parent team 显式标签和 PR/评论使用用户名。最终 99/99 与提交版本一致，前一版本的旧套 98/98 仅用于对照。

## 源测试与导出证据

- Python suite/export/protection 检查 21/21；Rust production `test_suites` 检查 7/7。
- Playwright helper 行为检查 3/3，包含装饰存在时的正确值、错值/多余值必须失败，以及输入文字不能算提交结果的反例。
- 按 recipe 重建 spec 和 case-plan，review 与 file hashes 一同更新至 spec_revision 3。Rust 的实际 `test_suites::extract` 导出 47/99 GitHub 与 24/72 Sheet；Python `verify_directory` 独立校验全部文件哈希。
- 源目录保留 GitHub 5 个、Sheet 17 个 INTEGRATION 文件；项目仅有 REQ，INTEGRATION 导出数为 0，目录继续使用 derived-tests。
- 模型 usage 记录 GitHub 1117、Sheet 266，条数和 sha256 均未增加或改变。本轮模型调用为 0。

内部 REQ 的通过率不代表官方 ARC 得分或视觉相似度；INTEGRATION 按用户要求暂不执行。原本的 source review manifest 仍标记 `not_run_against_product`，项目实测数据单独记录，避免把源审阅当成成绩。

证据目录：`audit/hackathon--github/recovery-20261001`、`audit/hackathon--sheet/recovery-20261001`、`audit/recovery-20261001`。原始基线继续在 `audit/hackathon--github/final-audit.json` 与 `audit/hackathon--sheet/final-audit.json`。

## 最终测量绑定与复现

最终 GitHub 报告为 `/home/chris/Works/hackathon-test2/audit/hackathon--github/recovery-20261001/final-username99/prepared/report.json`（47 个 REQ spec，99/99）；最终 Sheet 报告为 `/home/chris/Works/hackathon-test2/audit/hackathon--sheet/recovery-20261001/reviewed-full-r4/prepared/report.json`（24 个 REQ spec，72/72）。失败、超时、跳过、flaky 均为 0，每个用例仅一次执行；根任务独立核对报告中的文件名和标题集合与 reviewed case-plan 完全一致。

最终源码摘要：GitHub `839188f625e592455e29e5d5b20b91f88e70cd0328976e8dd6d046bc2a4007aa`；Sheet `1f4eca371b6d9910003b9560996758e6ad04b83b9bfbc5489b45a17d46e1b92e`。当前源码与实测快照一致，两项目 derived-tests 与 Rust production 导出逐字节一致，两个项目 git 工作区均干净。根任务的独立证据为 `/home/chris/Works/hackathon-test2/audit/recovery-20261001/final-report-integrity.json`、`final-source-integrity.json` 和 `export-integrity.json`。

源 helper 行为测试可在 Octos 仓库执行：

```bash
NODE_PATH="$PWD/arc/local-grader/node_modules" node arc/local-grader/node_modules/@playwright/test/cli.js test --config arc/tests/browser/playwright.config.cjs
```

项目全量验收使用 `arc/verify_app.py` 创建隔离副本，构建、启动、执行 REQ，再停止服务；不调用模型。原始项目数据和原生成验收证据保留。本轮临时 worktree 的源码已同步至当前仓库；审计导出和运行证据在 hackathon-test2/audit 内保留。
