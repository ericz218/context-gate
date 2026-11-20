"""Console navigation, page chrome and optional terminology explanations.

Only interface chrome is changed. Project content, model output, stored records,
API field names and element IDs are left intact.
"""
import json
import re

GUIDES = {
    'overview': ('总览', '查看 AI 用量、花费估算和最近任务。', ['tokens', '缓存', '对照测试']),
    'wb': ('项目进度', '按项目查看最近完成的事、当前状态和下一步。', ['交接']),
    'center': ('任务中心', '选择项目，把任务交给 AI，再查看结果和修改记录。', ['思考档位', '验收', '托管任务']),
    'group': ('群聊', '让多个 AI 在同一项目里分工；点成员查看各自的工作。', ['角色分工', '思考档位', '托管任务']),
    'todo': ('待办', '记下要做的事，完成后勾选；也可以批量导入。', []),
    'files': ('文件工具', '阅读、整理或对比文件内容。处理过程不调用 AI。', ['文字提取']),
    'memory': ('共享记忆', '查找项目和个人记忆，查看摘要、完整内容与原始依据。', ['权重', '置信度', '归档']),
    'gt': ('上下文压缩', '查看哪些内容发给了 AI，以及每次压缩任务的结果。', ['上下文', '估算用量', '对照测试']),
    'bill': ('花费估算', '按平台和模型查看花费；金额由用量和价格计算。', ['价格模式', 'tokens', '缓存']),
    'plat': ('平台对比', '比较各平台的用量、花费估算和响应时间。', ['tokens', '缓存', '对照测试']),
    'wallet': ('模型预算', '比较模型价格，估算预算能用多久，并手工记录余额。', ['预算记录', '预留与结算', '缓存']),
    'quota': ('订阅额度', '查看 Codex 和 Claude 的剩余额度、恢复时间与提醒。', ['额度周期', '提醒门槛', '托管任务']),
    'req': ('请求记录', '查看最近 50 次 AI 请求的用量、结果和耗时。', ['估算用量', 'tokens', '缓存']),
    'git': ('项目同步', '上传本机修改到 GitHub，或取回 GitHub 上的新版本。', ['push / pull', '提交', '分支']),
    'router': ('模型连接', '管理供应商、API 密钥，以及软件调用的模型名称。', ['模型连接', '模型别名', 'P50 / P95']),
    'sys': ('设置与诊断', '调整界面和快捷键；遇到问题时再展开连接检查与日志。', ['连接检查', '日志']),
}

TERMS = {
    'tokens': '模型计算文本用量的单位，不等于字数。输入是发给 AI 的内容，输出是 AI 的回答。',
    '缓存': '重复输入被复用，通常可减少输入费用。缓存命中率表示复用的输入所占比例。',
    '对照测试': '同一任务分别使用和不使用压缩，各运行一次后比较。未做对照的请求不计算节省。',
    '交接': '供下次继续工作使用的记录，包括已完成内容、未完成内容和下一步。',
    '思考档位': '模型投入多少思考。较高档位通常更慢，也可能消耗更多额度；具体取决于模型。',
    '验收': '检查结果是否符合你写的要求。任务结束与验收通过是两个不同状态。',
    '托管任务': '从本控制台的任务中心或群聊发起的任务。单独打开的其他聊天不一定能由这里控制。',
    '角色分工': '决策负责方案，执行负责实现；切换角色会沿用已有任务上下文。',
    '文字提取': '只读取文档中的文字和表格，不保留完整排版。图片中的文字目前不会自动识别。',
    '权重': '记忆被优先使用的程度。权重高不代表内容一定正确。',
    '置信度': '系统对这条记忆可靠程度的评估，不是经过保证的正确率。',
    '归档': '保留记录，通常不再优先用于当前任务；仍可查看或导出。',
    '上下文': 'AI 回答前能看到的项目文件、记忆和对话内容。压缩会挑选相关部分再发送。',
    '估算用量': '压缩前后按文本量估算；实际输入和输出来自供应商。估算不等于账单用量。',
    '价格模式': '按付费设置：免费额度和本地模型按 0 计算。按官方标价：估算相同用量的标价。两者都不是供应商账单。',
    '预算记录': '余额由你手工登记，这里不会读取真实账户余额，也不会实际扣款。',
    '预留与结算': '先从可用预算中预留一笔，结束后按登记用量结算。目前用于本机模拟记录。',
    '额度周期': '平台按 5 小时或每周等周期计算额度。恢复时间表示本周期何时结束。',
    '提醒门槛': '剩余额度低于这个百分比时提醒。例如填 20，表示剩余不超过 20% 时提醒。',
    'push / pull': 'push 把本机版本上传到 GitHub；pull 把 GitHub 的版本取回本机。',
    '提交': '把本机修改保存成一个 Git 版本。提交后还需要 push，才会保存到 GitHub。',
    '分支': '同一项目的一条独立工作线，用来分开不同功能或版本。这里显示正在同步哪条分支。',
    '模型连接': '把软件的 AI 请求送到所选供应商。API 密钥用于验证你有权使用该服务。',
    '模型别名': '给一个或多个实际模型起一个统一的调用名称，减少软件中需要更改的配置。',
    'P50 / P95': 'P50：一半请求在这个时间内完成；P95：95% 请求在这个时间内完成。用来判断典型速度和慢请求。',
    '连接检查': '检查所需配置是否存在、权限是否合适；默认只显示状态，不显示密钥内容。',
    '日志': '记录程序运行过程。排查失败原因时使用，不需要逐条阅读。',
}

