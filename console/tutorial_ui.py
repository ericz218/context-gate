# -*- coding: utf-8 -*-
"""Interactive onboarding tutorial, per-page first-visit guides, and extended i18n.

Supports automatic system-language detection and 8 languages:
zh (简体中文), zh-TW (繁體中文), en (English), ja (日本語),
ko (한국어), es (Español), fr (Français), de (Deutsch).
"""
import json

SUPPORTED_LANGS = ('zh', 'zh-TW', 'en', 'ja', 'ko', 'es', 'fr', 'de')

LANG_OPTIONS = (
    ('zh', '简体中文'),
    ('zh-TW', '繁體中文'),
    ('en', 'English'),
    ('ja', '日本語'),
    ('ko', '한국어'),
    ('es', 'Español'),
    ('fr', 'Français'),
    ('de', 'Deutsch'),
)

# English additions required by test_console_english.py (every CJK static label & T() key).
EN_ADDITIONS = {
    '简体中文': '简体中文',
    '繁體中文': '繁體中文',
    '日本語': '日本語',
    '多语言切换控制台界面语言，首次启动会自动匹配系统语言': 'Switch console language; auto-detects system language on first launch',
    '新手教程': 'Onboarding tutorial',
    '查看主界面与当前分页的新手引导': 'Open onboarding guide for the main UI or current page',
    '自动显示首次访问引导，也可随时重新播放主界面导览或重置各分页提示': 'Auto-show guides on first visit; replay the main tour or reset page tips anytime',
    '首次进入分页时自动显示引导': 'Auto-show guide on first page visit',
    '重播主界面导览': 'Replay main tour',
    '重置分页引导': 'Reset page guides',
    '已重置所有分页的新手引导，下次点开各分页时将重新提示。': 'All page guides reset. They will appear again on your next visit to each page.',
    '引导': 'Tour',
}

