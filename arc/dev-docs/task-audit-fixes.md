# 全任务复核与修复

2026-09-20，`v5` 工作分支。在现有 React/Vite/Radix 基线之上修改；没有修改官方 tasks、测试答案、历史压缩包或发布内核二进制，没有新建业务专用模板。

## 确认的问题与决策

| 问题 | 修复与边界 |
|---|---|
| 现有 v2/v3/v4 平台日志使用 `--workers=1`，适配器却默认 4 | Python 与 Rust 的 final workers 默认 1；Python `OCTOS_ARC_GRADER_WORKERS` 定义预期并发，`OCTOS_ARC_FINAL_WORKERS` 可独立覆盖内部并发。不是断言平台永远只用 1。内存仍可进一步限流。 |
| FILE/EDIT 重写相同内容被视为成功修改 | 比较最终正规化内容；原样重写不再更新有效写入列表，相同正文直接跳过磁盘写入。HTML charset 和 JS 换行修复后的内容也参与比较。 |
| 规划省略场景，且头部截断导致后半业务消失 | 保留不重复场景事实，优先结果步骤；预算不足先压缩完整目录，再均分详情空间。11 棵实际任务树在 12k 字符下均保留全部 ID。极小预算仍会明确提示省略，完整节点需求/公开规格在实现阶段继续提供。 |
| 设计 JSON 只验类型，两段各用一整份预算，截断可能破坏 JSON | 验证方法、绝对路径、重复项和契约结构；只添加完整 JSON 条目，两段总长不超 cap；稳定前缀选择不依赖当前节点。遗漏明确标注，完整设计仍保存到 `.arc/design/app.json`。缓存校验完整需求树，避免未进入摘要的变化被误复用。 |
| 推荐忽略场景、命中明确否定、Markdown 全局排斥富文本 | 读取结构化场景，保守过滤否定子句；只在相关 Markdown 编辑器上下文去重。仍是建议筛选器，不是安装决定或语义证明。 |
| 持久化后改 initial 不生效 | 增加显式版本化迁移，数据和执行账本同文件一次原子写入；无需生成另一套迁移框架。不得把缺失记录当作首次启动，迁移规则由需求决定。 |
| 大波次失败后，下批仍用大上限 | 记住缩小后的上限，尽量在同父模块边界结束，保持原拓扑顺序。格式纠正与原调用共用截止时间。仍保留每叶验收/修复与最终完整验收。 |
| 共同运行错误逐叶修复 | 首次可靠完整套件后，只对至少两个需求重复报告的明确 ReferenceError、SyntaxError、缺模块错误尝试一次共同修复。相同超时/断言不聚类。源码/锁文件无变化不重复跑套件；修改后全套验证，新失败或不可靠报告均回退。可用 `OCTOS_ARC_SHARED_REPAIR=0` 关闭。 |
| Vite 报 `src/App.jsx` 时修复提示只引用入口清单 | 识别前端相对路径、引用具体文件并带上固定栈约束。 |
| 回退采用 checkout 覆盖模式，新提交文件会残留 | 改用限定 frontend/backend 的 git restore；真实临时仓库测试验证原文件恢复、新文件移除、范围外文件保持。 |

## 新的抽象契约

在原有一次应用设计中增加 `contracts: [{requirements, invariants}]`，不额外新增规划模型调用。要求从实际需求定义：数据所有权/键域、命令前置条件与原子效果/撤销、草稿与持久状态边界、日期与截止时间、控件操作语义和服务端验证。规则只约束一致性，不预定义订单、便签、投票等业务实现。

日期不能一律套用真实今天或固定测试日期：日期型字符串保留日历含义，时间戳才代表瞬时点；到期时间持久化，倒计时依据服务端时间校准。只在需求明确给出参考日期时采用参考日期。未引入全局冻结时钟或替换全部日期处理的额外框架。

原生选择契约使用原生 select；富文本 editorProps 为实际可编辑区域设置 role=textbox、aria-label、aria-multiline。浏览器集成覆盖 `getByLabel().selectOption()` 和按名称定位的富文本 `fill()`，不是只检查 DOM 中存在编辑器。

## 可选迁移接口

```js
const store = require('../lib/store');
store.migrate('records', {items: []}, [
  {id: 'schema-v2', up(data) {
    for (const item of data.items) item.version ??= 2;
  }}
]);
```

也可传入 `collection(name, {idKey, initial, migrations})`。每个 id 最多执行一次；回调同步修改数据、返回 undefined。保留顶层 `__arcMigrations` 账本，追加新迁移而不改写已执行迁移。整组迁移在任何异常后都不落盘；不接收异步迁移。回调不能写其他存储，否则超出了单文件事务范围。该工具仅保证单 Node 进程同步更新与原子替换，不提供跨进程锁、跨文件事务或断电持久性保证；有这些需求时选事务型存储。

## 验证方式与尚未证明的收益

新增单元与真实 Node/Git 回归测试覆盖上述确定性行为；使用 Node 20.19.5 跑完整 Python 测试、npm 安装/构建和 Chromium 本地资源交互；Rust 库测试检查策略默认值兼容。验证结果以本次执行日志为准。

本次最终结果：Python 共 528 项，520 通过、8 跳过、0 失败（46.861 秒）；其中启用真实 npm 集成和 Chromium。Rust 库测试 127 通过、1 忽略、0 失败。`git diff --check` 与修改的 Rust 策略文件格式检查通过。日志：`/tmp/octos-audit-release-check.log`、`/tmp/octos-audit-rust.log`。

```sh
npx --yes --package=node@20.19.5 --call 'PYTHONPATH=arc ARC_TEST_NPM_INTEGRATION=1 ARC_TEST_PLAYWRIGHT_ROOT=/home/chris/Works/octos-arc/arc/local-grader python3 -m unittest discover -s arc/tests -q'
cargo test -p octos-arc --lib
```

尚未执行新一轮云端任务生成。因此不能声称首次通过率、token 数、缓存命中率或耗时已经提高。新增不变量会增加少量稳定输入；预期收益在于减少生成输出和重复修复，需同模型、同任务、同并发的云端对照验证。两叶小任务的 React 门槛未放宽，没有预装全部可选库，也没有开启每波完整构建（跨波中间状态可能尚未形成可运行应用）。
