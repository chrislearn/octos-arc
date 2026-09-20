# arc/ — 在这一个仓库里完成 ARC-Bench 的改、测、交

这个目录是 Octos 参加 ARC-Bench 的全部外围：平台适配包、公开验收测试、本地做题和打分脚本。
学员只需要这一个仓库。内核源码在上一级（`crates/`），适配包在这里。

## 五步

```sh
# 0. 准备（一次）
pip install -r arc/requirements.txt          # pyyaml、arcbench-runtime
export ARCBENCH_API_KEY=ak_...               # arc-bench.com 个人页的 API key
export NODE_BIN=/opt/homebrew/opt/node@24/bin # 你的 node 目录（Linux 一般不用设）

# 1. 拿一个 Octos 二进制：官方版，或自己编的魔改版
export OCTOS_BIN=/path/to/octos              # 不设则用 ../target/release/octos
cargo build --release -p octos-cli --no-default-features --features api   # 编魔改版时

# 2. 本机做题（约 5 分钟，不到一分钱）
python3 arc/run-task-local.py arc/tasks/smoke--counter --name try1
#    --port 43300 换端口可并行跑多题；--template <已有产物目录> 进入 evolution 模式
#    （先跑 smoke--counter，再以它的产物为模板跑 smoke-evolution--counter）

# 3. 用平台原版 Playwright 测试打分（首次会自动装 Playwright）
python3 arc/grade-local.py arc/arc-output/try1 smoke--counter
python3 arc/metrics.py arc/arc-output/try1        # 轮数 / Token / 费用 / 耗时 / 节点状态 / 打分，一行表格
python3 -m unittest discover -s arc/tests -t arc  # 编排器纯函数的单元测试

# 4. 改一处：main.py 的提示词 / 环境变量，octos_stdio.py 的启动参数，或 crates/ 里的内核
#    改完回到第 2、3 步，改前改后各跑一次，比数字

# 5. 打包上传
sh arc/pack.sh                               # 得到 octos-arc-bundle.zip
# 到 arc-bench.com 对应比赛页 New submission 上传，模型填 deepseek-v4-flash，
# Base URL 填 https://api.arc-bench.com/v1，然后选题、Run
```

## 改了内核怎么让平台用上

当前 v4 包在全新 codegen 任务开始前会安装跨任务通用的 Express 5 `backend/server.js`、`backend/lib/store.js` 和 `backend/lib/collection.js`；它们只提供路由、静态文件与通用持久化，不包含题目数据或业务规则。后端依赖写在 `backend/package.json`。已有应用不会被覆盖；设置 `OCTOS_ARC_GENERIC_TEMPLATE=0` 可关闭此行为。v3 包是原生 Node HTTP 版本，v2 无模板。

前端默认用可直接复制的 HTML/CSS/JS，以免简单任务承担框架安装和输出成本。复杂客户端状态可以改用 React + Vite；服务器渲染的局部交互可用 htmx；大量工具类样式可用 Tailwind CLI。平台最终验收会在前端运行 `npm install` 和 `npm run build`，在后端运行 `npm install` 和 `npm start`；本地验收也会按 `dependencies`、`devDependencies` 和 `optionalDependencies` 的变化安装，再构建。引入前端包时必须更新 `frontend/package.json` 的构建脚本，使所有页面、JS、CSS、字体和媒体进入 `frontend/dist/`。页面不能依赖 CDN 或远程浏览器模块；构建前后都有静态检查。npm 安装时访问包仓库不等于页面运行时使用 CDN。

v4.1 为全新 codegen 任务额外预置可选 `frontend/build.mjs`、`frontend/vite.config.mjs`，默认构建脚本不变；需要前端包时将 `frontend/package.json` 的 `build` 改为 `node build.mjs`。声明 `vite` 时自动构建 `src/**/*.html` 的所有页面，可选 `@vitejs/plugin-react` 与 `@tailwindcss/vite`；纯 HTML 模式声明 `tailwindcss` + `@tailwindcss/cli` 并在 CSS 中写 `@import "tailwindcss";` 即编译本地 CSS；声明 `htmx.org` 则复制 npm 包的脚本到 `dist/vendor/htmx.min.js`，页面引用 `/vendor/htmx.min.js`。蓝图不预装这些包，也不预置任何业务页面或样式。

