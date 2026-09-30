**v15 节点生成性能、上下文与缓存复审报告**

本报告复核了已完成请求的耗时和 token 记录，并对当前上下文组装、代码输出、工具修复及缓存指纹代码做了离线复现。报告时间为 2026-09-30T19:01:43.624290+08:00。主要结论是：输出生成与反复修复值得优先优化；源码上下文增长确实存在；冻结业务契约已经按节点选择；代理在同一工具轮次内改变工具集合，是一个有直接代码复现和运行证据支持的缓存失效候选原因。具体提速幅度尚无受控实验依据。

报告、原始数据、复算脚本和复审结论均保存在隔离 worktree。此次仅新增分析文档与离线审计脚本，没有修改生成策略、推理参数、测试断言或生产运行检查。原有源码修改和其他任务的工作均保留。

**数据范围需要先明确。** 主统计对象是 [此前 Sheet 运行](/home/chris/Works/octos-arc/arc/arc-output/v15-sheet-trusted-20260930-161037/run-metadata.json)，原始源码提交为 `56147ba514db484488dca0e29cce7dd2bd867ece`，模型为 `deepseek-v4-flash`。原始冻结套件为 24 个 spec 文件、113 个 case。132 条有完成记录的上游请求均报告了 usage，模式均为 `low`；第 11 个节点的启动故障没有产生这批统计中的模型请求。该运行因共享 Cargo 输出中的 octos 被覆盖而中断，退出码为 130，不能作为完整 24 节点或完整套件的成功证明。

原始二进制 SHA-256 为 `3f875cb105855a6c3701a170852cdacdb674995aaa386aa833c6f888fe165e81`；被替换版本为 `d03155c777933d08b48d8a1aab2bba675435934446aa7bc680f6f5ac34566b7a`。替换版本缺少 `serve` 子命令，stdio 启动返回 2，随后 Python 等待 profile 响应超时。证据见 [基础设施事件](/home/chris/Works/octos-arc/arc/arc-output/v15-sheet-trusted-20260930-161037/binary-replacement-incident.json)。该问题应通过独立构建目录和固定二进制路径处理，不应计作“模型因为上下文太大而卡住”。

统计使用 [llm-usage.jsonl](/home/chris/Works/octos-arc/arc/arc-output/v15-sheet-trusted-20260930-161037/.arc/llm-usage.jsonl)、[request-ledger.jsonl](/home/chris/Works/octos-arc/arc/arc-output/v15-sheet-trusted-20260930-161037/.arc/request-ledger.jsonl)、[flow-metrics.jsonl](/home/chris/Works/octos-arc/arc/arc-output/v15-sheet-trusted-20260930-161037/.arc/flow-metrics.jsonl) 和 [octos-events.jsonl](/home/chris/Works/octos-arc/arc/arc-output/v15-sheet-trusted-20260930-161037/.arc/octos-events.jsonl)。输入文件与相关代码的 SHA-256 记录在 [evidence.json](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/dev-docs/v15-performance-review-20260930/evidence.json)。不使用重复的日志文本行计数，也不使用包含父节点或旧状态的 node_states 数量推算成绩。

**复算后的总体指标如下。** 缓存比例采用输入 token 加权，即 `sum(cache_hit_tokens) / sum(prompt_tokens)`，不是各请求百分比的简单平均。completion token 已包括所报告的 reasoning token，不再次相加。

| 指标 | 复算结果 | 口径 |
| --- | ---: | --- |
| 完成并记录 usage 的上游请求 | 132 | 132 个不同 request_id |
| 请求累计耗时 | 6,030.605 秒，即 100.51 分钟 | 各上游请求 elapsed_ms 之和 |
| 输入 token | 3,674,067 | 供应商返回 usage |
| completion token | 621,296 | 包含推理及非推理输出 |
| reasoning token | 469,246 | completion 的 75.53% |
| 非推理 completion token | 152,050 | 不等同于全是可执行代码 |
| 输入缓存命中 token | 2,745,600 | 命中率 74.73% |
| 未缓存输入 token | 928,467 | 每请求平均约 7,033.8 |
| 各节点首次实现请求 | 10 | 排除 context、protocol、complete-blocks 和 retry 调用 |
| 首次实现输入缓存命中率 | 23.09% | 69,632 / 301,592 |
| 首次实现请求耗时中位数 | 94.111 秒 | 10 次已完成首次实现请求 |
| 格式/完整性重试外层调用 | 6 | 累计 1,322.502 秒，即 22.04 分钟 |
| 原运行墙钟时间 | 7,971.234 秒，即 132.85 分钟 | 包含测试、编排、启动故障和停止过程 |

