"""Lightweight UI internationalization (English / 简体中文 / हिन्दी).

Usage::

    from adaptive_soundscape.core import i18n
    i18n.set_language("zh")
    label.setText(i18n.tr("settings_title"))
"""
from __future__ import annotations

# (code, native display name) — shown as-is in the language selector
SUPPORTED_LANGUAGES: list[tuple[str, str]] = [
    ("en", "English"),
    ("zh", "中文"),
    ("hi", "हिन्दी"),
]

_DEFAULT_LANGUAGE = "en"
_current = _DEFAULT_LANGUAGE

# key -> {language: text}. Keys not present fall back to English, then to the key.
_STRINGS: dict[str, dict[str, str]] = {
    # ── General / nav ────────────────────────────────────────────
    "nav_home": {"en": "Home", "zh": "首页", "hi": "होम"},
    "nav_upload": {"en": "Upload", "zh": "上传", "hi": "अपलोड"},
    "nav_settings": {"en": "Settings", "zh": "设置", "hi": "सेटिंग्स"},
    # ── Home page ────────────────────────────────────────────────
    "home_motto": {
        "en": "Your Focus, Amplified by Sound",
        "zh": "让声音放大你的专注",
        "hi": "आपका फ़ोकस, ध्वनि से प्रवर्धित",
    },
    "home_focus": {"en": "FOCUS", "zh": "专注", "hi": "फ़ोकस"},
    "home_classify": {
        "en": "Confirm Classification",
        "zh": "确认分类",
        "hi": "वर्गीकरण की पुष्टि करें",
    },
    "home_pomodoro_idle": {
        "en": "Start Pomodoro",
        "zh": "开始番茄钟",
        "hi": "पोमोडोरो शुरू करें",
    },
    "home_pomodoro_active": {
        "en": "End Pomodoro",
        "zh": "结束番茄钟",
        "hi": "पोमोडोरो समाप्त करें",
    },
    "home_calibrate_idle": {
        "en": "Calibrate Focus",
        "zh": "校准专注",
        "hi": "फ़ोकस कैलिब्रेट करें",
    },
    "home_calibrate_active": {
        "en": "Cancel Calibration",
        "zh": "取消校准",
        "hi": "कैलिब्रेशन रद्द करें",
    },
    "home_calibrate_tip": {
        "en": "Run a 5–10 minute focused calibration for the current task profile.",
        "zh": "为当前任务配置文件运行 5–10 分钟的专注校准。",
        "hi": "वर्तमान कार्य प्रोफ़ाइल के लिए 5–10 मिनट की फ़ोकस कैलिब्रेशन चलाएँ।",
    },
    "ring_start": {"en": "START", "zh": "开始", "hi": "शुरू करें"},
    "ring_stop": {"en": "STOP", "zh": "停止", "hi": "रोकें"},
    "mood_deep_focus": {"en": "Deep Focus", "zh": "深度专注", "hi": "गहन फ़ोकस"},
    "mood_in_the_zone": {"en": "In the Zone", "zh": "进入状态", "hi": "ज़ोन में"},
    "mood_light_focus": {"en": "Light Focus", "zh": "轻度专注", "hi": "हल्का फ़ोकस"},
    "mood_wandering": {"en": "Wandering", "zh": "思绪游走", "hi": "भटकना"},
    "mood_distracted": {"en": "Distracted", "zh": "分心", "hi": "विचलित"},
    # ── Settings page ────────────────────────────────────────────
    "settings_title": {"en": "Settings", "zh": "设置", "hi": "सेटिंग्स"},
    "section_about": {"en": "About", "zh": "关于", "hi": "परिचय"},
    "about_text": {
        "en": (
            "Adaptive Cognitive Soundscape is an intelligent audio companion that "
            "monitors your workspace activity in real time — recognising whether you "
            "are coding, reading, designing, or distracted — and dynamically adjusts "
            "ambient background audio to sustain deep focus and reduce cognitive drift. "
            "It runs locally on your machine, works with your own sound libraries, "
            "and requires no internet connection."
        ),
        "zh": (
            "自适应认知声景是一款智能音频伴侣，实时监测你的工作区活动——识别你是"
            "在编程、阅读、设计还是分心——并动态调整环境背景音，帮助你保持深度专注、"
            "减少认知漂移。它完全在本机运行，使用你自己的声音库，无需联网。"
        ),
        "hi": (
            "एडेप्टिव कॉग्निटिव साउंडस्केप एक बुद्धिमान ऑडियो साथी है जो आपकी "
            "वर्कस्पेस गतिविधि पर रीयल-टाइम निगरानी करता है — चाहे आप कोडिंग, पढ़ाई, "
            "डिज़ाइन या विचलित अवस्था में हों — और गहन फ़ोकस बनाए रखने के लिए परिवेशी "
            "पृष्ठभूमि ऑडियो को गतिशील रूप से समायोजित करता है। यह आपके कंप्यूटर पर "
            "स्थानीय रूप से चलता है, आपकी स्वयं की ध्वनि लाइब्रेरी के साथ काम करता है, "
            "और इसे इंटरनेट कनेक्शन की आवश्यकता नहीं होती।"
        ),
    },
    "section_appearance": {"en": "Appearance", "zh": "外观", "hi": "दिखावट"},
    "dark_mode": {"en": "Dark Mode", "zh": "深色模式", "hi": "डार्क मोड"},
    "language_label": {"en": "Language", "zh": "语言", "hi": "भाषा"},
    "wave_label": {
        "en": "Waveform Smoothness",
        "zh": "波形平滑度",
        "hi": "वेवफ़ॉर्म स्मूथनेस",
    },
    "wave_hint": {
        "en": "Lower  →  more detailed ring ·  Higher  →  softer oval glow",
        "zh": "越低 → 圆环细节越丰富 · 越高 → 光晕越柔和",
        "hi": "कम → अधिक विस्तृत रिंग · अधिक → नरम अंडाकार चमक",
    },
    "aurora_label": {
        "en": "Aurora Brightness Gain",
        "zh": "极光亮度增益",
        "hi": "ऑरोरा ब्राइटनेस गेन",
    },
    "aurora_hint": {
        "en": "How strongly rising focus brightens the flowing lights behind the glass",
        "zh": "专注度上升时，玻璃背后的流动光斑会增强多少",
        "hi": "फ़ोकस बढ़ने पर कांच के पीछे बहती रोशनी कितनी तेज़ होती है",
    },
    "section_audio": {"en": "Audio", "zh": "音频", "hi": "ऑडियो"},
    "volume_label": {"en": "Master Volume", "zh": "主音量", "hi": "मुख्य वॉल्यूम"},
    "muffle_label": {
        "en": "Muffling Strength",
        "zh": "低音抑制强度",
        "hi": "मफलिंग ताकत",
    },
    "muffle_hint": {
        "en": "How strongly low focus muffles music (low-pass). Breaks use a stronger muffle.",
        "zh": "低专注度时对音乐的低通抑制强度。休息时会用更强的抑制。",
        "hi": "कम फ़ोकस पर संगीत को कितनी तेज़ी से मफल किया जाए (लो-पास)। ब्रेक में अधिक मफलिंग होती है।",
    },
    "section_cognitive": {"en": "Cognitive", "zh": "认知", "hi": "संज्ञानात्मक"},
    "threshold_label": {
        "en": "Concentration Threshold",
        "zh": "专注阈值",
        "hi": "एकाग्रता सीमा",
    },
    "threshold_hint": {
        "en": "Higher  →  more easily detected as distracted",
        "zh": "越高 → 越容易被判定为分心",
        "hi": "अधिक → अधिक आसानी से विचलित पहचाना जाता है",
    },
    "session_hint": {
        "en": (
            "Start Pomodoro and Calibrate Focus from the home page. "
            "The first 5 minutes of each Pomodoro work block also calibrate that session."
        ),
        "zh": (
            "从首页开始番茄钟和专注校准。"
            "每个番茄钟工作时段的头 5 分钟也会对该时段进行校准。"
        ),
        "hi": (
            "होम पेज से पोमोडोरो शुरू करें और फ़ोकस कैलिब्रेट करें। "
            "प्रत्येक पोमोडोरो कार्य ब्लॉक के पहले 5 मिनट उस सत्र को भी कैलिब्रेट करते हैं।"
        ),
    },
    "probe_btn": {
        "en": "Run Attention Probe",
        "zh": "运行注意力测试",
        "hi": "ध्यान परीक्षण चलाएँ",
    },
    "probes_label": {
        "en": "Attention Probes",
        "zh": "注意力测试",
        "hi": "ध्यान परीक्षण",
    },
    "privacy_hint": {
        "en": (
            "Focus data is local-only (categories & aggregates). No titles, keystrokes, "
            "clipboard, mic, or camera are stored."
        ),
        "zh": "专注数据仅保存在本地（类别与聚合数据）。不存储标题、按键、剪贴板、麦克风或摄像头内容。",
        "hi": "फ़ोकस डेटा केवल स्थानीय है (श्रेणियाँ और समग्र)। कोई शीर्षक, कीस्ट्रोक, क्लिपबोर्ड, माइक या कैमरा संग्रहीत नहीं होते।",
    },
    "section_personalization": {
        "en": "Personalization",
        "zh": "个性化",
        "hi": "निजीकरण",
    },
    "theme_label": {"en": "Main Theme", "zh": "主主题", "hi": "मुख्य थीम"},
    "categories_label": {
        "en": "Window Categories",
        "zh": "窗口分类",
        "hi": "विंडो श्रेणियाँ",
    },
    "manage_btn": {"en": "Manage…", "zh": "管理…", "hi": "प्रबंधित करें…"},
    "manage_tip": {
        "en": "Edit saved process names and title keywords used for window classification.",
        "zh": "编辑用于窗口分类的已保存进程名与标题关键词。",
        "hi": "विंडो वर्गीकरण के लिए सहेजे गए प्रक्रिया नाम और शीर्षक कीवर्ड संपादित करें।",
    },
    "categories_hint": {
        "en": "Choices from the unknown-window panel are saved here and kept after restart.",
        "zh": "未知窗口面板中的选择会保存在这里，并在重启后保留。",
        "hi": "अज्ञात-विंडो पैनल के विकल्प यहाँ सहेजे जाते हैं और पुनः आरंभ के बाद बने रहते हैं।",
    },
    "export_btn": {
        "en": "Export Focus Data",
        "zh": "导出专注数据",
        "hi": "फ़ोकस डेटा निर्यात करें",
    },
    "delete_btn": {
        "en": "Delete Focus Data",
        "zh": "删除专注数据",
        "hi": "फ़ोकस डेटा हटाएँ",
    },
    "section_status_colors": {
        "en": "Status Colors",
        "zh": "状态颜色",
        "hi": "स्थिति रंग",
    },
    "pick_btn": {"en": "Pick…", "zh": "选择…", "hi": "चुनें…"},
    "pick_color_for": {
        "en": "Pick colour for {}",
        "zh": "为 {} 选择颜色",
        "hi": "{} के लिए रंग चुनें",
    },
    "home_btn": {"en": "Return to Home", "zh": "返回首页", "hi": "होम पर लौटें"},
    "reset_btn": {"en": "Reset Settings", "zh": "重置设置", "hi": "सेटिंग्स रीसेट करें"},
    "quit_btn": {"en": "Quit App", "zh": "退出应用", "hi": "ऐप बंद करें"},
    "window_title": {
        "en": "Adaptive Cognitive Soundscape",
        "zh": "自适应认知声景",
        "hi": "एडेप्टिव कॉग्निटिव साउंडस्केप",
    },
    # ── Work-context theme names ─────────────────────────────────
    "theme_programming": {"en": "Coding", "zh": "编程", "hi": "कोडिंग"},
    "theme_team_workflow": {"en": "Collaborating", "zh": "协作", "hi": "सहयोग"},
    "theme_reading_writing": {
        "en": "Reading & Writing",
        "zh": "阅读与写作",
        "hi": "पढ़ना और लिखना",
    },
    "theme_scientific": {"en": "Research", "zh": "研究", "hi": "अनुसंधान"},
    "theme_creative_design": {"en": "Creating", "zh": "创作", "hi": "निर्माण"},
    "theme_distraction": {"en": "Distracted", "zh": "分心", "hi": "विचलित"},
    "theme_unknown": {"en": "Neutral", "zh": "中性", "hi": "तटस्थ"},
    # ── Cognitive-status display names ───────────────────────────
    "status_programming": {"en": "Deep Code", "zh": "深度编程", "hi": "गहन कोडिंग"},
    "status_team_workflow": {"en": "Collaborative", "zh": "协作", "hi": "सहयोगात्मक"},
    "status_reading_writing": {"en": "Quiet Study", "zh": "安静学习", "hi": "शांत अध्ययन"},
    "status_scientific": {"en": "Lab Focus", "zh": "研究专注", "hi": "प्रयोगशाला फ़ोकस"},
    "status_creative_design": {"en": "Creative Flow", "zh": "创意流动", "hi": "रचनात्मक प्रवाह"},
    "status_distraction": {"en": "Recovery", "zh": "恢复", "hi": "पुनर्प्राप्ति"},
    "status_unknown": {"en": "Neutral", "zh": "中性", "hi": "तटस्थ"},
    # ── Upload page ──────────────────────────────────────────────
    "upload_title": {
        "en": "Customize Soundtracks",
        "zh": "定制音轨",
        "hi": "साउंडट्रैक अनुकूलित करें",
    },
    "advanced_btn": {"en": "Advanced…", "zh": "高级…", "hi": "उन्नत…"},
    "advanced_tip": {
        "en": "Open full album / stem / intensity manager",
        "zh": "打开完整的专辑 / 音轨 / 强度管理器",
        "hi": "पूर्ण एल्बम / स्टेम / तीव्रता प्रबंधक खोलें",
    },
    "upload_hint": {
        "en": "Drop an audio file here\nor click to browse  (.wav / .mp3)",
        "zh": "将音频文件拖到此处\n或点击浏览（.wav / .mp3）",
        "hi": "ऑडियो फ़ाइल यहाँ छोड़ें\nया ब्राउज़ करने के लिए क्लिक करें  (.wav / .mp3)",
    },
    "swap_btn": {"en": "SWAP", "zh": "更换", "hi": "बदलें"},
    "swap_tip": {
        "en": "Add staged file as a new song family (auto stem-separates)",
        "zh": "将暂存文件添加为新歌曲族（自动分离音轨）",
        "hi": "स्टेज की गई फ़ाइल को नए गीत परिवार के रूप में जोड़ें (स्वचालित स्टेम पृथक्करण)",
    },
    "ai_layers_btn": {
        "en": "Generate AI Layers",
        "zh": "生成 AI 分层",
        "hi": "AI परतें उत्पन्न करें",
    },
    "no_track_label": {
        "en": "No song family loaded",
        "zh": "尚未加载歌曲族",
        "hi": "कोई गीत परिवार लोड नहीं",
    },
    "song_count": {
        "en": "{n} song(s): {names}",
        "zh": "{n} 首歌曲：{names}",
        "hi": "{n} गाने: {names}",
    },
    "current_track": {
        "en": "Current:  {name}",
        "zh": "当前：{name}",
        "hi": "वर्तमान: {name}",
    },
}

