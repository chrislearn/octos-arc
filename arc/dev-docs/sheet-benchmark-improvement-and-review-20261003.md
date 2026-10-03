# Sheet 基准生成代码改进与复审报告

日期：2026 年 10 月 3 日。本文面向维护代码生成流程、derived tests 和 Sheet 应用实现的人员。目标是解释低分运行 [8ff1885a8162](https://arc-bench.com/runs/8ff1885a8162) 的内部验收 **182/195** 与官方 **59/100** 为何分离，并用高分运行 [8aa637d019a5](https://arc-bench.com/runs/8aa637d019a5) 的实际下载包复核改进方向。结论是：低分运行同时存在测试交互方式不匹配、未修复的需求内缺陷和最终修复流程不足；不能用一个通过率代表另一个通过率，也不能把官方全部失败当成隐藏业务要求。

## 证据范围与版本

| 对象 | 已核实结果 | 证据 |
| --- | --- | --- |
| 低分运行的项目内最终测试 | 182 通过、13 失败，共 195 例 | [最终 acceptance 报告](/home/chris/Downloads/8ff1885a8162-template/template/.arc/acceptance-evidence/777c431508c145eaa72f7636c9906971/report.json) |
| 低分运行的官方评测 | 59 通过、41 失败，共 100 例 | [官方 Playwright 报告](/home/chris/Downloads/8ff1885a8162-template/template/.arc/playwright-report.json) |
| 高分运行的官方评测 | 87 通过、13 失败，共 100 例 | [高分包官方报告](/home/chris/Downloads/8aa637d019a5-template/template/.arc/playwright-report.json) |
| 当前本地参考应用 | 247 通过、1 例 harness 限制，共 248 例 | [本地复测摘要](/tmp/sheet-high-example-r12-compare/summary.json) |

两个运行包的 `requirements.yaml` SHA256 均为 `9cddf67be50748106289ed158648629a6c50c30a490d0eda5bd570c557440b96`，因此两次官方测试面对的是同一份需求文本。高分运行包与**当前** `../octos-arc2/arc/test-examples/hackathon--sheet` 的源码并非逐文件相同：当前参考应用另改过 `FilterDialog.jsx`、`FormulaBar.jsx`、`EditorPage.jsx`、`formula.js`、`structure.js` 和 `workbooks.js`。247/248 是当前参考应用的本地结果，不能写成高分运行当时的本地结果；87/100 才是其下载包中的官方结果。本地唯一失败为测试 harness 要求观察到恰好一次成功写入，实际观察到两次，尚不能据此判定应用违约。

官方包只有 Playwright 报告，没有完整官方测试源码。下文的“官方根因”严格指日志里的**首个失败点**。修复首个失败点后，后续断言是否通过仍需重跑。

## 两次官方结果的差异

高分运行 13 个失败与低分运行 41 个失败有 **12 个相同场景**。高分运行独有的失败是 `REQ-1-3-2` 的 CSV 导出场景 1；低分运行新增 **29 个失败场景**。这种差异主要集中在共享交互入口，而不是 29 个彼此独立的计算错误。

| 低分运行首个失败点 | 场景数 | 与高分实现的直接差异 | 结论等级 |
| --- | ---: | --- | --- |
| 点击原生 `<option>` 时不可见 | 22 | 低分排序、筛选、验证等表单用原生 `select`；高分用展开后可点击的 Radix `Select.Item` | 官方日志直接证明阻断；原生控件本身未被需求禁止 |
| 找不到 `Pivot table editor` 中的 Rows 控件 | 10 | 低分把透视状态存于来源表，并通过当前表反查；高分把透视状态关联结果表。这是结构差异，尚非已证实的根因 | 官方日志只证明 `region → Rows` 定位链失败；区域不存在、被隐藏或控件标签失配仍待区分 |
| 错误文案大小写不匹配 | 4 | 两份实现都使用需求原文首字母大写；官方相应正则大小写敏感 | 官方断言与需求原文不一致 |
| 更新时间不在工作簿链接内部 | 1 | 两份实现都把名称链接和更新时间放在同一列表项的不同元素 | 官方添加了需求没有规定的 DOM 嵌套条件 |
| 首页链接总数期望 2 | 1 | 测试时已有别的工作簿，实际为 63 个链接 | 全局数据隔离或断言范围问题，不能据此证明 Undo 污染 |
| 要求额外的 `Filter selected range` 对话框 | 1 | 需求允许从 Data 菜单直接创建筛选 | 官方增加了交互步骤 |
| 公式结果期望 12、实际 13 | 1 | 高分运行通过该场景，低分运行未通过 | 确认结果差异；缺完整官方输入，根因待复现 |
| 空引用提交后必须从空文本变成非空 | 1 | 需求未规定空引用的展示必须非空 | 官方 helper 前提过强；后续循环引用断言尚未执行 |

上述计数为 41。尤其是前两类合计 **32 例**：它们尚未验证后续公式、验证规则和透视汇总是否正确。不能把 32 直接视作可恢复分数。

官方各功能对比更直观：低分实现的排序为 0/6、验证为 0/6、透视表为 0/9；同一项目内的 derived tests 分别为 12/12、23/31、35/36。高分运行官方对应为 4/6、5/6、8/9。共享 UI 控件和透视创建后的状态链路，比逐个修改晚期断言更有价值。

## 已确认的低分实现缺陷

以下判断有需求原文、源码和本地失败或直接函数探针支撑。它们与官方首个失败点应分开跟踪。

| 问题 | 证据和影响 | 建议验收场景 |
| --- | --- | --- |
| 重开多格验证规则时只认完全相同选区 | [低分 Editor.jsx:455](/home/chris/Downloads/8ff1885a8162-template/template/frontend/src/pages/Editor.jsx:455) 只比较规则起止坐标。对 `A1:A2` 设规则后选择 `A1`，无法看到旧规则的删除入口；此时另存的单格规则会排在原规则之后，而[取规则逻辑](/home/chris/Downloads/8ff1885a8162-template/template/backend/lib/rules.js:28)先命中旧规则，因此新限制不能立即生效。低分最终测试已有相关失败。高分代码按[重叠关系查找](/home/chris/Downloads/8aa637d019a5-template/template/frontend/src/pages/EditorPage.jsx:705)。 | 设 `A1:A2` → 只选 `A1` 重开 → 修改上下限 → 两格均按新规则约束 → 删除后两格均解除约束，刷新仍一致。 |
| 删除非活动工作表不激活相邻表 | [低分 workbooks.js:273](/home/chris/Downloads/8ff1885a8162-template/template/backend/routes/workbooks.js:273) 仅在目标是活动表时改活动 ID；最终测试两例失败。高分运行当时也有同类源码问题，当前参考实现已修。 | 四张表时分别删除非活动的首表和末表，立即及刷新后均激活相邻表。 |
| 删除整个透视来源列后直接丢弃状态 | [低分 pivot.js:264](/home/chris/Downloads/8ff1885a8162-template/template/backend/routes/pivot.js:264) 删除 `pivot_state`，结果页失去 Refresh；最终测试确认。应保留最后成功结果及来源失效标记。 | 来源仅 A 列，B 列有同名表头；删 A 后刷新必须报字段失效，不能把 B 误当旧来源，结果不变。 |
| `Before` 条件把空日期算作匹配 | [低分 Filter.jsx:38](/home/chris/Downloads/8ff1885a8162-template/template/frontend/src/pages/editor/Filter.jsx:38) 日期解析失败后退回词典序，`'' < '2026-01-02'` 为真；最终测试空日期行可见而失败。 | 早于截止日、晚于截止日、空日期各一行，过滤及刷新后只保留早于者。 |
| 验证下拉项没有需求指定的 `option` 角色 | [低分 Grid.jsx:75](/home/chris/Downloads/8ff1885a8162-template/template/frontend/src/pages/editor/Grid.jsx:75) 用默认 `DropdownMenu.Item`，高分实现[显式设置 `role="option"`](/home/chris/Downloads/8aa637d019a5-template/template/frontend/src/components/SpreadsheetGrid.jsx:518)；[需求](/home/chris/Downloads/8ff1885a8162-template/template/requirements/requirements.yaml:2598) 明确规定该角色。 | 展开 `Open dropdown for A1`，按 `option` 角色选值，随后验证保存值和重开状态。 |
| 聚合公式把文本 `TRUE` 当作数字 | [低分 formula.js:27](/home/chris/Downloads/8ff1885a8162-template/template/backend/lib/formula.js:27) 把 `TRUE` 转为 1；以 `A1=TRUE`、`A2=2` 直接调用函数时，`COUNT(A1:A2)=2`、`SUM(A1:A2)=3`、`AVERAGE(A1:A2)=1.5`。[需求](/home/chris/Downloads/8ff1885a8162-template/template/requirements/requirements.yaml:1821) 要求 COUNT 及其他聚合只取数字。 | 混合数字、空白、普通文本和 `TRUE`/`FALSE`，分别断言五个聚合函数。 |

另有两项值得列入探索性检查，不计入已确认官方根因：低分数字规则接口用 `Number('')`，可能把空上下限当 0；筛选按钮放在数据[网格单元格](/home/chris/Downloads/8ff1885a8162-template/template/frontend/src/pages/editor/Grid.jsx:72)，而高分实现在[列头](/home/chris/Downloads/8aa637d019a5-template/template/frontend/src/components/SpreadsheetGrid.jsx:386)。后者是否违反“Each header”需要统一对“数据标题行”和“列头”的解释，再决定是否将 DOM 位置作为强制测试。

## Derived tests 与需求的复审

测试源文件经过人工审阅，且覆盖了大量原子要求，但“通过 182 例”不是“182 个官方场景等价通过”。[README](/home/chris/Works/octos-arc/arc/derived-tests/hackathon--sheet/README.md)说明源套件为 248 例，导出到生成项目的是 **195 个 REQ 例**；53 个 integration 文件不导出，部分跨节点行为被复制为 REQ context 用例。[case-plan](/home/chris/Downloads/8ff1885a8162-template/template/derived-tests/case-plan.json)中 **183/195** 例依赖创建空白工作簿，对种子工作簿及多操作连续路径的覆盖偏少。

最重要的测试方式偏差是 [helpers.ts:80](/home/chris/Downloads/8ff1885a8162-template/template/derived-tests/helpers.ts:80)：它检测原生 `SELECT` 并调用 `selectOption()`；官方使用可见 `option` 的点击。原生组合框符合原文的标签和选项语义，所以不应删除现有需求测试。应增加一层**官方兼容性测试**，对排序、筛选、验证、透视字段分别执行官方相同的展开和点击动作，并与需求语义测试分开报告。

还需补以下具有明确业务后果的见证：验证规则在区域内部重开和修改、空白日期的 `Before`、整列来源删除旁边有同名表头、聚合布尔文本、透视创建后立即切表与刷新、错误提交后依赖公式及原值保持。对 seed 的测试应打开完整 `Q3 Sales` 并覆盖刷新、重开和独立工作簿状态；现有种子源码虽然完整，不能由大量新建空白表用例代替。所有新增检查都应在参考实现和至少一个故意有缺陷的实现上分别运行，以证明它能区分正确与错误。

测试复审也须防止增加新的偏差。官方四个大小写正则、更新时间嵌套、首页全局链接数和额外筛选对话框不应并入需求规范测试；可放在独立兼容性清单中并注明其来源和争议。官方公式结果 12/13、透视编辑定位链失败及数据验证提示生命周期，需要完整操作轨迹或有控制的复现后才能定性。

## 生成与修复流程改进

低分产物的[质量摘要](/home/chris/Downloads/8ff1885a8162-template/template/.arc/quality-summary.json)把 `REQ-5-1-2` 记为 `generation_failed`、`REQ-5-2-1` 记为 `tool_incomplete`，`REQ-5-3-1` 和 `REQ-2-1-4` 为 `implemented_unverified`；最终 4 个节点测试失败。当前 [main.py](/home/chris/Works/octos-arc/arc/main.py:12754) 的 `OCTOS_FINAL_REPAIR_ROUNDS` 默认 0，`OCTOS_FINAL_SUITE_PASSES` 默认 1；最终全套发现失败后缺少常规的“修复并复测”机会。

建议按下列顺序实施。每步均要求产生修改前后同一场景的证据，不能仅看节点汇总：

1. **先修共享控件和透视状态入口。** 把排序、筛选、验证、透视字段统一到可见且可用键盘操作的选项组件；让下拉单元格显式暴露 `option`。以官方报告中 22 个选项阻断和 10 个透视入口阻断为回归清单，修复后确认每例越过原阻断点，再核对后续断言。
2. **修已确认的业务缺陷。** 修复验证规则区域查找和修改、非活动表删除、空日期 Before、透视来源丢失、聚合文本处理。每项保留失败前状态、成功后状态以及刷新后的断言。
3. **调整测试门禁。** 保留需求语义层，增加官方兼容性交互层；基础删除工作表测试放在早期节点，跨透视删除留在集成阶段。对同一个首个失败点聚类修复，避免几十个用例重复触发同一轮代码生成。
4. **为最终全套预留复测。** 在运行配置中至少安排一次完整测量、一次针对失败簇的修复、一次复测；在允许时间内设置正数 `OCTOS_FINAL_REPAIR_ROUNDS` 和不小于 2 的 `OCTOS_FINAL_SUITE_PASSES`。同时记录每次代码哈希、变更文件、首个失败点及其变化，避免将无效修改计为进展。
5. **控制证据体积。** 低分模板约 1.3 GB；其中 `.arc/acceptance-evidence` 约 1.2 GB，80 个子目录中的 **2381 个 `trace.zip` 合计约 1150 MiB**，应用 `frontend` 与 `backend` 合计约 516 KiB。交付包可保留最终报告及少量失败 trace，其余历史轮次另行归档并设容量上限。原始包目前保持不变。

完成标准不宜设为单纯的 derived 全绿。至少应满足：所有原先被共享控件阻断的官方操作路径能走到下一断言；上述已确认业务缺陷各有独立可复现回归；最终全套在相同源码哈希上无失败或留下明确争议清单；再次提交官方评测后逐场景比较，而非只比较总分。

## 对前次分析的复审结论

**确认：** 低分 59/100 与内部 182/195 均由下载包直接证实；原生选项点击是 22 例的首个阻断；透视编辑区的 Rows 定位链在 10 例中失败；文件夹体积主要由浏览器 trace 造成。需求文本哈希一致，排除了两次运行使用不同原始需求的解释。

**修正：** 前次引用的 87/100 原本来自另一份历史审计；现在已从 `8aa637d019a5` 本身的报告确认它确为 **87/100**。前次本地 247/248 使用的是后来又改过六个文件的参考应用，不能代表 `8aa637d019a5` 下载包的同版测试成绩。高分运行自身仍有非活动工作表删除等实现缺陷，不能把它当作完整正确的标准答案。

**保留不确定性：** 官方仅给首个失败和附近调用栈，不能据此断言透视区域是不存在、被隐藏还是 Rows 控件失配，也不能断言 22 个选项和 10 个透视入口修完后可全部通过。当前证据没有证明官方在这 41 例中大量测试了 requirements 未写明的 Sheet 业务常识；已确认的验证范围、透视来源、空日期和数字聚合问题，主要是**原子需求已有约束而实现或 derived 覆盖仍不足**。官方明确超出原文的项目则集中在部分定位、文案和全局数量断言。