代理 ledger 有 133 条 request_received，但只有 132 条 attempt_started 和 132 条 attempt_finished；一个本地收到的请求没有上游 attempt 记录，不计入这 132 次模型调用。两条 proxy_stopped 的 pending_requests 都为空。usage 记录之间没有 request_id 重复，所有记录的 `total_tokens = prompt_tokens + completion_tokens` 成立。以上是本地可核对的 usage，未与供应商账单独立对账。

**把实现和修复分开看，整体命中率会更容易解释。** 同一修复轮次内的连续工具请求有较长共同历史，因此其命中率会拉高总体数字；各节点第一次实现的命中率仍偏低。每个外层 turn 默认重建会话，但同一工具 turn 内包含多次模型请求；“外层 turn”“上游请求”和“节点”是三个不同统计单位。

| 阶段 | 请求数 | 请求耗时合计（分钟） | 输入 token | completion token | 推理占 completion | 输入缓存命中率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 实现：纯文本文件/编辑协议 | 17 | 42.56 | 512,175 | 295,223 | 60.40% | 50.08% |
| 修复：纯文本协议 | 4 | 10.16 | 104,229 | 62,165 | 83.40% | 55.75% |
| 修复：工具模式 | 111 | 47.78 | 3,057,663 | 263,908 | 90.59% | 79.50% |

实现纯文本请求的输入范围为 18,547–38,439 token；修复纯文本请求为 17,498–29,602；修复工具请求为 7,307–45,327。不能把此前描述中的“约 1.8 万到 4.5 万”当作全部请求的准确区间。

同一模型和配置下，纯文本请求的输出 token 与耗时有很强的描述性相关关系，工具请求也类似；工具模式的 Pearson 相关系数约 0.997。但样本包含不同任务、不同输出量和缓存状态，相关关系不能用于证明输入大小没有影响，更不能推断增大上下文会提速。最直接的事实是：有输入命中 94%–99% 的请求，仍因为较长输出等待数分钟；因此只追求命中率不能解决全部耗时。

75.53% 是推理 token 占 completion token 的比例，不是“75.53% 的运行时间”。同理，22.04 分钟是这些纠错调用已消耗的时间，不是优化后可保证收回的时间。首次实现失败后的纠错可能仍需完成必要实现。

流式 first_output_ms 的实现把 reasoning 或 content 片段都计作首次输出；工具路径使用非流式响应，其 response_headers_ms 往往包含完整生成等待。现有数据无法提供两种模式可直接比较的“首个有效代码 token 延迟”或精确 prefill/decode 时间拆分。若增加分析字段，应分别记录首个推理片段、首个正文片段、首个工具调用以及首个实际应用的源码变化。

**节点级记录显示，少数节点的反复调用消耗了大量时间。** 下表汇总该节点标签下的全部已完成请求，包含实现、协议纠错、上下文补充和业务修复。最后一列是该节点最后一次本地自身测试测量，发生在不同源码版本上，不能跨行相加当成一次整套成绩。

| 节点 | 模型请求数 | 请求耗时（分钟） | 推理 token | 输入缓存命中率 | 最后一次自身测量 |
| --- | ---: | ---: | ---: | ---: | ---: |
| REQ-1-1-1 | 7 | 24.34 | 78,027 | 57.95% | 0/3 |
| REQ-1-2-1 | 25 | 10.69 | 54,572 | 80.70% | 1/2 |
| REQ-1-2-2 | 15 | 7.64 | 38,799 | 73.48% | 3/3 |
| REQ-1-3-1 | 29 | 17.48 | 89,888 | 75.42% | 3/3 |
| REQ-1-3-2 | 6 | 1.20 | 5,163 | 67.22% | 2/2 |
| REQ-2-1-3 | 1 | 1.73 | 9,210 | 61.79% | 2/2 |
| REQ-2-1-1 | 30 | 8.90 | 39,063 | 82.66% | 3/3 |
| REQ-2-2-1 | 15 | 17.09 | 94,482 | 69.43% | 8/8 |
| REQ-2-2-2 | 1 | 1.95 | 7,804 | 22.22% | 7/8 |
| REQ-3-1-1 | 3 | 9.49 | 52,238 | 64.89% | 3/3 |

