import hashlib,json,re,sys
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parent
SUITE=ROOT/'template/derived-tests'
SOURCE=ROOT/'template/requirements/requirements.yaml'
WORKSPACE=ROOT.parents[1]
sys.path.insert(0,str(WORKSPACE/'arc'))
from embedded_suites import verify_directory,requirements_digest
from requirement_order import topo_order

# Manual semantic review of the downloaded specs, including the 53 retained
# cross-node witnesses. Counts measure case identity, not clause coverage.
REVIEW={
'REQ-1-1-1':('P2','首页打开、稳定地址、刷新、独立浏览器会话；后续 context 验证时间戳一致、工作簿隔离及复合状态重开','编辑后的 last updated 是否真正更新未验证；独立会话的完整筛选、验证、选区、透视配置组合覆盖有限'),
'REQ-1-2-1':('P1','创建后单一 Sheet1、A1 选中、刷新及直接地址；后续验证新工作簿不继承他簿状态','没有创建保存失败、可重试及首页无残留记录的用例；基础创建只检查 A1 为空，并未检查整个已渲染数据区'),
'REQ-1-2-2':('P1','修剪、成功改名、首页重开、空名称拒绝；context 验证只改当前工作簿','没有有效名称在服务器保存失败时保留原名的用例；prefill 只验证非空，未与最后保存名逐字比较'),
'REQ-1-3-1':('P1','Unicode、逗号、引号、嵌入换行、007、空字段、错误引号无残留；context 验证首行普通数据及只剥离最后扩展名','有效 CSV 的存储失败及重试没有覆盖；普通字段经 Formula bar 作精确检查，但网格 helper 本身压缩空白'),
'REQ-1-3-2':('P2','下载文件名、独立 CSV parser、转义、空字段、计算结果、当前表限定、隐藏行仍导出、状态保留','导出前后不是完整状态快照；部分网格及选区仍只检查少量坐标，尚缺筛选和选区同时保持的完整比较'),
'REQ-2-1-1':('P1','新增激活、顺序及 A1；context 验证 first unused SheetN、既有数据及筛选和验证隔离','没有新增保存失败时无新 tab、原表不变的用例；从有透视结果的工作簿新增空表后，对透视继承的显式断言有限'),
'REQ-2-1-2':('P2','选中单元格、完整矩形选区、最后活动表、公式、验证及筛选独立；复合重开验证透视结果','跨表状态隔离已较广，但没有一套每表完整结构、公式、选区、筛选、验证、透视配置的统一状态快照'),
'REQ-2-1-3':('P1','prefill、修剪、空白及重复拒绝、刷新、顺序及数据规则保留','有效新名称遇到保存失败时的错误和原名保持没有覆盖；失败后即时状态及首页重开覆盖不完整'),
'REQ-2-1-4':('P1','删除确认、目标名称、末表保护、相邻激活、删源表保护、删透视表释放约束、命名空位复用','一般存储失败时目标 tab 及全部数据保持未测；删除包含 numeric rule 的表时，没有通过后续输入证明规则已完全清理'),
'REQ-2-2-1':('P1','seed 移动完整记录、上下插入、删除、刷新；后续 context 覆盖公式、筛选、规则及透视源联动','没有插入或删除保存失败后的结构原子性；多行连续变动、结构变化中复合范围公式的边界仍有限'),
'REQ-2-2-2':('P1','seed 完整列移动、左右插入、删除、刷新；context 覆盖 #REF、验证、筛选、透视字段移动及删除','没有插删列保存失败后原结构保持；删除被选透视字段后只打开 editor 而不点 Refresh 的错误路径未单独验证'),
'REQ-3-1-1':('P1','grid 与 Formula bar 的 Enter、blur、Escape；文本、数字、布尔类、日期；HTTP 500 保存失败及重试','失败测试额外要求 alert role 且限定 HTTP 请求体；通过 inline Edit 控件输入公式未覆盖；普通值空白损坏可能被 helper 漏掉'),
'REQ-3-1-2':('P1','完整 TSV、空字段、目标外保持、菜单和 Ctrl+V、覆盖公式及依赖重算；验证失败全量回滚','没有有效矩形在存储失败时所有目标及依赖保持的用例；只用 values 的普通文本缺精确空白检查'),
'REQ-3-1-3':('P2','正向及反向拖动、替换选区、刷新、跨表保持、范围排序不扩展','outside 列表仅抽样，不能排除未列出的格子残留 aria-selected=true；缺首页重开后的完整矩形检查'),
'REQ-3-2-1':('P1','二维 copy/cut、源及目标保持、重叠剪切、外部剪贴板替换、相对及绝对引用、验证拒绝','没有有效移动遇到保存失败后的源目标及依赖全量回滚；先显示完整目标再清源只验证前后状态，未观测中间顺序'),
'REQ-3-2-2':('P2','连续 undo/redo、按钮及快捷键、新分支禁 redo、跨簿隔离；context 覆盖公式、结构、规则及透视有效性','删除结构与恢复的矩阵仍有限；一个透视联动用例在 Refresh 后要求还能 Redo，额外假定 Refresh 不进入历史'),
'REQ-4-1-1':('P2','基本运算、括号、A1、六种聚合、大小写、忽略空格子及文本、负数 MAX、原公式及持久化','没有通过 grid inline editor 输入公式的用例；连续区域聚合大多只用单列，二维区域及复杂引用组合不足'),
'REQ-4-1-2':('P2','相对及完整绝对引用、二维拷贝、目标结果、源保持、越界 =#REF!、刷新','位移主要为对角线；仅水平或垂直位移、范围引用拷贝及更远列的覆盖仍有限；混合引用语义可作为后续需求澄清'),
'REQ-4-2-1':('P2','直接及传递依赖，编辑、paste、move；context 验证结构调整及另一表不变','依赖图主要为简单链；多支合流和二维 SUM 区域的结构变动可补强，不能据此判定已有结果错误'),
'REQ-4-2-2':('P2','五类稳定错误、直接及间接环、刷新、错误修复、依赖恢复、错误隔离及传播','各错误类型的 inline editor 输入及多分支错误隔离未覆盖；间接循环用例没有逐个验证两格的原公式'),
'REQ-5-1-1':('P1','文本升降序、稳定相等键、数字、表头、完整数值记录、范围外保持、公式及过滤验证联动','日期样本全为 ISO，字符串排序也通过；没测排序保存失败后的原序保持；基础升降序漏断言 Status 列，补充数字用例不能替代此分支'),
'REQ-5-1-2':('P2','值过滤、五种条件、跨列 AND、隐藏非删除、清除恢复、隐藏行导出及透视、结构联动','日期 Before 样本同样无法排除字符串比较；没有完整验证 distinct checkbox 集合；清除后的公式及规则仅有部分 context 见证'),
'REQ-5-2-1':('P1','下拉修剪、上下含边界、定制界限、所有输入路径拒绝、批量原子性、修改及删除规则、结构随动','Number range 未测试非数字字符串；有效规则保存、修改及删除的存储失败分支缺失；存在使用旧错误文本即可满足下一次断言的风险'),
'REQ-5-3-1':('P2','SUM/COUNT/AVERAGE、行列布局、首次出现顺序、总计、隐藏行参与、显式 refresh、源字段删除及重选、undo 关联','未在重开后验证所有 Columns 配置；尚缺其它可达 invalid range 路径；部分无数字分组输出在原需求未明确，不宜擅自强制 0 或空值'),
}