EN = {
    '项目进度': 'Project progress', '文件工具': 'File tools', '共享记忆': 'Shared memory',
    '上下文压缩': 'Context filtering', '花费估算': 'Cost estimates', '平台对比': 'Compare platforms',
    '模型预算': 'Model budgets', '请求记录': 'Request history', '模型连接': 'Model connections',
    '设置与诊断': 'Settings and diagnostics', '这页怎么看': 'How to read this page',
    '页面说明': 'Page help', '已更新 · ': 'Updated · ', '正在更新当前页…': 'Updating this page…', '当前页更新失败，已保留上次结果；请查看页内提示。': 'This page could not be updated. Previous results are kept; see the message on the page.', '正在编辑或处理其他操作，稍后再刷新': 'An edit or operation is in progress. Refresh again when it finishes.', '已切换页面，请刷新当前页': 'Page changed; refresh the current page.', ' 组对照': ' measured pairs', '省 ': 'Saved ', '尚无实测对照': 'No measured comparisons yet', '使用说明': 'Page help', '相关概念': 'Terms used here', '工作': 'Work', '用量': 'Usage', '管理': 'Manage',
    '查看 AI 用量、花费估算和最近任务。': 'Review AI usage, estimated costs, and recent tasks.',
    '按项目查看最近完成的事、当前状态和下一步。': 'See recent work, current status, and next steps for each project.',
    '选择项目，把任务交给 AI，再查看结果和修改记录。': 'Choose a project, assign a task to AI, and review its results and changes.',
    '让多个 AI 在同一项目里分工；点成员查看各自的工作。': 'Let several AIs share work on one project. Select a member to inspect its work.',
    '记下要做的事，完成后勾选；也可以批量导入。': 'Add tasks and check them off, or import a list.',
    '阅读、整理或对比文件内容。处理过程不调用 AI。': 'Read, organize, or compare file contents without AI calls.',
    '查找项目和个人记忆，查看摘要、完整内容与原始依据。': 'Find memories and read summaries, full entries, and their sources.',
    '查看哪些内容发给了 AI，以及每次压缩任务的结果。': 'Review what was sent to AI and the outcome of each filtering task.',
    '按平台和模型查看花费；金额由用量和价格计算。': 'Review estimated costs by platform and model, calculated from usage and prices.',
    '比较各平台的用量、花费估算和响应时间。': 'Compare usage, estimated costs, and response times across platforms.',
    '比较模型价格，估算预算能用多久，并手工记录余额。': 'Compare prices, estimate how far a budget goes, and record balances manually.',
    '查看 Codex 和 Claude 的剩余额度、恢复时间与提醒。': 'Check remaining Codex and Claude quotas, reset times, and alerts.',
    '查看最近 50 次 AI 请求的用量、结果和耗时。': 'Review usage, results, and timing for the latest 50 AI requests.',
    '上传本机修改到 GitHub，或取回 GitHub 上的新版本。': 'Upload local changes to GitHub or bring new versions back.',
    '管理供应商、API 密钥，以及软件调用的模型名称。': 'Manage providers, API keys, and the model names used by your software.',
    '调整界面和快捷键；遇到问题时再展开连接检查与日志。': 'Adjust appearance and shortcuts. Expand connection checks and logs when needed.',
}