**本地的环境变量不会跟到平台上。** 平台在自己的容器里跑 zip 里的 `main.py`，`OCTOS_BIN`、`OCTOS_ARC_*`
这些只在本机 `run-task-local.py` 有效；`main.py` 也不读任何配置文件（`arc-policy.toml` 只有 Rust 引擎读）。
要在线上生效，改动必须落在 `main.py` 的默认值里，或按下面两条之一带进包。

两条路，二选一：

1. **发 Release 让平台现场下载**（默认）：编译 Linux x86_64 版 → 在本仓库发一个 Release 挂上 tar.gz →
   把 `main.py` 里 `OCTOS_RELEASE_URL` 这个**常量**改成那个地址（不是环境变量）→ 重新 `pack.sh` 上传。
2. **把内核放进 zip**（`pack.sh` 默认就这么做）：`cargo build --release` 之后 `sh arc/pack.sh` 会自动把
   本机构建的内核 `strip` 后打成包内的 `bin/octos`，`main.py` 优先用它，省掉线上那段很慢的下载。
   来源按 `ARC_KERNEL_BIN` → `arc/bin/octos` → `target/x86_64-unknown-linux-gnu/release/octos` →
   `target/release/octos` 取第一个**是 Linux x86_64 ELF、且要求的 glibc 不高于平台**的（自带的二进制
   排在下载前面，装错了平台会直接加载失败且不会回落 —— 云端 `e70711133d37` 就是这样卡死的：本机 glibc
   2.43 编出的内核要求 GLIBC_2.43，官方 release 在 `ubuntu-latest` 上编、只要求 2.39，平台介于两者之间）。
   **在本机 `cargo build` 出来的内核多半会被拒绝**，`pack.sh` 会打印原因并退回下载路径。要在本机编出能自带
   的内核，用和 CI 同一个底座的容器（实测 5 分半）：

   ```sh
   sh arc/build-kernel-docker.sh          # ubuntu:24.04 + rustup 1.98.0，产物 -> arc/bin/octos，末尾打印 glibc 校验结果
   sudo -g docker sh arc/build-kernel-docker.sh   # 刚加入 docker 组、还没重新登录时
   sh arc/pack.sh                          # 通过 2.39 校验，打进包
   ```

   没有 docker 就走路 1 的 CI release，或 `cargo zigbuild --target x86_64-unknown-linux-gnu.2.39`。压缩后约 36M，先确认平台的上传体积上限；`ARC_PACK_KERNEL=0 sh arc/pack.sh`
   强制不自带内核；`ARC_KERNEL_MAX_GLIBC=2.4x` 只在确认平台镜像更新后才放宽。

两条都不做，平台跑的仍是 `OCTOS_RELEASE_URL` 常量指向的那个版本，改了等于没改。

## 目录

| 文件 | 作用 |
|---|---|
| `main.py` | 平台入口与编排器：骨架轮 → 按依赖序逐节点「设计 → 实现 → 本地跑该节点的验收 spec → 修复 ≤5 轮 → 通过即 commit」→ 启动演练 |
| `requirement_order.py` | 需求树拓扑排序、祖先查找、节点指纹（evolution 差异） |
| `acceptance.py` | 本地 Playwright 验收：spec↔节点映射、起服务、跑 spec、四字段失败摘要 |
| `guard.py` | 守护规则：未验证就宣称完成、连续同一错误、改保护路径 |
| `octos_stdio.py` | 通过 `octos serve --stdio` 驱动内核（默认每轮新 session） |
| `metrics.py` | 从事件流读 Token / 费用 / 耗时 / 节点状态 |
| `CHANGELOG.md` | 每条改动的改前改后数据 |
| `public-tests/<题目>/` | 本地开发用的公开 Playwright 验收测试，不随提交包上传；部署使用平台 `/workspace/tests` 或 `ARCBENCH_TESTS_DIR` |
| `tasks/<题目>/` | 各题需求文件的离线副本 |
| `run-task-local.py` / `grade-local.py` / `pack.sh` | 本机做题、打分、打包 |