第 11 个节点 REQ-3-1-2 的实现 turn 因 stdio 基础设施故障耗时约 270 秒，但没有上游模型 attempt，因此不进入上表的模型耗时。后续针对现有应用的局部测量也不能证明该节点已完成实现。当前旧测试里某些入口用例依赖尚未实现的跨节点能力，更新后的冻结套件已重新划分节点测试与最终集成测试；这个调整会改变后续运行的失败分布，应独立解释。

**冻结契约没有整套展开进每个节点。** [app_design_blocks](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:837) 对 `frozen=true` 且 `review_status=reviewed` 的设计走专用分支：

| 材料 | 单节点实际处理方式 | 位置或作用 |
| --- | --- | --- |
| data_model、domain_contracts、notes | 共享完整保留 | 稳定设计块，Sheet 为 9 个实体 |
| contracts、commands | 根据显式 active IDs 和 spec 文本中的 REQ IDs 选择完整条目 | 节点业务块 |
| 原始节点描述、scenarios、dependencies | 当前节点信息随实现任务进入；修复携带选定原始节点描述 | 行为依据 |
| requirement-contracts.json | 整份加载供流程使用；可信 spec 路径没有在每次实现中整份渲染它 | 无 spec/derived 路径才按指定节点渲染 |
| test-obligations.json | 加载并留存在冻结模型材料中 | 不等同于每次把整份 JSON 拼入 prompt |
| 当前 spec | 当前节点对应 spec 文件 | 实现与测量依据 |
| shared helpers | 尝试按可达声明裁剪；本次实际触发整文件回退 | 见下文 |
| 应用源码 | 相关性排序并按完整上下文预算选择 | 默认仍可能选入许多其他模块 |

完整设计紧凑 JSON 为 131,448 字符、131,478 UTF-8 字节；磁盘上带缩进的文件更大。离线重建 24 个节点的稳定设计块均为 11,853 字符，且 SHA-256 完全相同。活动节点业务块范围为 6,189–12,804 字符。此前给出的 6.5–9.6KB 只是几个示例；本报告明确区分“字符”“UTF-8 字节”和供应商 token。

冻结分支不会把相关条款截断来满足 24,000 字符的设计偏好预算。对于超过 6 个 active IDs 的全套/大批次请求，它会省略 basis 以 verbatim 开头的重复原文条目，并让完整冻结文件继续留在磁盘；这与单节点保留完整活动条款不同，不能写成“任何阶段全部条款都内联”。

普通非冻结设计路径则不同：能装下时整份带入；装不下时 data_model、domain_contracts、contracts、commands 仍进入 mandatory core，偏好预算会扩展。这一路更有按实体依赖分层的优化空间。相关代码见 [设计分层与预算](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:818)、[节点 spec/helper 渲染](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:5485) 和 [原始修复需求选择](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:5572)。

**上下文增长主要可见于源码部分，但尚无完整历史请求分段账本。** 实现 prompt 的记录从 74,619 字符增长到 145,510 字符，而设计块在约 18,042–21,848 字符之间变化。设计块较稳定、源码持续增长支持“源码是主要增长候选”的判断；目前没有保存每次历史请求全部分段大小，不能把差额全部认定为源码。