def flatten(n):
 yield n
 for c in n.get('children',[]):yield from flatten(c)
def line_map(n,result):
 if isinstance(n,yaml.MappingNode):
  d={k.value:v for k,v in n.value}
  if 'id'in d:result[d['id'].value]=d['description'].start_mark.line+1
  for _,v in n.value:line_map(v,result)
 elif isinstance(n,yaml.SequenceNode):
  for v in n.value:line_map(v,result)
def link(rel,line,label):
 return f'[{label}]({ROOT/rel}:{line})'
tree=yaml.safe_load(SOURCE.read_text()); nodes=list(flatten(tree)); atomic=[n for n in nodes if n['type']=='ATOMIC'];assert set(REVIEW)=={n['id'] for n in atomic}
manifest=verify_directory(SUITE,tree,'hackathon--sheet');plan=json.loads((SUITE/'case-plan.json').read_text());line={};line_map(yaml.compose(SOURCE.read_text()),line)
rows=[]
for n in atomic:
 priority,covered,gaps=REVIEW[n['id']];f=SUITE/(n['id']+'.spec.ts');cases=[p for p in plan if p['node_id']==n['id']];actual=re.findall(r'^test\("([^"\n]*)"',f.read_text(),re.M);assert actual==[p['title']for p in cases]
 rows.append({'requirement_id':n['id'],'name':n['name'],'priority':priority,'primary_cases':len(cases),'covered':covered,'gaps':gaps,'requirement_description_line':line[n['id']],'primary_spec':f.name,'context_origin_cases':sum(p.get('origin_node_id')==n['id'] for p in plan)})
