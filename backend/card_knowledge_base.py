"""
TCGE Card Intelligence System 2.0 - 卡牌視覺特徵知識庫
======================================================
這個知識庫包含了各個 TCG 遊戲的卡牌視覺特徵定義，
用於圖像識別時判斷卡牌所屬遊戲和卡牌屬性。

支援遊戲:
- OP: One Piece Card Game (航海王卡牌遊戲)
- UA: Union Arena (聯合競技場)
- VG: Cardfight!! Vanguard (卡片戰鬥先導者)
- DM: Duel Masters (決鬥大師)
"""

# ============================================================
# ONE PIECE CARD GAME (OP) 知識庫
# ============================================================
OP_KNOWLEDGE = {
    "game_name": "One Piece Card Game",
    "game_code": "OP",
    "manufacturer": "Bandai",
    
    # 卡號格式
    "card_number_patterns": [
        r"OP(\d{2})-(\d{3})",           # OP01-001 ~ OP14-119
        r"ST(\d{2})-(\d{3})",           # ST01-001 (起始牌組)
        r"EB(\d{2})-(\d{3})",           # EB01-001 (擴充包)
        r"POP(\d{2})-(\d{3})",          # 促銷卡
        r"P-(\d{3})",                    # 促銷卡
    ],
    
    # 卡牌顏色 (邊框顏色)
    "colors": {
        "赤": {  # 紅色
            "name_cn": "紅",
            "name_jp": "赤",
            "hsv_ranges": [
                {"h_min": 0, "h_max": 10, "s_min": 100, "s_max": 255, "v_min": 100, "v_max": 255},
                {"h_min": 160, "h_max": 180, "s_min": 100, "s_max": 255, "v_min": 100, "v_max": 255},
            ],
            "rgb_sample": (220, 50, 50),
            "series": ["OP01", "OP02", "OP04", "OP06", "OP07", "OP09", "OP10", "OP12", "OP13"],
        },
        "青": {  # 藍色
            "name_cn": "藍",
            "name_jp": "青",
            "hsv_ranges": [
                {"h_min": 100, "h_max": 130, "s_min": 100, "s_max": 255, "v_min": 100, "v_max": 255},
            ],
            "rgb_sample": (50, 100, 220),
            "series": ["OP01", "OP02", "OP03", "OP05", "OP07", "OP08", "OP10", "OP11", "OP13", "OP14"],
        },
        "緑": {  # 綠色 (包含青綠/綠松石)
            "name_cn": "綠",
            "name_jp": "緑",
            "hsv_ranges": [
                {"h_min": 35, "h_max": 85, "s_min": 80, "s_max": 255, "v_min": 80, "v_max": 255},   # 純綠
                {"h_min": 75, "h_max": 100, "s_min": 80, "s_max": 255, "v_min": 80, "v_max": 255},  # 青綠
            ],
            "rgb_sample": (50, 180, 120),
            "series": ["OP01", "OP02", "OP03", "OP04", "OP06", "OP08", "OP09", "OP11", "OP12", "OP14"],
        },
        "紫": {  # 紫色
            "name_cn": "紫",
            "name_jp": "紫",
            "hsv_ranges": [
                {"h_min": 125, "h_max": 160, "s_min": 80, "s_max": 255, "v_min": 60, "v_max": 255},
            ],
            "rgb_sample": (150, 50, 180),
            "series": ["OP01", "OP02", "OP04", "OP05", "OP06", "OP08", "OP09", "OP11", "OP12", "OP13"],
        },
        "黄": {  # 黃色
            "name_cn": "黃",
            "name_jp": "黄",
            "hsv_ranges": [
                {"h_min": 15, "h_max": 35, "s_min": 100, "s_max": 255, "v_min": 150, "v_max": 255},
            ],
            "rgb_sample": (230, 200, 50),
            "series": ["OP04", "OP05", "OP06", "OP07", "OP08", "OP10", "OP11", "OP13", "OP14"],
        },
        "黒": {  # 黑色
            "name_cn": "黑",
            "name_jp": "黒",
            "hsv_ranges": [
                {"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 80, "v_min": 0, "v_max": 60},
            ],
            "rgb_sample": (40, 40, 40),
            "series": ["OP03", "OP05", "OP07", "OP09", "OP10", "OP12", "OP13", "OP14"],
        },
    },
    
    # 卡牌類型
    "card_types": {
        "LEADER": {
            "name_jp": "リーダー",
            "name_cn": "隊長",
            "features": ["紅色卡背", "在隊長區域使用"],
            "power_range": [4000, 6000],
        },
        "CHARACTER": {
            "name_jp": "キャラクター",
            "name_cn": "角色",
            "features": ["藍色卡背", "有費用和力量值"],
            "power_range": [1000, 12000],
            "cost_range": [0, 10],
        },
        "EVENT": {
            "name_jp": "イベント",
            "name_cn": "事件",
            "features": ["一次性效果"],
            "cost_range": [0, 10],
        },
        "STAGE": {
            "name_jp": "ステージ",
            "name_cn": "舞台",
            "features": ["持續效果", "每個玩家只能放一張"],
            "cost_range": [1, 5],
        },
        "DON": {
            "name_jp": "ドン!!",
            "name_cn": "DON!!",
            "features": ["白色卡背", "資源卡"],
        },
    },
    
    # 力量值 (Power)
    "power_values": [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000],
    
    # 費用值 (Cost) - 左上角
    "cost_values": list(range(0, 11)),  # 0-10
    
    # Counter 值 - 底部
    "counter_values": [0, 1000, 2000],
    
    # 稀有度
    "rarities": {
        "L": "Leader (隊長)",
        "C": "Common (普通)",
        "UC": "Uncommon (非普通)",
        "R": "Rare (稀有)",
        "SR": "Super Rare (超稀有)",
        "SEC": "Secret Rare (秘密稀有)",
        "SP": "Special (特別)",
        "P": "Promo (促銷)",
        "DON": "DON!! Card",
    },
    
    # 卡牌布局 (用於視覺定位)
    "layout": {
        "cost_position": {"x": 0.05, "y": 0.02, "w": 0.12, "h": 0.10},  # 左上角
        "power_position": {"x": 0.60, "y": 0.02, "w": 0.35, "h": 0.10},  # 右上角
        "name_position": {"x": 0.10, "y": 0.78, "w": 0.80, "h": 0.08},  # 底部名稱區
        "card_number_position": {"x": 0.70, "y": 0.92, "w": 0.25, "h": 0.06},  # 右下角
        "attribute_position": {"x": 0.80, "y": 0.02, "w": 0.15, "h": 0.10},  # 右上屬性圖標
        "border_width": 0.08,  # 邊框寬度比例
        "aspect_ratio": 0.715,  # 寬/高比例 (約63mm x 88mm)
    },
    
    # 屬性圖標 (右上角)
    "attributes": {
        "斬": {"color": "red", "icon": "slash"},
        "打": {"color": "blue", "icon": "strike"},
        "射": {"color": "green", "icon": "ranged"},
        "知": {"color": "purple", "icon": "wisdom"},
        "特": {"color": "yellow", "icon": "special"},
    },
    
    # 常見角色名對照表
    "character_names": {
        # 草帽海賊團
        "ルフィ": ["LUFFY", "路飛", "魯夫"],
        "ゾロ": ["ZORO", "索隆", "索羅"],
        "ナミ": ["NAMI", "娜美"],
        "ウソップ": ["USOPP", "騙人布", "烏索普"],
        "サンジ": ["SANJI", "山治", "香吉士"],
        "チョッパー": ["CHOPPER", "喬巴"],
        "ロビン": ["ROBIN", "羅賓", "妮可·羅賓"],
        "フランキー": ["FRANKY", "弗蘭奇", "佛朗乞"],
        "ブルック": ["BROOK", "布魯克"],
        "ジンベエ": ["JINBE", "甚平", "吉貝爾"],
        
        # 七武海/強敵
        "ミホーク": ["MIHAWK", "鷹眼", "密佛格"],
        "ジュラキュール": ["DRACULE", "朱洛基爾"],
        "クロコダイル": ["CROCODILE", "克洛克達爾", "沙鱷"],
        "ハンコック": ["HANCOCK", "女帝", "漢考克", "波雅·漢考克"],
        "ドフラミンゴ": ["DOFLAMINGO", "多佛朗明哥", "唐乔克·多弗朗明戈"],
        "ロー": ["LAW", "羅", "特拉法爾加·羅"],
        
        # 四皇
        "シャンクス": ["SHANKS", "紅髮", "香克斯"],
        "カイドウ": ["KAIDO", "凱多", "百獸凱多"],
        "ビッグ・マム": ["BIG MOM", "大媽", "夏洛特·玲玲"],
        "黒ひげ": ["BLACKBEARD", "黑鬍子", "馬歇爾·D·蒂奇"],
        "白ひげ": ["WHITEBEARD", "白鬍子", "愛德華·乌鍍哥"],
        
        # 其他
        "エース": ["ACE", "艾斯", "波特卡斯·D·艾斯"],
        "サボ": ["SABO", "薩波"],
        "ヤマト": ["YAMATO", "大和"],
        "ロジャー": ["ROGER", "羅傑", "哥爾·D·羅傑"],
    },
}


# ============================================================
# UNION ARENA (UA) 知識庫
# ============================================================
UA_KNOWLEDGE = {
    "game_name": "Union Arena",
    "game_code": "UA",
    "manufacturer": "Bandai",
    
    # 卡號格式
    "card_number_patterns": [
        r"UA(\d{2})BT/([A-Z]{3})-(\d)-(\d{3})",    # UA01BT/JJK-1-001
        r"UA(\d{2})BT-(\d{3})",                     # UA01BT-001
        r"EX(\d{2})BT/([A-Z]{3})-(\d)-(\d{3})",    # EX01BT/HTR-1-001
    ],
    
    # 卡牌顏色
    "colors": {
        "赤": {
            "name_cn": "紅",
            "name_jp": "赤",
            "hsv_ranges": [
                {"h_min": 0, "h_max": 10, "s_min": 100, "s_max": 255, "v_min": 100, "v_max": 255},
                {"h_min": 160, "h_max": 180, "s_min": 100, "s_max": 255, "v_min": 100, "v_max": 255},
            ],
        },
        "青": {
            "name_cn": "藍",
            "name_jp": "青",
            "hsv_ranges": [
                {"h_min": 100, "h_max": 130, "s_min": 100, "s_max": 255, "v_min": 100, "v_max": 255},
            ],
        },
        "緑": {
            "name_cn": "綠",
            "name_jp": "緑",
            "hsv_ranges": [
                {"h_min": 35, "h_max": 85, "s_min": 80, "s_max": 255, "v_min": 80, "v_max": 255},
            ],
        },
        "黄": {
            "name_cn": "黃",
            "name_jp": "黄",
            "hsv_ranges": [
                {"h_min": 15, "h_max": 35, "s_min": 100, "s_max": 255, "v_min": 150, "v_max": 255},
            ],
        },
        "紫": {
            "name_cn": "紫",
            "name_jp": "紫",
            "hsv_ranges": [
                {"h_min": 125, "h_max": 160, "s_min": 80, "s_max": 255, "v_min": 60, "v_max": 255},
            ],
        },
        "白": {
            "name_cn": "白",
            "name_jp": "白",
            "hsv_ranges": [
                {"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 30, "v_min": 200, "v_max": 255},
            ],
        },
    },
    
    # 卡牌類型
    "card_types": {
        "CHARACTER": {"name_jp": "キャラクター", "name_cn": "角色"},
        "EVENT": {"name_jp": "イベント", "name_cn": "事件"},
        "FIELD": {"name_jp": "フィールド", "name_cn": "場地"},
        "ACTION_POINT": {"name_jp": "アクションポイント", "name_cn": "行動點"},
    },
    
    # BP值 (Battle Point)
    "bp_values": list(range(1000, 10001, 500)),  # 1000-10000, 每500
    
    # 需要的能量
    "energy_values": list(range(0, 8)),  # 0-7
    
    # 稀有度
    "rarities": {
        "C": "Common",
        "UC": "Uncommon", 
        "R": "Rare",
        "SR": "Super Rare",
        "SR★★★": "Super Rare Parallel",
        "AP": "Action Point",
    },
    
    # 合作作品列表
    "franchises": {
        "JJK": "呪術廻戦 (Jujutsu Kaisen)",
        "HTR": "HUNTER×HUNTER",
        "TLR": "To LOVEる",
        "NRT": "NARUTO",
        "BSD": "文豪ストレイドッグス",
        "BLC": "BLEACH",
        "MHA": "僕のヒーローアカデミア",
        "SAO": "Sword Art Online",
        "REZ": "Re:ゼロ",
        "GNT": "銀魂",
        "CCS": "Cardcaptor Sakura",
    },
    
    # 卡牌布局
    "layout": {
        "bp_position": {"x": 0.05, "y": 0.02, "w": 0.15, "h": 0.10},
        "energy_position": {"x": 0.05, "y": 0.12, "w": 0.10, "h": 0.08},
        "name_position": {"x": 0.10, "y": 0.75, "w": 0.80, "h": 0.10},
        "card_number_position": {"x": 0.60, "y": 0.92, "w": 0.35, "h": 0.06},
        "aspect_ratio": 0.715,
    },
}


# ============================================================
# CARDFIGHT!! VANGUARD (VG) 知識庫
# ============================================================
VG_KNOWLEDGE = {
    "game_name": "Cardfight!! Vanguard",
    "game_code": "VG",
    "manufacturer": "Bushiroad",
    
    # 卡號格式
    "card_number_patterns": [
        r"D-([A-Z]{2,3})(\d{2})/(\d{3})",          # D-BT01/001
        r"DZ-([A-Z]{3})(\d{2})/(\d{3})",           # DZ-LBT01/001
        r"D-PR/(\d{3})",                            # D-PR/001 (促銷)
        r"V-([A-Z]{2,3})(\d{2})/(\d{3})",          # V-BT01/001
        r"G-([A-Z]{2,3})(\d{2})/(\d{3})",          # G-BT01/001
    ],
    
    # 國家/陣營
    "nations": {
        "ケテルサンクチュアリ": {"name_en": "Keter Sanctuary", "color": "yellow"},
        "ドラゴンエンパイア": {"name_en": "Dragon Empire", "color": "red"},
        "ダークステイツ": {"name_en": "Dark States", "color": "purple"},
        "ブラントゲート": {"name_en": "Brandt Gate", "color": "blue"},
        "ストイケイア": {"name_en": "Stoicheia", "color": "green"},
        "リリカルモナステリオ": {"name_en": "Lyrical Monasterio", "color": "pink"},
    },
    
    # 等級 (Grade)
    "grades": [0, 1, 2, 3, 4, 5],
    
    # 力量值 (Power)
    "power_values": list(range(3000, 15001, 1000)),  # 3000-15000
    
    # 護盾值 (Shield)
    "shield_values": [0, 5000, 10000, 15000, 20000],
    
    # 卡牌類型
    "card_types": {
        "UNIT": {"name_jp": "ユニット", "name_cn": "單位"},
        "TRIGGER": {"name_jp": "トリガー", "name_cn": "觸發"},
        "ORDER": {"name_jp": "オーダー", "name_cn": "命令"},
        "RIDE_LINE": {"name_jp": "ライドライン", "name_cn": "騎乘路線"},
    },
    
    # 觸發類型
    "trigger_types": {
        "CRITICAL": {"icon": "★", "color": "yellow"},
        "DRAW": {"icon": "♠", "color": "green"},
        "FRONT": {"icon": "◆", "color": "purple"},
        "HEAL": {"icon": "♥", "color": "green"},
        "OVER": {"icon": "∞", "color": "gold"},
    },
    
    # 稀有度
    "rarities": {
        "C": "Common",
        "R": "Rare",
        "RR": "Double Rare",
        "RRR": "Triple Rare",
        "VR": "Vanguard Rare",
        "SP": "Special",
        "OR": "Origin Rare",
        "DSR": "Destiny Rare",
        "USR": "Ultimate Stride Rare",
        "FFR": "Full Frame Rare",
        "SR": "Special Rare",
    },
    
    # 卡牌布局
    "layout": {
        "grade_position": {"x": 0.03, "y": 0.02, "w": 0.12, "h": 0.12},
        "power_position": {"x": 0.03, "y": 0.85, "w": 0.20, "h": 0.10},
        "shield_position": {"x": 0.80, "y": 0.85, "w": 0.15, "h": 0.10},
        "name_position": {"x": 0.15, "y": 0.75, "w": 0.70, "h": 0.08},
        "card_number_position": {"x": 0.60, "y": 0.02, "w": 0.35, "h": 0.06},
        "trigger_position": {"x": 0.85, "y": 0.02, "w": 0.12, "h": 0.12},
        "aspect_ratio": 0.715,
    },
}


# ============================================================
# DUEL MASTERS (DM) 知識庫
# ============================================================
DM_KNOWLEDGE = {
    "game_name": "Duel Masters",
    "game_code": "DM",
    "manufacturer": "Takara Tomy",
    
    # 卡號格式
    "card_number_patterns": [
        r"DM(\d{2})-(\d{1,3})",                     # DM01-001
        r"DMR-(\d{2})/(\d{1,3})",                   # DMR-01/001
        r"DMRP-(\d{2})/(\d{1,3})",                  # DMRP-01/001
        r"RP(\d{2})([A-Z]{1,2})(\d{1,2})/([A-Z\d]+)",  # RP20KM3/KM5
        r"(\d{2})BD(\d{1,2})/(\d{1,2})",            # 23BD21/16
    ],
    
    # 文明/顏色
    "civilizations": {
        "光": {
            "name_en": "Light",
            "color": "yellow",
            "hsv_ranges": [{"h_min": 20, "h_max": 40, "s_min": 100, "s_max": 255, "v_min": 200, "v_max": 255}],
        },
        "水": {
            "name_en": "Water",
            "color": "blue",
            "hsv_ranges": [{"h_min": 100, "h_max": 130, "s_min": 100, "s_max": 255, "v_min": 100, "v_max": 255}],
        },
        "闇": {
            "name_en": "Darkness",
            "color": "black",
            "hsv_ranges": [{"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 80, "v_min": 0, "v_max": 60}],
        },
        "火": {
            "name_en": "Fire",
            "color": "red",
            "hsv_ranges": [{"h_min": 0, "h_max": 15, "s_min": 150, "s_max": 255, "v_min": 150, "v_max": 255}],
        },
        "自然": {
            "name_en": "Nature",
            "color": "green",
            "hsv_ranges": [{"h_min": 35, "h_max": 85, "s_min": 80, "s_max": 255, "v_min": 80, "v_max": 255}],
        },
        "ゼロ": {
            "name_en": "Zero",
            "color": "colorless",
            "hsv_ranges": [{"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 30, "v_min": 150, "v_max": 255}],
        },
    },
    
    # 卡牌類型
    "card_types": {
        "CREATURE": {"name_jp": "クリーチャー", "name_cn": "生物"},
        "SPELL": {"name_jp": "呪文", "name_cn": "咒文"},
        "CROSS_GEAR": {"name_jp": "クロスギア", "name_cn": "十字齒輪"},
        "EVOLUTION": {"name_jp": "進化クリーチャー", "name_cn": "進化生物"},
        "CASTLE": {"name_jp": "城", "name_cn": "城"},
        "WEAPON": {"name_jp": "ウエポン", "name_cn": "武器"},
        "FORTRESS": {"name_jp": "フォートレス", "name_cn": "要塞"},
        "FIELD": {"name_jp": "フィールド", "name_cn": "場地"},
        "GACHARANGE": {"name_jp": "GRクリーチャー", "name_cn": "GR生物"},
        "OREGA_AURA": {"name_jp": "オレガオーラ", "name_cn": "Orega光環"},
        "STAR_EVOLUTION": {"name_jp": "スター進化", "name_cn": "星進化"},
    },
    
    # 魔力消耗 (Mana Cost)
    "mana_costs": list(range(1, 16)),  # 1-15
    
    # 力量值 (Power)
    "power_values": list(range(1000, 20001, 500)),  # 1000-20000
    
    # 稀有度
    "rarities": {
        "C": "Common",
        "UC": "Uncommon",
        "R": "Rare",
        "VR": "Very Rare",
        "SR": "Super Rare",
        "MR": "Master Rare",
        "KM": "King Master",
        "SE": "Secret",
        "OR": "Over Rare",
        "LEG": "Legend",
    },
    
    # 卡牌布局
    "layout": {
        "mana_position": {"x": 0.03, "y": 0.02, "w": 0.15, "h": 0.12},
        "power_position": {"x": 0.03, "y": 0.85, "w": 0.25, "h": 0.10},
        "name_position": {"x": 0.10, "y": 0.70, "w": 0.80, "h": 0.10},
        "civilization_frame": {"border_width": 0.05},
        "aspect_ratio": 0.715,
    },
}


# ============================================================
# 遊戲識別函數
# ============================================================
def identify_game_from_card_number(card_number: str) -> str:
    """根據卡號識別所屬遊戲"""
    import re
    
    card_number = card_number.upper().strip()
    
    # OP 格式
    if re.match(r'^(OP|ST|EB|POP|P-)\d', card_number):
        return "OP"
    
    # UA 格式
    if re.match(r'^(UA|EX)\d{2}BT', card_number):
        return "UA"
    
    # VG 格式
    if re.match(r'^(D-|DZ-|V-|G-|CP/)', card_number):
        return "VG"
    
    # DM 格式
    if re.match(r'^(DM|DMR|DMRP|RP\d|BD)', card_number):
        return "DM"
    
    return "UNKNOWN"


def get_game_knowledge(game_code: str) -> dict:
    """取得指定遊戲的知識庫"""
    knowledge_map = {
        "OP": OP_KNOWLEDGE,
        "UA": UA_KNOWLEDGE,
        "VG": VG_KNOWLEDGE,
        "DM": DM_KNOWLEDGE,
    }
    return knowledge_map.get(game_code.upper(), {})


def get_all_card_number_patterns() -> list:
    """取得所有遊戲的卡號正則模式"""
    patterns = []
    for knowledge in [OP_KNOWLEDGE, UA_KNOWLEDGE, VG_KNOWLEDGE, DM_KNOWLEDGE]:
        patterns.extend(knowledge.get("card_number_patterns", []))
    return patterns


def get_color_by_name(game_code: str, color_name: str) -> dict:
    """根據顏色名稱取得顏色定義"""
    knowledge = get_game_knowledge(game_code)
    colors = knowledge.get("colors", {})
    return colors.get(color_name, {})


# ============================================================
# 視覺特徵提取輔助函數
# ============================================================
def get_layout_region(game_code: str, region_name: str, img_width: int, img_height: int) -> tuple:
    """根據遊戲和區域名稱取得圖像區域座標"""
    knowledge = get_game_knowledge(game_code)
    layout = knowledge.get("layout", {})
    region = layout.get(f"{region_name}_position", {})
    
    if not region:
        return None
    
    x = int(region.get("x", 0) * img_width)
    y = int(region.get("y", 0) * img_height)
    w = int(region.get("w", 0.1) * img_width)
    h = int(region.get("h", 0.1) * img_height)
    
    return (x, y, x + w, y + h)


def analyze_card_aspect_ratio(width: int, height: int) -> str:
    """分析卡牌長寬比來判斷可能的遊戲"""
    ratio = width / height
    
    # 標準 TCG 卡牌約 0.715 (63mm x 88mm)
    if 0.65 < ratio < 0.75:
        return "STANDARD_TCG"  # 可能是 OP, UA, VG, DM
    elif 0.55 < ratio < 0.65:
        return "PORTRAIT_TCG"
    elif ratio > 0.9:
        return "LANDSCAPE_TCG"
    else:
        return "UNKNOWN"