EN.update({
    " 个模型缺少价格，只统计用量。": " models have no price; only usage is counted.",
    "Local Model Router 汇总自定义连接与本地模型；付费模型仍按原价格计算，不因分类改变而变成免费。": "Local Model Router includes custom connections and local models. Paid models keep their original rates.",
    "两边改到了同一处，已保留双方内容，等待合并。": "Both computers changed the same content. Both versions are saved and need merging.",
    "价格与统计说明": "Prices and calculations",
    "价格配置：": "Price configuration: ",
    "刷新失败，保留上次结果：": "Refresh failed; previous results are kept: ",
    "原始模型名": "Original model name",
    "原应用会话 ": "Native app session ",
    "发现可能含有密码的文件，已暂停上传。": "Upload paused: a file may contain a password or secret.",
    "发送第一条消息后建立原应用会话": "A native app session is created after the first message.",
    "另一台停止中": "Stopping on the other computer",
    "另一台准备执行": "Preparing on the other computer",
    "另一台执行中": "Running on the other computer",
    "另一台排队中": "Queued on the other computer",
    "另一台正在派发": "Starting on the other computer",
    "另一台等待预约时间": "Scheduled on the other computer",
    "只有同一任务分别使用和不使用压缩后，才计算对照节省。": "Savings are counted only when the same task has been run both with and without compression.",
    "可信程度评估于 ": "Confidence assessed on ",
    "同一模型的不同思考档位合并统计，原始名称保留在请求详情。": "Reasoning levels of the same model are grouped together. Original names remain in request details.",
    "对比文字与表格内容，不比较排版或图表。": "Compare text and table contents. Formatting and charts are not compared.",
    "尚无价格：": "No price available: ",
    "尚未加入自动同步": "Not included in automatic sync",
    "尚未连接 GitHub，当前无法上传或取回更新。": "GitHub is not connected. Uploads and downloads are unavailable.",
    "已有版本已同步；另有本机修改，提交后会自动上传。": "Committed versions are synced. Local edits will upload after they are committed.",
    "当前打开的工作版本与自动同步设置不同，需要核对。": "The current branch differs from the sync setting. Review the branch configuration.",
    "找不到登记的位置。项目可能已移动，或所在硬盘未连接。": "The saved project location is unavailable. The project may have moved or its drive may be disconnected.",
    "换项目后下一轮生效；已有原应用会话会带着原项目的上下文继续，建议重要群聊保持项目不变。": "Project changes apply next round. Existing native app sessions retain the previous project context; keep important group chats on the same project.",
    "新版本已取回这台电脑": "New versions have been downloaded to this computer.",
    "暂时连接不上 GitHub，稍后会重试。": "GitHub is temporarily unreachable. Sync will retry later.",
    "更新中…": "Updating…",
    "更新记忆文档": "Update memory documents",
    "最近没有文件传输。没有改动时不会重复上传或下载。": "No recent transfers. Files are transferred only when something changes.",
    "本机修改已保存到 GitHub": "Local changes have been saved to GitHub.",
    "本项目只取回更新，不自动上传修改。": "This project downloads updates only. Local edits are not uploaded automatically.",
    "点击“更新记忆文档”生成完整阅读文档。": "Select “Update memory documents” to generate readable documents.",
    "登记位置：": "Saved location: ",
    "自动同步已暂停": "Automatic sync is paused.",
    "自动同步需要处理，请展开详情查看原因。": "Automatic sync needs attention. Open the details to see why.",
    "角色分工 · 决策 / 执行 / 自动交接": "Roles · planning, implementation and automatic handoff",
    "读取数据失败：": "Could not load data: ",
    "还没有可读取的记忆文档。点击“更新记忆文档”生成。": "No readable memory documents yet. Select “Update memory documents” to generate them.",
    "重新定位项目": "Locate project",
    "重试更新": "Retry update",
    "项目正在被修改，下一轮再检查。": "The project is being edited. Sync will check again next round.",
    "- [ ] 整理项目资料\n- [x] 完成本周计划\n1. 测试新版应用": "- [ ] Organize project files\n- [x] Finish this week’s plan\n1. Test the new app",
    "一份完整文档": "One complete document",
    "从系统开始记录账号时统计；更早的用量不归到当前账号。": "Usage is attributed from the time account tracking began. Earlier usage is not assigned to the current account.",
    "保留完整原始记录，适合备份或进一步处理。": "Keep the complete source records for backup or further processing.",
    "分类文档包": "Documents by topic",
    "原件保存在本机，不调用 AI。支持文字版 PDF；扫描图片暂不能识别。旧版 Word/Excel 请先另存为 DOCX/XLSX。": "Originals stay on this computer; no AI is used. Text-based PDFs are supported; scanned images are not. Convert older Word or Excel files to DOCX or XLSX first.",
    "原始记录包": "Source records",
    "只控制本机已连接的 Claude Code、Codex 和控制台任务。远程或未连接的聊天可能需要手动停止，结果会逐项显示。持续低额度时每 30 秒重试，不取消未来预约。平台没有提供的额度显示为未知。": "Controls connected Claude Code, Codex and console tasks on this computer. Remote or disconnected chats may need to be stopped manually; results are listed individually. Retries every 30 seconds while quota stays low. Future scheduled tasks are kept. Quota unavailable from a provider is shown as unknown.",
    "合成一份可阅读文档，并附原始记录；包括已归档和到期内容。": "Combine everything into one readable document with source records, including archived and expired entries.",
    "导出分类文档": "Export documents by topic",
    "按主题保存文档、目录和依据，保留文件夹结构。": "Save documents, indexes and sources by topic, preserving their folder structure.",
    "按行对比，黄色标出变化；左右可以分别翻页。": "Compare line by line; changes are highlighted in yellow. Each side can be paged separately.",
    "搜索项目": "Search projects",
    "筛选项目": "Filter projects",
    "每 5 分钟检查一次。有改动才上传或更新；没有变化就不传文件。这里显示这台电脑的同步情况。": "Checks every 5 minutes. Files are uploaded or downloaded only when something changes. Status is for this computer.",
    "电脑睡眠时暂停额度检查。": "Quota checks pause while this computer is asleep.",
    "自动停止与继续的范围": "Which tasks can be paused and resumed",
    "运行日志": "Activity logs",
    "按付费设置": "Configured cost",
    "每 5 秒更新显示；编辑中的表单会保留，关闭后可手动刷新": "Update the display every 5 seconds. Edits are preserved. Turn off for manual refresh."
})