# Core UI chrome translations for the 6 newly added languages (unmapped deep strings fall back to EN, or zh for zh-TW).
EXTRA_I18N = {
    'zh-TW': {
        'Context Gate 控制台': 'Context Gate 控制台',
        '主导航': '主導覽',
        '跳到主要内容': '跳到主要內容',
        '总览': '總覽', '任务中心': '任務中心', '项目进度': '專案進度', '上下文压缩': '上下文壓縮',
        '群聊': '群聊', '待办': '待辦', '共享记忆': '共享記憶', '文件工具': '檔案工具',
        '花费估算': '花費估算', '平台对比': '平台對比', '模型预算': '模型預算', '请求记录': '請求紀錄',
        '订阅额度': '訂閱額度', '项目同步': '專案同步', '模型连接': '模型連線', '设置与诊断': '設定與診斷',
        '工作': '工作', '用量': '用量', '管理': '管理',
        '切换深浅主题': '切換深淺主題', '管家（任意视图可用）': '管家（任意檢視可用）', '管家': '管家', '刷新': '重新整理',
        '刷新中…': '重新整理中…', '在线': '線上', '离线': '離線', '已停止': '已停止', '读取中…': '讀取中…',
        '全部时间': '全部時間', '今天': '今天', '本周': '本週', '本月': '本月', '全部平台': '全部平台',
        '全部供应商': '全部供應商', '价格模式': '價格模式', '按付费设置': '按付費設定', '按官方标价': '按官方標價',
        '页面说明': '頁面說明', '使用说明': '使用說明', '收起/展开侧边栏': '收起/展開側邊欄',
        '搜索 Gate 内容': '搜尋 Gate 內容', '搜索': '搜尋', '搜索结果': '搜尋結果',
        '已发送请求': '已傳送請求', '实际用量 · tokens': '實際用量 · tokens', '对照测试节省': '對照測試節省', '平均响应时间': '平均回應時間',
        '用量趋势': '用量趨勢', '7 天': '7 天', '30 天': '30 天', '本年': '本年', '总计': '總計',
        '显示缓存命中率': '顯示快取命中率', '显示 tokens': '顯示 tokens',
        '最近请求': '最近請求', '最近压缩任务': '最近壓縮任務', '查看全部 →': '檢視全部 →',
        '设置': '設定', '外观主题': '外觀主題', '选择主题风格和明暗模式，全局生效': '選擇主題風格與明暗模式，全域生效',
        '现有风格': '現有風格', '现代简约': '現代簡約', '浅色': '淺色', '深色': '深色',
        '自动刷新': '自動重新整理', '侧边栏收起': '側邊欄收起', '切换收起/展开': '切換收起/展開',
        '管家模型': '管家模型', '配置': '設定', '界面语言': '介面語言',
        '多语言切换控制台界面语言，首次启动会自动匹配系统语言': '多語言切換控制台介面語言，首次啟動會自動配對系統語言',
        '新手教程': '新手教學', '查看主界面与当前分页的新手引导': '檢視主介面與目前分頁的新手引導',
        '自动显示首次访问引导，也可随时重新播放主界面导览或重置各分页提示': '自動顯示首次造訪引導，也可隨時重新播放主介面導覽或重設各分頁提示',
        '首次进入分页时自动显示引导': '首次進入分頁時自動顯示引導',
        '重播主界面导览': '重播主介面導覽', '重置分页引导': '重設分頁引導',
        '已重置所有分页的新手引导，下次点开各分页时将重新提示。': '已重設所有分頁的新手引導，下次點開各分頁時將重新提示。',
        '控制': '控制', '全局快捷键：': '全域快捷鍵：', '录制快捷键': '錄製快捷鍵',
        '连接与密钥检查': '連線與金鑰檢查', '运行日志': '執行日誌',
        '关闭': '關閉', '取消': '取消', '确定': '確定', '确认': '確認', '保存': '儲存', '重试': '重試',
        '暂无数据': '暫無資料', '暂无请求': '暫無請求', '暂无任务': '暫無任務', '暂无记录': '暫無紀錄',
        '开始任务': '開始任務', '项目': '專案', '执行平台': '執行平台', '模型': '模型', '思考档位': '思考檔位',
        '任务目标': '任務目標', '完成标准（选填）': '完成標準（選填）', '添加文件夹': '新增資料夾',
        '我的常用任务': '我的常用任務', '任务与成果': '任務與成果', '预约执行': '預約執行', '用量提醒': '用量提醒',
        '成果库': '成果庫', '版本对比': '版本對比', '连接检查': '連線檢查',
        '计费': '計費', '平台': '平台', '时间': '時間', '状态': '狀態', '引导': '導覽',
    },
    'ja': {
        'Context Gate 控制台': 'Context Gate コンソール',
        '主导航': 'メインナビゲーション',
        '跳到主要内容': 'メインコンテンツへスキップ',
        '总览': '概要', '任务中心': 'タスクセンター', '项目进度': 'プロジェクト進捗', '上下文压缩': 'コンテキスト圧縮',
        '群聊': 'グループチャット', '待办': 'To-Do', '共享记忆': '共有メモリ', '文件工具': 'ファイルツール',
        '花费估算': 'コスト見積もり', '平台对比': 'プラットフォーム比較', '模型预算': 'モデル予算', '请求记录': 'リクエスト履歴',
        '订阅额度': 'サブスク枠', '项目同步': 'プロジェクト同期', '模型连接': 'モデル接続', '设置与诊断': '設定と診断',
        '工作': 'ワーク', '用量': '使用量', '管理': '管理',
        '切换深浅主题': 'ライト/ダークテーマ切替', '管家（任意视图可用）': 'バトラー（全画面で利用可）', '管家': 'バトラー', '刷新': '更新',
        '刷新中…': '更新中…', '在线': 'オンライン', '离线': 'オフライン', '已停止': '停止', '读取中…': '読み込み中…',
        '全部时间': '全期間', '今天': '今日', '本周': '今週', '本月': '今月', '全部平台': '全プラットフォーム',
        '全部供应商': '全プロバイダー', '价格模式': '価格モード', '按付费设置': '支払い設定準拠', '按官方标价': '公式定価換算',
        '页面说明': 'ページヘルプ', '使用说明': '使い方', '收起/展开侧边栏': 'サイドバー開閉',
        '搜索 Gate 内容': 'Gate 内を検索', '搜索': '検索', '搜索结果': '検索結果',
        '已发送请求': '送信リクエスト', '实际用量 · tokens': '実使用量 · tokens', '对照测试节省': 'A/Bテスト節約', '平均响应时间': '平均応答時間',
        '用量趋势': '使用量トレンド', '7 天': '7日間', '30 天': '30日間', '本年': '今年', '总计': '累計',
        '显示缓存命中率': 'キャッシュ率を表示', '显示 tokens': 'トークンを表示',
        '最近请求': '最近のリクエスト', '最近压缩任务': '最近の圧縮タスク', '查看全部 →': 'すべて表示 →',
        '设置': '設定', '外观主题': '外観テーマ', '选择主题风格和明暗模式，全局生效': 'スタイルとライト/ダークモードを選択',
        '现有风格': 'オリジナル', '现代简约': 'モダン', '浅色': 'ライト', '深色': 'ダーク',
        '自动刷新': '自動更新', '侧边栏收起': 'サイドバー折りたたみ', '切换收起/展开': '開閉切替',
        '管家模型': 'バトラーモデル', '配置': '設定', '界面语言': '表示言語',
        '多语言切换控制台界面语言，首次启动会自动匹配系统语言': '表示言語を切り替えます（初回起動時はシステム言語を自動選択）',
        '新手教程': 'チュートリアル', '查看主界面与当前分页的新手引导': 'メイン画面や現在ページのガイドを表示',
        '自动显示首次访问引导，也可随时重新播放主界面导览或重置各分页提示': '初回訪問時にガイドを自動表示します。いつでも再生・リセットできます',
        '首次进入分页时自动显示引导': '各ページの初回表示時にガイドを自動表示',
        '重播主界面导览': 'メインツアーを再生', '重置分页引导': 'ページガイドをリセット',
        '已重置所有分页的新手引导，下次点开各分页时将重新提示。': 'すべてのページガイドをリセットしました。次回開くと再表示されます。',
        '控制': 'コントロール', '全局快捷键：': 'グローバルショートカット：', '录制快捷键': 'ショートカット記録',
        '连接与密钥检查': '接続とキー診断', '运行日志': '実行ログ',
        '关闭': '閉じる', '取消': 'キャンセル', '确定': 'OK', '确认': '確認', '保存': '保存', '重试': '再試行',
        '暂无数据': 'データなし', '暂无请求': 'リクエストなし', '暂无任务': 'タスクなし', '暂无记录': '記録なし',
        '开始任务': 'タスク開始', '项目': 'プロジェクト', '执行平台': '実行プラットフォーム', '模型': 'モデル', '思考档位': '推論レベル',
        '任务目标': 'タスク目標', '完成标准（选填）': '完了基準（任意）', '添加文件夹': 'フォルダ追加',
        '我的常用任务': '保存済みタスク', '任务与成果': 'タスクと成果', '预约执行': '予約実行', '用量提醒': '使用量アラート',
        '成果库': '成果ライブラリ', '版本对比': 'バージョン比較', '连接检查': '接続チェック',
        '计费': '課金', '平台': 'プラットフォーム', '时间': '時間', '状态': '状態', '引导': 'ガイド',
    },
    'ko': {
        'Context Gate 控制台': 'Context Gate 콘솔',
        '主导航': '기본 탐색',
        '跳到主要内容': '본문으로 건너뛰기',
        '总览': '개요', '任务中心': '작업 센터', '项目进度': '프로젝트 진행', '上下文压缩': '컨텍스트 압축',
        '群聊': '그룹 채팅', '待办': '할 일', '共享记忆': '공유 메모리', '文件工具': '파일 도구',
        '花费估算': '비용 추정', '平台对比': '플랫폼 비교', '模型预算': '모델 예산', '请求记录': '요청 기록',
        '订阅额度': '구독 한도', '项目同步': '프로젝트 동기화', '模型连接': '모델 연결', '设置与诊断': '설정 및 진단',
        '工作': '작업', '用量': '사용량', '管理': '관리',
        '切换深浅主题': '라이트/다크 테마 전환', '管家（任意视图可用）': '버틀러(모든 화면에서 사용 가능)', '管家': '버틀러', '刷新': '새로고침',
        '刷新中…': '새로고침 중…', '在线': '온라인', '离线': '오프라인', '已停止': '중지됨', '读取中…': '불러오는 중…',
        '全部时间': '전체 기간', '今天': '오늘', '本周': '이번 주', '本月': '이번 달', '全部平台': '전체 플랫폼',
        '全部供应商': '전체 공급자', '价格模式': '가격 기준', '按付费设置': '결제 설정 기준', '按官方标价': '공식 정가 기준',
        '页面说明': '페이지 도움말', '使用说明': '사용 안내', '收起/展开侧边栏': '사이드바 접기/펼치기',
        '搜索 Gate 内容': 'Gate 내용 검색', '搜索': '검색', '搜索结果': '검색 결과',
        '已发送请求': '전송된 요청', '实际用量 · tokens': '실제 사용량 · tokens', '对照测试节省': 'A/B 테스트 절감', '平均响应时间': '평균 응답 시간',
        '用量趋势': '사용량 추이', '7 天': '7일', '30 天': '30일', '本年': '올해', '总计': '전체',
        '显示缓存命中率': '캐시 적중률 표시', '显示 tokens': '토큰 표시',
        '最近请求': '최근 요청', '最近压缩任务': '최근 압축 작업', '查看全部 →': '전체 보기 →',
        '设置': '설정', '外观主题': '화면 테마', '选择主题风格和明暗模式，全局生效': '테마 스타일과 라이트/다크 모드 선택',
        '现有风格': '오리지널', '现代简约': '모던', '浅色': '라이트', '深色': '다크',
        '自动刷新': '자동 새로고침', '侧边栏收起': '사이드바 접기', '切换收起/展开': '접기/펼치기 전환',
        '管家模型': '버틀러 모델', '配置': '설정', '界面语言': '인터페이스 언어',
        '多语言切换控制台界面语言，首次启动会自动匹配系统语言': '콘솔 표시 언어를 변경합니다(첫 실행 시 시스템 언어 자동 감지)',
        '新手教程': '시작 가이드', '查看主界面与当前分页的新手引导': '메인 화면 또는 현재 페이지 가이드 열기',
        '自动显示首次访问引导，也可随时重新播放主界面导览或重置各分页提示': '첫 방문 시 가이드를 자동 표시하며, 언제든 다시 재생하거나 초기화할 수 있습니다',
        '首次进入分页时自动显示引导': '각 페이지 첫 방문 시 가이드 자동 표시',
        '重播主界面导览': '메인 투어 다시 보기', '重置分页引导': '페이지 가이드 초기화',
        '已重置所有分页的新手引导，下次点开各分页时将重新提示。': '모든 페이지 가이드가 초기화되었습니다. 다음 방문 시 다시 표시됩니다.',
        '控制': '제어', '全局快捷键：': '전역 단축키:', '录制快捷键': '단축키 기록',
        '连接与密钥检查': '연결 및 키 점검', '运行日志': '실행 로그',
        '关闭': '닫기', '取消': '취소', '确定': '확인', '确认': '확인', '保存': '저장', '重试': '다시 시도',
        '暂无数据': '데이터 없음', '暂无请求': '요청 없음', '暂无任务': '작업 없음', '暂无记录': '기록 없음',
        '开始任务': '작업 시작', '项目': '프로젝트', '执行平台': '실행 플랫폼', '模型': '모델', '思考档位': '추론 수준',
        '任务目标': '작업 목표', '完成标准（选填）': '완료 기준(선택)', '添加文件夹': '폴더 추가',
        '我的常用任务': '저장된 작업', '任务与成果': '작업 및 결과', '预约执行': '예약 실행', '用量提醒': '사용량 알림',
        '成果库': '결과물 보관함', '版本对比': '버전 비교', '连接检查': '연결 점검',
        '计费': '비용', '平台': '플랫폼', '时间': '시간', '状态': '상태', '引导': '가이드',
    },
    'es': {
        'Context Gate 控制台': 'Consola de Context Gate',
        '主导航': 'Navegación principal',
        '跳到主要内容': 'Saltar al contenido',
        '总览': 'Resumen', '任务中心': 'Centro de tareas', '项目进度': 'Progreso', '上下文压缩': 'Compresión',
        '群聊': 'Chat grupal', '待办': 'Tareas', '共享记忆': 'Memoria', '文件工具': 'Archivos',
        '花费估算': 'Costos', '平台对比': 'Plataformas', '模型预算': 'Presupuesto', '请求记录': 'Solicitudes',
        '订阅额度': 'Cuotas', '项目同步': 'Sincronización', '模型连接': 'Conexiones', '设置与诊断': 'Ajustes',
        '工作': 'Trabajo', '用量': 'Uso', '管理': 'Gestión',
        '切换深浅主题': 'Cambiar tema claro/oscuro', '管家（任意视图可用）': 'Asistente (disponible en cualquier vista)', '管家': 'Asistente', '刷新': 'Actualizar',
        '刷新中…': 'Actualizando…', '在线': 'En línea', '离线': 'Sin conexión', '已停止': 'Detenido', '读取中…': 'Cargando…',
        '全部时间': 'Todo el tiempo', '今天': 'Hoy', '本周': 'Esta semana', '本月': 'Este mes', '全部平台': 'Todas las plataformas',
        '全部供应商': 'Todos los proveedores', '价格模式': 'Base de costo', '按付费设置': 'Costo real', '按官方标价': 'Precio oficial',
        '页面说明': 'Ayuda de página', '使用说明': 'Ayuda', '收起/展开侧边栏': 'Contraer/expandir barra lateral',
        '搜索 Gate 内容': 'Buscar en Context Gate', '搜索': 'Buscar', '搜索结果': 'Resultados',
        '已发送请求': 'Solicitudes enviadas', '实际用量 · tokens': 'Uso real · tokens', '对照测试节省': 'Ahorro A/B medido', '平均响应时间': 'Duración media',
        '用量趋势': 'Tendencia de uso', '7 天': '7 días', '30 天': '30 días', '本年': 'Este año', '总计': 'Todo',
        '显示缓存命中率': 'Ver tasa de caché', '显示 tokens': 'Ver tokens',
        '最近请求': 'Recientes', '最近压缩任务': 'Tareas de compresión', '查看全部 →': 'Ver todo →',
        '设置': 'Ajustes', '外观主题': 'Apariencia', '选择主题风格和明暗模式，全局生效': 'Elige estilo y modo claro u oscuro',
        '现有风格': 'Original', '现代简约': 'Moderno', '浅色': 'Claro', '深色': 'Oscuro',
        '自动刷新': 'Autoactualizar', '侧边栏收起': 'Barra compacta', '切换收起/展开': 'Alternar',
        '管家模型': 'Modelo del asistente', '配置': 'Configurar', '界面语言': 'Idioma',
        '多语言切换控制台界面语言，首次启动会自动匹配系统语言': 'Cambia el idioma; detecta el idioma del sistema al iniciar por primera vez',
        '新手教程': 'Tutorial inicial', '查看主界面与当前分页的新手引导': 'Abrir guía interactiva de esta vista',
        '自动显示首次访问引导，也可随时重新播放主界面导览或重置各分页提示': 'Muestra guías en la primera visita; repite el recorrido o restablece los consejos',
        '首次进入分页时自动显示引导': 'Mostrar guía al abrir cada pestaña por primera vez',
        '重播主界面导览': 'Repetir recorrido', '重置分页引导': 'Restablecer guías',
        '已重置所有分页的新手引导，下次点开各分页时将重新提示。': 'Guías de pestañas restablecidas. Aparecerán en tu próxima visita.',
        '控制': 'Controles', '全局快捷键：': 'Atajo global:', '录制快捷键': 'Grabar atajo',
        '连接与密钥检查': 'Auditoría de claves', '运行日志': 'Registros',
        '关闭': 'Cerrar', '取消': 'Cancelar', '确定': 'Aceptar', '确认': 'Confirmar', '保存': 'Guardar', '重试': 'Reintentar',
        '暂无数据': 'Sin datos', '暂无请求': 'Sin solicitudes', '暂无任务': 'Sin tareas', '暂无记录': 'Sin registros',
        '开始任务': 'Iniciar tarea', '项目': 'Proyecto', '执行平台': 'Plataforma', '模型': 'Modelo', '思考档位': 'Razonamiento',
        '任务目标': 'Objetivo', '完成标准（选填）': 'Criterios (opcional)', '添加文件夹': 'Añadir carpeta',
        '计费': 'Costos', '平台': 'Plataforma', '时间': 'Hora', '状态': 'Estado', '引导': 'Guía',
    },
    'fr': {
        'Context Gate 控制台': 'Console Context Gate',
        '主导航': 'Navigation principale',
        '跳到主要内容': 'Aller au contenu',
        '总览': 'Aperçu', '任务中心': 'Tâches', '项目进度': 'Avancement', '上下文压缩': 'Compression',
        '群聊': 'Chat de groupe', '待办': 'À faire', '共享记忆': 'Mémoire', '文件工具': 'Fichiers',
        '花费估算': 'Coûts', '平台对比': 'Plateformes', '模型预算': 'Budget', '请求记录': 'Requêtes',
        '订阅额度': 'Quotas', '项目同步': 'Synchro Git', '模型连接': 'Connexions', '设置与诊断': 'Paramètres',
        '工作': 'Travail', '用量': 'Usage', '管理': 'Gestion',
        '切换深浅主题': 'Changer de thème', '管家（任意视图可用）': 'Majordome (disponible partout)', '管家': 'Majordome', '刷新': 'Actualiser',
        '刷新中…': 'Actualisation…', '在线': 'En ligne', '离线': 'Hors ligne', '已停止': 'Arrêté', '读取中…': 'Chargement…',
        '全部时间': 'Tout', '今天': 'Aujourd’hui', '本周': 'Cette semaine', '本月': 'Ce mois', '全部平台': 'Toutes les plateformes',
        '全部供应商': 'Tous les fournisseurs', '价格模式': 'Base de coût', '按付费设置': 'Coût configuré', '按官方标价': 'Tarif officiel',
        '页面说明': 'Aide de la page', '使用说明': 'Aide', '收起/展开侧边栏': 'Réduire/déplier la barre',
        '搜索 Gate 内容': 'Rechercher dans Gate', '搜索': 'Rechercher', '搜索结果': 'Résultats',
        '已发送请求': 'Requêtes envoyées', '实际用量 · tokens': 'Usage réel · tokens', '对照测试节省': 'Économies A/B', '平均响应时间': 'Durée moyenne',
        '用量趋势': 'Tendance d’usage', '7 天': '7 j', '30 天': '30 j', '本年': 'Cette année', '总计': 'Total',
        '显示缓存命中率': 'Taux de cache', '显示 tokens': 'Afficher tokens',
        '最近请求': 'Récentes', '最近压缩任务': 'Tâches de compression', '查看全部 →': 'Tout voir →',
        '设置': 'Paramètres', '外观主题': 'Apparence', '选择主题风格和明暗模式，全局生效': 'Choisissez le style et le mode clair/sombre',
        '现有风格': 'Original', '现代简约': 'Moderne', '浅色': 'Clair', '深色': 'Sombre',
        '自动刷新': 'Auto-actualisation', '侧边栏收起': 'Barre compacte', '切换收起/展开': 'Basculer',
        '管家模型': 'Modèle du majordome', '配置': 'Configurer', '界面语言': 'Langue',
        '多语言切换控制台界面语言，首次启动会自动匹配系统语言': 'Changer de langue (détection automatique au premier lancement)',
        '新手教程': 'Tutoriel', '查看主界面与当前分页的新手引导': 'Ouvrir le guide de cette page',
        '自动显示首次访问引导，也可随时重新播放主界面导览或重置各分页提示': 'Guides automatiques à la première visite ; rejouez ou réinitialisez à tout moment',
        '首次进入分页时自动显示引导': 'Afficher le guide à la première visite de chaque onglet',
        '重播主界面导览': 'Rejouer la visite', '重置分页引导': 'Réinitialiser les guides',
        '已重置所有分页的新手引导，下次点开各分页时将重新提示。': 'Guides réinitialisés. Ils réapparaîtront à votre prochaine visite.',
        '控制': 'Contrôles', '全局快捷键：': 'Raccourci global :', '录制快捷键': 'Enregistrer',
        '连接与密钥检查': 'Audit des clés', '运行日志': 'Journaux',
        '关闭': 'Fermer', '取消': 'Annuler', '确定': 'OK', '确认': 'Confirmer', '保存': 'Enregistrer', '重试': 'Réessayer',
        '暂无数据': 'Aucune donnée', '暂无请求': 'Aucune requête', '暂无任务': 'Aucune tâche', '暂无记录': 'Aucune entrée',
        '开始任务': 'Lancer', '项目': 'Projet', '执行平台': 'Plateforme', '模型': 'Modèle', '思考档位': 'Raisonnement',
        '任务目标': 'Objectif', '完成标准（选填）': 'Critères (optionnel)', '添加文件夹': 'Ajouter dossier',
        '计费': 'Coûts', '平台': 'Plateforme', '时间': 'Heure', '状态': 'Statut', '引导': 'Guide',
    },
    'de': {
        'Context Gate 控制台': 'Context Gate Konsole',
        '主导航': 'Hauptnavigation',
        '跳到主要内容': 'Zum Inhalt springen',
        '总览': 'Übersicht', '任务中心': 'Aufgaben', '项目进度': 'Projektstatus', '上下文压缩': 'Kompression',
        '群聊': 'Gruppenchat', '待办': 'To-dos', '共享记忆': 'Speicher', '文件工具': 'Dateien',
        '花费估算': 'Kosten', '平台对比': 'Plattformen', '模型预算': 'Budget', '请求记录': 'Anfragen',
        '订阅额度': 'Kontingente', '项目同步': 'Git-Sync', '模型连接': 'Verbindungen', '设置与诊断': 'Einstellungen',
        '工作': 'Arbeit', '用量': 'Nutzung', '管理': 'Verwaltung',
        '切换深浅主题': 'Hell/Dunkel wechseln', '管家（任意视图可用）': 'Butler (überall verfügbar)', '管家': 'Butler', '刷新': 'Aktualisieren',
        '刷新中…': 'Lädt…', '在线': 'Online', '离线': 'Offline', '已停止': 'Gestoppt', '读取中…': 'Laden…',
        '全部时间': 'Gesamt', '今天': 'Heute', '本周': 'Diese Woche', '本月': 'Dieser Monat', '全部平台': 'Alle Plattformen',
        '全部供应商': 'Alle Anbieter', '价格模式': 'Preisbasis', '按付费设置': 'Reale Kosten', '按官方标价': 'Listenpreis',
        '页面说明': 'Seitenhilfe', '使用说明': 'Hilfe', '收起/展开侧边栏': 'Seitenleiste umschalten',
        '搜索 Gate 内容': 'In Gate suchen', '搜索': 'Suchen', '搜索结果': 'Ergebnisse',
        '已发送请求': 'Anfragen', '实际用量 · tokens': 'Tatsächliche Tokens', '对照测试节省': 'A/B-Ersparnis', '平均响应时间': 'Ø Antwortzeit',
        '用量趋势': 'Nutzungstrend', '7 天': '7 Tage', '30 天': '30 Tage', '本年': 'Dieses Jahr', '总计': 'Gesamt',
        '显示缓存命中率': 'Cache-Rate', '显示 tokens': 'Tokens anzeigen',
        '最近请求': 'Letzte Anfragen', '最近压缩任务': 'Kompressionsaufgaben', '查看全部 →': 'Alle ansehen →',
        '设置': 'Einstellungen', '外观主题': 'Design', '选择主题风格和明暗模式，全局生效': 'Stil und Hell-/Dunkelmodus wählen',
        '现有风格': 'Original', '现代简约': 'Modern', '浅色': 'Hell', '深色': 'Dunkel',
        '自动刷新': 'Auto-Refresh', '侧边栏收起': 'Kompakte Leiste', '切换收起/展开': 'Umschalten',
        '管家模型': 'Butler-Modell', '配置': 'Konfigurieren', '界面语言': 'Sprache',
        '多语言切换控制台界面语言，首次启动会自动匹配系统语言': 'Sprache wechseln (erkennt beim ersten Start automatisch die Systemsprache)',
        '新手教程': 'Einführung', '查看主界面与当前分页的新手引导': 'Interaktive Anleitung öffnen',
        '自动显示首次访问引导，也可随时重新播放主界面导览或重置各分页提示': 'Zeigt beim ersten Besuch Tipps; jederzeit wiederholbar oder zurücksetzbar',
        '首次进入分页时自动显示引导': 'Anleitung beim ersten Öffnen jeder Seite anzeigen',
        '重播主界面导览': 'Haupttour starten', '重置分页引导': 'Seiten-Tipps zurücksetzen',
        '已重置所有分页的新手引导，下次点开各分页时将重新提示。': 'Alle Seiten-Tipps wurden zurückgesetzt.',
        '控制': 'Steuerung', '全局快捷键：': 'Globaler Shortcut:', '录制快捷键': 'Aufnehmen',
        '连接与密钥检查': 'Schlüsselprüfung', '运行日志': 'Protokolle',
        '关闭': 'Schließen', '取消': 'Abbrechen', '确定': 'OK', '确认': 'Bestätigen', '保存': 'Speichern', '重试': 'Erneut',
        '暂无数据': 'Keine Daten', '暂无请求': 'Keine Anfragen', '暂无任务': 'Keine Aufgaben', '暂无记录': 'Keine Einträge',
        '开始任务': 'Starten', '项目': 'Projekt', '执行平台': 'Plattform', '模型': 'Modell', '思考档位': 'Denktiefe',
        '任务目标': 'Ziel', '完成标准（选填）': 'Kriterien (optional)', '添加文件夹': 'Ordner wählen',
        '计费': 'Kosten', '平台': 'Plattform', '时间': 'Zeit', '状态': 'Status', '引导': 'Tour',
    },
}

