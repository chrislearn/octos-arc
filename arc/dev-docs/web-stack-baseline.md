# Web 框架基线与依赖审计

2026-09-20，当前 `v5` 分支；未进行新一轮云端 ARC 评测。

## 基线决策

新建、codegen 模式、至少 3 个原子需求且尚无应用源码的任务，预置 React + Vite + Radix + React Router，后端继续使用 Express 5。一至两个需求的任务保留轻量前端；已有应用和 evolution 不迁移。`OCTOS_ARC_GENERIC_TEMPLATE=0` 仍可关闭新建脚手架。这个门槛是通用规模策略，不按任务名选择实现。

固定前端核心为 React / React DOM 19.3.0、radix-ui 1.6.7、React Router 7.18.4、Vite 7.3.6、plugin-react 5.2.0。精确版本的唯一运行时目录在 `arc/web_stack.py`，对应安装样板与包含传递依赖 integrity 的 lockfile 在 `arc/blueprints/react-deps/`；测试检查两者一致。React Router 没有跟随需要 Node 22 的最新大版本。已验证 Node 22.23.2 和 Node 20.19.5；未声称验证所有 Node 小版本。

脚手架在全树规划**之前**安装，规划、生成、工具修复都看到同一技术约束。`index.html → main.jsx → App.jsx` 已接线，BrowserRouter 和 `arc.spa=true` 已配置。模型只生成业务页面和状态，不再生成自己的 DOM 渲染器、全局事件分发或弹窗焦点系统。Radix 直接使用，不再叠加一套自制通用组件 API。原生表单控件足够时优先原生控件。

## 全任务审计

检查了 `arc/tasks/` 全部 11 棵需求树（468 个原子需求），读取节点描述和场景；未把账号、初始记录、页面文案或测试答案放进模板。

| 任务 | 原子需求 | 主要可复用能力 |
|---|---:|---|
| Keep | 32 | 弹窗/菜单、受控布尔值、编辑草稿、列表更新、图标 |
| BookStack | 34 | 表单、保存/取消、草稿与正文编辑、层级路由 |
| 12306 | 117 | 注册校验、日期选择、筛选排序、订单金额、付款状态 |
| Ctrip | 125 | 多步表单、日期范围、乘客/联系人列表、附加服务计价、订单 |
| PrestaShop | 86 | 轮播、筛选、商品变体、购物车计价、结账、发票下载 |
| Stack Overflow | 66 | 表单、Markdown 编辑与预览、排序、投票与跨视图更新 |
| Smoke Counter / Dice | 各 1 | 原生输入与本地状态，无需框架 |
| Smoke Evolution Counter / Dice | 各 2 | 保留已有架构，追加状态和操作 |
| Ticket Booking | 2 | 注册、登录/退出；保留轻量路线 |

通用推荐目录如下。只有与需求名称/描述/结构化场景步骤相关的建议进入该应用的固定提示前缀，不读取 task ID、公开测试代码或测试结果来挑库；只是建议，不自动安装。明确否定的语句不触发推荐；Markdown 编辑器的去重限定在相关子树，不会全局删除独立富文本需求。关键词仍不是完整语义分析器，模型需按真实需求决定是否使用。

| 能力 | 固定候选 | 使用边界 |
|---|---|---|
| 样式 | Tailwind + @tailwindcss/vite | 本地 CSS 编译；普通 CSS 足够时不引入 |
| 复杂表单/校验 | React Hook Form + Zod + resolvers | Radix 用 Controller 适配；后端也校验；简单表单不必引入 |
| 日历/日期运算 | React DayPicker + date-fns | 简单日期用原生控件；日期字符串不随意转换 UTC |
| Markdown | react-markdown + remark-gfm | 受控 textarea 保存源文；不手写解析器或启用原始 HTML |
| 富文本 | Tiptap React / Core / PM / StarterKit 同版本 | JSON 文档保存；不重置正在编辑的内容；普通文本不用编辑器库 |
| 金额 | decimal.js（前后端可用） | 整数最小货币单位优先；复杂小数才用库；后端算权威总额 |
| 轮播 | Embla React | 本地媒体；计时器正确清理 |
| 图标 | lucide-react | 命名导入；按钮保留可访问名称 |
| PDF/发票 | PDFKit（后端） | 实际 PDF 字节、正确响应头，本地字体 |