EN.update({
    "多设备数据共享已连接": "Multi-device data sharing connected",
    "多设备数据共享暂未连通，连接后会自动补齐": "Multi-device sync is disconnected. Missing changes will sync when reconnected.",
    "按官方标价估算，包含免费请求；这不是实际账单。": "Estimated at official list prices, including free requests. This is not a provider invoice.",
    "按当前付费设置估算；免费额度和本地调用记为 $0。": "Estimated using configured payment settings. Free quotas and local calls count as $0.",
    "有修改并成功上传后，会显示时间": "The time appears after changes are uploaded successfully.",
    "有新版并成功取回后，会显示时间": "The time appears after a new version is downloaded successfully.",
    "每 5 秒检查变化": "Checks for changes every 5 seconds",
    "没有符合条件的项目。": "No matching projects.",
    "还没有项目加入同步。": "No projects have been added to sync yet.",
    "需要留意": "Needs attention",
    "有改动待提交": "Uncommitted changes",
    "已暂停上传": "Uploads paused",
    "未开启上传": "Uploads not enabled",
    "暂无上传记录": "No uploads yet",
    "暂无取回记录": "No downloads yet",
    "尚无检查记录": "Not checked yet",
    "还没有同步记录": "No sync activity yet",
    "已合并两边修改": "Changes merged",
    "已在这台电脑保存，等待上传": "Committed locally; waiting to upload",
    "上传或更新已恢复": "Uploads or downloads resumed",
    "当前分支": "Current branch"
})