# UI strings for the onboarding overlay controls in all 8 languages.
TOUR_UI = {
    'zh': {
        'badge_main': '新手导览',
        'badge_page': '分页首次引导',
        'auto_lang': '已按系统语言自动选择：',
        'choose_lang': '界面语言',
        'start': '开始导览 →',
        'prev': '上一步',
        'next': '下一步 →',
        'done': '知道了',
        'finish': '完成并开始使用',
        'skip': '跳过',
        'mute': '不再自动弹出分页引导',
        'menu_title': '新手教程',
        'menu_desc': '随时查看主界面导览，或重新学习当前分页的图标与操作。',
        'menu_page': '查看当前分页引导',
        'menu_main': '重播主界面与导航导览',
        'menu_reset': '重置全部 16 个分页的首次提示',
    },
    'zh-TW': {
        'badge_main': '新手導覽',
        'badge_page': '分頁首次引導',
        'auto_lang': '已依系統語言自動選擇：',
        'choose_lang': '介面語言',
        'start': '開始導覽 →',
        'prev': '上一步',
        'next': '下一步 →',
        'done': '知道了',
        'finish': '完成並開始使用',
        'skip': '略過',
        'mute': '不再自動彈出分頁引導',
        'menu_title': '新手教學',
        'menu_desc': '隨時檢視主介面導覽，或重新學習目前分頁的圖示與操作。',
        'menu_page': '檢視目前分頁引導',
        'menu_main': '重播主介面與導覽列教學',
        'menu_reset': '重設全部 16 個分頁的首次提示',
    },
    'en': {
        'badge_main': 'Getting Started',
        'badge_page': 'First-Visit Page Guide',
        'auto_lang': 'Auto-selected from your system language:',
        'choose_lang': 'Interface language',
        'start': 'Start Tour →',
        'prev': 'Back',
        'next': 'Next →',
        'done': 'Got it',
        'finish': 'Finish & Explore',
        'skip': 'Skip',
        'mute': 'Don’t auto-show page guides',
        'menu_title': 'Onboarding Tutorial',
        'menu_desc': 'Replay the main workspace tour or inspect the icons and controls on this page.',
        'menu_page': 'Guide for this page',
        'menu_main': 'Replay main interface & sidebar tour',
        'menu_reset': 'Reset all 16 first-visit page guides',
    },
    'ja': {
        'badge_main': 'スタートガイド',
        'badge_page': '初回ページガイド',
        'auto_lang': 'システム言語に合わせて自動選択しました：',
        'choose_lang': '表示言語',
        'start': 'ツアーを開始 →',
        'prev': '戻る',
        'next': '次へ →',
        'done': '了解',
        'finish': '完了して使い始める',
        'skip': 'スキップ',
        'mute': '初回ガイドを自動表示しない',
        'menu_title': 'チュートリアル',
        'menu_desc': 'メイン画面ツアーの再生や、現在のページのアイコン説明を確認できます。',
        'menu_page': 'このページのガイドを見る',
        'menu_main': 'メイン画面・ナビツアーを再生',
        'menu_reset': '全16ページの初回ガイドをリセット',
    },
    'ko': {
        'badge_main': '시작 가이드',
        'badge_page': '페이지 첫 방문 안내',
        'auto_lang': '시스템 언어에 맞춰 자동 선택되었습니다:',
        'choose_lang': '표시 언어',
        'start': '투어 시작 →',
        'prev': '이전',
        'next': '다음 →',
        'done': '확인',
        'finish': '완료하고 시작하기',
        'skip': '건너뛰기',
        'mute': '페이지 가이드 자동 표시 끄기',
        'menu_title': '시작 가이드',
        'menu_desc': '메인 화면 투어를 다시 보거나 현재 페이지의 아이콘과 기능을 확인하세요.',
        'menu_page': '현재 페이지 가이드 보기',
        'menu_main': '메인 화면 및 사이드바 투어 다시 보기',
        'menu_reset': '전체 16개 페이지 첫 방문 가이드 초기화',
    },
    'es': {
        'badge_main': 'Guía inicial',
        'badge_page': 'Guía de primera visita',
        'auto_lang': 'Idioma detectado automáticamente del sistema:',
        'choose_lang': 'Idioma de la interfaz',
        'start': 'Iniciar recorrido →',
        'prev': 'Anterior',
        'next': 'Siguiente →',
        'done': 'Entendido',
        'finish': 'Finalizar y explorar',
        'skip': 'Omitir',
        'mute': 'No mostrar guías automáticamente',
        'menu_title': 'Tutorial inicial',
        'menu_desc': 'Repite el recorrido principal o revisa los iconos y controles de esta pestaña.',
        'menu_page': 'Guía de esta página',
        'menu_main': 'Repetir recorrido principal y barra lateral',
        'menu_reset': 'Restablecer las 16 guías de página',
    },
    'fr': {
        'badge_main': 'Prise en main',
        'badge_page': 'Guide de première visite',
        'auto_lang': 'Langue détectée automatiquement :',
        'choose_lang': 'Langue de l’interface',
        'start': 'Démarrer la visite →',
        'prev': 'Précédent',
        'next': 'Suivant →',
        'done': 'Compris',
        'finish': 'Terminer',
        'skip': 'Passer',
        'mute': 'Ne plus afficher automatiquement',
        'menu_title': 'Tutoriel',
        'menu_desc': 'Rejouez la visite principale ou découvrez les icônes de cette page.',
        'menu_page': 'Guide de cette page',
        'menu_main': 'Rejouer la visite principale et le menu',
        'menu_reset': 'Réinitialiser les 16 guides de page',
    },
    'de': {
        'badge_main': 'Schnellstart',
        'badge_page': 'Seiten-Einführung',
        'auto_lang': 'Automatisch aus Ihrer Systemsprache gewählt:',
        'choose_lang': 'Oberflächensprache',
        'start': 'Tour starten →',
        'prev': 'Zurück',
        'next': 'Weiter →',
        'done': 'Verstanden',
        'finish': 'Fertig & loslegen',
        'skip': 'Überspringen',
        'mute': 'Seiten-Tipps nicht mehr automatisch öffnen',
        'menu_title': 'Einführung',
        'menu_desc': 'Starten Sie die Haupttour erneut oder sehen Sie sich die Icons dieser Seite an.',
        'menu_page': 'Anleitung für diese Seite',
        'menu_main': 'Hauptoberfläche & Seitenleiste erklären',
        'menu_reset': 'Alle 16 Seiten-Tipps zurücksetzen',
    },
}

