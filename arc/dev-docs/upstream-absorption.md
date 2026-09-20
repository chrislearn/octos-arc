# v5.2 基线上的上游改进吸收

2026-09-20；参考上游 `octos-org/octos-arc` 的 `a2ad359d8d6b722235fbdfaef75e2056012b5406`。
在当前 `v5` 分支定向移植，没有合并上游完整工作流，也没有覆盖已有 v5.2.zip。

## 保留的基线

继续使用 React/Vite/Radix、Express、本地构建与本地静态资源、一次应用设计、预算内整应用/波次生成、精确 EDIT、稳定提示前缀、逐叶定点修复和最终全套确认。
不引入业务专用模板；不改变默认模型、思考策略和总 token 上限；不采用按整个应用代码体积一刀切退出 codegen 的策略。
修改作用于默认 Python 调度器。可选 Rust 引擎及随包内核二进制没有变更。

## 吸收并适配的机制

1. **代理兼容**：带路径的 provider base 视为完整 API 根路径，避免 `/custom/v4/v1/...`；只按完整 `/v1/` 段处理，不误改 `/v10/`。
   回环地址，包括 IPv6 和 127/8，不使用环境 HTTP 代理；远端仍尊重代理配置。启动探测使用同一机制。
   仅在路由确实换了模型、且上游明确返回模型不存在的 404 时，禁用该路由模型并回退一次到原模型及参数。
   普通地址 404、鉴权、限流不触发模型回退；两次实际请求分别计量，不伪装成一次调用。
2. **修复结果分型**：记录 applied、partial、unchanged、guard_refused、anchor_failed、format_error、no_blocks、incomplete_blocks、generation_failed。
   已完成文件块后的截断也不再被报告为完全应用成功。保留完整文件，剩余部分定点恢复。
   格式错误可在同一时间预算内重试一次，追加简短格式反馈、保留原提示前缀；拒写需要重新引用文件；不能落地时才用工具回退。
3. **减少空转**：首次实现的 NO CHANGE 仍要验收。修复已知失败时，NO CHANGE 或原样输出不视为有效修复。
   工具模式比较执行前后应用文件内容，而不是相信模型声明、write 工具调用数或元数据 commit。
   本地图片、字体、锁文件也参与有效修改判断；node_modules、dist 等派生产物不参与。
   节点、checkpoint、最终套件在有界回退后仍无修改时，不重复跑相同验收；最终外层 passes 也停止空转。
   部分修改仍会验收，原有最佳状态回退、真实失败后的改变策略和全绿确认保留。
4. **按阶段分配时间**：整应用首轮之后按实际失败节点数分配，而非按全部节点原索引；预留 `min(300 秒, 修复阶段初始剩余时间的 10%)` 给最终阶段。
   默认节点基准仍为 1500 秒，前面节点实际节省的额度最多取一半追加，默认单节点最多 3000 秒。
   显式设置 `OCTOS_NODE_TIME_BUDGET` 则始终是硬上限。没有提高全局时间或 token 预算。
   是否启动下一轮修复，参考同执行模式最近 12 次已落地、正常结束修复的耗时中位数 × 1.1；最低仍是 `OCTOS_MIN_REPAIR_SECONDS`。
   格式重试和工具回退共用截止时间，启动修复也如此；不再将不足 60 秒的剩余额度强制扩为 60 秒。
5. **启动错误摘要**：优先实际异常及附近文件/行上下文，过滤 Node 的误导性 ESM 提示和 npm notice。
   避免真正的 SyntaxError 被前部 warning 挤出上下文，引导模型无谓切换模块制式。
6. **独立诊断日志**：`.arc/flow-metrics.jsonl` 记录 turn 的实际 codegen/tools 模式、阶段、耗时，以及代码应用结果和节点/最终套件验收轮次。
   不把原始源码、提示全文或诊断 hash 塞回提示词；用现有 proxy usage 日志核对实际计费请求和缓存命中。
   这些记录不是跨波次首过率统计器：节点 round 0 可能已在全应用首轮后，不能直接当作整个任务首次生成的通过率。
7. **精简部署包**：pack.sh 不再携带所有题目的 public-tests，仓库中的本地测试和发现逻辑保留。
   部署使用平台 `/workspace/tests` 或显式 `ARCBENCH_TESTS_DIR`；脱离平台运行时需提供测试目录。
   仍保留已验证的本地内核打包机制，不强制改成运行时下载。

## 验证与局限

新增本地 HTTP 线级测试、格式/无修改/部分修改回归、真实工具回合的内容变化检测、预算边界测试、隔离目录打包及解包入口导入测试。
测试不会调用付费模型接口，不修改官方任务及公开验收测试。

本次验证：Python 全套 549 项，541 通过、8 跳过；启用 Node 20.19.5 的 npm 集成及本地 Chromium 测试。
Rust 兼容回归 127 通过、1 ignored；`git diff --check` 通过。
21 项新增测试包含在 Python 总数内。打包验证只在临时目录进行，未生成新发布版本、覆盖旧包或提交 Git。

```sh
npx --yes --package=node@20.19.5 --call 'PYTHONPATH=arc ARC_TEST_NPM_INTEGRATION=1 ARC_TEST_PLAYWRIGHT_ROOT=/home/chris/Works/octos-arc/arc/local-grader python3 -m unittest discover -s arc/tests -q'
cargo test -p octos-arc --lib
```

这些变更针对可复现的机制缺陷；实际 token、缓存命中率、生成时间与平台通过率的改善仍需下一次 ARC 实测，不能用本地单测代替。

## v5.3 thinking 默认关闭重打包

按后续要求，将 Python 默认、随包 arc-policy.toml 和 Rust 源码默认统一设为 `none`。
原默认 `auto` 在大任务启用 low；现在默认规划、生成、修复均关闭，只有显式配置才重新开启。
代理关闭指令覆盖内核可能发来的 `thinking: enabled` 并去掉 `reasoning_effort`；内核配置也默认设为 none。
保留小规格的紧凑提示规则，不因关闭 thinking 而改变原来的大小分档。
现有兼容内核不重新编译；Rust 可选引擎通过随包策略显式读取 none。不同模型的关闭能力取决于供应商协议，未假定所有模型都支持 DeepSeek 字段。

重打包验证：Python 554 项，546 通过、8 跳过（含 npm/浏览器集成）；Rust 127 通过、1 ignored。
已替换根目录 v5.3.zip，SHA256：`5d16dced16283b55eb3685df89c2a470a16ecaed9cf8dd9c702068a04d1cd98a`。
