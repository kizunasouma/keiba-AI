"""
JV-Dataレコードパーサー
JV-Linkから返るShift-JIS固定長テキストを辞書に変換する

【フィールド位置は JV-Data仕様書 Ver.4.9.0.1 準拠】
  仕様書は1始まり（spec pos）、本コードは0始まり（Python index = spec pos - 1）。

【共通ヘッダー】
  pos 0-1  : レコード種別ID ("RA", "SE", "UM" 等)
  pos 2    : データ区分 (1バイト)
  pos 3-10 : 作成年月日 YYYYMMDD (8バイト)
  pos 11-  : レコード固有フィールド（開催年4+開催月日4=race_date 8バイト等）
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class Field:
    """固定長フィールドの定義"""
    name: str
    start: int   # 0始まりバイト位置（Python index）
    length: int  # バイト長
    type: str = "str"

    @property
    def end(self) -> int:
        return self.start + self.length


def _extract(raw: bytes, field: Field) -> Any:
    if field.start + field.length > len(raw):
        return None
    chunk = raw[field.start:field.end]
    try:
        text = chunk.decode("cp932").strip()
    except UnicodeDecodeError:
        text = chunk.decode("cp932", errors="replace").strip()

    if field.type == "skip" or text == "":
        return None

    if field.type == "int":
        try:
            return int(text) if text else None
        except ValueError:
            return None

    if field.type == "float":
        try:
            return float(text) if text else None
        except ValueError:
            return None

    if field.type == "date":
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        return None

    return text if text else None


def parse_record(raw: bytes) -> dict | None:
    """
    JV-Dataの1レコードを辞書に変換する。
    先頭2バイトのレコード種別IDでパーサーを切り替える。
    """
    if len(raw) < 2:
        return None

    try:
        record_type = raw[0:2].decode("cp932")
    except UnicodeDecodeError:
        return None

    parsers = {
        "RA": _parse_ra,
        "SE": _parse_se,
        "HR": _parse_hr,
        "UM": _parse_um,
        "KS": _parse_ks,
        "CH": _parse_ch,
        "BT": _parse_bt,
        "HC": _parse_hc,
        "WC": _parse_wc,
        "WH": _parse_wh,
        "WE": _parse_we,
        "O1": _parse_o1,  # 単勝・複勝オッズ
    }

    parser = parsers.get(record_type)
    if parser is None:
        return None

    result = parser(raw)
    if result is not None:
        result["_record_type"] = record_type
    return result


def _build_race_key(result: dict) -> str | None:
    """race_date + venue_code + kai + nichi + race_num で16桁キーを生成"""
    if not result.get("race_date") or not result.get("venue_code"):
        return None
    date_str = result["race_date"].replace("-", "")
    kai = str(result.get("kai") or 0).zfill(2)
    nichi = str(result.get("nichi") or 0).zfill(2)
    race_num = str(result.get("race_num") or 0).zfill(2)
    return f"{date_str}{result['venue_code']}{kai}{nichi}{race_num}"


# ---------------------------------------------------------------------------
# RA レコード（レース詳細） レコード長: 1273バイト (CRLF含む)
# JV-Data仕様書 Ver.4.9 「２．レース詳細」準拠
# ---------------------------------------------------------------------------
_RA_FIELDS = [
    Field("record_type",    0,    2),
    Field("data_kubun",     2,    1),
    Field("make_date",      3,    8, "date"),   # 作成年月日 YYYYMMDD
    # 開催情報（開催年4 + 開催月日4 を合わせてrace_dateとして扱う）
    Field("race_date",     11,    8, "date"),   # 開催年月日 YYYYMMDD
    Field("venue_code",    19,    2),           # 競馬場コード
    Field("kai",           21,    2, "int"),    # 開催回[第N回]
    Field("nichi",         23,    2, "int"),    # 開催日目[N日目]
    Field("race_num",      25,    2, "int"),    # レース番号
    # レース情報
    Field("race_name",     32,   60),           # 競走名本題（全角30文字）
    Field("race_name_sub", 92,   60),           # 競走名副題
    Field("race_name_short",572, 20),           # 競走名略称10文字
    Field("grade",        614,    1),           # グレードコード（sp=一般, 1=G1, 2=G2, 3=G3 等）
    Field("race_type",    616,    2, "int"),    # 競走種別コード
    Field("race_symbol",  618,    3),           # 競走記号コード（牝馬限定・混合等の判定用）
    Field("weight_type",  621,    1, "int"),    # 重量種別コード（1=定量,2=別定,3=ハンデ等）
    Field("condition_2yo",622,    3, "int"),    # 競走条件コード 2歳
    Field("condition_3yo",625,    3, "int"),    # 競走条件コード 3歳
    Field("condition_4yo",628,    3, "int"),    # 競走条件コード 4歳
    Field("condition_5up",631,    3, "int"),    # 競走条件コード 5歳以上
    Field("condition_youngest",634,3, "int"),   # 競走条件コード 最若年条件
    # 距離・コース
    Field("distance",     697,    4, "int"),    # 距離(m)
    Field("track_code",   705,    2, "int"),    # トラックコード（10=芝左,11=芝右,17=芝直,22=ダ左,23=ダ右,51=障害等）
    # 賞金（単位:百円、繰返し7回=1~5着+同着2回分）
    Field("prize_1st",    713,    8, "int"),    # 1着本賞金（百円）
    Field("prize_2nd",    721,    8, "int"),    # 2着本賞金
    Field("prize_3rd",    729,    8, "int"),    # 3着本賞金
    # 発走・頭数
    Field("start_time",   873,    4),           # 発走時刻 HHMM
    Field("horse_count_reg",881,  2, "int"),    # 登録頭数
    Field("horse_count",  883,    2, "int"),    # 出走頭数
    # 天候・馬場
    Field("weather",      887,    1, "int"),    # 天候コード
    Field("turf_cond",    888,    1, "int"),    # 芝馬場状態コード
    Field("dirt_cond",    889,    1, "int"),    # ダート馬場状態コード
]

# ラップタイム: pos 890 から25ハロン分（各3バイト, 単位0.1秒）
_RA_LAP_START = 890
_RA_LAP_COUNT = 25
_RA_LAP_WIDTH = 3


def _parse_ra(raw: bytes) -> dict:
    result = {f.name: _extract(raw, f) for f in _RA_FIELDS}
    result["race_key"] = _build_race_key(result)

    # ラップタイム
    laps = []
    for i in range(_RA_LAP_COUNT):
        pos = _RA_LAP_START + i * _RA_LAP_WIDTH
        if pos + _RA_LAP_WIDTH <= len(raw):
            chunk = raw[pos:pos + _RA_LAP_WIDTH].decode("cp932", errors="replace").strip()
            if chunk and chunk.isdigit() and chunk != "000":
                laps.append(int(chunk))
    result["laps"] = laps

    # トラックコードから track_type (1=芝,2=ダート,3=障害) と track_dir (1=右,2=左,3=直線) を導出
    tc = result.pop("track_code", None)
    if tc:
        if tc < 20:
            result["track_type"] = 1      # 芝
        elif tc < 30:
            result["track_type"] = 2      # ダート
        else:
            result["track_type"] = 3      # 障害
        # 右回り: 11,23 / 左回り: 10,22 / 直線: 17,27,29
        last_digit = tc % 10
        if last_digit == 1 or last_digit == 3:
            result["track_dir"] = 1       # 右
        elif last_digit == 0 or last_digit == 2:
            result["track_dir"] = 2       # 左
        elif last_digit == 7 or last_digit == 9:
            result["track_dir"] = 3       # 直線
        else:
            result["track_dir"] = None
    else:
        result["track_type"] = 0
        result["track_dir"] = None

    # 馬場状態（芝/ダートに応じて切り替え）
    if result.get("track_type") == 2:
        result["track_cond"] = result.pop("dirt_cond", None)
        result.pop("turf_cond", None)
    else:
        result["track_cond"] = result.pop("turf_cond", None)
        result.pop("dirt_cond", None)

    # グレードコード: 仕様書コード表2003 → DB用整数に変換
    # A=G1, B=G2, C=G3, D=重賞, E=OP/特別, F=Listed(L)
    _GRADE_MAP = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
    grade_str = str(result.get("grade") or "").strip()
    result["grade"] = _GRADE_MAP.get(grade_str)

    # 重量種別コードからハンデ判定
    result["is_handicap"] = result.get("weight_type") == 3

    # 競走記号コードから牝馬限定・混合を判定
    # コード表2006: 牝馬限定系="019","020","701"等, 混合="701"〜等
    symbol = result.pop("race_symbol", None) or ""
    result["is_female_only"] = symbol in ("019", "020", "701", "702", "703", "704")
    result["is_mixed"] = symbol.startswith("7")  # 700番台は混合系

    # 競走条件コード（最若年条件を代表として使う）
    result["condition_code"] = result.pop("condition_youngest", None)
    result.pop("condition_2yo", None)
    result.pop("condition_3yo", None)
    result.pop("condition_4yo", None)
    result.pop("condition_5up", None)

    return result


# ---------------------------------------------------------------------------
# SE レコード（馬毎レース情報）★学習データの中心
# レコード長: 555バイト (CRLF含む)
# JV-Data仕様書 Ver.4.9 「３．馬毎レース情報」準拠
# ---------------------------------------------------------------------------
_SE_FIELDS = [
    Field("record_type",    0,    2),
    Field("data_kubun",     2,    1),
    Field("make_date",      3,    8, "date"),
    # 開催情報
    Field("race_date",     11,    8, "date"),
    Field("venue_code",    19,    2),
    Field("kai",           21,    2, "int"),
    Field("nichi",         23,    2, "int"),
    Field("race_num",      25,    2, "int"),
    # 馬情報（仕様書: 枠番=spec28, 馬番=spec29）
    Field("frame_num",     27,    1, "int"),    # 枠番（1バイト）
    Field("horse_num",     28,    2, "int"),    # 馬番（2バイト）
    Field("blood_reg_num", 30,   10),           # 血統登録番号
    Field("horse_name",    40,   36),           # 馬名（全角18文字）
    # 属性
    Field("sex",           78,    1, "int"),    # 性別コード（1=牡,2=牝,3=騸）
    Field("age",           82,    2, "int"),    # 馬齢
    # 東西所属コード（1=関東, 2=関西, 3=地方 等）
    Field("belong_region",  84,    1, "int"),   # spec 85
    # 調教師
    Field("trainer_code",  85,    5),           # 調教師コード
    # 負担重量（斤量）
    Field("weight_carry", 288,    3, "int"),    # 単位0.1kg（例: "550" = 55.0kg）
    # 変更前負担重量（斤量変更があった場合の元斤量、0.1kg単位）
    Field("prev_weight_carry", 291, 3, "int"),  # spec 292
    # ブリンカー使用区分（0=未使用, 1=使用）
    Field("blinker_code", 294,    1, "int"),    # spec 295
    # 騎手
    Field("jockey_code",  296,    5),           # 騎手コード
    # 変更前騎手コード（騎手変更があった場合の元騎手コード）
    Field("prev_jockey_code", 301, 5),          # spec 302
    # 騎手見習コード（0=非見習, 1=1kg減, 2=2kg減, 3=3kg減）
    Field("apprentice_code", 322,  1, "int"),   # spec 323
    # 馬体重
    Field("horse_weight", 324,    3, "int"),    # 馬体重(kg)
    Field("weight_sign",  327,    1),           # 増減符号（+/-/スペース）
    Field("weight_diff",  328,    3, "int"),    # 増減差(kg)
    # 結果
    Field("abnormal_code",331,    1, "int"),    # 異常区分コード（0=正常,1=取消等）
    Field("finish_order", 334,    2, "int"),    # 確定着順
    Field("finish_time",  338,    4, "int"),    # 走破タイム（MSSF: M分SS秒F=1/10秒）
    Field("margin",       342,    3, "int"),    # 着差コード
    # コーナー通過順位
    Field("corner_1",     351,    2, "int"),
    Field("corner_2",     353,    2, "int"),
    Field("corner_3",     355,    2, "int"),
    Field("corner_4",     357,    2, "int"),
    # オッズ
    Field("odds_win",     359,    4, "int"),    # 単勝オッズ（×10, 例: "0338" = 33.8倍）
    Field("popularity",   363,    2, "int"),    # 単勝人気順
    # タイム
    Field("last_3f",      390,    3, "int"),    # 後3ハロンタイム（×10秒）
]


def _parse_se(raw: bytes) -> dict:
    result = {f.name: _extract(raw, f) for f in _SE_FIELDS}
    result["race_key"] = _build_race_key(result)

    # 斤量: 0.1kg 単位 → kg に変換
    if result.get("weight_carry"):
        result["weight_carry"] = result["weight_carry"] / 10.0

    # 変更前斤量: 0.1kg 単位 → kg に変換
    if result.get("prev_weight_carry"):
        result["prev_weight_carry"] = result["prev_weight_carry"] / 10.0

    # 単勝オッズ: ×10 → 実オッズに変換
    if result.get("odds_win"):
        result["odds_win"] = result["odds_win"] / 10.0

    # 増減差に符号を適用
    sign = result.pop("weight_sign", None)
    if sign == "-" and result.get("weight_diff"):
        result["weight_diff"] = -result["weight_diff"]

    return result


# ---------------------------------------------------------------------------
# UM レコード（競走馬マスタ） レコード長: 1609バイト
# JV-Data仕様書 「１３．競走馬マスタ」準拠
# ---------------------------------------------------------------------------
_UM_FIELDS = [
    Field("record_type",       0,    2),
    Field("data_kubun",        2,    1),
    Field("make_date",         3,    8, "date"),
    Field("blood_reg_num",    11,   10),          # spec 12
    Field("birth_date",       38,    8, "date"),  # spec 39
    Field("name_kana",        82,   36),          # spec 83 馬名半角ｶﾅ
    Field("name_eng",        118,   60),          # spec 119
    Field("sex",             200,    1, "int"),   # spec 201
    Field("coat_color",      202,    2, "int"),   # spec 203
    # 3代血統情報: spec 205, 14繰返し×46バイト
    # 順序: 父,母,父父,父母,母父,母母,...
    Field("father_code",     204,   10),          # 父・繁殖登録番号
    Field("father_name",     214,   36),          # 父・馬名
    Field("mother_code",     250,   10),          # 母・繁殖登録番号
    Field("mother_name",     260,   36),          # 母・馬名
    Field("mother_father_code",388, 10),          # 母父・繁殖登録番号
    Field("mother_father",   398,   36),          # 母父・馬名
    # 所属・生産
    Field("producer_name",   890,   72),          # spec 891 生産者名(法人格無)
    Field("area_name",       962,   20),          # spec 963 産地名
    Field("owner_name",      988,   64),          # spec 989 馬主名(法人格無)
    # 賞金
    Field("total_earnings", 1052,    9, "int"),   # spec 1053 平地本賞金累計（百円）
]

# UM の中央合計着回数: spec 1125, 6繰返し×3バイト (1着〜着外)
_UM_WINS_START = 1124   # Python index (spec 1125 - 1)
_UM_WINS_WIDTH = 3
_UM_WINS_COUNT = 6      # 1着,2着,3着,4着,5着,着外


def _parse_um(raw: bytes) -> dict:
    result = {f.name: _extract(raw, f) for f in _UM_FIELDS}
    # 中央合計着回数から total_wins / total_races を算出
    wins = 0
    total = 0
    for i in range(_UM_WINS_COUNT):
        pos = _UM_WINS_START + i * _UM_WINS_WIDTH
        if pos + _UM_WINS_WIDTH <= len(raw):
            chunk = raw[pos:pos + _UM_WINS_WIDTH].decode("cp932", errors="replace").strip()
            if chunk.isdigit():
                val = int(chunk)
                if i == 0:
                    wins = val
                total += val
    result["total_wins"] = wins
    result["total_races"] = total
    return result


# ---------------------------------------------------------------------------
# KS レコード（騎手マスタ） レコード長: 4173バイト
# JV-Data仕様書 「１４．騎手マスタ」準拠
# ---------------------------------------------------------------------------
_KS_FIELDS = [
    Field("record_type",   0,    2),
    Field("data_kubun",    2,    1),
    Field("make_date",     3,    8, "date"),
    Field("jockey_code",  11,    5),           # spec 12
    Field("birth_date",   33,    8, "date"),   # spec 34
    Field("name_kanji",   41,   34),           # spec 42 騎手名（全角17文字）
    Field("name_kana",   109,   30),           # spec 110 騎手名半角ｶﾅ
    Field("belong_code", 230,    1, "int"),    # spec 231 東西所属コード
]

# 累計成績: spec 1016 + 2×1052 = spec 3120 (Python 3119) が累計ブロック開始
# 平地着回数: 相対pos 45, 6繰返し×6バイト (1着〜着外)
# 障害着回数: 相対pos 81, 6繰返し×6バイト
_KS_CUM_BASE = 3119     # 累計ブロック開始 Python index
_KS_FLAT_OFFSET = 44     # 平地着回数の相対位置(0始まり)
_KS_JUMP_OFFSET = 80     # 障害着回数の相対位置(0始まり)
_KS_WIN_WIDTH = 6
_KS_WIN_COUNT = 6


def _parse_ks(raw: bytes) -> dict:
    result = {f.name: _extract(raw, f) for f in _KS_FIELDS}
    # 累計成績（平地+障害）から通算成績を算出
    total_1st = total_2nd = total_3rd = total_races = 0
    for offset in [_KS_FLAT_OFFSET, _KS_JUMP_OFFSET]:
        for i in range(_KS_WIN_COUNT):
            pos = _KS_CUM_BASE + offset + i * _KS_WIN_WIDTH
            if pos + _KS_WIN_WIDTH <= len(raw):
                chunk = raw[pos:pos + _KS_WIN_WIDTH].decode("cp932", errors="replace").strip()
                if chunk.isdigit():
                    val = int(chunk)
                    if i == 0:
                        total_1st += val
                    elif i == 1:
                        total_2nd += val
                    elif i == 2:
                        total_3rd += val
                    total_races += val
    result["total_1st"] = total_1st
    result["total_2nd"] = total_2nd
    result["total_3rd"] = total_3rd
    result["total_races"] = total_races
    return result


# ---------------------------------------------------------------------------
# CH レコード（調教師マスタ） レコード長: 3862バイト
# JV-Data仕様書 「１５．調教師マスタ」準拠
# ---------------------------------------------------------------------------
_CH_FIELDS = [
    Field("record_type",   0,    2),
    Field("data_kubun",    2,    1),
    Field("make_date",     3,    8, "date"),
    Field("trainer_code", 11,    5),            # spec 12
    Field("birth_date",   33,    8, "date"),    # spec 34
    Field("name_kanji",   41,   34),            # spec 42 調教師名（全角17文字）
    Field("name_kana",    75,   30),            # spec 76 調教師名半角ｶﾅ
    Field("belong_code", 194,    1, "int"),     # spec 195 東西所属コード
]

# 累計成績: spec 705 + 2×1052 = spec 2809 (Python 2808) が累計ブロック開始
# 平地着回数: 相対pos 45, 6繰返し×6バイト
# 障害着回数: 相対pos 81, 6繰返し×6バイト
_CH_CUM_BASE = 2808
_CH_FLAT_OFFSET = 44
_CH_JUMP_OFFSET = 80
_CH_WIN_WIDTH = 6
_CH_WIN_COUNT = 6


def _parse_ch(raw: bytes) -> dict:
    result = {f.name: _extract(raw, f) for f in _CH_FIELDS}
    # 累計成績（平地+障害）
    total_1st = total_races = 0
    for offset in [_CH_FLAT_OFFSET, _CH_JUMP_OFFSET]:
        for i in range(_CH_WIN_COUNT):
            pos = _CH_CUM_BASE + offset + i * _CH_WIN_WIDTH
            if pos + _CH_WIN_WIDTH <= len(raw):
                chunk = raw[pos:pos + _CH_WIN_WIDTH].decode("cp932", errors="replace").strip()
                if chunk.isdigit():
                    val = int(chunk)
                    if i == 0:
                        total_1st += val
                    total_races += val
    result["total_1st"] = total_1st
    result["total_races"] = total_races
    return result


# ---------------------------------------------------------------------------
# WH レコード（馬体重速報）
# ---------------------------------------------------------------------------
_WH_FIELDS = [
    Field("record_type",   0,   2),
    Field("data_kubun",    2,   1),
    Field("make_date",     3,   8, "date"),
    Field("race_date",    11,   8, "date"),
    Field("venue_code",   19,   2),
    Field("kai",          21,   2, "int"),
    Field("nichi",        23,   2, "int"),
    Field("race_num",     25,   2, "int"),
    Field("horse_num",    27,   2, "int"),
    Field("weight",       29,   3, "int"),
    Field("weight_diff",  32,   3, "int"),
]


def _parse_wh(raw: bytes) -> dict:
    result = {f.name: _extract(raw, f) for f in _WH_FIELDS}
    result["race_key"] = _build_race_key(result)
    return result


# ---------------------------------------------------------------------------
# WE レコード（調教タイム）
# ---------------------------------------------------------------------------
_WE_FIELDS = [
    Field("record_type",   0,   2),
    Field("data_kubun",    2,   1),
    Field("make_date",     3,   8, "date"),
    Field("blood_reg_num",11,  10),
    Field("training_date",21,   8, "date"),
    Field("course_type",  29,   1, "int"),
    Field("distance",     30,   4, "int"),
    Field("lap_time",     34,   4, "int"),
    Field("last_3f",      38,   3, "int"),
    Field("last_1f",      41,   3, "int"),
    Field("rank",         44,   1),
]


def _parse_we(raw: bytes) -> dict:
    return {f.name: _extract(raw, f) for f in _WE_FIELDS}


# ---------------------------------------------------------------------------
# BT レコード（系統情報） レコード長: 6889バイト
# ---------------------------------------------------------------------------
_BT_FIELDS = [
    Field("record_type",    0,    2),
    Field("data_kubun",     2,    1),
    Field("make_date",      3,    8, "date"),
    Field("breed_reg_num", 11,   10),          # spec 12 繁殖登録番号
    Field("lineage_id",    21,   30),          # spec 22 系統ID（2桁区切り系譜コード）
    Field("lineage_name",  51,   36),          # spec 52 系統名（サンデーサイレンス系等）
]


def _parse_bt(raw: bytes) -> dict:
    return {f.name: _extract(raw, f) for f in _BT_FIELDS}


# ---------------------------------------------------------------------------
# HC レコード（坂路調教） レコード長: 60バイト
# JV-Data仕様書 「２２．坂路調教」準拠
# ---------------------------------------------------------------------------

def _parse_hc(raw: bytes) -> dict:
    """坂路調教レコードをパース"""
    try:
        trecen = raw[11:12].decode("cp932").strip()       # spec 12: トレセン区分 0=美浦,1=栗東
        t_date = raw[12:20].decode("cp932").strip()       # spec 13: 調教年月日
        t_time = raw[20:24].decode("cp932").strip()       # spec 21: 調教時刻
        brn = raw[24:34].decode("cp932").strip()          # spec 25: 血統登録番号
        f4_total = raw[34:38].decode("cp932").strip()     # spec 35: 4ハロンタイム合計
        lap_8_6 = raw[38:41].decode("cp932").strip()      # spec 39: 800M-600M
        f3_total = raw[41:45].decode("cp932").strip()     # spec 42: 3ハロンタイム合計
        lap_6_4 = raw[45:48].decode("cp932").strip()      # spec 46: 600M-400M
        f2_total = raw[48:52].decode("cp932").strip()     # spec 49: 2ハロンタイム合計
        lap_4_2 = raw[52:55].decode("cp932").strip()      # spec 53: 400M-200M
        lap_2_0 = raw[55:58].decode("cp932").strip()      # spec 56: 200M-0M（最終1F）
    except (UnicodeDecodeError, IndexError):
        return None

    if not brn or not t_date or len(t_date) != 8:
        return None

    def to_int(s):
        return int(s) if s and s.isdigit() and s != "0000" and s != "000" else None

    return {
        "_record_type": "HC",
        "blood_reg_num": brn,
        "training_date": f"{t_date[:4]}-{t_date[4:6]}-{t_date[6:8]}",
        "trecen": int(trecen) if trecen.isdigit() else 0,  # 0=美浦, 1=栗東
        "course_type": 1,  # 坂路=1
        "distance": 800,   # 坂路は800m固定
        "lap_time": to_int(f4_total),   # 4ハロン全体（0.1秒単位）
        "last_3f": to_int(f3_total),    # 上がり3F
        "last_1f": to_int(lap_2_0),     # 最終1F
    }


# ---------------------------------------------------------------------------
# WC レコード（ウッドチップ調教） レコード長: 105バイト
# JV-Data仕様書 「３２．ウッドチップ調教」準拠
# ---------------------------------------------------------------------------

def _parse_wc(raw: bytes) -> dict:
    """ウッドチップ調教レコードをパース"""
    try:
        trecen = raw[11:12].decode("cp932").strip()
        t_date = raw[12:20].decode("cp932").strip()
        t_time = raw[20:24].decode("cp932").strip()
        brn = raw[24:34].decode("cp932").strip()
        course = raw[34:35].decode("cp932").strip()       # 0=A, 1=B, 2=C...
        direction = raw[35:36].decode("cp932").strip()    # 0=右, 1=左
        # 5ハロンタイム合計(1000M～0M) = spec 73, 4 bytes
        f5_total = raw[72:76].decode("cp932").strip()
        # 3ハロンタイム合計(600M～0M) = 手計算: spec 87位
        # 実際の位置: 10F=38, 9F=45, 8F=52, 7F=59, 6F=66, 5F=73, 4F=80, 3F=87
        f3_total = raw[86:90].decode("cp932").strip()
        # 最終1F: spec 100位 (200M-0M)
        lap_2_0 = raw[99:102].decode("cp932").strip()
    except (UnicodeDecodeError, IndexError):
        return None

    if not brn or not t_date or len(t_date) != 8:
        return None

    def to_int(s):
        return int(s) if s and s.isdigit() and s not in ("0000", "000", "9999", "999") else None

    return {
        "_record_type": "WC",
        "blood_reg_num": brn,
        "training_date": f"{t_date[:4]}-{t_date[4:6]}-{t_date[6:8]}",
        "trecen": int(trecen) if trecen.isdigit() else 0,
        "course_type": 2,    # ウッドチップ=2
        "distance": 1000,    # 通常1000m
        "lap_time": to_int(f5_total),
        "last_3f": to_int(f3_total),
        "last_1f": to_int(lap_2_0),
    }


# ---------------------------------------------------------------------------
# HR レコード（払戻） レコード長: 719バイト
# JV-Data仕様書 「４．払戻」準拠
# 各券種の払戻情報を payouts リストとして返す
# ---------------------------------------------------------------------------

# 払戻セクション定義: (bet_type, spec_start, repeat, combo_len, payout_len, pop_len)
_HR_SECTIONS = [
    # bet_type: 1=単勝,2=複勝,3=枠連,4=馬連,5=ワイド,6=馬単,7=三連複,8=三連単
    (1, 103, 3, 2, 9, 2),    # 単勝: spec103, 3回, 組番2+払戻9+人気2=13
    (2, 142, 5, 2, 9, 2),    # 複勝: spec142, 5回, 組番2+払戻9+人気2=13
    (3, 207, 3, 2, 9, 2),    # 枠連: spec207, 3回, 組番2+払戻9+人気2=13
    (4, 246, 3, 4, 9, 3),    # 馬連: spec246, 3回, 組番4+払戻9+人気3=16
    (5, 294, 7, 4, 9, 3),    # ワイド: spec294, 7回, 組番4+払戻9+人気3=16
    (6, 454, 6, 4, 9, 3),    # 馬単: spec454, 6回, 組番4+払戻9+人気3=16
    (7, 550, 3, 6, 9, 3),    # 三連複: spec550, 3回, 組番6+払戻9+人気3=18
    (8, 604, 6, 6, 9, 4),    # 三連単: spec604, 6回, 組番6+払戻9+人気4=19
]


def _parse_hr(raw: bytes) -> dict:
    """HR（払戻）レコードをパース。payoutsリストを含む辞書を返す。"""
    result = {}
    # 共通ヘッダー
    result["record_type"] = raw[0:2].decode("cp932", errors="replace")
    result["data_kubun"] = raw[2:3].decode("cp932", errors="replace").strip()

    # race_key生成用
    try:
        year = raw[11:15].decode("cp932")
        mmdd = raw[15:19].decode("cp932")
        venue = raw[19:21].decode("cp932")
        kai = raw[21:23].decode("cp932")
        nichi = raw[23:25].decode("cp932")
        race_num = raw[25:27].decode("cp932")
        result["race_date"] = f"{year}-{mmdd[:2]}-{mmdd[2:]}"
        result["venue_code"] = venue
        result["kai"] = int(kai) if kai.strip() else 0
        result["nichi"] = int(nichi) if nichi.strip() else 0
        result["race_num"] = int(race_num) if race_num.strip() else 0
        result["race_key"] = _build_race_key(result)
    except (UnicodeDecodeError, ValueError):
        return None

    if not result.get("race_key"):
        return None

    # 各券種の払戻を解析
    payouts = []
    for bet_type, spec_start, repeat, combo_len, payout_len, pop_len in _HR_SECTIONS:
        entry_size = combo_len + payout_len + pop_len
        base = spec_start - 1  # Python 0-indexed

        for i in range(repeat):
            pos = base + i * entry_size
            if pos + entry_size > len(raw):
                break

            combo_raw = raw[pos:pos + combo_len].decode("cp932", errors="replace").strip()
            payout_raw = raw[pos + combo_len:pos + combo_len + payout_len].decode("cp932", errors="replace").strip()
            pop_raw = raw[pos + combo_len + payout_len:pos + entry_size].decode("cp932", errors="replace").strip()

            # 空・ゼロ・発売なしはスキップ
            if not combo_raw or combo_raw == "0" * combo_len:
                continue
            if not payout_raw or not payout_raw.isdigit():
                continue

            payout_val = int(payout_raw)
            if payout_val == 0:
                continue

            # 組番をハイフン区切りに変換（"0307" → "03-07", "030712" → "03-07-12"）
            if bet_type <= 3:
                # 単勝/複勝/枠連: 2桁そのまま
                combination = combo_raw
            elif bet_type <= 6:
                # 馬連/ワイド/馬単: 4桁 → "NN-NN"
                combination = f"{combo_raw[:2]}-{combo_raw[2:]}"
            else:
                # 三連複/三連単: 6桁 → "NN-NN-NN"
                combination = f"{combo_raw[:2]}-{combo_raw[2:4]}-{combo_raw[4:]}"

            pop_val = int(pop_raw) if pop_raw.isdigit() else None

            payouts.append({
                "bet_type": bet_type,
                "combination": combination,
                "payout": payout_val,
                "popularity": pop_val,
            })

    result["payouts"] = payouts
    return result


# ---------------------------------------------------------------------------
# O1 レコード（単勝・複勝オッズ）
# JV-Data仕様書 「５．オッズ（単勝・複勝）」準拠
#
# レコード構造:
#   共通ヘッダー: レコード種別(2) + データ区分(1) + 作成日(8)
#     + 開催年月日(8) + 場コード(2) + 回次(2) + 日次(2) + レース番号(2) = 27バイト
#   発走時刻: 4バイト (HHMM) → spec 28
#   登録頭数: 2バイト → spec 32
#   出走頭数: 2バイト → spec 34
#
#   馬ごとデータ (28頭分繰返し):
#     馬番(2) + 単勝オッズ(6) + 複勝最低オッズ(6) + 複勝最高オッズ(6) = 20バイト
#     → spec 36 から開始
#
# データ区分:
#   1=通常データ（速報）, 7=確定データ 等
#   → snapshot_type として保存
# ---------------------------------------------------------------------------

# データ区分 → snapshot_type マッピング
# JV-Data仕様: データ区分コード表2001
# 1=通常データ（速報）, 7=確定データ
_O1_KUBUN_MAP = {
    "1": 3,  # 通常（当日発売中） → snapshot_type 3
    "2": 1,  # 前日第1回 → snapshot_type 1（前日9時相当）
    "3": 2,  # 前日第2回 → snapshot_type 2（前日17時相当）
    "4": 4,  # 締切直前 → snapshot_type 4
    "5": 4,  # 締切直前（別パターン）
    "7": 5,  # 確定データ → snapshot_type 5
    "9": 5,  # 確定（別パターン）
    "A": 5,  # 成績確定
}

# O1の馬ごとデータ開始位置とレイアウト
_O1_HORSE_DATA_START = 35  # 0始まり（spec 36）
_O1_HORSE_ENTRY_SIZE = 20  # 馬番(2) + 単勝オッズ(6) + 複勝最低(6) + 複勝最高(6)
_O1_MAX_HORSES = 28


def _parse_o1(raw: bytes) -> dict:
    """
    O1（単勝・複勝オッズ）レコードをパース。
    odds_entries リスト（各馬のオッズ）を含む辞書を返す。
    """
    result = {}

    # 共通ヘッダー
    try:
        result["record_type"] = raw[0:2].decode("cp932", errors="replace")
        data_kubun = raw[2:3].decode("cp932", errors="replace").strip()
        result["data_kubun"] = data_kubun
        result["make_date"] = raw[3:11].decode("cp932", errors="replace").strip()

        # race_key 生成用
        year = raw[11:15].decode("cp932")
        mmdd = raw[15:19].decode("cp932")
        venue = raw[19:21].decode("cp932")
        kai = raw[21:23].decode("cp932")
        nichi = raw[23:25].decode("cp932")
        race_num = raw[25:27].decode("cp932")
        result["race_date"] = f"{year}-{mmdd[:2]}-{mmdd[2:]}"
        result["venue_code"] = venue
        result["kai"] = int(kai) if kai.strip() else 0
        result["nichi"] = int(nichi) if nichi.strip() else 0
        result["race_num"] = int(race_num) if race_num.strip() else 0
        result["race_key"] = _build_race_key(result)
    except (UnicodeDecodeError, ValueError, IndexError):
        return None

    if not result.get("race_key"):
        return None

    # snapshot_type を data_kubun から決定
    result["snapshot_type"] = _O1_KUBUN_MAP.get(data_kubun, 3)

    # 発走時刻（参考情報として保存）
    try:
        start_time = raw[27:31].decode("cp932", errors="replace").strip()
        result["start_time"] = start_time if start_time.isdigit() and len(start_time) == 4 else None
    except (UnicodeDecodeError, IndexError):
        result["start_time"] = None

    # 登録頭数・出走頭数
    try:
        horse_count_str = raw[33:35].decode("cp932", errors="replace").strip()
        horse_count = int(horse_count_str) if horse_count_str.isdigit() else _O1_MAX_HORSES
    except (UnicodeDecodeError, IndexError):
        horse_count = _O1_MAX_HORSES

    # 各馬のオッズを解析
    odds_entries = []
    for i in range(min(horse_count, _O1_MAX_HORSES)):
        pos = _O1_HORSE_DATA_START + i * _O1_HORSE_ENTRY_SIZE
        if pos + _O1_HORSE_ENTRY_SIZE > len(raw):
            break

        try:
            horse_num_str = raw[pos:pos + 2].decode("cp932", errors="replace").strip()
            odds_win_str = raw[pos + 2:pos + 8].decode("cp932", errors="replace").strip()
            odds_place_min_str = raw[pos + 8:pos + 14].decode("cp932", errors="replace").strip()
            odds_place_max_str = raw[pos + 14:pos + 20].decode("cp932", errors="replace").strip()
        except (UnicodeDecodeError, IndexError):
            continue

        # 馬番が空・ゼロならスキップ
        if not horse_num_str or not horse_num_str.isdigit():
            continue
        horse_num = int(horse_num_str)
        if horse_num == 0:
            continue

        # オッズ変換（×10表記 → 実数）
        # 例: "000338" = 33.8倍, "000010" = 1.0倍
        def _parse_odds(s: str) -> float | None:
            if not s or not s.isdigit():
                return None
            val = int(s)
            if val == 0:
                return None
            return val / 10.0

        odds_entries.append({
            "horse_num": horse_num,
            "odds_win": _parse_odds(odds_win_str),
            "odds_place_min": _parse_odds(odds_place_min_str),
            "odds_place_max": _parse_odds(odds_place_max_str),
        })

    result["odds_entries"] = odds_entries
    return result