# Main welcome & sidebar tour steps (translated across all 8 languages).
MAIN_TOUR = {
    'zh': [
        {
            'target': None, 'langPicker': True,
            'title': '欢迎使用 Context Gate 控制台',
            'body': '这是一个本地优先的 AI 上下文网关与多 Agent 控制台。你可以用它统一派发任务、编排多 AI 群聊、监控 token 用量与订阅额度，并管理共享记忆与模型连接。\n\n我们已根据你的系统语言自动切换了界面，你也可以在下方随时更换语种。',
        },
        {
            'target': '.console-header',
            'title': '顶部标题栏与全局图标',
            'body': '右侧常用图标与按钮在任何页面都可用：\n• ？图标：随时打开当前页面的术语与口径说明\n• {{ic:tour}} 引导图标：重播新手教程或查看本页图标说明\n• {{ic:theme}} 主题图标：一键切换深色 / 浅色外观\n• 管家：跨页面唤起 AI 管家帮忙查项目或派活\n• 刷新：手动拉取最新统计与状态',
        },
        {
            'target': '#sidenav .nav-list',
            'title': '左侧导览（一）：工作区',
            'body': '「工作」分组集中了日常高频操作：\n• 总览：全局搜索、核心指标与用量趋势图\n• 任务中心：派发 AI 任务、看 diff 与验收（展开可看「项目进度」「上下文压缩」）\n• 群聊：让多个 AI 在同一项目里分工协作\n• 待办 / 共享记忆 / 文件工具：管理待办、跨会话记忆与本地文档对比',
        },
        {
            'target': '#sidenav .nav-item[data-v="bill"]',
            'title': '左侧导览（二）：用量与费用',
            'body': '「用量」分组帮你算清每一笔消耗：\n• 花费估算：按平台与模型拆解估算金额（展开可看「平台对比」「模型预算」「请求记录」）\n• 订阅额度：监控 Claude Code / Codex 的 5 小时与周额度，低额度时自动提醒或保护本地任务',
        },
        {
            'target': '#sidenav .nav-item[data-v="sys"]',
            'title': '左侧导览（三）：管理与底部状态',
            'body': '「管理」分组用于底层连接与系统设置：\n• 项目同步：查看本机 Git 仓库与 GitHub 的自动同步状态\n• 模型连接：管理供应商、API 密钥与模型别名\n• 设置与诊断：主题、语言、快捷键、密钥体检与日志\n• 侧栏底部：绿点显示本地服务在线状态，箭头图标 ‹ 可收起为紧凑图标条',
        },
        {
            'target': None,
            'title': '准备就绪！分页首次访问也会贴心引导',
            'body': '主界面介绍完毕。接下来当你第一次点开左侧任意具体分页时，都会自动弹出该页的专属引导，逐个介绍页面里的图标与按钮用途。\n\n你随时可以点击顶部 {{ic:tour}} 图标或在「设置与诊断」里重播或关闭自动引导。',
        },
    ],
    'zh-TW': [
        {
            'target': None, 'langPicker': True,
            'title': '歡迎使用 Context Gate 控制台',
            'body': '這是一個本機優先的 AI 上下文閘道與多 Agent 控制台，整合任務派發、多 AI 群聊、token 用量與訂閱額度監控，以及共享記憶管理。\n\n系統已依您的語言自動切換介面，您也可在下方隨時更換語種。',
        },
        {
            'target': '.console-header',
            'title': '頂部標題列與全域圖示',
            'body': '右上角常用圖示在任何頁面都可用：\n• ？圖示：檢視目前頁面的術語與統計口徑\n• {{ic:tour}} 引導圖示：重播新手教學或查看本頁圖示說明\n• {{ic:theme}} 主題圖示：一鍵切換深色 / 淺色外觀\n• 管家：跨頁面喚起 AI 管家協助查專案或派工\n• 重新整理：手動更新最新資料',
        },
        {
            'target': '#sidenav .nav-list',
            'title': '左側導覽（一）：工作區',
            'body': '「工作」分組集中日常高頻功能：\n• 總覽：全域搜尋、核心指標與用量趨勢\n• 任務中心：派發任務、檢視 diff 與驗收（含「專案進度」「上下文壓縮」）\n• 群聊：讓多個 AI 在同一專案中分工協作\n• 待辦 / 共享記憶 / 檔案工具：管理待辦清單、跨會話記憶與本機文件對比',
        },
        {
            'target': '#sidenav .nav-item[data-v="bill"]',
            'title': '左側導覽（二）：用量與花費',
            'body': '「用量」分組幫您掌握所有消耗：\n• 花費估算：依平台與模型拆解費用（含「平台對比」「模型預算」「請求紀錄」）\n• 訂閱額度：監控 Claude Code / Codex 的 5 小時與每週額度並設定提醒',
        },
        {
            'target': '#sidenav .nav-item[data-v="sys"]',
            'title': '左側導覽（三）：管理與底部狀態',
            'body': '「管理」分組負責連線與系統設定：\n• 專案同步：檢視本機 Git 倉庫與 GitHub 自動同步狀態\n• 模型連線：管理供應商、API 金鑰與模型別名\n• 設定與診斷：主題、語言、快捷鍵、金鑰檢查與日誌\n• 側欄底部：圓點顯示服務狀態，箭頭圖示 ‹ 可收起為圖示條',
        },
        {
            'target': None,
            'title': '準備就緒！首次開啟分頁將自動引導',
            'body': '主介面導覽完成。接下來當您第一次點開左側任意具體分頁時，都會自動顯示該頁的專屬引導，逐一說明頁面內的圖示與按鈕。',
        },
    ],
    'en': [
        {
            'target': None, 'langPicker': True,
            'title': 'Welcome to Context Gate Console',
            'body': 'A local-first AI context gateway and multi-agent workspace. Dispatch coding tasks, orchestrate multi-AI group chats, track token spend & subscription quotas, and manage shared memory.\n\nWe automatically matched your system language—you can switch languages anytime below.',
        },
        {
            'target': '.console-header',
            'title': 'Top Bar & Global Action Icons',
            'body': 'These controls stay available on every page:\n• ? Icon: Open page-specific terminology and calculation notes\n• {{ic:tour}} Guide Icon: Replay this tour or inspect the icons on the current page\n• {{ic:theme}} Theme Icon: Toggle dark and warm light appearance\n• Butler: Summon the AI assistant from any view\n• Refresh: Pull the latest local stats and live status',
        },
        {
            'target': '#sidenav .nav-list',
            'title': 'Left Sidebar (1/3): Work',
            'body': 'Daily workflows live under Work:\n• Overview: Global search, KPI cards, and usage trend chart\n• Task Center: Dispatch tasks, inspect diffs, and review outcomes (expands to Project Progress & Context Filtering)\n• Group Chat: Coordinate multiple AIs on the same project\n• To-do / Shared Memory / File Tools: Checklists, cross-session memory, and offline file diffs',
        },
        {
            'target': '#sidenav .nav-item[data-v="bill"]',
            'title': 'Left Sidebar (2/3): Usage & Spend',
            'body': 'Track every token and subscription window under Usage:\n• Cost Estimates: Drill down by platform and model (expands to Compare Platforms, Model Budgets & Request History)\n• Quota: Monitor Claude Code & Codex 5-hour/weekly quotas with threshold alerts and optional auto-pause',
        },
        {
            'target': '#sidenav .nav-item[data-v="sys"]',
            'title': 'Left Sidebar (3/3): Manage & Footer',
            'body': 'Configure connections and diagnostics under Manage:\n• Project Sync: Monitor local Git repos syncing with GitHub\n• Model Connections: Manage providers, API keys, and model aliases\n• Settings & Diagnostics: Theme, language, global hotkey, credential audit, and logs\n• Sidebar Footer: Live service dot and ‹ icon to collapse into a slim icon rail',
        },
        {
            'target': None,
            'title': 'All Set! First-Visit Guides on Every Tab',
            'body': 'Whenever you open any sidebar tab for the first time, a focused page guide will highlight its key icons and controls.\n\nClick the {{ic:tour}} icon in the top bar or visit Settings anytime to replay or reset tutorials.',
        },
    ],
    'ja': [
        {
            'target': None, 'langPicker': True,
            'title': 'Context Gate コンソールへようこそ',
            'body': 'ローカル優先の AI コンテキストゲートウェイ兼マルチエージェント管理画面です。タスク実行、複数 AI グループチャット、トークン・課金・サブスク枠の監視、共有メモリを一元管理できます。\n\nシステム言語に合わせて自動選択しました。下からいつでも言語を変更できます。',
        },
        {
            'target': '.console-header',
            'title': '上部バーと共通アイコン',
            'body': '右上のアイコンは全画面で使えます：\n• ？アイコン：現在ページの用語と計算基準を表示\n• {{ic:tour}} ガイドアイコン：チュートリアル再生やアイコン説明を表示\n• {{ic:theme}} テーマアイコン：ダーク／ライトテーマ切替\n• バトラー：どの画面からでも AI アシスタントを呼び出し\n• 更新：最新データを手動取得',
        },
        {
            'target': '#sidenav .nav-list',
            'title': '左ナビゲーション（1/3）：ワーク',
            'body': '日常作業は「ワーク」に集約されています：\n• 概要：横断検索、主要指標、使用量トレンド\n• タスクセンター：AI へタスクを依頼・差分確認・検収（配下にプロジェクト進捗／コンテキスト圧縮）\n• グループチャット：複数 AI で役割分担して作業\n• To-Do／共有メモリ／ファイルツール：タスク管理・メモリ検索・ローカル文書比較',
        },
        {
            'target': '#sidenav .nav-item[data-v="bill"]',
            'title': '左ナビゲーション（2/3）：使用量とコスト',
            'body': '「使用量」でトークンと費用を把握できます：\n• コスト見積もり：プラットフォーム・モデル別内訳（配下にプラットフォーム比較／モデル予算／リクエスト履歴）\n• サブスク枠：Claude Code / Codex の5時間・週間枠とアラート監視',
        },
        {
            'target': '#sidenav .nav-item[data-v="sys"]',
            'title': '左ナビゲーション（3/3）：管理とフッター',
            'body': '「管理」で接続や設定を行います：\n• プロジェクト同期：ローカル Git と GitHub の自動同期状況\n• モデル接続：プロバイダー・API キー・モデルエイリアス管理\n• 設定と診断：テーマ、言語、ショートカット、キー診断、ログ\n• 左下フッター：接続状態ドットと ‹ アイコンでサイドバーを折りたたみ',
        },
        {
            'target': None,
            'title': '準備完了！各ページ初回表示時にもガイドが出ます',
            'body': 'メイン案内は完了です。各タブを初めて開くと、そのページのアイコンやボタンの役割を順番に案内します。上部の {{ic:tour}} アイコンからいつでも再表示できます。',
        },
    ],
    'ko': [
        {
            'target': None, 'langPicker': True,
            'title': 'Context Gate 콘솔에 오신 것을 환영합니다',
            'body': '로컬 우선 AI 컨텍스트 게이트웨이 및 멀티 에이전트 작업 공간입니다. 작업 실행, 멀티 AI 그룹 채팅, 토큰 비용·구독 한도 추적, 공유 메모리를 한곳에서 관리하세요.\n\n시스템 언어에 맞춰 자동 선택되었으며 아래에서 언제든 변경할 수 있습니다.',
        },
        {
            'target': '.console-header',
            'title': '상단 바 및 전역 아이콘',
            'body': '우측 상단 버튼은 모든 페이지에서 사용할 수 있습니다:\n• ? 아이콘: 현재 페이지 용어 및 집계 기준 보기\n• {{ic:tour}} 가이드 아이콘: 튜토리얼 다시 보기 및 페이지 아이콘 안내\n• {{ic:theme}} 테마 아이콘: 다크 / 라이트 테마 전환\n• 버틀러: 어느 화면에서나 AI 비서 호출\n• 새로고침: 최신 로컬 통계 수동 갱신',
        },
        {
            'target': '#sidenav .nav-list',
            'title': '좌측 탐색 (1/3): 작업',
            'body': '일상 작업은 «작업» 그룹에 모여 있습니다:\n• 개요: 통합 검색, 핵심 지표, 사용량 추이 차트\n• 작업 센터: AI 작업 지시, diff 확인 및 검수(하위: 프로젝트 진행, 컨텍스트 압축)\n• 그룹 채팅: 여러 AI가 같은 프로젝트에서 협업\n• 할 일 / 공유 메모리 / 파일 도구: 체크리스트, 메모리 검색, 오프라인 파일 비교',
        },
        {
            'target': '#sidenav .nav-item[data-v="bill"]',
            'title': '좌측 탐색 (2/3): 사용량 및 비용',
            'body': '«사용량» 그룹에서 비용과 한도를 확인합니다:\n• 비용 추정: 플랫폼·모델별 비용 분석(하위: 플랫폼 비교, 모델 예산, 요청 기록)\n• 구독 한도: Claude Code / Codex 5시간 및 주간 한도 모니터링과 알림',
        },
        {
            'target': '#sidenav .nav-item[data-v="sys"]',
            'title': '좌측 탐색 (3/3): 관리 및 하단 상태',
            'body': '«관리» 그룹에서 연결과 설정을 관리합니다:\n• 프로젝트 동기화: 로컬 Git과 GitHub 자동 동기화 상태\n• 모델 연결: 공급자, API 키, 모델 별칭 관리\n• 설정 및 진단: 테마, 언어, 단축키, 키 점검 및 로그\n• 좌측 하단: 서비스 상태 표시등과 ‹ 아이콘으로 사이드바 접기',
        },
        {
            'target': None,
            'title': '준비 완료! 각 탭 첫 방문 시 상세 안내가 열립니다',
            'body': '기본 안내가 끝났습니다. 왼쪽의 각 탭을 처음 열 때마다 해당 화면의 아이콘과 버튼 설명이 자동으로 표시됩니다. 상단 {{ic:tour}} 아이콘에서 언제든 다시 열 수 있습니다.',
        },
    ],
    'es': [
        {
            'target': None, 'langPicker': True,
            'title': 'Bienvenido a la Consola de Context Gate',
            'body': 'Tu espacio local para gestionar contexto de IA, tareas con agentes, chat grupal multi-IA, costos de tokens, cuotas y memoria compartida.\n\nDetectamos automáticamente el idioma de tu sistema; puedes cambiarlo aquí abajo.',
        },
        {
            'target': '.console-header',
            'title': 'Barra superior e iconos globales',
            'body': 'Siempre visibles en cualquier vista:\n• Icono ?: Explicación de términos y métricas de esta página\n• Icono {{ic:tour}}: Repetir el tutorial o ver la guía de iconos\n• Icono {{ic:theme}}: Alternar entre tema oscuro y claro\n• Asistente: Invocar al asistente IA desde cualquier vista\n• Actualizar: Recargar datos locales al instante',
        },
        {
            'target': '#sidenav .nav-list',
            'title': 'Barra lateral (1/3): Trabajo',
            'body': 'Tus herramientas diarias:\n• Resumen: Búsqueda global, tarjetas KPI y gráfico de tendencia\n• Centro de tareas: Asignar tareas, revisar diffs y aceptar resultados (incluye Progreso y Compresión)\n• Chat grupal: Coordinar varias IAs en un proyecto\n• Tareas / Memoria / Archivos: Listas, memoria compartida y comparación local',
        },
        {
            'target': '#sidenav .nav-item[data-v="bill"]',
            'title': 'Barra lateral (2/3): Uso y costos',
            'body': 'Controla tu consumo:\n• Costos: Desglose por plataforma y modelo (incluye Plataformas, Presupuesto y Solicitudes)\n• Cuotas: Vigila los límites de 5 horas y semanales de Claude Code y Codex',
        },
        {
            'target': '#sidenav .nav-item[data-v="sys"]',
            'title': 'Barra lateral (3/3): Gestión y pie',
            'body': 'Configuración y conexiones:\n• Sincronización: Estado de Git con GitHub\n• Conexiones: Proveedores, claves API y alias de modelos\n• Ajustes: Tema, idioma, atajo global, auditoría y registros\n• Pie lateral: Estado del servicio local e icono ‹ para contraer el menú',
        },
        {
            'target': None,
            'title': '¡Listo! Guías automáticas en cada pestaña',
            'body': 'La primera vez que abras cada pestaña verás una guía dedicada explicando sus iconos y botones. Puedes reabrirla desde el icono {{ic:tour}}.',
        },
    ],
    'fr': [
        {
            'target': None, 'langPicker': True,
            'title': 'Bienvenue dans la console Context Gate',
            'body': 'Espace local pour orchestrer vos agents IA, suivre vos tokens, coûts et quotas, et gérer votre mémoire partagée.\n\nLa langue du système a été détectée automatiquement ; vous pouvez la changer ci-dessous.',
        },
        {
            'target': '.console-header',
            'title': 'Barre supérieure et icônes globales',
            'body': 'Disponibles sur chaque page :\n• Icône ? : Glossaire et règles de calcul de la page\n• Icône {{ic:tour}} : Rejouer le tutoriel ou voir le guide des icônes\n• Icône {{ic:theme}} : Basculer entre thème sombre et clair\n• Majordome : Lancer l’assistant IA depuis n’importe quelle vue\n• Actualiser : Recharger les statistiques locales',
        },
        {
            'target': '#sidenav .nav-list',
            'title': 'Menu latéral (1/3) : Travail',
            'body': 'Vos outils quotidiens :\n• Aperçu : Recherche globale, indicateurs et courbe d’usage\n• Tâches : Lancer des tâches IA, voir les diffs et valider (inclut Avancement et Compression)\n• Chat de groupe : Coordonner plusieurs IA sur un projet\n• À faire / Mémoire / Fichiers : Listes, mémoire partagée et comparaison locale',
        },
        {
            'target': '#sidenav .nav-item[data-v="bill"]',
            'title': 'Menu latéral (2/3) : Usage et coûts',
            'body': 'Maîtrisez vos dépenses :\n• Coûts : Détail par plateforme et modèle (inclut Plateformes, Budget et Requêtes)\n• Quotas : Suivi des limites 5 h / hebdomadaires de Claude Code et Codex',
        },
        {
            'target': '#sidenav .nav-item[data-v="sys"]',
            'title': 'Menu latéral (3/3) : Gestion et pied',
            'body': 'Connexions et réglages :\n• Synchro Git : État des dépôts avec GitHub\n• Connexions : Fournisseurs, clés API et alias de modèles\n• Paramètres : Thème, langue, raccourci, audit et journaux\n• Pied de menu : Voyant de service et icône ‹ pour réduire la barre',
        },
        {
            'target': None,
            'title': 'C’est parti ! Guides dédiés sur chaque onglet',
            'body': 'Lors de votre première visite sur chaque onglet, un guide vous présentera ses icônes et boutons. Cliquez sur {{ic:tour}} pour le rouvrir à tout moment.',
        },
    ],
    'de': [
        {
            'target': None, 'langPicker': True,
            'title': 'Willkommen in der Context Gate Konsole',
            'body': 'Ihr lokaler Arbeitsbereich für KI-Kontextsteuerung, Multi-Agent-Aufgaben, Token- & Kostenüberblick sowie gemeinsamen Speicher.\n\nIhre Systemsprache wurde automatisch erkannt – unten können Sie sie jederzeit wechseln.',
        },
        {
            'target': '.console-header',
            'title': 'Kopfleiste & globale Icons',
            'body': 'Auf jeder Seite verfügbar:\n• ?-Icon: Begriffe und Berechnungen der aktuellen Seite\n• {{ic:tour}}-Icon: Tour wiederholen oder Seiten-Icons erklären lassen\n• {{ic:theme}}-Icon: Zwischen Dunkel- und Hellmodus wechseln\n• Butler: KI-Assistent aus jeder Ansicht aufrufen\n• Aktualisieren: Lokale Daten sofort neu laden',
        },
        {
            'target': '#sidenav .nav-list',
            'title': 'Seitenleiste (1/3): Arbeit',
            'body': 'Tägliche Workflows:\n• Übersicht: Globale Suche, Kennzahlen und Nutzungstrend\n• Aufgaben: KI-Tasks starten, Diffs prüfen & abnehmen (inkl. Projektstatus & Kompression)\n• Gruppenchat: Mehrere KIs gemeinsam an einem Projekt koordinieren\n• To-dos / Speicher / Dateien: Aufgabenlisten, Speicher und lokaler Dateivergleich',
        },
        {
            'target': '#sidenav .nav-item[data-v="bill"]',
            'title': 'Seitenleiste (2/3): Nutzung & Kosten',
            'body': 'Verbrauch im Blick behalten:\n• Kosten: Aufschlüsselung nach Plattform und Modell (inkl. Plattformen, Budget & Anfragen)\n• Kontingente: 5-Stunden- & Wochenlimits von Claude Code / Codex überwachen',
        },
        {
            'target': '#sidenav .nav-item[data-v="sys"]',
            'title': 'Seitenleiste (3/3): Verwaltung & Fußzeile',
            'body': 'Verbindungen & System:\n• Git-Sync: Automatischer Abgleich lokaler Repos mit GitHub\n• Verbindungen: Anbieter, API-Schlüssel und Modell-Aliase\n• Einstellungen: Design, Sprache, Shortcut, Schlüsselprüfung & Logs\n• Fußzeile: Online-Statuspunkt und ‹-Icon zum Einklappen der Leiste',
        },
        {
            'target': None,
            'title': 'Bereit! Jeder Tab erklärt sich beim ersten Öffnen',
            'body': 'Beim ersten Besuch jedes Tabs erscheint automatisch eine kurze Anleitung zu dessen Icons und Bedienelementen. Über {{ic:tour}} oben jederzeit erneut abrufbar.',
        },
    ],
}