| 实现上下文记录 | prompt 字符 | 设计块字符 | 必须包含的源码路径数 |
| --- | ---: | ---: | ---: |
| REQ-1-1-1 | 74,619 | 21,406 | 6 |
| REQ-1-2-1 | 100,961 | 18,672 | 10 |
| REQ-1-2-2 | 105,717 | 18,797 | 10 |
| REQ-1-3-1 | 112,542 | 21,848 | 10 |
| REQ-1-3-2 | 113,212 | 19,409 | 10 |
| REQ-2-1-3 | 112,848 | 18,384 | 10 |
| REQ-2-1-1 | 116,512 | 18,042 | 11 |
| REQ-2-2-1 | 128,474 | 19,899 | 11 |
| REQ-2-2-1 | 128,844 | 19,899 | 11 |
| REQ-2-2-2 | 139,254 | 20,379 | 12 |
| REQ-3-1-1 | 144,410 | 18,331 | 14 |
| REQ-3-1-1 | 144,528 | 18,331 | 14 |
| REQ-3-1-2 | 145,510 | 19,226 | 12 |

这里的 prompt_chars 是组装后的实现 prompt，纯文本发送时另加 FORMAT_INSTRUCTIONS 和系统提示；不能把它当作完整 HTTP body 字节数，也不能按固定“四字符一 token”推算中文或代码的实际计费。

当前 [codegen_implement_prompt](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:3441) 默认完整上下文上限为 196,608 字符，focused_sources 默认 False。它先确定必须包含的入口、目标和依赖，再在剩余预算中纳入其他源码；相关性排序并不意味着只携带当前节点源码。原运行末尾应用源码合计约 101,247 字节，其中 workbooks.js 27,703 字节、Editor.jsx 16,159、Grid.jsx 9,270。只要预算仍能装下，就可能反复携带较多当前应用。

[required_source_context](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:3431) 还会从所有 domain_contracts 中提取源码 owner 路径，交给 SourceIndex.contract_context 追踪依赖。在此 Sheet 设计中 owner 都是业务责任描述，没有具体 frontend/backend 源码路径；不能说已通过它实现了精确的契约到文件映射。普通设计若给出很多实体的源码 owner，则有机会把多个实体的文件同时列为必须包含，应在改进前核对。

**helper 裁剪回退已得到直接复现。** Sheet helper 含 `export { expect };`。[trim_helper_to_references](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:1124) 无法给这类导出行匹配命名声明，于是保守返回整个 helper。24 个旧节点样本都实际得到 11,383 字符，没有发生预期的可达函数裁剪。

离线诊断只在内存中临时移除这行，让现有裁剪器计算可达声明，再把该导出行长度加回。假设能够正确支持该语法，则每个节点可能减少 3,165–9,359 字符，中位数 6,715.5。它只是字符规模估算，没有修改 helper，没有编译候选裁剪结果，也不是经过语义验收的实现。

| 节点 | 活动业务块字符 | 单个 spec 文件字符 | helper 假设可减少的字符 |
| --- | ---: | ---: | ---: |
| REQ-1-1-1 | 9,553 | 3,584 | 3,165 |
| REQ-1-2-1 | 6,819 | 1,768 | 6,013 |
| REQ-1-2-2 | 6,944 | 2,397 | 8,563 |
| REQ-1-3-1 | 9,995 | 2,985 | 8,561 |
| REQ-1-3-2 | 7,556 | 1,986 | 6,405 |
| REQ-2-1-1 | 6,189 | 2,581 | 5,785 |
| REQ-2-1-2 | 6,862 | 1,062 | 9,184 |
| REQ-2-1-3 | 6,531 | 2,356 | 7,026 |
| REQ-2-1-4 | 7,986 | 3,767 | 6,155 |
| REQ-2-2-1 | 8,046 | 5,848 | 4,871 |
| REQ-2-2-2 | 8,526 | 5,611 | 5,224 |
| REQ-3-1-1 | 6,478 | 2,307 | 7,332 |
| REQ-3-1-2 | 7,373 | 2,587 | 7,368 |
| REQ-3-1-3 | 8,050 | 2,206 | 8,244 |
| REQ-3-2-1 | 8,195 | 2,888 | 7,368 |
| REQ-3-2-2 | 7,600 | 5,731 | 5,234 |
| REQ-4-1-1 | 6,615 | 2,811 | 9,264 |
| REQ-4-1-2 | 7,194 | 902 | 9,359 |
| REQ-4-2-1 | 7,194 | 2,346 | 8,181 |
| REQ-4-2-2 | 6,761 | 3,342 | 9,184 |
| REQ-5-1-1 | 7,369 | 4,704 | 6,353 |
| REQ-5-1-2 | 9,008 | 6,151 | 3,231 |
| REQ-5-2-1 | 12,432 | 6,560 | 6,093 |
| REQ-5-3-1 | 12,804 | 11,163 | 6,165 |