EN.update({
    '使用与协作约定': 'Collaboration rules',
    '偏好与其他信息': 'Preferences and other information',
    '工作与验证记录': 'Work and verification history',
    '记忆系统与工具': 'Memory system and tools',
    '项目相关记录': 'Project records',
})

EN.update({
    "厂商官方价": "Vendor list price",
    "服务商参考价": "Provider reference",
    "价格来源": "Price source",
    "价格依据": "Price reference",
    "查看价格来源": "View price source",
    "美元 / 百万 tokens": "USD / million tokens",
    "核对日期": "Checked on",
    "Contributor 档位按其官方优惠价计算。": "Contributor mode uses its published discounted rate.",
    "按 DeepSeek 高峰标价比较；低谷与节假日优惠不另算。": "Uses DeepSeek peak list prices; off-peak and holiday discounts are not applied.",
    "按常规标价比较，不使用限时首发优惠。": "Uses standard list prices, excluding the limited-time launch promotion.",
    "缓存读取采用隐式缓存价；原始记录未区分显式缓存。": "Uses implicit-cache read rates; source records do not identify explicit caching.",
    "Flash-Next 按官方对应的 Qwen3.8-Flash 服务价格比较。": "Flash-Next is compared at the official corresponding Qwen3.8-Flash service rate.",
    "未公布缓存优惠，缓存输入按普通输入价比较。": "No cache discount is published; cached input is compared at the ordinary input rate.",
    "官方标价优先用厂商价格；开源模型可用已注明来源的服务商参考价。价格按核对日的公开标价比较，不是历史账单。": "Vendor list prices take priority. Open models may use a labelled hosting-provider reference. Estimates use public list prices checked on the stated date, not historical invoices."
})

TERM_EN = {'tokens': ('tokens',
            'Units used to measure model input and output; they are not the same as characters or '
            'words.'),
 '缓存': ('Cache',
        'Reused input can reduce input costs. The cache hit rate is the proportion of input that was '
        'reused.'),
 '对照测试': ('A/B comparison',
          'Run the same task once with compression and once without it, then compare. Requests without '
          'a measured pair do not count toward savings.'),
 '交接': ('Handoff',
        'A record for continuing work later: what is finished, what remains and what to do next.'),
 '思考档位': ('Reasoning effort',
          'How much reasoning the model uses. Higher levels may take longer or use more quota, '
          'depending on the model.'),
 '验收': ('Review',
        'Check whether the result meets your requirements. A finished task is separate from an approved '
        'result.'),
 '托管任务': ('Managed task',
          'A task started from this console’s Task Center or Group Chat. Separate chats in other apps '
          'may not be controllable here.'),
 '角色分工': ('Roles',
          'Planning sets the approach; implementation carries it out. Existing task context is retained '
          'when roles change.'),
 '文字提取': ('Text extraction',
          'Reads text and tables without preserving full formatting. Text inside images is not '
          'recognized automatically.'),
 '权重': ('Priority weight',
        'How strongly a memory is prioritized. A higher weight does not guarantee that its content is '
        'correct.'),
 '置信度': ('Confidence', 'An assessment of a memory’s reliability, not a guaranteed accuracy rate.'),
 '归档': ('Archive',
        'Keep the record while usually excluding it from current priorities. It can still be viewed or '
        'exported.'),
 '上下文': ('Context',
         'Project files, memories and conversation the AI can see before responding. Compression '
         'selects relevant parts to send.'),
 '估算用量': ('Estimated usage',
          'Before-and-after compression figures are estimated from text. Actual input and output come '
          'from the provider; estimates are not billable usage.'),
 '价格模式': ('Cost basis',
          'Configured cost treats free quotas and local models as zero. Official price estimates what '
          'the same usage would cost at list price. Neither is a provider invoice.'),
 '预算记录': ('Budget record',
          'Balances are entered manually. This console does not read real account balances or charge '
          'your account.'),
 '预留与结算': ('Reserve and settle',
           'Reserve part of the available budget, then settle it using recorded usage. This currently '
           'simulates local bookkeeping.'),
 '额度周期': ('Quota window',
          'Providers measure usage over periods such as 5 hours or a week. The reset time marks the end '
          'of the current window.'),
 '提醒门槛': ('Alert threshold',
          'Alert when remaining quota falls to this percentage or below. For example, 20 means 20% '
          'remaining.'),
 'push / pull': ('push / pull',
                 'Push uploads local versions to GitHub. Pull brings GitHub versions back to this '
                 'computer.'),
 '提交': ('Commit',
        'Save local edits as a Git version. A commit must still be pushed to be saved on GitHub.'),
 '分支': ('Branch',
        'A separate line of work in a project, used to keep features or versions apart. This view shows '
        'the branch being synced.'),
 '模型连接': ('Model connections',
          'Send AI requests from your software to a selected provider. An API key verifies your access '
          'to the service.'),
 '模型别名': ('Model alias',
          'A shared name for one or more actual models, so you can change routing without reconfiguring '
          'every app.'),
 'P50 / P95': ('P50 / P95',
               'P50: half the requests finish within this time. P95: 95% finish within it. These show '
               'typical performance and slow requests.'),
 '连接检查': ('Connection checks',
          'Check that required settings exist and permissions are suitable. Only status is shown by '
          'default, not secret values.'),
 '日志': ('Logs',
        'Records of how the program ran, used to investigate failures. You do not need to read every '
        'entry.')}