# Per-page first-visit walkthroughs for all 16 views.
# Chinese (zh) and English (en) are fully authored; zh-TW/ja/ko/es/fr/de get localized summaries + EN fallback per step.
PAGE_TOURS = {
    'overview': {
        'zh': [
            {'target': '#page-toolbar', 'title': '总览筛选栏与价格模式', 'body': '顶部筛选条可按「时间范围」和「平台」过滤统计数字；右侧「按付费设置 / 按官方标价」用于切换免费额度按 $0 计算还是按官方标价折算。'},
            {'target': '#search-form', 'title': '全局搜索框', 'body': '输入任务编号、项目名、模型名或关键词，即可一次检索历史任务、请求日志、归档成果、项目进度和待办。'},
            {'target': '.grid[data-view="overview"]', 'title': '四大核心指标卡片', 'body': '依次展示已发送请求数、供应商实测 tokens、A/B 对照实测节省量，以及平均响应时间与输出速度（TPS）。'},
            {'target': '#chartwrap', 'title': '交互式用量趋势图', 'body': '上方按钮可切换 7 天 / 30 天 / 本年 / 总计，右侧按钮可切换「缓存命中率」。悬停查看单日数值，点击任意数据点直接弹出当天请求日志。'},
        ],
        'en': [
            {'target': '#page-toolbar', 'title': 'Filters & Cost Basis Toggle', 'body': 'Filter metrics by time range and platform. Use the right-hand segmented toggle to switch between Configured Cost ($0 for free/local) and Official List Price.'},
            {'target': '#search-form', 'title': 'Global Gate Search', 'body': 'Search across past tasks, requests, logs, archived outcomes, project handoffs, and to-dos by ID, project, model name, or keyword.'},
            {'target': '.grid[data-view="overview"]', 'title': 'Key Metric Cards', 'body': 'Shows sent requests, provider-reported tokens, measured A/B compression savings, and average latency plus output speed (tokens/s).'},
            {'target': '#chartwrap', 'title': 'Interactive Usage Trend', 'body': 'Switch between 7d / 30d / Year / All time or toggle Cache Hit Rate. Hover any point for details, or click it to open that day’s request log.'},
        ],
    },
    'center': {
        'zh': [
            {'target': '#center-form', 'title': '派发新任务与快捷模板', 'body': '先选项目（点「添加文件夹」可接入本地目录）、执行平台、模型与思考档位，填写目标后点击「开始任务」。底部「检查项目 / 审查修改 / 生成交接」可一键填入常用指令。'},
            {'target': '#center-list', 'title': '任务进度与验收操作', 'body': '每个任务卡片提供「查看成果」「查看修改（diff）」「接续任务」「确认验收通过」「撤回修改」与「停止」按钮，关闭窗口后任务仍会在后台执行。'},
            {'target': 'details.ux-advanced[data-view="center"]', 'title': '进阶折叠工具箱', 'body': '下方折叠区收录了「我的常用任务」「预约执行」「用量提醒」「版本对比」和「一键查故障」，需要时点击标题展开。'},
        ],
        'en': [
            {'target': '#center-form', 'title': 'Dispatch Tasks & Quick Fill', 'body': 'Pick a project (or click Add Folder), platform, model, and reasoning effort, then enter your goal. Use the Quick Fill buttons for common read-only checks or handoffs.'},
            {'target': '#center-list', 'title': 'Task Cards & Review Controls', 'body': 'Inspect outcomes, review file diffs, continue a session, accept results, or roll back changes. Tasks keep running even if you close this window.'},
            {'target': 'details.ux-advanced[data-view="center"]', 'title': 'Collapsible Advanced Tools', 'body': 'Expand these sections whenever you need Saved Tasks, Scheduled Runs, Usage Alerts, Version Compare, or Connectivity Diagnostics.'},
        ],
    },
    'wb': {
        'zh': [
            {'target': '#workbench', 'title': '项目进度与状态圆点', 'body': '每行左侧圆点颜色代表项目状态（绿=正常、黄=进行中、红=需关注），右侧显示最近交接日期。点击任意项目行展开「做了什么」「当前状态」与「下一步」。'},
        ],
        'en': [
            {'target': '#workbench', 'title': 'Project Handoffs & Status Dots', 'body': 'Colored dots indicate project health (green = healthy, yellow = in progress, red = needs attention). Click any project row to expand Done, Current State, and Next Step.'},
        ],
    },
    'gt': {
        'zh': [
            {'target': '#gt-prop', 'title': '压缩任务状态比例条', 'body': '顶部统计各状态任务数量，彩色进度条按比例展示已完成（绿）、运行中（紫）和失败/中断（黄）。'},
            {'target': '#gt-filters', 'title': '筛选与逐轮压缩日志', 'body': '用「分类」和「时间」下拉快速筛选任务；点击下方任务行可展开上下文打包前后估算与逐轮网关事件日志。'},
        ],
        'en': [
            {'target': '#gt-prop', 'title': 'Status Summary & Proportion Bar', 'body': 'Shows total Gate tasks and a color-coded bar for Done (green), Running (purple), and Failed/Interrupted (amber).'},
            {'target': '#gt-filters', 'title': 'Filters & Per-Turn Gateway Logs', 'body': 'Filter by status category or time window, then click any task row to inspect before/after pack estimates and per-turn raw logs.'},
        ],
    },
    'group': {
        'zh': [
            {'target': '.group-top', 'title': '群聊顶部工具栏', 'body': '在这里切换或新建群聊、改名/换项目；右侧布局按钮可在「单栏」与「并排（简报 + 成员聊天同时显示）」之间切换。'},
            {'target': '.group-side', 'title': '成员栏与图标按钮', 'body': '点击「＋」图标添加新 AI 成员；成员前圆点表示工作状态；底部可「换模型」「移出成员」，边缘箭头图标可收起成员栏腾出空间。'},
            {'target': '#group-send-form', 'title': '群发、@ 点名、/ 命令与附件图标', 'body': '直接输入发给全群，输入 @ 可指定单个成员，输入 / 可调出 /mod（角色分工）、/model、/delete 等快捷指令；点击回形针/附件按钮可附加图片或项目文件。'},
        ],
        'en': [
            {'target': '.group-top', 'title': 'Group Chat Top Bar', 'body': 'Switch or create groups, rename or change the project folder, and toggle between Single-Pane and Side-by-Side layouts.'},
            {'target': '.group-side', 'title': 'Members Rail & Icons', 'body': 'Click ＋ to add an AI member, watch live status dots, change models or remove members at the bottom, or collapse the rail for more reading room.'},
            {'target': '#group-send-form', 'title': '@Mentions, /Commands & Attachments', 'body': 'Send to everyone by default, type @ to target one member, type / for commands (/mod, /model, /delete), or click Attach to drop images/files.'},
        ],
    },
    'todo': {
        'zh': [
            {'target': '#todo-add-form', 'title': '快速添加与置顶浮窗', 'body': '输入待办后回车即可保存。在 macOS 壳 App 中，右上角「浮窗」按钮可一键弹出或隐藏屏幕右上角的置顶待办小窗。'},
            {'target': '#todo-page', 'title': '筛选、批量导入与多选操作', 'body': '支持按「全部 / 未完成 / 已完成」筛选、从 TXT/Markdown 文件批量导入、点「多选」批量勾选或删除，以及一键导出 Markdown。'},
        ],
        'en': [
            {'target': '#todo-add-form', 'title': 'Quick Add & Floating Panel', 'body': 'Type a task and press Enter to save. In the macOS desktop shell, the Float button toggles an always-on-top mini to-do window.'},
            {'target': '#todo-page', 'title': 'Filters, Batch Import & Multi-Select', 'body': 'Filter by All / Open / Done, import checklists from text or Markdown files, toggle Select for batch actions, or export to Markdown.'},
        ],
    },
    'memory': {
        'zh': [
            {'target': '.memory-toolbar', 'title': '记忆搜索、视图模式与同步按钮', 'body': '上方可关键词检索记忆，点击「更新记忆文档」同步最新内容；右侧按钮可在「总览 / 目录 / 大纲 / 详细」「文字 / 星云模式」间切换，并可调整字号或打开「实时事件」。'},
            {'target': '.memory-export', 'title': '三种记忆导出方式', 'body': '支持现场导出「一份完整文档」「分类文档包 ZIP」和「原始记录包 ZIP」，导出后会自动保存在本地文档文件夹。'},
        ],
        'en': [
            {'target': '.memory-toolbar', 'title': 'Search, Reading Modes & Sync', 'body': 'Search memories by topic or keyword, sync documents, switch between Overview / Directory / Outline / Detail or Text / Nebula mode, adjust font size, and inspect Live Events.'},
            {'target': '.memory-export', 'title': 'Export Packages', 'body': 'Generate a single merged document, a topic-organized ZIP, or a raw snapshot ZIP locally on demand.'},
        ],
    },
    'files': {
        'zh': [
            {'target': '#import-drop', 'title': '本地文件拖拽导入区', 'body': '拖入或点击选择 TXT、Markdown、CSV、JSON、DOCX、XLSX、PDF（≤512KB）。纯本地解析整理结构，完全不调用 AI 模型。'},
            {'target': '[data-view="files"]:last-of-type', 'title': '已导入列表与并排文件对比', 'body': '下方可分页预览或批量删除已导入副本（不影响电脑原件），并可选两份文件按行或按表格单元格高亮并排对比。'},
        ],
        'en': [
            {'target': '#import-drop', 'title': 'Local File Drop Zone', 'body': 'Drop or pick TXT, Markdown, CSV, JSON, DOCX, XLSX, or PDF files (up to 512 KB). Structure extraction runs 100% locally without calling any AI model.'},
            {'target': '[data-view="files"]:last-of-type', 'title': 'Imported Files & Side-by-Side Diff', 'body': 'Preview paginated text/tables, batch-delete local copies (originals stay untouched), or compare two files side by side with cell-level highlights.'},
        ],
    },
    'bill': {
        'zh': [
            {'target': '#bill-mode', 'title': '计费 / 用量滑动开关', 'body': '点击此开关可在「估算金额」与「Token 用量」之间平滑切换排序和条形图；顶部工具栏还可切换「按付费设置」或「按官方标价」。'},
            {'target': '#bill-tiles', 'title': '平台下钻卡片', 'body': '点击任意平台条或卡片可下钻查看该平台下的每个模型；继续点击具体模型还能查看输出速度（TPS）统计和逐条请求明细。'},
        ],
        'en': [
            {'target': '#bill-mode', 'title': 'Cost / Usage Toggle', 'body': 'Flip between estimated spend and raw token volume with animated re-ranking. Combine with the top Cost Basis switch for configured vs. official list prices.'},
            {'target': '#bill-tiles', 'title': 'Drill-Down Platform Tiles', 'body': 'Click any platform bar or tile to inspect its models; click a model tile to view output speed (TPS) distribution and individual request records.'},
        ],
    },
    'plat': {
        'zh': [
            {'target': '#plat-viz', 'title': '平台用量横向对比图', 'body': '一眼看出各平台（Claude、Codex、ZCode、Local Model Router 等）的 token 占比与请求数排名。'},
            {'target': '#plat', 'title': '平台明细数据表', 'body': '横向对比请求数、输入/输出/缓存 tokens、估算花费、实测 A/B 对照节省和平均耗时。'},
        ],
        'en': [
            {'target': '#plat-viz', 'title': 'Platform Volume Comparison', 'body': 'Compare total token volume and request counts across Claude, Codex, ZCode, Local Model Router, and other platforms at a glance.'},
            {'target': '#plat', 'title': 'Full Comparison Table', 'body': 'Side-by-side breakdown of requests, input/output tokens, estimated spend, measured A/B savings, and average latency.'},
        ],
    },
    'wallet': {
        'zh': [
            {'target': '#mw-root', 'title': '模型预算子导航与换算工具', 'body': '顶部子标签涵盖「成本计算」「模型库」「钱包与账本」「路由模拟」和「设置」。可按预算反算可用 tokens、覆盖自定义单价，并手工记账管理余额（纯本地模拟，不会真实扣款）。'},
        ],
        'en': [
            {'target': '#mw-root', 'title': 'Model Budgets & Cost Calculator', 'body': 'Use the sub-tabs (Calculator, Model Catalog, Wallets & Ledger, Route Sim, Settings) to estimate how far a budget goes, set custom prices, and track manual balances locally.'},
        ],
    },
    'quota': {
        'zh': [
            {'target': '[data-view="quota"]', 'title': '订阅额度守卫', 'body': '实时监控 Claude Code 和 Codex 的 5 小时与周额度剩余百分比与恢复倒计时。可设置提醒门槛，并按需开启低额度时自动暂停本机托管任务。'},
        ],
        'en': [
            {'target': '[data-view="quota"]', 'title': 'Subscription Quota Guard', 'body': 'Tracks remaining 5-hour and weekly quotas plus reset timers for Claude Code and Codex. Set alert thresholds and optional auto-pause for local managed tasks.'},
        ],
    },
    'req': {
        'zh': [
            {'target': '#req-sums', 'title': '最近请求汇总条', 'body': '快速统计最近 50 次请求中的成功、失败、进行中数量及总 token 消耗。'},
            {'target': '#recent', 'title': '请求账本明细（点击可看详情）', 'body': '展示每次请求的模型、压缩估算、实测输入/输出、缓存读与耗时。点击任意一行可弹出耗时分段与可关联日志详情。'},
        ],
        'en': [
            {'target': '#req-sums', 'title': 'Recent Requests Summary', 'body': 'Quick tally of succeeded, failed, and pending requests plus total tokens across the latest 50 ledger entries.'},
            {'target': '#recent', 'title': 'Clickable Request Ledger', 'body': 'Inspect pack estimates, actual provider input/output, cache reads, and wall-clock duration. Click any row for timing breakdowns and linked logs.'},
        ],
    },
    'git': {
        'zh': [
            {'target': '[data-view="git"]', 'title': '项目 Git 自动同步管理', 'body': '查看本机 Git 仓库与 GitHub 的同步状态（每 5 分钟自动检查）。每张卡片支持开关同步、点「重试」「打开文件夹」「重新定位」或在发生冲突时「标记已解决」。'},
        ],
        'en': [
            {'target': '[data-view="git"]', 'title': 'GitHub Project Sync', 'body': 'Monitor automatic 5-minute sync status for local Git repos. Each card lets you toggle sync, retry, reveal in Finder, relocate a moved folder, or mark conflicts resolved.'},
        ],
    },
    'router': {
        'zh': [
            {'target': '.router-top', 'title': '本地模型路由控制栏', 'body': '一键启动或打开本地模型路由器，下方分页可分别查看路由统计总览、配置供应商与 API 密钥、管理模型别名，以及执行连通性测试。'},
        ],
        'en': [
            {'target': '.router-top', 'title': 'Local Model Router Controls', 'body': 'Start or open your local model router, then use the tabs below to inspect routing stats, manage providers & API keys, configure model aliases, and run connection tests.'},
        ],
    },
    'sys': {
        'zh': [
            {'target': 'section[data-view="sys"]', 'title': '外观、语言与新手教程设置', 'body': '在这里切换主题风格、自动刷新、侧边栏形态、管家模型和 8 种界面语言；底部「新手教程」行可随时重播主界面导览或重置全部 16 个分页的首次提示。'},
            {'target': 'details.ux-advanced[data-view="sys"]', 'title': '快捷键、密钥体检与脱敏日志', 'body': '可一键启动 Claude / ZCode / Codex、录制全局唤起快捷键；下方折叠区提供只报状态不露内容的密钥权限检查与可点击放大的脱敏运行日志。'},
        ],
        'en': [
            {'target': 'section[data-view="sys"]', 'title': 'Appearance, Language & Tutorial Settings', 'body': 'Customize theme presets, auto-refresh, sidebar mode, Butler model, and 8 UI languages. Use the Onboarding Tutorial row anytime to replay or reset guides.'},
            {'target': 'details.ux-advanced[data-view="sys"]', 'title': 'Shortcuts, Credential Audit & Redacted Logs', 'body': 'Launch Claude / ZCode / Codex or record a global hotkey, and expand the diagnostics below for status-only credential audits and redacted service logs.'},
        ],
    },
}