已知平台细节：容器里 `/workspace/tests` 有验收测试；订票题的测试默认连 3301 端口而平台起在 3000，`main.py` 会要求后端两个端口都监听。平台最终验收会分别安装前后端依赖；本地生成器配置了 npmmirror，但平台安装所用的 registry 由平台自身决定。避免无必要的包，同时允许确实简化业务实现的依赖。

## 编排器开关（环境变量）

| 变量 | 默认 | 作用 |
|---|---|---|
| `OCTOS_TIME_BUDGET` / `OCTOS_NODE_TIME_BUDGET` | max(3600, 1500×节点数) / 1500 s | 整体与单节点（含修复轮）的墙钟预算；单节点预算按剩余时间/剩余节点数自适应 |
| `OCTOS_NODE_TIMEOUT` / `OCTOS_DESIGN_TIMEOUT` | 1200 / 420 s | 单轮上限 |
| `OCTOS_ARC_WHOLE_APP_WAVE_NODES` / `OCTOS_ARC_CODEGEN_OUTPUT_TOKENS` | 6 / 输出上限的 60% | 波次同时受输入及估计输出预算限制；超预算先拆分，不先消耗一次截断请求 |
| `OCTOS_ARC_MAX_TOTAL_TOKENS_ABS` | 0（关闭） | 逐请求检查的累计 token 阈值；达到后不再发上游请求，已在途请求可能超出，依赖供应商 usage 计量 |
| `OCTOS_REPAIR_ROUNDS` / `OCTOS_MIN_REPAIR_SECONDS` | 5 / 300 | 每节点验收修复轮数 K；剩余不足 300 s 不再开修复轮 |
| `OCTOS_ARC_REGRESSION_CHECKPOINT` | 4 | 第 4、8、16、24…个节点后并行重跑此前通过的用例（后续间隔不超过配置值的两倍），把实际失败传给下一节点修复；0 关闭。末节点由全套验收覆盖，剩余不足修复时间时跳过 |
| `OCTOS_DESIGN_TURN` / `OCTOS_DESIGN_MODE` | 1 / separate | 0 = 跳过设计轮；`inline` = 设计 JSON 在实现轮开头写出，不单开一轮（TB 上更省钱但更慢，见 CHANGELOG R7/R8） |
| `OCTOS_SESSION_SCOPE` | turn | 新 session 的粒度：`turn`（每轮新，spec 已内嵌所以修复轮自足）、`node`（设计/实现/修复共用）、`run`（全程一个） |
| `OCTOS_DESIGN_MIN_NODES` / `OCTOS_IMPLEMENT_FRACTION` | 2 / 0.6 | 节点数不足时跳过设计轮；实现轮最多占节点预算的比例，留时间给修复轮 |
| `OCTOS_PERF_CONTRACT` / `OCTOS_GUARD` | 1 / 1 | 0 = 关闭性能规则 / 守护注入 |
| `OCTOS_ARC_ALIAS_SPEC_IDS` | 1 | 0 = 不把节点状态镜像到 spec 侧 id |
| `OCTOS_ARC_INSTALL_PLAYWRIGHT` | 1 | 0 = 找不到 Playwright 时不尝试安装 |
| `OCTOS_ARC_PLAYWRIGHT_ROOT` | 自动 | 指定含 `node_modules/@playwright/test` 的目录 |
| `OCTOS_ARC_FULLY_PARALLEL` | 0 | 1 = 本地验收让同一文件内的测试也并行（比平台更严的压力测试） |
| `OCTOS_ARC_TEST_TIMEOUT_MS` / `OCTOS_ARC_SLOW_MS` | 10000 / 3000 | 本地验收单测试超时；超过 SLOW 阈值即提醒模型 |

Web 大题（32–138 节点）的建议参数见 `CHANGELOG.md` 末尾「ARC-Bench Web 六题的建议参数」。