for term, (label, explanation) in TERM_EN.items():
    EN[term] = label
    EN[TERMS[term]] = explanation

# Secondary views stay next to their parent, rather than competing with every
# daily destination. All original buttons and their keyboard handlers survive.
NAV_GROUPS = (
    ('工作', ('overview', 'center', 'group', 'todo', 'memory', 'files')),
    ('用量', ('bill', 'quota')),
    ('管理', ('git', 'router', 'sys')),
)
NAV_CHILDREN = {'center': ('wb', 'gt'), 'bill': ('plat', 'wallet', 'req')}

CSS = r'''
.console-header{display:grid;grid-template-columns:minmax(0,1fr) auto;column-gap:24px;row-gap:16px;align-items:center;margin:0 0 4px;padding:0;border:0}
.page-heading{display:flex;align-items:center;gap:10px;min-width:0}
.console-header h1{font-size:24px;font-weight:650;letter-spacing:-.025em;line-height:1.3;width:auto}
.page-help{display:inline-grid;place-items:center;width:24px;height:24px;min-height:24px;padding:0;border:0;border-radius:50%;color:var(--muted);background:transparent;font-size:13px}
.page-help:hover{background:var(--rowhover);color:var(--text)}
.page-help[hidden]{display:none}
.global-actions{display:flex;gap:8px;align-items:center;justify-content:flex-end}
.global-actions button{min-height:34px;font-size:13px;white-space:nowrap}
.global-actions .iconbtn{width:34px;height:34px}
.refresh-control{flex:none;width:84px}
.refresh-control #refresh{width:84px;min-width:84px;max-width:84px;min-height:34px;padding:0;background:var(--cardT);color:var(--text);border:1px solid var(--line2);box-shadow:none}
.refresh-control #refresh:hover{background:var(--rowhover)}
.page-toolbar{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding-bottom:16px;border-bottom:1px solid var(--line)}
.page-toolbar[hidden]{display:none}
.page-toolbar #dd-period,.page-toolbar #dd-router-period{margin-left:0}
.page-toolbar #cost-mode{margin-left:auto}
#cost-mode[hidden]{display:none!important}
#refresh-note{min-height:32px;max-width:none;margin:0 0 12px;padding:4px 0;font-size:12px;line-height:24px;white-space:normal;overflow-wrap:anywhere;color:var(--muted)}
#refresh-note[data-state=error]{color:var(--bad)}
#refresh-note:empty:before{content:'\00a0'}
#sidenav{padding:22px 10px 10px;background:var(--sidebg)}
#sidenav .brand{padding:0 10px 20px;font-size:14px}
.nav-list{gap:2px;scrollbar-gutter:auto}
.nav-group-label{font-size:11px;font-weight:500;color:var(--muted);padding:18px 10px 6px;margin:0}
.nav-group-label:first-child{display:none}
#sidenav .nav-item{min-height:38px;padding:8px 10px;font-size:13px;border-radius:6px}
#sidenav .nav-item.on,#sidenav .nav-item.is-current-section{background:var(--accentbg);color:var(--accent);border-color:transparent}
.nav-sub{display:none;margin:4px 0 6px 19px;padding-left:8px;border-left:1px solid var(--line2)}
.nav-branch.is-open>.nav-sub{display:grid;gap:2px}
#sidenav .nav-sub .nav-item{min-height:34px;font-size:12px}
#sidenav .nav-sub svg{width:15px;height:15px}
.nav-footer{display:flex;align-items:center;gap:8px;border-top:1px solid var(--line);margin-top:12px;padding-top:8px;min-height:48px;flex-shrink:0}
.nav-footer .hstatus{min-width:0;margin:0;flex:1;font-size:11px}
.nav-footer #updated{display:none}
.nav-footer #svc{padding:0;background:transparent;font-size:12px}
.nav-footer .nav-toggle{margin:0;min-width:32px;min-height:32px}
body.sidemini .nav-group-label,body.sidemini .nav-footer .hstatus{display:none}
body.sidemini .nav-sub{margin:3px 0;padding:0;border:0}
body.sidemini .nav-footer{justify-content:center}
.ux-terms{display:grid;grid-template-columns:minmax(90px,auto) 1fr;gap:16px 24px;margin:24px 0 4px;font-size:13px;line-height:1.75}
.ux-terms dt{font-weight:600;color:var(--text)}.ux-terms dd{margin:0;color:var(--muted)}
.ux-note{font-size:13px;color:var(--muted);line-height:1.75}
.ux-advanced{padding:16px 20px;border:1px solid var(--line);border-radius:8px;background:var(--card);margin-bottom:12px}
.ux-advanced>summary{font-size:13px;cursor:pointer;color:var(--muted);font-weight:500}
.ux-advanced[open]>summary{color:var(--text);margin-bottom:16px}
body[data-console-view=group] .group-grid{height:calc(100dvh - 210px)}
@media(max-width:55em){
 #sidenav,body.sidemini #sidenav{height:auto;min-height:48px;padding:4px 8px;background:var(--cardT)}
 .nav-group-label,.nav-footer{display:none}
 .nav-list{gap:4px;align-items:center}
 .nav-branch{display:flex;align-items:center}
 .nav-sub,.nav-branch.is-open>.nav-sub{display:flex;margin:0 4px;padding:0;border:0}
 .nav-sub{display:none}
 #sidenav .nav-item,body.sidemini #sidenav .nav-item{min-height:38px;padding:8px 12px}
 #sidenav .nav-sub .nav-item{font-size:12px}
 .console-header{gap:12px}.console-header h1{font-size:22px}
 .page-toolbar #cost-mode{margin-left:0}
 .ux-terms{grid-template-columns:1fr;gap:4px}.ux-terms dd{margin-bottom:12px}
}
@media(max-width:520px){.console-header{grid-template-columns:1fr}.global-actions{justify-content:flex-start}.page-toolbar{gap:8px}.page-toolbar #cost-mode{flex-basis:100%;width:max-content;max-width:100%}}
'''