# Localized page tour titles/bodies for zh-TW, ja, ko, es, fr, de (concise, natural per-page guides).
PAGE_TOURS_LOCALIZED = {
    'zh-TW': {
        'overview': [
            {'target': '#page-toolbar', 'title': '總覽篩選列與價格模式', 'body': '可依時間範圍與平台篩選統計數字；右側切換「按付費設定 / 按官方標價」。'},
            {'target': '#search-form', 'title': '全域搜尋框', 'body': '輸入編號、專案名或關鍵字，一次檢索歷史任務、請求日誌、成果與待辦。'},
            {'target': '#chartwrap', 'title': '互動式用量趨勢圖', 'body': '切換 7 天 / 30 天 / 本年 / 總計或快取命中率，點擊資料點可開啟當天請求日誌。'},
        ],
        'center': [
            {'target': '#center-form', 'title': '派發新任務與快捷範本', 'body': '選擇專案、平台、模型與思考檔位後點「開始任務」；下方快捷按鈕可一鍵填入常用指令。'},
            {'target': '#center-list', 'title': '任務進度與驗收操作', 'body': '支援檢視成果、diff 修改紀錄、接續任務、確認驗收或撤回修改。'},
        ],
        'group': [
            {'target': '.group-top', 'title': '群聊頂部工具列', 'body': '切換或新建群聊、改名/換專案，右側可切換單欄或並排檢視。'},
            {'target': '.group-side', 'title': '成員欄與圖示按鈕', 'body': '點「＋」新增成員，圓點代表狀態；底部可換模型或移出成員。'},
            {'target': '#group-send-form', 'title': '@ 點名、/ 指令與附件', 'body': '輸入 @ 指定成員、輸入 / 叫出快捷指令，點附件按鈕可加入圖片或檔案。'},
        ],
    },
    'ja': {
        'overview': [
            {'target': '#page-toolbar', 'title': 'フィルターと価格モード', 'body': '期間・プラットフォームで絞り込み、右側のスイッチで支払い設定準拠と公式定価換算を切り替えられます。'},
            {'target': '#search-form', 'title': '横断検索', 'body': 'タスクID、プロジェクト名、モデル名などで履歴・ログ・成果物を一括検索できます。'},
            {'target': '#chartwrap', 'title': '使用量トレンドグラフ', 'body': '期間切替やキャッシュ率表示に対応。各点をクリックするとその日のリクエスト履歴が開きます。'},
        ],
        'center': [
            {'target': '#center-form', 'title': 'タスク依頼とテンプレート', 'body': 'プロジェクト・プラットフォーム・モデル・推論レベルを選んで開始します。下部のクイック入力も便利です。'},
            {'target': '#center-list', 'title': '成果確認と差分・ロールバック', 'body': '成果表示、diff 確認、継続、検収承認、変更の取り消しがカード単位で行えます。'},
        ],
        'group': [
            {'target': '.group-top', 'title': 'グループ上部ツールバー', 'body': 'グループ作成・切替・名前変更や、1カラム／2カラム表示の切替を行います。'},
            {'target': '.group-side', 'title': 'メンバー一覧とアイコン', 'body': '「＋」で AI メンバーを追加し、ステータスドットやモデル変更・削除を操作できます。'},
            {'target': '#group-send-form', 'title': '@メンション・/コマンド・添付', 'body': '@ で個別指定、/ で役割分担などのコマンドを呼び出し、添付ボタンで画像やファイルを追加できます。'},
        ],
    },
    'ko': {
        'overview': [
            {'target': '#page-toolbar', 'title': '필터 및 가격 기준', 'body': '기간과 플랫폼별로 통계를 필터링하고, 우측 토글로 결제 설정 기준과 공식 정가 기준을 전환합니다.'},
            {'target': '#search-form', 'title': '통합 검색', 'body': '작업 ID, 프로젝트, 모델명 또는 키워드로 작업·요청·로그·할 일을 한 번에 검색하세요.'},
            {'target': '#chartwrap', 'title': '사용량 추이 차트', 'body': '기간 전환 및 캐시 적중률 보기를 지원하며, 데이터 포인트를 클릭하면 해당 날짜 요청 로그가 열립니다.'},
        ],
        'center': [
            {'target': '#center-form', 'title': '작업 생성 및 빠른 입력', 'body': '프로젝트, 플랫폼, 모델, 추론 수준을 선택해 작업을 시작하세요. 하단 버튼으로 자주 쓰는 지시를 빠르게 채울 수 있습니다.'},
            {'target': '#center-list', 'title': '결과 확인 및 검수', 'body': '결과 보기, diff 확인, 이어서 실행, 검수 승인, 변경 되돌리기를 카드에서 바로 수행합니다.'},
        ],
        'group': [
            {'target': '.group-top', 'title': '그룹 채팅 상단 바', 'body': '그룹 전환·생성·이름 변경과 단일/나란히 레이아웃 전환을 지원합니다.'},
            {'target': '.group-side', 'title': '멤버 목록 및 아이콘', 'body': '＋ 아이콘으로 AI 멤버를 추가하고 상태 점, 모델 변경, 멤버 제거를 관리합니다.'},
            {'target': '#group-send-form', 'title': '@멘션, /명령어 및 첨부', 'body': '@로 특정 멤버 지정, /로 역할 분담 등 명령어 실행, 첨부 버튼으로 파일·이미지를 보낼 수 있습니다.'},
        ],
    },
}

CSS = r'''
.tour-trigger{display:inline-flex;align-items:center;justify-content:center;gap:5px;min-height:34px;padding:0 10px;border-radius:7px;font-size:12px;color:var(--muted)}
.tour-trigger:hover{color:var(--text);border-color:var(--line2)}
.tour-trigger svg{width:15px;height:15px;flex:none}
.tour-trigger-dot{width:6px;height:6px;border-radius:50%;background:var(--accent);display:inline-block}
.tour-trigger-dot[hidden]{display:none}
html.tour-lock,html.tour-lock body{overflow:hidden!important;overscroll-behavior:none!important}
@keyframes tourCenterIn{from{opacity:0;transform:translate(-50%,-50%) scale(.98)}to{opacity:1;transform:translate(-50%,-50%)}}
.tour-backdrop{position:fixed;inset:0;z-index:120;background:rgba(6,8,12,.58);backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);animation:fadeIn .16s ease}
.tour-backdrop.is-instant{animation:none}
:root[data-theme=warm] .tour-backdrop{background:rgba(43,37,32,.36)}
.tour-shield{position:fixed;z-index:120;background:transparent;pointer-events:auto}
.tour-spotlight{position:fixed;z-index:121;border-radius:10px;border:2px solid var(--accent);box-shadow:0 0 0 4px var(--accentbg),0 0 0 9999px rgba(6,8,12,.56);pointer-events:none;transition:top .24s cubic-bezier(.2,.8,.2,1),left .24s cubic-bezier(.2,.8,.2,1),width .24s cubic-bezier(.2,.8,.2,1),height .24s cubic-bezier(.2,.8,.2,1)}
:root[data-theme=warm] .tour-spotlight{box-shadow:0 0 0 4px var(--accentbg),0 0 0 9999px rgba(43,37,32,.34)}
.tour-card{position:fixed;z-index:122;width:min(430px,calc(100vw - 24px));max-height:calc(100dvh - 24px);overflow:auto;background:var(--glassbg);backdrop-filter:blur(24px) saturate(170%);-webkit-backdrop-filter:blur(24px) saturate(170%);border:1px solid var(--line2);border-radius:14px;padding:18px 20px;box-shadow:0 24px 68px rgba(0,0,0,.48);color:var(--text);animation:modalIn .18s ease}
.tour-card.is-centered{top:50%;left:50%;transform:translate(-50%,-50%);animation:tourCenterIn .18s ease}
.tour-card.is-instant{animation:none}
:root[data-theme=warm] .tour-card{box-shadow:0 20px 54px rgba(43,37,32,.22)}
.tour-ic{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;vertical-align:-3px;border-radius:5px;background:var(--chip);border:1px solid var(--line);color:var(--text);margin:0 2px}
.tour-ic svg,.tour-badge svg{width:12px;height:12px;flex:none}
.tour-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
.tour-badge{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:999px;background:var(--accentbg);color:var(--accent);font-size:11.5px;font-weight:600}
.tour-step{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.tour-card h3{margin:0 0 8px;font-size:16px;font-weight:650;line-height:1.35}
.tour-body{margin:0;font-size:13px;line-height:1.68;color:var(--muted);white-space:pre-line}
.tour-lang-box{margin-top:14px;padding:10px 12px;border-radius:10px;background:var(--chip);border:1px solid var(--line)}
.tour-lang-note{font-size:11.5px;color:var(--accent);margin-bottom:8px;font-weight:500}
.tour-lang-grid{display:flex;flex-wrap:wrap;gap:6px}
.tour-lang-btn{min-height:28px;padding:3px 10px;border-radius:999px;font-size:12px;border:1px solid var(--line2);background:var(--cardT);color:var(--text)}
.tour-lang-btn.on{background:var(--accent);border-color:transparent;color:var(--onaccent);font-weight:600}
.tour-dots{display:flex;gap:5px;margin-top:14px;align-items:center}
.tour-dots i{display:block;width:6px;height:6px;border-radius:999px;background:var(--line2);transition:width .2s ease,background-color .2s ease}
.tour-dots i.on{width:18px;background:var(--accent)}
.tour-mute{display:inline-flex;align-items:center;gap:6px;margin-top:12px;font-size:12px;color:var(--muted);cursor:pointer;user-select:none}
.tour-mute input{accent-color:var(--accent);margin:0}
.tour-actions{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:16px;flex-wrap:wrap}
.tour-actions-right{display:flex;align-items:center;gap:8px;margin-left:auto}
.tour-btn-skip{background:transparent;border-color:transparent;color:var(--muted);padding:6px 10px;font-size:12.5px}
.tour-btn-skip:hover{color:var(--text);background:var(--rowhover)}
.tour-btn-primary{background:var(--accent);border-color:transparent;color:var(--onaccent);font-weight:600}
.tour-menu-list{display:grid;gap:8px;margin-top:12px}
.tour-menu-list button{text-align:left;padding:10px 12px;font-size:13px}
.tour-sys-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
'''