每个候选都固定直接依赖版本和简短 API 用法；不是一份任意使用 `latest` 的库名单。可选库加入后的传递依赖由应用自己的 lockfile 固定，不宣称跨所有任务组合有一个通用锁。没有发现必须引入图表、地图、拖拽系统或上传框架的共性，因此不预装这些库，也不强制引入全局状态管理器。

## 同步修复的适配问题

- Python 和 Rust 源码发现支持 JSX/TSX/TS/Vue/MJS/CJS 等，修复不再看不到 React 页面。快照包含前端 manifest、Vite 配置和 npm lockfile，而不只是 HTML/JS。
- Python 扫描直接剪枝 node_modules/dist，而不是先遍历框架依赖再过滤文件。反复启动验收服务时正确关闭父进程的日志描述符，避免泄漏。
- lockfile 不进入模型源码上下文、源码预算或必须引用的修复列表，避免把约 128 KB 依赖锁当业务源码重复喂给模型。快照仍保存它，便于复现。
- 构建缓存跟踪 manifest **和 lockfile**；安装后记录实际锁内容，防止 npm 修改 lockfile 导致下一轮无意义重复安装。
- Vite 的 root 是 `src/`，显式把项目级 `frontend/public/` 设为 publicDir，修正本地公共资源漏打包；普通可选构建也支持 public。未配置编译器时，复制构建拒绝 JSX/TSX/Vue。
- SPA 检查识别 React Router 的 JSX/TSX 入口，避免首页可用但深层地址刷新 404。保留 API 与缺失静态文件 404，不回退成 HTML。
- CDN 静态检查覆盖 JSX/TSX/Vue 的直接资源、CSS、模块导入和 JS `src` 字面量，同时允许普通导航/API URL，不误判 SVG 命名空间。它是保守的静态检查，不是假称可证明所有动态拼接 URL 安全的沙箱。
- 明确受控布尔值、Radix 事件签名、asChild 单子元素、Portal/Overlay/Title、状态单一所有者、异步旧响应与计时器清理。根据需求决定 Save/Cancel/自动保存，去掉“一律关闭即保存”的跨业务假设。
- 全套修复不再忽略 codegen 返回值。格式错误最多一次纠正，未应用修改、显式 NO CHANGE 或未解决的拒写转工具修复；重试和工具回退共用一个截止时间，预算耗尽返回 unapplied，不谎称成功。

## 验证及可复现命令

本轮最终结果：Node 20.19.5 下开启 npm 集成和浏览器验证的 Python 全量测试 510 项，502 通过、8 跳过；Rust crate 127 通过、1 忽略。核心与可选依赖的生产构建/浏览器冒烟也单独在 Node 22.23.2 验证通过。`git diff --check` 无错误。

单元回归：

```sh
PYTHONPATH=arc python3 -m unittest discover -s arc/tests -q
cargo test -p octos-arc --lib
```

真实安装、生产构建及浏览器验收（Playwright 路径需有对应 Chromium）：

```sh
PYTHONPATH=arc:arc/tests ARC_TEST_NPM_INTEGRATION=1 \
  ARC_TEST_PLAYWRIGHT_ROOT=/home/chris/Works/octos-arc/arc/local-grader \
  python3 -m unittest test_web_stack -q
```

验证先从提交的 lockfile 执行 `npm ci` 构建核心，再安装所有推荐组合并构建；浏览器屏蔽非本地请求，检查原生/Radix checkbox、Dialog 打开/背景隔离/Escape/焦点恢复、菜单单次事件、表单校验、Markdown、富文本、日历、金额、SPA 路由刷新和公共资源。测试 fixture 不在平台打包清单中。

以上仅证明基础设施和所选依赖组合可运行，不能替代 6 个应用各自的模型生成与业务验收。后续同题对照应记录：首次完整套件通过数、实际应用改动的修复轮数、生成 token、输入 cache miss、安装/构建时间和最终平台分数。依赖与契约会增加少量稳定前缀及首次安装时间，是否换来净 token/耗时下降必须实测。

Rust 改动已同步源码发现与快照并运行 crate 测试；本轮未重编发布用内核，亦未覆盖 `octos-arc-v5.1.zip`。当前云端 Python 编排路径的修复不依赖这次 Rust 源码改动。