JS = r'''
const PAGE_GUIDES=__GUIDES__,PAGE_TERMS=__TERMS__;
function updatePageGuide(view){
 const guide=PAGE_GUIDES[view];if(!guide)return;
 if(document.body.dataset.consoleView!==view)$('refresh-note').textContent='';
 document.body.dataset.consoleView=view;
 if(view!=='router'){const key=$('router-local-key');if(key)key.value='';}
 $('page-title').textContent=T(guide[0]);
 const help=$('page-help');help.hidden=!guide[2].length;help.title=T(guide[0])+' · '+T('使用说明');
 help.onclick=()=>openModal(help.title,'<p class="ux-note">'+esc(T(guide[1]))+'</p>'+(guide[2].length?'<dl class="ux-terms">'+guide[2].map(term=>'<dt>'+esc(T(term))+'</dt><dd>'+esc(T(PAGE_TERMS[term]))+'</dd>').join('')+'</dl>':''));
 const filtered=['overview','bill','plat','req'].includes(view),router=view==='router';
 $('dd-period').hidden=!filtered;$('dd-platform').hidden=!filtered;$('cost-mode').hidden=!['overview','bill','plat'].includes(view);
 $('page-toolbar').hidden=!filtered&&!router;
 if(!filtered)$('filterchip').style.display='none';
 for(const branch of document.querySelectorAll('.nav-branch')){
  const selected=[...branch.querySelectorAll('.nav-item')].some(b=>b.dataset.v===view);
  branch.classList.toggle('is-open',selected);
  branch.querySelector('.nav-item').classList.toggle('is-current-section',selected);
 }
}
'''