### 同题内按步骤选择模型

v5.3 重新打包版默认关闭 thinking：`OCTOS_ARC_REASONING=none`，不再根据任务大小自动开启。
规划、生成和修复均沿用关闭状态。需要开启时显式设置 `OCTOS_ARC_REASONING=low`（或 `medium`/`high`）；
`auto` 可恢复原先按任务大小选择的规则。显式的阶段覆盖或模型路由参数仍优先；不同供应商是否支持关闭取决于其 API。

`OCTOS_ARC_MODEL_ROUTES` 接受有序 JSON 规则。同一题的不同节点、首轮与修复可以使用不同模型；匹配依据只有阶段、完整消息与工具定义的字符数、工具/图片能力，不按题名分支。第一条匹配的规则生效，无匹配则保留原请求模型；不配置时保持原行为。上下文字符数按完整消息与工具定义的紧凑 JSON 计算（Unicode 字符，不是 token）。

Python 和支持 `--model-routes-json` 的新版 Rust 内核使用同一规则格式；旧版 Rust 会明确报不支持参数，需换用新构建。Rust 的代码生成和工具请求共用本机转发层，实际模型记录在 `.arc/model-routes.jsonl`；分档开启后单模型费用估算为空，费用以 provider 账单为准。尚未完成云端对等验证，默认引擎仍为 Python。

云端提交也可携带同一规则：保存为任意 JSON 文件，然后运行 `sh arc/pack.sh /path/to/routes.json`，包内会增加 `model-routes.json`。打包和运行都会校验规则。环境变量 `OCTOS_ARC_MODEL_ROUTES` 优先于包内配置，显式设置为空可禁用分档；不传配置文件时，打包结果不包含任何默认模型规则。

本地验证真实 CLI 与内核请求链路（不调用付费 provider）：

```sh
cargo build --locked -p octos-cli --bin octos
python3 arc/integration/routed_cli.py target/debug/octos /tmp/octos-routing-evidence
```

脚本让真实工具模式完成设计，再切换到代码生成模型，模拟余额错误后检查整个运行失败且不再请求。该检查不证明模型生成质量或云端成绩。

下面仅是配置示例，不是经过费用/质量验证的默认值。模型 ID 来自 2026-09-15 ARC provider 的 `/v1/models`；该端点没有提供参数量和价格，也没有列出 `qwen3.8-27b`。应以使用时 provider 返回的目录和参数能力为准。

```json
[
  {
    "model": "qwen3.6-flash",
    "phases": ["implement"],
    "max_input_chars": 8000,
    "tools": false,
    "images": false,
    "parameters": {"max_tokens": 4096}
  },
  {
    "model": "qwen3.8-max",
    "phases": ["repair"],
    "tools": true,
    "images": false,
    "parameters": {"max_tokens": 8192}
  }
]
```

- 允许阶段：`implement`、`repair`、`verify`、`design`。修复含重写；阶段由流程设置。小模型失败后，现有验收/修复流程进入 `repair`，使用该阶段的匹配规则。
- `max_input_chars` 是字符预算，不是 token 上下文容量或模型能力的保证；用实际任务对比校准，给输出与协议开销留余量。
- `tools` / `images` 表示能力声明，默认 false；含工具历史也要求工具能力。声明应先验证，路由不会虚构 provider 能力。
- `parameters` 可覆盖 `temperature`、`top_p`、`max_tokens`、`max_completion_tokens`、`thinking`、`reasoning_effort`。切换模型会去掉原请求的供应商推理字段，再应用该规则的参数，避免跨模型照搬。
- 模型偏好由规则顺序明确表达；不根据未验证价格自动排序。不存在的模型或不支持的参数由 provider 报错，不偷偷更换并重复计费。
- 用量 JSONL 记录每次请求选中的 `model`、`phase`、耗时和 provider 返回的 token 用量。模型价格未提供时不编造成本。
- 当前仅 Python 引擎支持；配置路由并选择 Rust 会明确报错。Rust 路由与跨模型效果仍待实现/评测。多个模型请求仍遵守同 key 串行的费用计量约束。