# WorkContext value (str) -> translation key
THEME_TR_KEYS: dict[str, str] = {
    "programming": "theme_programming",
    "team_workflow": "theme_team_workflow",
    "reading_writing": "theme_reading_writing",
    "scientific": "theme_scientific",
    "creative_design": "theme_creative_design",
    "distraction": "theme_distraction",
    "unknown": "theme_unknown",
}

# Cognitive status profile id -> translation key
STATUS_TR_KEYS: dict[str, str] = {
    "programming": "status_programming",
    "team_workflow": "status_team_workflow",
    "reading_writing": "status_reading_writing",
    "scientific": "status_scientific",
    "creative_design": "status_creative_design",
    "distraction": "status_distraction",
    "unknown": "status_unknown",
}


def set_language(code: str) -> None:
    """Set the active UI language (must be a supported code, else English)."""
    global _current
    if code not in (c for c, _ in SUPPORTED_LANGUAGES):
        code = _DEFAULT_LANGUAGE
    _current = code


def get_language() -> str:
    return _current


def tr(key: str, fallback: str | None = None) -> str:
    """Return the localized text for *key* (falls back to English, then key)."""
    entry = _STRINGS.get(key)
    if not entry:
        return fallback if fallback is not None else key
    return entry.get(_current) or entry.get(_DEFAULT_LANGUAGE) or (fallback if fallback is not None else key)


def theme_label(context_value: str) -> str:
    """Localized display name for a WorkContext string value."""
    key = THEME_TR_KEYS.get(context_value)
    if key:
        return tr(key)
    return context_value.title()


def status_label(profile_id: str) -> str:
    """Localized display name for a cognitive-status profile id."""
    key = STATUS_TR_KEYS.get(profile_id)
    if key:
        return tr(key)
    return profile_id
