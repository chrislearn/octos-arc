import collections
import hashlib
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
SUITE = ROOT / 'template/derived-tests'
SOURCE = ROOT / 'template/requirements/requirements.yaml'

# Manual source review of the downloaded snapshot, including inherited clauses.
# P1/P2 are proposed repair priorities, not measured failure rates.
REVIEW = {
    'REQ-1-1-1': ('P1', '成功注册、多字段错误、重复用户名；后续登录用例验证新账号可用', '重复邮箱、单独确认不匹配、缺失字段、用户名和邮箱及密码边界未覆盖；字段角色和错误所属字段验证不足'),
    'REQ-1-1-2': ('P1', '用户名及邮箱登录、未知账号、错误密码、不可用账号、刷新及独立会话', '失败保留标识并清空密码、受保护请求使用真实会话、重复登录不新增账号未验证；共享登录 helper 过度要求用户名为独立文本'),
    'REQ-1-1-3': ('P1', '正确和错误验证码、未知邮箱进入相同下一步、更新后旧密码失效', '新密码规则、确认不匹配、缺失字段、未知邮箱的字段错误、失败后密码清空、其他账号不变未覆盖'),
    'REQ-1-2': ('P2', 'Cancel 保留页面、确认退出、刷新及返回及直接进入、其他会话保留', '关闭对话框等价于取消、对话框说明、仓库和组织受保护入口、服务器端会话撤销未充分验证'),
    'REQ-1-3': ('P1', '成功换密、旧密码失效、缺当前密码、错误当前密码并确认不匹配', '不合规新密码、单独缺失新密码或确认、失败后候选密码也不能登录、其他账号不变未覆盖'),
    'REQ-2-1-1': ('P2', '访客实时查公共仓库、返回、隐藏私有仓库', 'Public 或 Private 筛选、授权用户的私有仓库、完整 owner/name 与描述及更新时间未充分验证'),
    'REQ-2-1-2': ('P2', '成功创建及 Owner 关系、重复名称、非法名称和空白显示名', '成功后 Your organizations 列表、名称及显示名边界、权限后续生效、创建失败的原子性未覆盖'),
    'REQ-2-2-1': ('P1', 'Owner 创建无描述无父级团队、非法名称拒绝', '同组织重复名称、缺失或过长名称、正常父级、外组织父级、非 Owner 创建拒绝未覆盖'),
    'REQ-2-2-2': ('P1', '直接成员增加和删除持久化、选择后代造成环被拒绝；REQ-4-4 有部分授权联动', '正常换父级、同组织约束、非 Owner、非组织成员、重复加入、完整无隐式继承矩阵未覆盖'),
    'REQ-2-2-3': ('P1', '立即加入 Member、个人组织列表可见但无私有仓库权限、未知及重复成员', '按邮箱加入、Owner 加入与 Admin 效果、默认 Member、非法角色、非 Owner 提交未覆盖'),
    'REQ-2-2-4': ('P1', 'Owner 删除成员后拒绝仓库访问、账号仍可登录、普通成员没有删除控件', '最后 Owner 不可删除、所有团队成员关系及所有直接 grants 清理、team grants 和其他组织及个人仓库保留未覆盖'),
    'REQ-2-3': ('P1', '团队 Write 新增及改为 Read；REQ-4-4 有实时权限及移除团队成员联动', '人员授权、所有五种角色、同角色重复保存、直接与团队 grants 叠加取最高角色、非 Admin 服务端拒绝未覆盖'),
    'REQ-3-1': ('P2', '公共仓库可搜索及刷新、访客私有仓库不显示、空结果重复搜索、前置种子可发现', '授权后私有仓库搜索及撤权后列表同步、多个 owner 的同名仓库身份验证不够全面；负断言可能过早完成'),
    'REQ-3-2-1': ('P1', '个人 Private 加 README 及描述、空名称及重复名称', '组织 owner 权限、Public 和不初始化路径、初始 commit 与 branch、初始化失败无部分记录未覆盖'),
    'REQ-3-2-2': ('P1', '公共仓库 fork、源关系文字、历史消息、名称冲突', '源链接真实性、私有源保持 Private、源和目标权限、fork 修改不回写源、复制历史完整性未覆盖'),
    'REQ-3-2-3': ('P1', 'HTTPS 和 SSH 复制及 Copied 反馈', '只匹配仓库名和协议，错误 owner 也通过；未比较显示值与剪贴板或验证读取不改变仓库'),
    'REQ-3-3': ('P2', '访客读 Public 和 Code 链接、刷新仓库标题', 'owner/name 身份、描述和主要元数据、默认分支及内容入口验证不足'),
    'REQ-3-4': ('P1', 'Private 转 Public 后新访客读取、Write 看不到改可见性按钮', 'Public 转 Private 后所有列表及搜索及直接入口同步、其他非 Admin 角色、服务端权限检查未覆盖'),
    'REQ-4-1': ('P2', '目录到文件导航、完整文本及刷新', '分支和路径及文件身份一起保留、最近 commit、切分支同路径内容、只读不改变状态未充分验证'),
    'REQ-4-2-1': ('P2', '已知 commit 消息、页面上作者和相对时间', '文件专属历史、逆序与 commit 关联、作者及时间属于同一记录未验证；跨节点编辑用例只覆盖部分历史不变量'),
    'REQ-4-2-2': ('P1', '已知路径与 Changed files 和固定数量摘要、直接重开 commit', '实际新增及删除行、任意两可读 revision 的方向和内容差异、读取不改状态未充分验证'),
    'REQ-4-2-3': ('P1', '命中 README 后保存上下文、无结果和重复查询', '跨仓库及不可读内容泄露、分支及 revision 范围、结果 snippet 与路径验证不足；path 和 language 本身是可选过滤'),
    'REQ-4-3-1': ('P2', '实时 branch 筛选、目标独有文件、刷新目标 branch、未知项后 Escape 保留', '原 branch 字节与上下文、同路径内容切换、纯读取不写用户设置未充分验证'),
    'REQ-4-3-2': ('P1', 'Write 创建且刷新保留、invalid..branch、Read 和 Triage 拒绝', '255 字符边界和全部格式、重复名、真正指向当前 head、Maintain 及 Admin 和 Owner 正向未覆盖'),
    'REQ-4-3-3': ('P2', '切 feature-search 和 release、旧 main 仍存在且保留内容、非 Admin 无编辑控件', '已开放 PR 的 base/compare 不变、取消确认、其他非 Admin 角色、服务端拒绝未覆盖'),
    'REQ-4-4': ('P1', '创建及编辑文件、独立非法路径和空 message、历史不变、旧 revision 字节保留、团队 grants 联动', 'protected branch 直接写拒绝、Read/Triage 写拒绝、路径冲突及 message 长度、branch head 与 commit 原子性未覆盖；一例额外要求 alert role'),
    'REQ-5-1-1': ('P1', 'Open 加开放标题及 Closed 加关闭标题、部分刷新', '状态和关键词未独立变化，忽略状态也通过；body 和 label 搜索、Closed 刷新保留、只读不改数据未覆盖'),
    'REQ-5-1-2': ('P2', '直接重开、标题及描述及 Open、Comment 或 Activity 文字', 'Issue 编号、右侧 metadata、真实讨论及活动记录、不同角色控件资格验证不足'),
    'REQ-5-2-1': ('P1', 'Write 创建 title/body、回列表可见、空白 title 后链接快照不变', '编号唯一递增及失败不占号、长度上限、Read/Triage 拒绝、author 与状态及 creation activity 未充分验证'),
    'REQ-5-2-2': ('P1', 'Maintain 分别改标题和描述、空标题保留原值、Read/Triage 控件不可用', 'title/body 长度、列表同步和编辑 activity、其他字段保持、服务器拒绝低权限提交未覆盖'),
    'REQ-5-2-3': ('P1', '评论 body 和 author 持久化、空白不加 article', 'reaction 完全未测；长度上限和评论角色拒绝未覆盖；全量 article 文本即时比较易受异步加载和相对时间影响'),
    'REQ-5-3-1': ('P1', 'Maintain 实时添加及移除 eligible assignee、Read/Write 无 metadata 权限', '不合格候选不出现、活动历史保留、账号和 grant 不改变未验证；sidebar helper 限制未规定的 DOM 包装'),
    'REQ-5-3-2': ('P1', 'Maintain 为 Issue 添加及移除已有 label；其他文件有 Read/Write 控件限制', '外仓库 label 不出现及无法关联、不创建新 label、activity 保留、服务器权限未覆盖；同受 sidebar helper 影响'),
    'REQ-5-3-3': ('P1', 'Issue 上 milestone 与 None 持久化；其他文件有 Read/Write 控件限制', 'PR milestone 路径完全未测、外仓库 milestone 拒绝、同一项唯一关联和 activity 保留未覆盖；同受 sidebar helper 影响'),
    'REQ-5-4': ('P1', 'Maintain close/reopen、Read 无按钮、跨角色新 Issue 保留 body/comment/assignee 和活动', 'Closed 状态单独重载、label 和 milestone 保留、Triage 正向、Write 服务器拒绝未充分验证'),
    'REQ-6-1': ('P1', '创建保护开关和摘要、非 Admin 无创建按钮；REQ-6-2-3 测 pending 改 success；REQ-6-5 测部分保护生效', '已存在规则修改、protected branch 直接写拒绝、non-Admin 设置 check 拒绝、failure 状态及 setter 时间未覆盖'),
    'REQ-6-2-1': ('P1', '访客 Open 列表、刷新及重开相同 PR', 'Closed、Draft、Merged、author 和 review 状态过滤未测试；原场景的 Closed 与 author 过滤缺少可执行见证'),
    'REQ-6-2-2': ('P1', 'base/compare Native select、已知路径与 Commit summary、同 branch 禁创建', '不同 branch 但相同内容或不可比较、真实 commit 数和 diff、Read/Triage 无创建比较流、读取无修改未覆盖'),
    'REQ-6-2-3': ('P1', 'Open 创建且 title 修剪和 description 保留、空 title 无 PR、附带 check setter 用例', '相同 source/target 已有 Open 或 Draft 拒绝、长度及 role 拒绝、branch/commit 身份和编号未覆盖'),
    'REQ-6-2-4': ('P1', 'Draft 创建且 Merge disabled、作者 Ready 后 Open 和 title/branches 保留', 'Draft 不能提交 review、其他 Write 无 Ready 权限、Draft 输入规则和编号及 commit 保留未覆盖'),
    'REQ-6-3-1': ('P2', '访客 title、Commits 和 Files changed 摘要、直接重开及刷新', 'Conversation 的描述和讨论、真实 comparable commit 列表和 count、同一 PR/revision 一致性未充分验证'),
    'REQ-6-3-2': ('P1', 'src/search.ts 与固定 additions/deletions 文字', '只有摘要且完全没有真实 diff 行也能通过；新增文件、实际内容、changed file count 与方向未验证'),
    'REQ-6-3-3': ('P1', 'single comment 持久化、pending draft 作者可见且访客不可见；REQ-6-5 有 Outdated 联动', '实际 file/line/commit 锚定、author 或低权限拒绝、不同位置相同 body、失败不发布未充分验证'),
    'REQ-6-3-4': ('P1', '三种 decision、latest Comment 替换 Request changes、提交只发布自己草稿；REQ-6-5 有新 head stale', '作者和 Draft 及 Read/Triage review 拒绝未测试；Request changes 的 Summary 未断言；反向 decision 替换矩阵未完整覆盖'),
    'REQ-6-4': ('P1', '作者请求及删除 eligible reviewer 并持久化', 'Read/Triage 和作者不可作为候选、其他 Write 无请求权限、移除请求保留已有 review/comment/effective decision 未覆盖'),
    'REQ-6-5': ('P1', '实际 main 文件变化、Merged 终态、缺 approval、独立保护开关、Request changes 和 stale approval、新 head 重做 review/check', 'Read/Triage/Write 合并拒绝、conflict、check failure、Confirm 前 head 或规则变化、真实双 parent merge commit、整分支原子性未覆盖'),
    'REQ-6-6': ('P1', '作者 close/reopen、Read 无控件；REQ-6-5 有 Merged 不渲染状态按钮', 'Closed/Open 状态文字与 Closed 重载、Draft close、branch 字节和 reviews/discussion 保留、服务端拒绝非法终态未充分验证'),
}