JS = r'''
const TOUR_LANG_OPTIONS=__TOUR_LANG_OPTIONS__,TOUR_UI=__TOUR_UI__,MAIN_TOUR=__MAIN_TOUR__,PAGE_TOURS=__PAGE_TOURS__,PAGE_TOURS_LOCALIZED=__PAGE_TOURS_LOCALIZED__;
const TOUR_MAIN_KEY='cg-tour-main-done',TOUR_PAGES_KEY='cg-tour-pages',TOUR_AUTO_KEY='cg-tour-auto';
function tourUi(){return TOUR_UI[LANG]||TOUR_UI.en;}
function tourLangLabel(code){const f=TOUR_LANG_OPTIONS.find(x=>x[0]===code);return f?f[1]:code;}
function tourAutoEnabled(){try{return localStorage.getItem(TOUR_AUTO_KEY)!=='0';}catch(e){return true;}}
function setTourAutoEnabled(on){try{localStorage.setItem(TOUR_AUTO_KEY,on?'1':'0');}catch(e){}const cb=$('tour-auto-chk');if(cb)cb.checked=on;}
function tourVisitedPages(){try{const raw=localStorage.getItem(TOUR_PAGES_KEY);const obj=raw?JSON.parse(raw):{};return obj&&typeof obj==='object'?obj:{};}catch(e){return {};}}
function markTourPageSeen(view){try{const obj=tourVisitedPages();obj[view]=1;localStorage.setItem(TOUR_PAGES_KEY,JSON.stringify(obj));}catch(e){}syncTourTriggerDot();}
function tourMainDone(){try{return localStorage.getItem(TOUR_MAIN_KEY)==='1';}catch(e){return false;}}
function markTourMainDone(){try{localStorage.setItem(TOUR_MAIN_KEY,'1');}catch(e){}syncTourTriggerDot();}
function resetAllPageTours(){try{localStorage.removeItem(TOUR_PAGES_KEY);}catch(e){}syncTourTriggerDot();}
function syncTourTriggerDot(){
  const dot=$('tour-trigger-dot');if(!dot)return;
  const visited=tourVisitedPages();
  dot.hidden=tourMainDone()&&!!visited[curView];
}
function getPageTourSteps(view){
  const loc=PAGE_TOURS_LOCALIZED[LANG]&&PAGE_TOURS_LOCALIZED[LANG][view];
  if(loc&&loc.length)return loc;
  const base=PAGE_TOURS[view];
  if(!base)return [];
  return base[LANG]||base.en||base.zh||[];
}
const TOUR_ICONS={
  tour:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="12" height="12" rx="3"/><path d="M10.4 5.6L9 9l-3.4 1.4L7 7z"/></svg>',
  theme:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="3"/><path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1"/></svg>',
  help:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6"/><path d="M6.4 6.2a1.7 1.7 0 0 1 3.2.6c0 1.1-1.6 1.3-1.6 2.3"/><circle cx="8" cy="11.6" r=".5" fill="currentColor" stroke="none"/></svg>'
};
function tourFormatBody(text){
  return esc(text).replace(/\{\{ic:(tour|theme|help)\}\}/g,(_,k)=>'<span class="tour-ic" aria-hidden="true">'+TOUR_ICONS[k]+'</span>');
}
let tourState=null,tourPageTimer=null;
function onTourPointer(e){
  if(!tourState)return;
  if(tourState.card&&tourState.card.contains(e.target))return;
  const step=tourState.steps[tourState.index];
  const target=findTourTarget(step&&step.target);
  if(target&&target.contains(e.target))return;
  e.preventDefault();e.stopImmediatePropagation();
}
function onTourWheel(e){
  if(!tourState)return;
  if(tourState.card&&tourState.card.contains(e.target)&&tourState.card.scrollHeight>tourState.card.clientHeight)return;
  e.preventDefault();
}
function closeTour(markDone){
  if(!tourState)return;
  const st=tourState;tourState=null;
  document.documentElement.classList.remove('tour-lock');
  if(st.els){st.els.forEach(el=>el&&el.remove());}
  window.removeEventListener('resize',renderTourPosition);
  window.removeEventListener('scroll',renderTourPosition,true);
  window.removeEventListener('wheel',onTourWheel,true);
  window.removeEventListener('touchmove',onTourWheel,true);
  document.removeEventListener('keydown',onTourKey,true);
  document.removeEventListener('click',onTourPointer,true);
  document.removeEventListener('mousedown',onTourPointer,true);
  document.removeEventListener('pointerdown',onTourPointer,true);
  if(markDone){
    if(st.kind==='main')markTourMainDone();
    else if(st.view)markTourPageSeen(st.view);
  }
  syncTourTriggerDot();
}
function findTourTarget(selector){
  if(!selector)return null;
  try{
    const nodes=[...document.querySelectorAll(selector)];
    for(const el of nodes){
      const r=el.getBoundingClientRect();
      if(r.width>4&&r.height>4&&getComputedStyle(el).display!=='none'&&getComputedStyle(el).visibility!=='hidden')return el;
    }
  }catch(e){}
  return null;
}
function renderTourPosition(){
  if(!tourState)return;
  const step=tourState.steps[tourState.index];
  const spot=tourState.spot,card=tourState.card,back=tourState.back,shields=tourState.shields||[];
  const target=findTourTarget(step.target);
  const vw=window.innerWidth,vh=window.innerHeight;
  if(target){
    back.style.display='none';
    spot.style.display='block';
    card.classList.remove('is-centered');
    const r=target.getBoundingClientRect(),pad=6;
    const top=Math.max(4,r.top-pad),left=Math.max(4,r.left-pad);
    const width=Math.min(vw-left-4,r.width+pad*2),height=Math.min(vh-top-4,r.height+pad*2);
    const right=Math.min(vw,left+width),bottom=Math.min(vh,top+height);
    Object.assign(spot.style,{top:top+'px',left:left+'px',width:width+'px',height:height+'px'});
    if(shields.length===4){
      Object.assign(shields[0].style,{display:'block',top:'0px',left:'0px',width:vw+'px',height:Math.max(0,top)+'px'});
      Object.assign(shields[1].style,{display:'block',top:bottom+'px',left:'0px',width:vw+'px',height:Math.max(0,vh-bottom)+'px'});
      Object.assign(shields[2].style,{display:'block',top:top+'px',left:'0px',width:Math.max(0,left)+'px',height:Math.max(0,bottom-top)+'px'});
      Object.assign(shields[3].style,{display:'block',top:top+'px',left:right+'px',width:Math.max(0,vw-right)+'px',height:Math.max(0,bottom-top)+'px'});
    }
    card.style.transform='';
    const cw=card.offsetWidth||380,ch=card.offsetHeight||220,gap=14;
    let cx=left,cy=top+height+gap;
    if(cy+ch>vh-12){
      if(top-ch-gap>=12)cy=top-ch-gap;
      else if(left+width+cw+gap<=vw-12){cx=left+width+gap;cy=Math.max(12,Math.min(top,vh-ch-12));}
      else if(left-cw-gap>=12){cx=left-cw-gap;cy=Math.max(12,Math.min(top,vh-ch-12));}
      else{cy=Math.max(12,vh-ch-12);}
    }
    cx=Math.max(12,Math.min(cx,vw-cw-12));
    cy=Math.max(12,Math.min(cy,vh-ch-12));
    Object.assign(card.style,{top:cy+'px',left:cx+'px'});
  }else{
    spot.style.display='none';
    shields.forEach(s=>{s.style.display='none';});
    back.style.display='block';
    card.classList.add('is-centered');
    Object.assign(card.style,{top:'',left:'',transform:''});
  }
}
function renderTourStep(){
  if(!tourState)return;
  const ui=tourUi(),st=tourState,step=st.steps[st.index],total=st.steps.length,last=st.index===total-1;
  const target=findTourTarget(step.target);
  if(target){try{document.documentElement.classList.remove('tour-lock');target.scrollIntoView({block:'center',inline:'nearest',behavior:'auto'});}catch(e){}document.documentElement.classList.add('tour-lock');}
  let langHtml='';
  if(step.langPicker){
    langHtml='<div class="tour-lang-box">'
      +(LANG_AUTO?'<div class="tour-lang-note">'+esc(ui.auto_lang)+' '+esc(tourLangLabel(LANG))+'</div>':'<div class="tour-lang-note">'+esc(ui.choose_lang)+'</div>')
      +'<div class="tour-lang-grid">'+TOUR_LANG_OPTIONS.map(([code,label])=>'<button type="button" class="tour-lang-btn'+(code===LANG?' on':'')+'" data-tour-lang="'+esc(code)+'">'+esc(label)+'</button>').join('')+'</div></div>';
  }
  const dots=total>1?'<div class="tour-dots" aria-hidden="true">'+st.steps.map((_,i)=>'<i'+(i===st.index?' class="on"':'')+'></i>').join('')+'</div>':'';
  const muteHtml=st.kind==='page'?'<label class="tour-mute"><input type="checkbox" id="tour-mute-chk"'+(tourAutoEnabled()?'':' checked')+'><span>'+esc(ui.mute)+'</span></label>':'';
  const primaryText=st.kind==='main'&&st.index===0?ui.start:(last?(st.kind==='main'?ui.finish:ui.done):ui.next);
  st.card.innerHTML='<div class="tour-top"><span class="tour-badge">'+TOUR_ICONS.tour+(st.kind==='main'?esc(ui.badge_main):esc(ui.badge_page))+'</span><span class="tour-step">'+(st.index+1)+' / '+total+'</span></div>'
    +'<h3>'+esc(step.title)+'</h3>'
    +'<p class="tour-body">'+tourFormatBody(step.body)+'</p>'
    +langHtml+dots+muteHtml
    +'<div class="tour-actions"><button type="button" class="tour-btn-skip" data-tour-act="skip">'+esc(ui.skip)+'</button>'
    +'<div class="tour-actions-right">'+(st.index>0?'<button type="button" data-tour-act="prev">'+esc(ui.prev)+'</button>':'')
    +'<button type="button" class="tour-btn-primary" data-tour-act="'+(last?'finish':'next')+'">'+esc(primaryText)+'</button></div></div>';
  st.card.querySelectorAll('[data-tour-lang]').forEach(btn=>btn.onclick=()=>{
    const nextLang=btn.dataset.tourLang;if(nextLang===LANG)return;
    try{localStorage.setItem('cg-lang',nextLang);sessionStorage.setItem('cg-tour-lang-switch','1');}catch(e){}
    try{window.webkit?.messageHandlers?.language?.postMessage(nextLang);}catch(e){}
    location.reload();
  });
  const mute=$('tour-mute-chk');if(mute)mute.onchange=()=>setTourAutoEnabled(!mute.checked);
  st.card.querySelectorAll('[data-tour-act]').forEach(btn=>btn.onclick=()=>{
    const a=btn.dataset.tourAct;
    if(a==='skip'||a==='finish'){closeTour(true);}
    else if(a==='prev'&&st.index>0){st.index--;renderTourStep();}
    else if(a==='next'&&st.index<total-1){st.index++;renderTourStep();}
  });
  renderTourPosition();
  setTimeout(renderTourPosition,180);
  (st.card.querySelector('.tour-btn-primary')||st.card).focus({preventScroll:true});
}
function onTourKey(e){
  if(!tourState)return;
  if(e.key==='Escape'){e.preventDefault();closeTour(true);}
  else if(e.key==='ArrowRight'&&tourState.index<tourState.steps.length-1){e.preventDefault();tourState.index++;renderTourStep();}
  else if(e.key==='ArrowLeft'&&tourState.index>0){e.preventDefault();tourState.index--;renderTourStep();}
  else if(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End'].includes(e.key)||(e.key===' '&&!(tourState.card&&tourState.card.contains(e.target)))){e.preventDefault();}
}
function startTour(kind,view,instant){
  if(typeof todoMini!=='undefined'&&todoMini)return;
  const steps=kind==='main'?(MAIN_TOUR[LANG]||MAIN_TOUR.en):getPageTourSteps(view||curView);
  if(!steps||!steps.length)return;
  closeTour(false);
  document.documentElement.classList.add('tour-lock');
  const back=document.createElement('div');back.className='tour-backdrop'+(instant?' is-instant':'');
  const shields=[0,1,2,3].map(()=>{const s=document.createElement('div');s.className='tour-shield';s.style.display='none';return s;});
  const spot=document.createElement('div');spot.className='tour-spotlight';
  const card=document.createElement('div');card.className='tour-card'+(!findTourTarget(steps[0].target)?' is-centered':'')+(instant?' is-instant':'');card.setAttribute('role','dialog');card.setAttribute('aria-modal','true');card.tabIndex=-1;
  document.body.append(back,...shields,spot,card);
  tourState={kind,view:view||curView,steps,index:0,back,shields,spot,card,els:[back,...shields,spot,card]};
  window.addEventListener('resize',renderTourPosition);
  window.addEventListener('scroll',renderTourPosition,true);
  window.addEventListener('wheel',onTourWheel,{passive:false,capture:true});
  window.addEventListener('touchmove',onTourWheel,{passive:false,capture:true});
  document.addEventListener('keydown',onTourKey,true);
  document.addEventListener('click',onTourPointer,true);
  document.addEventListener('mousedown',onTourPointer,true);
  document.addEventListener('pointerdown',onTourPointer,true);
  renderTourStep();
}
function openTourMenu(){
  const ui=tourUi(),pageSteps=getPageTourSteps(curView);
  openModal(ui.menu_title,'<p class="ux-note">'+esc(ui.menu_desc)+'</p><div class="tour-menu-list">'
    +(pageSteps.length?'<button type="button" id="tm-page">'+esc(ui.menu_page)+' ('+esc($('page-title')?.textContent||curView)+')</button>':'')
    +'<button type="button" id="tm-main">'+esc(ui.menu_main)+'</button>'
    +'<button type="button" id="tm-reset">'+esc(ui.menu_reset)+'</button></div>');
  const bp=$('tm-page');if(bp)bp.onclick=()=>{closeModal();setTimeout(()=>startTour('page',curView),180);};
  const bm=$('tm-main');if(bm)bm.onclick=()=>{closeModal();setTimeout(()=>startTour('main','overview'),180);};
  const br=$('tm-reset');if(br)br.onclick=()=>{resetAllPageTours();closeModal();setTimeout(()=>startTour('page',curView),180);};
}
function maybeStartPageTour(view){
  clearTimeout(tourPageTimer);
  if(typeof todoMini!=='undefined'&&todoMini)return;
  if(tourState||!tourMainDone()||!tourAutoEnabled())return;
  const visited=tourVisitedPages();
  if(visited[view])return;
  const steps=getPageTourSteps(view);
  if(!steps.length)return;
  tourPageTimer=setTimeout(()=>{
    if(!tourState&&curView===view&&!tourVisitedPages()[view])startTour('page',view);
  },260);
}
function bootOnboarding(){
  if(typeof todoMini!=='undefined'&&todoMini)return;
  const trigger=$('tour-open');if(trigger&&!trigger.__wired){trigger.__wired=true;trigger.onclick=openTourMenu;}
  const cb=$('tour-auto-chk');if(cb&&!cb.__wired){cb.__wired=true;cb.checked=tourAutoEnabled();cb.onchange=()=>setTourAutoEnabled(cb.checked);}
  const bm=$('tour-replay-main');if(bm&&!bm.__wired){bm.__wired=true;bm.onclick=()=>{applyView('overview');setTimeout(()=>startTour('main','overview'),200);};}
  const br=$('tour-reset-pages');if(br&&!br.__wired){br.__wired=true;br.onclick=()=>{resetAllPageTours();const n=$('tour-sys-note');if(n)n.textContent=T('已重置所有分页的新手引导，下次点开各分页时将重新提示。');};}
  syncTourTriggerDot();
  let langSwitched=false;
  try{langSwitched=sessionStorage.getItem('cg-tour-lang-switch')==='1';if(langSwitched)sessionStorage.removeItem('cg-tour-lang-switch');}catch(e){}
  if(!tourMainDone()){
    if(langSwitched){startTour('main','overview',true);}
    else{setTimeout(()=>{if(!tourState&&!tourMainDone())startTour('main','overview');},420);}
  }
}
'''