修复时需要完整保留导入、re-export/alias、test fixture、初始化副作用及函数的传递依赖。仅按出现的函数名删除声明可能改变测试语义。将来的候选实现应先离线编译所有相关 spec 与 helper 闭包，再通过已有产品验收衡量影响。冻结 spec 文件字节不需要改变，优化对象是模型可见引用的渲染。

**工具修复的慢主要体现在模型往返，而非工具执行本身。** 143 次工具调用中 read_file 为 105、edit_file 为 28、bash 为 6、grep 为 3、list_dir 为 1；报告的工具执行时长总计仅 2,225 毫秒。这个数值只覆盖工具执行事件，不覆盖调度、模型思考、网络或完整输出，所以不能说整个工具链只用了两秒。

读文件频率最高的是 Editor.jsx 32 次、Grid.jsx 21 次、workbooks.js 14 次。它们也是高频修改文件。但 context ledger 的 duplicate_read_chars 合计为 0，不能把这 105 次读取统称为重复浪费：不同区间、不同文件版本、不同外层修复都可能需要读取。建议是增加单次请求中准确且可编辑的局部上下文、合并独立读取、减少盲目探索；必须给读取是否必要保留证据。

[structured_edit_turn](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:5353) 保留至多约 16,000 字符的已引用小文件，把其他文件换成按需读取提示。在 [use_structured_edits](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:5318) 中，宽实现 scope 超过默认 3 个文件时会继续使用纯文本协议；局部修复已有文件时更容易进入工具模式。将宽实现一律改成工具模式，或一律禁止工具读取，都缺少本次数据的支持。

**缓存复审发现了比“前缀文本长度”更具体的问题。** REQ-2-2-1 的同一修复 turn 中，工具集合发生两次变化：

| 同一 turn 的请求顺序 | 工具集合变化 | 输入 token | 命中 token | 与前一请求消息文本的共同字符前缀 |
| --- | --- | ---: | ---: | ---: |
| 第 7 次 | 五个工具仍完整 | 40,944 | 39,168 | 140,680 |
| 第 8 次 | 移除 list_dir，保留 read/edit/write/grep | 42,641 | 0 | 145,721 |
| 第 9 次 | 恢复 list_dir | 42,214 | 0 | 150,281 |
| 第 10 次 | 工具集合再次稳定 | 43,907 | 38,912 | 150,915 |

这两次零命中请求的未缓存输入合计 84,855 token，占工具修复全部未缓存输入约 13.54%。不能据此保证固定 schema 后可全部省去，但它们是明确的异常候选。

离线纯函数复现确认：[force_write_decision](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/llm_proxy.py:736) 在长时间未写入的预算阶段删掉 list_dir；历史中出现写入调用后直接返回原始请求，又恢复该工具。[prompt_fingerprint](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/llm_proxy.py:878) 仅拼接 role/content，不包含工具 schema、tool_calls 参数和完整消息结构。构造相同 messages、不同 tools 的两个请求，会得到相同 fingerprint。因此，“共享 15 万字符”无法证明真实缓存输入一致。

工具集合变化与零命中同时发生，随后命中恢复；代码机制也能复现。这足以把“同一 turn 的 schema 稳定性”提高为优先项，仍不足以证明 schema 是两次零命中的唯一原因。ARC 网关的内部缓存路由、TTL 和生成参数对缓存 key 的作用没有完整观测，应以同一模型/端点上的受控实验确认。

其他值得处理的缓存因素包括：实现和修复使用不同模板前缀；route_table_note 和 adapter 状态出现在共享设计块之前；source_change_counts 依据累计 Git 修改次数排序，新增文件或修改次数变化可能改变展示顺序；重复读压缩若改写早期工具结果，会让该位置之后不再是原前缀。本次 ledger 没有 context_compacted 事件，因此不能把本次 miss 归因于已经发生的读压缩。