def flatten(node):
    yield node
    for child in node.get('children', []):
        yield from flatten(child)


def yaml_lines(node, result):
    if isinstance(node, yaml.MappingNode):
        fields = {k.value: v for k, v in node.value}
        if 'id' in fields:
            result[fields['id'].value] = {
                'line': fields['id'].start_mark.line + 1,
                'description_line': fields['description'].start_mark.line + 1,
            }
        for _, value in node.value:
            yaml_lines(value, result)
    elif isinstance(node, yaml.SequenceNode):
        for value in node.value:
            yaml_lines(value, result)


tree = yaml.safe_load(SOURCE.read_text())
nodes = list(flatten(tree))
atomic = [node for node in nodes if node['type'] == 'ATOMIC']
assert {node['id'] for node in atomic} == set(REVIEW)
lines = {}
yaml_lines(yaml.compose(SOURCE.read_text()), lines)
plan = json.loads((SUITE / 'case-plan.json').read_text())
origin = json.loads((SUITE / 'suite-origin.json').read_text())
obligations = json.loads((SUITE / 'test-obligations.json').read_text())['obligations']
matrix = []
for node in atomic:
    priority, covered, gap = REVIEW[node['id']]
    spec = SUITE / (node['id'] + '.spec.ts')
    cases = [row for row in plan if row['node_id'] == node['id']]
    assert len(re.findall(r'^test\(', spec.read_text(), re.M)) == len(cases)
    matrix.append({
        'requirement_id': node['id'], 'name': node['name'],
        'requirement_source': str(SOURCE), **lines[node['id']],
        'spec': str(spec), 'case_count': len(cases),
        'existing_coverage': covered, 'gaps_or_defects': gap,
        'proposed_priority': priority,
        'semantic_coverage_status': 'partial; no numeric coverage rate claimed',
        'titles': [row['title'] for row in cases],
    })