(ROOT/'coverage-audit.json').write_text(json.dumps({'basis':'Manual assertion review of downloaded snapshot; contextual witnesses included; primary counts are not clause coverage percentages','rows':rows},ensure_ascii=False,indent=2)+'\n')
results=json.loads((ROOT/'oracle-checks/results.json').read_text())
summary={'run_id':'03a12926c294','nodes':len(nodes),'atomic_requirements':len(atomic),'scenario_count':sum(len(n.get('scenarios',[]))for n in nodes),'generic_workflow_scenarios':100,'specs':manifest['spec_count'],'cases':len(plan),'raw_requirements_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'canonical_requirements_sha256':requirements_digest(tree),'manifest_identity_verified':True,'obligation_inventory_count':len(json.loads((SUITE/'test-obligations.json').read_text())['obligations']),'oracle_checks':results['stats'],'product_suite_executed':False,'confirmed_findings':['values helper collapses whitespace','values helper removes all button data','save failure imposes alert role','date fixture cannot distinguish lexical from chronological sorting'],'excluded_hypothesis':'inline timestamp layout restriction did not reproduce'}
(ROOT/'audit-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
report='''本报告对照 [ARC Bench 表格运行](https://arc-bench.com/runs/03a12926c294) 下载快照中的 requirements 与 derived-tests。结论是：**需求来源和测试身份一致，主要成功流程及大量跨节点联动已覆盖，但测试尚不能作为完整需求一致性的验收依据。确认存在过度约束、断言漏检和失败分支覆盖不足。**

下载时间为 2026 年 10 月 2 日 12:38（Asia/Shanghai），页面当时仍在 Stage 2，Stage 3 未评测。本报告审核固定的下载内容，不代表此后的最新运行产物或平台成绩。未修改生产代码、下载测试或需求，也未提交 Git。

## 下载来源和核对口径

ZIP 已下载至 `/home/chris/Downloads/03a12926c294-template.zip`，解压目录为本报告旁的 `template/`，共 79 个文件。ZIP SHA256 为 `707f837eb7da808cb669d8962cac454f853388a624cc2afd3649cc044d053b54`；download.json 保存文件摘要及来源。

需求树有 42 个节点，其中 24 个原子需求、100 个 scenario。两个 requirements.yaml 字节完全相同，原始 SHA256 为 `9cddf67be50748106289ed158648629a6c50c30a490d0eda5bd570c557440b96`。suite-origin 中的 `0cd43ed5…` 是排序键后的规范 JSON 摘要，核验通过，**这不是需求版本冲突**。

24 个 spec 注册了 131 个测试，Playwright discovery、case-plan、review 及文件摘要全部对应。未发现 skip、fixme 或 only。review 标记是源码审查；源文件自己声明 `runtime_status=not_run_against_product`，不能将 trusted 或 reviewed 等同于运行通过或需求全覆盖。

100 个 scenario 均出现 “the requested workflow”，部分句子缺失具体动作。因此，本轮以原子 description 和父节点约束作为判断基准，并保留 scenario 中仍明确的值和持久化约束。原始 scenario 的修复也属于后续改进范围。

## 已确认的测试问题

### 单元格值断言会忽略有业务意义的空白

'''
report+=link('template/derived-tests/helpers.ts',26,'helpers 的 values 函数')+' 对实际和预期值都执行 `replace(/\\s+/g, " ").trim()`。`双"引号\\n下一行` 与 `双"引号 下一行` 会相等，`  a  b  ` 与 `a b` 也会相等。隔离复现中，错误文本通过了原 helper。对于普通文本、paste 和 copy 的原文保持，这削弱了判断能力。\n\n'
report+='这里不能笼统地说 CSV 换行已经完全漏测：导入用例通过 ordinary 还检查 Formula bar 的精确值，导出用例通过独立 parser 检查 CSV。缺陷主要在网格显示检查和只调用 values 的路径。建议将数据原文检查与装饰性 UI 文本检查分开，普通值通过 Formula bar 或明确的数据值读取作精确比较。\n\n'
report+='### 单元格 helper 过度删除所有按钮文本\n\n'+link('template/derived-tests/helpers.ts',32,'values 中的内容过滤')+' 将所有 button 和 role=button 子元素都移除。确认两种后果：多出来的可见按钮文本被忽略；正常数据文本若渲染在按钮内，则 helper 得到空串并误判失败。requirements 规定 gridcell 的角色及坐标名称，没有规定数据必须位于按钮之外。\n\n建议只排除已明确属于装饰的内容，或对值和菜单按钮作分别断言；不要以任意 button 标签作为删除数据的规则。\n\n'
report+='### 保存失败用例增加了需求未规定的错误角色\n\n'+link('template/derived-tests/REQ-3-1-1.spec.ts',24,'failed cell save 用例')+' 要求错误位于 `[role="alert"]:visible`，而 '+link('template/requirements/requirements.yaml',1161,'REQ-3-1-1')+' 只要求显示错误并保留最后成功的值及依赖。普通可见错误段落会被该断言拒绝，已作隔离复现。\n\n此外，它只拦截同源 POST、PUT、PATCH 且请求体包含候选字符串的写入，再要求 intercepted attempts 大于零。WebSocket、编码后的 body 或独立 API origin 等实现可能不适配。这属于测试适配限制，不能直接当作产品不符合需求。失败注入应由目标实现适配器识别真正的写操作，并检查错误可见及完整状态未变；有意要求 alert role 时，应先写进 requirements。\n\n'
report+='### 日期用例不能排除错误的字符串比较\n\n'+link('template/derived-tests/REQ-5-1-1.spec.ts',25,'日期排序用例')+' 使用 YYYY-MM-DD 的 ISO 文本。这组数据按字符串和按日期比较的顺序完全一致，已用同一数据复现。'+link('template/derived-tests/REQ-5-1-2.spec.ts',22,'Before 过滤')+' 的输入与阈值也都是相同格式，因此同样无法排除字符串比较。\n\n建议采用需求允许的可解析日期，并加入两种比较产生不同结果的见证；例如明确支持后，使用 2026-1-2、2026-2-1、2026-12-31。不要无依据扩展成对所有地区日期格式的强制要求。数字排序用 100、2、30，已经能够区分字典序，这部分设计是有效的。\n\n'
report+='## 失败分支和状态恢复的覆盖缺口\n\n全套只有一个 `page.route` 保存失败注入，位于单元格编辑测试。空名称、重复名称、非法 CSV、非法验证值和无数字透视字段已覆盖，但这些是输入或业务拒绝，不能代替有效请求遭遇存储失败。\n\n尚缺的明确需求分支包括：创建工作簿失败后无残留且可重试；工作簿或工作表改名保存失败保留原名；新增表失败无 tab；一般删表失败保留 tab 和数据；插删行列失败无部分移动；有效 paste/cut 保存失败全部回滚；排序失败保留原序。这些约束都写在原子或父节点 description 中。\n\n每项失败测试应比较操作前、报错后、刷新后以及重试成功后的状态，包括所有相关格子、原公式、计算结果、选区、表名及顺序、规则、筛选和透视源配置；同时保留另一工作表或工作簿作为隔离见证。使用 UI 成功刷新只能证明浏览器可重读，不能证明真正磁盘故障或进程重启下的数据行为。针对这些故障，需要控制实现进程和存储的测试 harness。\n\n## 需要进一步澄清的额外假设\n\n'+link('template/derived-tests/REQ-5-3-1.spec.ts',109,'透视与 undo redo 联动用例')+' 在 Undo 后刷新透视表，再要求 Redo 仍能恢复结构。另一个同文件用例在 '+link('template/derived-tests/REQ-5-3-1.spec.ts',141,'注释')+' 已承认 Refresh 可以成为新的历史操作。前一个用例因而依赖额外历史策略；requirements 未明确 Refresh 是否影响 redo 分支。本轮未在产品中复现此冲突，不把它列为已确认产品错误。建议把 redo 检查放在中间更新前，或者先明确历史策略。\n\n部分错误用例重复用同一错误文本断言，旧提示可能使下一次断言立即满足。最终数据未变仍有价值，但不能单凭旧文本证明新的提交被正确拒绝。建议断言输入恢复、提交完成和与当前操作关联的新反馈。\n\n## 逐项需求对照\n\n下表将后续节点承接的 context 见证也计入判断。用例数仅表示该 spec 的主节点归属，其中可能承接别的需求；它不是该需求的条款覆盖率。P1 为应优先修补的问题，P2 为后续补强，不代表线上实际失败概率。\n\n| 需求 | 本 spec 用例数 | 已有有效覆盖 | 剩余缺口 | 优先级 |\n| --- | ---: | --- | --- | --- |\n'
for r in rows:
 report+='| '+link('template/requirements/requirements.yaml',r['requirement_description_line'],r['requirement_id'])+' | '+str(r['primary_cases'])+' | '+r['covered']+' | '+r['gaps']+' | '+r['priority']+' |\n'
report+='''
## 导出文件省略情况

suite-origin 登记省略 17 个 INTEGRATION spec、源套件 184 个用例、导出 131 个用例。本轮对照了当前本地 Sheet 源套件：下载的 24 个 REQ spec 均与源文件逐字一致，source_manifest 摘要也一致。17 个被省略文件共含 53 个原始用例，其 origin_title 在导出 case-plan 中都有对应的 53 个 context 见证，没有缺少来源标题。不能把这些文件的省略直接算成 53 个行为漏测。

已声明 requires 的执行顺序核对通过，没有晚于所属节点的依赖。该核对证明的是声明一致，不证明 requires 自动捕获了全部隐含能力。最终验收仍适合另设完整场景运行，以验证节点完成之后的最新代码没有破坏早先能力。

## 后续改进顺序

1. **先修断言和明确契约。** 去掉未经需求规定的 alert role；拆开精确数据值与装饰 UI 检查；明确失败注入适配层及 Refresh 的历史策略。每个修改先用已知正确和已知错误页面验证，防止修复一个误判又引入另一个。
2. **补有效操作的失败回滚矩阵。** 优先覆盖创建、改名、插删行列和剪切。这些操作的部分成功容易同时影响多个状态。将业务拒绝、网络失败、服务端写入失败和实际存储失败分别记录。
3. **增加能识别错误实现的数据。** 日期使用能区分字符串比较的数据；数字验证补非数字输入；公式通过 inline editor、二维聚合和水平或垂直位移执行；各排序方向逐列断言整个记录。
4. **统一状态快照与隔离检查。** 对每个工作表记录完整已用范围、原公式及结果、完整选区、规则、过滤及透视配置。比较刷新、首页重开和独立浏览器会话，减少抽样坐标遗漏。
5. **建立条款到断言的覆盖台账。** 339 项 test-obligations 目前明确是原文条款清单，没有自动推出可执行见证。建议给每个可验证条款记录 case、关键断言、成功或拒绝分支、持久化与隔离见证、未覆盖原因；先去除摘要和范围说明，再讨论覆盖率。
6. **用错误实现验证测试判别力。** 注入字典序日期排序、只移动排序键列、部分 paste、提前清 cut 源、忽略非数字验证、刷新后丢选区等变体。正确实现应通过；每个违反已明确需求的变体应被相应断言抓住。
7. **修复泛化的原始 scenario。** 恢复明确前置条件、动作、输出和失败后状态，保留原文版本与变更记录；不要把后生成的测试假设倒写成已有需求。

优先落点是 arc/embedded_sheet_cases.py、共享 helper 的生成来源、导出审查及覆盖台账。改动后重新生成 suite-origin、review 和清单摘要，避免直接修改 frozen spec 却保留旧的 trusted 标记。本轮仅提供审查和复现证据，未实施这些修改。

## 复现和范围

Playwright 实際 discovery 为 131 tests in 24 files。另用下载的原 helper 作 6 项隔离检查，最终 6 项通过：五项确认指定的断言弱点或日期数据不可区分性，一项对照排除了“inline 时间戳布局会失败”的怀疑。检查通过意味着发现被复现或怀疑被排除，不意味着下载产品通过 131 项验收。未启动产品、未跑平台官方评测。

原 helper 复制件与下载原文件字节一致。oracle-checks 中的小型页面是受控见证，不是下载应用。原始怀疑第一次执行未复现，因此修正了验证假设；最终测试保留成功的反证对照，报告没有将该猜测列为问题。

本目录保留 download.json、integrity-checks.json、audit-summary.json、coverage-audit.json、requirements-readable.txt、discovery.log、复现代码及 results.json，build_audit.py 可重新生成本报告与对照表。discovery 和复现使用本机现有的 Playwright 1.63.0；未安装新依赖。
'''
report=report.replace('实際','实际')
(ROOT/'audit-report.md').write_text(report)
print(json.dumps({'report':str(ROOT/'audit-report.md'),'rows':len(rows),'cases':len(plan),'oracle_stats':results['stats']},ensure_ascii=False,indent=2))
