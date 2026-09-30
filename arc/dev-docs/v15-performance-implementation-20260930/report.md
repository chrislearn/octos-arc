性能改进实施与代码复核记录（2026-09-30）

已先将原有全部修改提交为 `d1294135`，随后复核并实施报告中有代码依据的 P0/P1 项。全程由同一代理完成，没有委派代理或调用其他模型。原始报告的 12 项离线检查再次全部通过，数值与代码事实成立；缓存 miss 的唯一原因、可以节省的分钟数和推理策略收益仍属于待验证假设。

原始报告：[report.md](../v15-performance-review-20260930/report.md)。原报告 SHA-256 为 `c04c638615fb12ed353750788f9b5bb400ff9f637f560e6dfbeb480776fb061c`，复算结果保存在 [historical-review-checks.json](historical-review-checks.json)。该复算使用原报告所在工作树，以复现历史缺陷；新实现由当前仓库的回归测试验证。旧工作树清理时，原始报告已原样迁入当前仓库，源码及忽略文件保存在恢复快照中，见 [worktree-cleanup.json](worktree-cleanup.json)。

| 项目 | 实施与复核结论 |
| --- | --- |
| 工具 schema 稳定 | 长时间未写入及预算耗尽提醒只追加尾部消息，保留原工具定义及顺序。写入前后不再删掉、恢复 list_dir。硬预算由已有请求准入检查执行，保护 hook 保留。 |
| 最终转发请求观测 | 指纹覆盖工具 schema、tool_choice、response_format、完整有序消息、tool_calls 参数与多模态内容。context ledger 和 usage 增加最终 wire SHA、完整请求结构 SHA、工具 schema SHA、消息 SHA 和版本标记。记录点位于流式转换后，能够区别 request_received 中较早的 forwarded_sha256；只保存哈希和计数。 |
| FILE/EDIT/NEEDS_CONTEXT | 当前代码已允许不同路径混用 FILE/EDIT，并在纠错时保留原提示、追加错误与当前上下文。复核并运行现有原子应用、锚点失败、非法上下文及格式恢复测试，保留同一路径混用禁令。没有扩大模糊输出的自动应用范围。 |
| helper 裁剪 | 支持简单 export 列表、别名及外部 re-export，保留 imports、fixture 注册、可疑 eager 初始化、顶层副作用和传递依赖。不能可靠识别的绑定、嵌套模板、复杂返回类型及边界回退全文。仅改变模型看到的文本，源 spec/helper 字节保持一致。 |
| 源码范围 | 已有明确文件匹配或活动契约文件 owner 时，优先该范围及传递依赖、入口与共享布局；无法定位具体业务文件时保留宽范围。补齐 mjs/cjs/json/css 和目录 index 依赖识别。命名匹配仍是启发式线索，文件清单、NEEDS_CONTEXT 和现有文件写入保护继续负责补足上下文。 |
| 上下文完整性 | 修改过的共享 scaffold 库及其依赖必须引用。回归前至多三个改动文件仍作为有界上下文保留；较大历史 diff 继续按当前失败位置选择。活动节点以外、明确绑定到其他节点的契约 owner 不再强制扩张当前范围。 |
| 静态前缀与排序 | 动态路由表、adapter/seed 状态和缺失启动入口说明后置。正常实现与修复使用同一提示构建入口，修复保留调用方诊断、纠正与争议协议；旧的有界回退仍保留。Git 修改次数的展示权重在本次运行内固定，源码内容每次从当前磁盘读取。 |
| 推理策略与大文件拆分 | 保留默认推理策略。已有设计提示要求按页面、编辑器、API/状态所有者划分模块并避免超大模块。本次没有修改运行中的生成项目，也没有用不同模型、端点或推理强度开展付费对照。具体收益需要后续受控实验。 |

新增 [test_performance_review.py](../../tests/test_performance_review.py) 的 13 项回归，覆盖 schema 写入前后稳定、最终 wire 结构指纹、别名/副作用闭包、安全回退、活动 owner、依赖范围、当前磁盘内容、展示权重及实现/修复共同前缀。代码第二轮复核额外检查了立即调用的函数初始化、属性访问、赋值、多声明和分号缺失边界；这些情况保留初始化或回退全文。

最终 Python 全量回归运行 2,196 项：2,168 项通过，28 项按各测试已有的环境条件跳过，无失败。`git diff --check` 通过。没有 Rust 源码或二进制改动；运行中的独立工作树及固定二进制保持原样。

全部 71 个 REQ 的原始 helper 和裁剪闭包通过 TypeScript 5.9.3 检查。在临时应用副本与独立 DATA_FILE 上使用裁剪闭包运行：GitHub 98/98、Sheet 72/72，全都通过，失败、flaky、skip 均为零。后续保守解析修订生成的 71 份闭包 SHA 与实际执行的闭包完全相同。原始 spec/helper SHA 在执行前后保持一致，INTEGRATION 仍保留在内嵌 derived-tests 中，未写入临时项目或执行。详情见 [evidence.json](evidence.json)、[test-summary.json](test-summary.json)。

| 套件 | REQ 文件 | 原 helper 字符数 | 裁剪后每节点中位字符数 | 每节点中位减少字符数 |
| --- | ---: | ---: | ---: | ---: |
| hackathon--github | 47 | 7,754 | 2,910 | 4,844 |
| hackathon--sheet | 24 | 11,383 | 2,198 | 9,185 |

这些数字是当前 REQ 套件的 helper 文本规模，不能等同于请求 token 或耗时节省。原报告使用的是旧测试分布，本次节点测试已将后续复杂流程移到暂不使用的 INTEGRATION，不能拿两批运行当作模型性能 A/B。

复现最终全量回归：

```sh
cd /home/chris/Works/octos-arc
PYTHONPATH=arc:arc/tests python3 -m unittest discover -s arc/tests
```

复现 helper 编译与已有产品验收（使用新的临时输出目录，依赖可从本机 npm 缓存离线安装）：

```sh
npm install --offline --prefix /tmp/octos-v15-performance-ts-check --no-package-lock --ignore-scripts typescript@5.9.3 @types/node@22.20.4
python3 arc/dev-docs/v15-performance-implementation-20260930/verify.py \
  --projects /home/chris/Works/hackathon-test \
  --ts-root /tmp/octos-v15-performance-ts-check \
  --output /tmp/octos-v15-performance-closures-recheck
```

[verify.py](verify.py) 使用现有项目及 Playwright、检查 REQ spec/helper 源字节、只在临时目录替换 helper 闭包，并自动停止临时服务器。完整运行日志保存在 `/tmp/octos-v15-performance-closures`；不需要启动模型，也不写入已有项目。