建议把每个 turn 的系统提示、工具集合及 schema 顺序固定，仍使用现有预算准入和保护 hook 控制执行；动态剩余预算与失败证据放在尾部。稳定源码顺序也要固定，但内容必须是当前磁盘版本，不能为了命中而引用旧源码。将相同规则与完整共享实体模型放在节点材料之前；对动态路由表、adapter 差异、临时路径等使用单独尾部块。局部修改阶段继续允许必要的上下文请求与现有精确锚点保护。

项目已经有 Rust 侧 [归一化缓存输入 manifest](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/crates/octos-llm/src/cache_manifest.rs:1)、[离线 manifest 比较工具](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/crates/octos-llm/examples/prompt_cache_manifest_diff.rs:1) 和 [语义边界缓存 ADR](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/docs/adr/oup-semantic-boundary-context-cache.md:1793)。应复用这些已有机制。Rust 的 manifest 在 provider serializer 之后生成，但 Python proxy 随后还会替换 system、删工具、变换消息和模型参数，因此它也不能独自证明最终送往 ARC 的请求相同。现有 incoming_sha256/forwarded_sha256 可以关联变换，进一步观测应同时覆盖最终 forwarded body 的脱敏结构指纹，而不是保存明文提示或凭证。

兼容端点的 prompt_cache_key 等参数已有能力门控；不应为 ARC 网关擅自加入 OpenAI 专有缓存字段。供应商文档说明缓存复用已保存的相同前缀，输出仍需要计算，命中按尽力而为提供；这些机制解释了为什么需要稳定输入，但具体 ARC 网关行为仍以运行 usage 为依据。[DeepSeek 官方缓存说明](https://api-docs.deepseek.com/guides/kv_cache/)

**推理策略也需要区分默认行为和试验行为。** [default_reasoning_for_model](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/llm_proxy.py:282) 默认返回 low，本次所有请求均记录为 low。[codegen_reasoning](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/main.py:3741) 的小 spec 自动 none 判断只在基础模式为 auto/none/off/disabled 时生效，默认 low 会提前返回。因此修复 helper 裁剪并不会在默认设置下自动关闭推理。

可试验简单格式纠正、定位明确的小编辑和短入口任务的推理强度；公式引用、验证规则、复制剪切原子性、结构变更恢复、跨角色权限等复杂能力应保留原策略作为对照。代理发出 thinking/reasoning 字段，并不代表当前兼容网关一定按预期执行；需要看实际 reasoning_tokens 与完整验收。此次没有发起任何用于推理对比的额外模型调用。

**建议的实施顺序与验收范围如下。** 优先级表达的是本次证据支持的调查/实施顺序，不代表收益已经验收。

| 优先级 | 改进 | 证据强度 | 验收指标与业务约束 |
| --- | --- | --- | --- |
| P0 | 同一工具 turn 固定 schema，避免删掉再恢复工具 | 代码可复现；两次实测零命中伴随切换 | schema 哈希稳定；未缓存输入减少；预算与保护策略保留；最终业务结果通过 |
| P0 | 提高 FILE/EDIT/NEEDS_CONTEXT 输出成功率，减少整文件重发 | 6 次纠错累计 22.04 分钟；有锚点与不完整输出失败 | 首次应用成功率、纠错请求数、源码变更可原子应用；同一路径单一格式 |
| P1 | 正确支持简单 re-export 的 helper 引用裁剪 | 24 个旧节点都回退整文件；字符收益可复算 | fixture/import/alias/副作用/传递依赖完整；离线编译和既有产品验收 |
| P1 | 节点源码按显式依赖缩小范围，固定展示顺序 | prompt 增长；当前默认可装入额外模块 | 未缓存 token、缺失上下文次数、有效源码写入时间、完整业务通过率 |
| P1 | 实现/修复统一静态规则与共享模型前缀 | 两种模板不同；现有文本指纹不能覆盖全部输入 | 按阶段/执行模式统计缓存；动态材料后置；保留当前版本源码 |
| P2 | 试验简单编辑的推理策略 | 默认 low；工具输出 90.59% 是推理 | reasoning token、节点总耗时和通过率同时比较；复杂业务保留对照 |
| P2 | 按职责拆分高频修改的大文件 | Editor/Grid/workbooks 读写集中 | 减少重发/锚点失败；导入与数据所有者关系完整；整套回归通过 |

纯文本协议本来就允许不同路径混用 FILE 和 EDIT，只禁止同一路径同时使用；优化时应围绕这个明确边界，不能把协议误改成“整个响应只能一种格式”。格式纠错可以保留原始前缀，在末尾追加最小错误与当前上下文。缩小源码也可能引入更多 NEEDS_CONTEXT 往返，需要测量总请求数，而不是只比较第一条请求更短。

实验应使用同一源码起点、同一冻结套件及需求哈希、同一模型/端点、同一预算和相近运行条件，一次只改一个因素。模型有随机性，完整原流程可用于至少三组配对样本；先离线验证引用与 schema，再决定是否使用模型预算。这个计划尚未执行，不会新增线上 spec 生成、审计、等待或缺失节点检测环节。

建议同时记录每节点请求总数、输入命中/未命中 token、推理/非推理输出、首次有效源码变化时间、协议拒绝次数、需要补上下文的次数、首次测试通过率、最终完整验收、峰值内存和基础设施故障。单次 turn 的工具集合/schema 哈希、model/route、共享规则哈希以及主动上下文窗口切换原因应可关联；字段存在不等于供应商缓存一定命中，缓存也不参与业务正确性判定。

**正在运行的补跑提供运行证据，不构成性能 A/B。** 截至 2026-09-30T18:58:13.874881+08:00，补跑已完成 17 次模型请求，进程仍在运行。它使用保留的旧应用源码，但重新执行全部 24 个节点；没有继承此前节点通过状态。新冻结套件为 41 个 spec 文件、123 个 case，包含重新分配的节点测试和最终集成测试。其源码快照为 `eb0be5d678c2f60987141c8b4987d121a4b9666e86dd5829ba402d99214f1465`，固定二进制为 `0167785099f8165c34c29d956d0fe00b074853081726d2fcedddfd5767d6b960`。

补跑的应用起点、测试分布、输出目录和缓存状态都与旧运行不同，不能用它较早的节点通过或速度宣称本报告某项优化有效。本文的建议尚未进入补跑生成策略。补跑状态见 [continuation-snapshot.json](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/dev-docs/v15-performance-review-20260930/continuation-snapshot.json)，实时运行记录见 [run-metadata.json](/home/chris/Works/octos-arc/arc/arc-output/v15-sheet-isolated-20260930-182910/run-metadata.json)。报告冻结后，实时进度可能继续变化。

**复审结论是：主要数值和代码事实通过复核，具体优化收益仍待实验。** [离线复审](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/dev-docs/v15-performance-review-20260930/review-checks.json) 的 12 项检查全部通过，覆盖去重、token 算术、加权缓存、首次实现子集、重试统计、工具事件、schema 切换、指纹盲点、冻结设计一致性、helper 回退以及基础设施中断。它验证分析证据，没有声称产品完整测试通过。

复审修订了初稿的 token/时间比例混用风险、字符/字节单位、部分示例范围与全部节点范围、读取次数与重复读取的区别、文本前缀与真实缓存输入的区别，以及补跑与受控实验的区别。详细记录见 [review.md](/home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/dev-docs/v15-performance-review-20260930/review.md)。复算命令与输出均留在 worktree，便于继续审查：

```sh
python3 /home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc/arc/dev-docs/v15-performance-review-20260930/audit.py \
  --run /home/chris/Works/octos-arc/arc/arc-output/v15-sheet-trusted-20260930-161037 \
  --source /home/chris/.codex/worktrees/hackathon-frozen-specs/octos-arc \
  --output /tmp/octos-v15-performance-audit-recheck
```

复算脚本只读取已保存的运行数据与代码并写入报告输出目录，不调用模型、不运行产品、不修改冻结测试或生成策略。运行环境需能导入当前 ARC Python 依赖。证据与结论按“实测事实、代码事实、离线规模估算、待验证假设”分别描述，保留相应的实际限制。