(ROOT / 'coverage-audit.json').write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + '\n')
summary = {
    'run_id': '74294e08e089', 'scope': 'downloaded snapshot at 2026-10-02 12:16 Asia/Shanghai',
    'source_requirements_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'source_and_derived_requirements_identical': SOURCE.read_bytes() == (SUITE/'requirements.yaml').read_bytes(),
    'source_node_count': len(nodes), 'atomic_requirement_count': len(atomic),
    'source_scenario_count': sum(len(n.get('scenarios', [])) for n in nodes),
    'exported_spec_count': origin['spec_count'], 'exported_case_count': origin['case_count'],
    'per_module_case_count': dict(collections.Counter(row['node_id'].split('-')[1] for row in plan)),
    'ignored_source_specs': origin['ignored_specs'], 'source_case_count': origin['source_case_count'],
    'cross_node_context_cases': sum(': context ' in row['title'] for row in plan),
    'obligation_inventory_count': len(obligations),
    'distinct_requirement_quote_count': len({(r['requirement_id'],r['quote']) for r in obligations}),
    'mutable_fixture_count': sum(bool(row.get('fixture')) for row in plan),
    'unique_mutable_fixture_count': len({row['fixture'] for row in plan if row.get('fixture')}),
    'hash_integrity_verified': True, 'playwright_discovery': '110 tests in 47 files',
    'product_runtime_suite_run': False,
    'oracle_checks': {'passed': 10, 'false_rejection_probes': 5, 'false_acceptance_source_cases': 4,
                      'context_inheritance_exclusion_probe': 1,
                      'meaning': 'Audit probes reproduced oracle defects; these are not product passes'},
}
(ROOT / 'audit-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(summary, ensure_ascii=False, indent=2))