def apply_tutorial_and_i18n(page):
    """Inject multi-language support, system-language detection, and onboarding tutorial."""
    # 1. Inject CSS
    page = page.replace('</style>', CSS + '\n</style>', 1)

    # 2. Expand language selector with all 8 languages & updated description
    old_lang_row = (
        '<div class="setrow"><div class="sinfo"><div class="sname">界面语言</div>'
        '<div class="sdesc">中文 / English 切换控制台界面语言，立即生效</div></div>'
        '<div class="sctl"><select id="lang-select" aria-label="界面语言">'
        '<option value="zh">中文</option><option value="en">English</option></select></div></div>'
    )
    lang_options_html = ''.join(f'<option value="{code}">{label}</option>' for code, label in LANG_OPTIONS)
    new_lang_and_tour_rows = (
        '<div class="setrow"><div class="sinfo"><div class="sname">界面语言</div>'
        '<div class="sdesc">多语言切换控制台界面语言，首次启动会自动匹配系统语言</div></div>'
        f'<div class="sctl"><select id="lang-select" aria-label="界面语言">{lang_options_html}</select></div></div>'
        '<div class="setrow"><div class="sinfo"><div class="sname">新手教程</div>'
        '<div class="sdesc">自动显示首次访问引导，也可随时重新播放主界面导览或重置各分页提示</div>'
        '<div class="sdesc" id="tour-sys-note" role="status" aria-live="polite"></div></div>'
        '<div class="sctl"><div class="tour-sys-actions">'
        '<label class="chk"><input type="checkbox" id="tour-auto-chk" checked>首次进入分页时自动显示引导</label>'
        '<button type="button" id="tour-replay-main">重播主界面导览</button>'
        '<button type="button" id="tour-reset-pages">重置分页引导</button>'
        '</div></div></div>'
    )
    if old_lang_row not in page:
        raise ValueError('Language settings row not found in console page')
    page = page.replace(old_lang_row, new_lang_and_tour_rows, 1)

    # 3. Add topbar tutorial trigger icon button right before theme icon
    tour_btn = (
        '<button class="tour-trigger" id="tour-open" title="查看主界面与当前分页的新手引导" type="button">'
        '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="2" y="2" width="12" height="12" rx="3"/><path d="M10.4 5.6L9 9l-3.4 1.4L7 7z"/></svg>'
        '<span>引导</span><i class="tour-trigger-dot" id="tour-trigger-dot" hidden></i></button>\n'
    )
    page = page.replace('<button class="iconbtn" id="themeicon"', tour_btn + '<button class="iconbtn" id="themeicon"', 1)

    # 4. Upgrade language auto-detection + multi-language lookup while preserving test_console_english.py anchors
    old_lang_init = (
        "let LANG='zh';try{LANG=localStorage.getItem('cg-lang')||window.__contextGateLanguage||'zh'}catch(e){}\n"
        "if(!['zh','en'].includes(LANG))LANG='zh';\n"
        "const LOCALE=()=>LANG==='en'?'en-US':'zh-CN';"
    )
    new_lang_init = (
        "let LANG='zh',LANG_AUTO=false;\n"
        f"const SUPPORTED_LANGS={json.dumps(list(SUPPORTED_LANGS))};\n"
        "function detectSystemLang(){\n"
        "  try{\n"
        "    if(typeof navigator==='undefined')return null;\n"
        "    const list=(Array.isArray(navigator.languages)&&navigator.languages.length)?navigator.languages:[navigator.language];\n"
        "    let saw=false;\n"
        "    for(const raw of list){\n"
        "      if(!raw)continue;saw=true;\n"
        "      const s=String(raw).toLowerCase().replace(/_/g,'-');\n"
        "      if(s==='zh-tw'||s==='zh-hk'||s==='zh-mo'||s.startsWith('zh-hant'))return 'zh-TW';\n"
        "      if(s.startsWith('zh'))return 'zh';\n"
        "      if(s.startsWith('en'))return 'en';\n"
        "      if(s.startsWith('ja'))return 'ja';\n"
        "      if(s.startsWith('ko'))return 'ko';\n"
        "      if(s.startsWith('es'))return 'es';\n"
        "      if(s.startsWith('fr'))return 'fr';\n"
        "      if(s.startsWith('de'))return 'de';\n"
        "    }\n"
        "    if(saw)return 'en';\n"
        "  }catch(e){}\n"
        "  return null;\n"
        "}\n"
        "try{\n"
        "  const saved=localStorage.getItem('cg-lang');\n"
        "  const shell=typeof window!=='undefined'?window.__contextGateLanguage:undefined;\n"
        "  if(saved!==null&&saved!==undefined&&saved!==''){LANG=saved;}\n"
        "  else if(shell){LANG=shell;}\n"
        "  else{const sys=detectSystemLang();if(sys){LANG=sys;LANG_AUTO=true;}}\n"
        "}catch(e){}\n"
        "if(!SUPPORTED_LANGS.includes(LANG))LANG='zh';\n"
        "const LOCALE=()=>({zh:'zh-CN','zh-TW':'zh-TW',en:'en-US',ja:'ja-JP',ko:'ko-KR',es:'es-ES',fr:'fr-FR',de:'de-DE'}[LANG]||'en-US');"
    )
    if old_lang_init not in page:
        raise ValueError('Language init block not found in console page')
    page = page.replace(old_lang_init, new_lang_init, 1)

    # 5. Merge EN_ADDITIONS and EXTRA_I18N right before `const T=s=>`
    i18n_inject = (
        'Object.assign(EN,' + json.dumps(EN_ADDITIONS, ensure_ascii=False) + ');\n'
        'const EXTRA_I18N=' + json.dumps(EXTRA_I18N, ensure_ascii=False) + ';\n'
    )
    page = page.replace('const T=s=>', i18n_inject + 'const T=s=>', 1)

    # Upgrade T() and Tc() and applyStaticLang() to support all 8 languages
    old_t = (
        "const T=s=>LANG==='en'?(EN[s]??s):s;\n"
        "const Tc=(n,zh,one,many)=>LANG==='en'?(n===1?one:many):zh; // 数字量词：n===1 用单数"
    )
    new_t = (
        "const T=s=>{if(LANG==='zh')return s;const d=EXTRA_I18N[LANG];if(d&&s in d)return d[s];if(LANG==='zh-TW')return s;return EN[s]??s;};\n"
        "const Tc=(n,zh,one,many)=>LANG==='zh'||LANG==='zh-TW'?zh:(n===1?one:many); // 数字量词：n===1 用单数"
    )
    if old_t not in page:
        raise ValueError('T/Tc definition not found in console page')
    page = page.replace(old_t, new_t, 1)

    old_static_lang = (
        "  document.documentElement.lang=LANG==='en'?'en':'zh-CN';\n"
        "  try{window.webkit?.messageHandlers?.language?.postMessage(LANG)}catch(e){}\n"
        "  if(LANG!=='en')return;\n"
        "  const skip=n=>n.parentElement&&n.parentElement.closest('script,style,pre,#modal-body');\n"
        "  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode:n=>(n.nodeValue.trim()&&!skip(n))?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT});\n"
        "  const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);\n"
        "  nodes.forEach(n=>{const v=EN[n.nodeValue.trim()];if(v!==undefined)n.nodeValue=v;});\n"
        "  document.querySelectorAll('input[placeholder],textarea[placeholder]').forEach(el=>{const v=EN[el.getAttribute('placeholder')];if(v!==undefined)el.setAttribute('placeholder',v);});\n"
        "  document.querySelectorAll('[title]').forEach(el=>{const v=EN[el.getAttribute('title')];if(v!==undefined)el.setAttribute('title',v);});\n"
        "  document.querySelectorAll('[aria-label]').forEach(el=>{const v=EN[el.getAttribute('aria-label')];if(v!==undefined)el.setAttribute('aria-label',v);});\n"
        "  document.querySelectorAll('option').forEach(el=>{const v=EN[el.textContent.trim()];if(v!==undefined&&el.textContent.trim())el.textContent=v;});"
    )
    new_static_lang = (
        "  const htmlLang={zh:'zh-CN','zh-TW':'zh-TW',en:'en',ja:'ja',ko:'ko',es:'es',fr:'fr',de:'de'}[LANG]||'en';\n"
        "  document.documentElement.lang=htmlLang;\n"
        "  try{window.webkit?.messageHandlers?.language?.postMessage(LANG)}catch(e){}\n"
        "  if(LANG==='zh')return;\n"
        "  const tr=s=>{const v=T(s);return v!==s?v:undefined;};\n"
        "  const skip=n=>n.parentElement&&n.parentElement.closest('script,style,pre,#modal-body');\n"
        "  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode:n=>(n.nodeValue.trim()&&!skip(n))?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT});\n"
        "  const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);\n"
        "  nodes.forEach(n=>{const v=tr(n.nodeValue.trim());if(v!==undefined)n.nodeValue=v;});\n"
        "  document.querySelectorAll('input[placeholder],textarea[placeholder]').forEach(el=>{const v=tr(el.getAttribute('placeholder'));if(v!==undefined)el.setAttribute('placeholder',v);});\n"
        "  document.querySelectorAll('[title]').forEach(el=>{const v=tr(el.getAttribute('title'));if(v!==undefined)el.setAttribute('title',v);});\n"
        "  document.querySelectorAll('[aria-label]').forEach(el=>{const v=tr(el.getAttribute('aria-label'));if(v!==undefined)el.setAttribute('aria-label',v);});\n"
        "  document.querySelectorAll('option').forEach(el=>{const v=tr(el.textContent.trim());if(v!==undefined&&el.textContent.trim())el.textContent=v;});"
    )
    if old_static_lang not in page:
        raise ValueError('applyStaticLang block not found in console page')
    page = page.replace(old_static_lang, new_static_lang, 1)

    # 6. Inject tutorial JS and hook into applyView() and bootTail()
    tour_js = (
        JS.replace('__TOUR_LANG_OPTIONS__', json.dumps(LANG_OPTIONS, ensure_ascii=False))
          .replace('__TOUR_UI__', json.dumps(TOUR_UI, ensure_ascii=False))
          .replace('__MAIN_TOUR__', json.dumps(MAIN_TOUR, ensure_ascii=False))
          .replace('__PAGE_TOURS__', json.dumps(PAGE_TOURS, ensure_ascii=False))
          .replace('__PAGE_TOURS_LOCALIZED__', json.dumps(PAGE_TOURS_LOCALIZED, ensure_ascii=False))
    )
    page = page.replace('const VIEWS=', tour_js + '\nconst VIEWS=', 1)
    page = page.replace('  updatePageGuide(v);\n', '  updatePageGuide(v);\n  maybeStartPageTour(v);\n  syncTourTriggerDot();\n', 1)
    page = page.replace('    uiWired=true;\n', '    uiWired=true;\n    bootOnboarding();\n', 1)
    return page