def _navigation(page):
    pattern = r'<button type="button" class="nav-item[^"\n]*" data-v="([^"\n]+)"[^>]*>.*?</button>'
    buttons = {}
    for match in re.finditer(pattern, page, re.S):
        view = match[1]
        button = match[0]
        title = GUIDES[view][0]
        button = re.sub(r'title="[^"]*"', 'title="'+title+'"', button, count=1)
        button = re.sub(r'<span>[^<]*</span>', '<span>'+title+'</span>', button, count=1)
        buttons[view] = button
    if set(buttons) != set(GUIDES):
        raise ValueError('Navigation is missing a console view')
    parts=[]
    for label, views in NAV_GROUPS:
        parts.append('<p class="nav-group-label">'+label+'</p>')
        for view in views:
            if view in NAV_CHILDREN:
                parts.append('<div class="nav-branch">'+buttons[view]+'<div class="nav-sub">'+''.join(buttons[v] for v in NAV_CHILDREN[view])+'</div></div>')
            else:
                parts.append(buttons[view])
    start=page.index('<div class="nav-list">')+len('<div class="nav-list">')
    end=page.index('</div><div class="nav-footer">',start)
    footer_end=page.index('</nav>',end)
    footer=re.sub(pattern, '', page[end:footer_end], flags=re.S)
    return page[:start]+''.join(parts)+footer+page[footer_end:]


def improve_page(page):
    page = page.replace('</style>', CSS + '\n</style>', 1)
    # Static labels are translated once during startup. The complete dictionary
    # must be present before that pass, not when the late view helpers run.
    page = page.replace('const T=s=>', 'Object.assign(EN,' + json.dumps(EN, ensure_ascii=False) + ');\nconst T=s=>', 1)
    script = JS.replace('__GUIDES__', json.dumps(GUIDES, ensure_ascii=False)).replace('__TERMS__', json.dumps(TERMS, ensure_ascii=False))
    page = page.replace('const VIEWS=', script + '\nconst VIEWS=', 1)
    page = _navigation(page)
    # Remove redundant page introductions from the markup, keeping live metadata.
    page = re.sub(r'(<div class="pagehead" data-view="[^"]+">)<h2>[^<]*</h2>(?:<p>[^<]*</p>)?', r'\1', page)
    # Troubleshooting remains available without displacing daily settings.
    for title, label in [('连接与密钥检查<span class="h2-meta">只报状态，不显示内容</span>', '连接与密钥检查'), ('日志（已脱敏）<span class="h2-meta">点击内容可放大查看</span>', '运行日志')]:
        pattern = r'<section data-view="sys"><h2>' + re.escape(title) + r'</h2>(.*?)</section>'
        page = re.sub(pattern, lambda m: '<details class="ux-advanced" data-view="sys"><summary>' + label + '</summary>' + m[1] + '</details>', page, count=1, flags=re.S)
    for title in ('我的常用任务', '预约执行', '用量提醒', '版本对比', '连接检查'):
        pattern=r'<section data-view="center"><h2>'+title+r'</h2>(.*?)</section>'
        page=re.sub(pattern,lambda m:'<details class="ux-advanced" data-view="center"><summary>'+title+'</summary>'+m[1]+'</details>',page,count=1,flags=re.S)
    return page
