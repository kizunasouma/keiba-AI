"""
ダミーデータ投入スクリプト
全機能をUI上で確認できるように、リア��な競馬データを模したダミーを生成する

実行:
  cd backend
  poetry run python scripts/seed_dummy_data.py
"""
import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta, datetime
from sqlalchemy import text
from app.core.database import engine, SessionLocal

random.seed(42)

# --- マスタデータ ---
SIRE_NAMES = [
    "ディープインパクト", "キングカメハメハ", "ロードカナロア", "ハーツクライ",
    "エピファネイア", "ドゥラメンテ", "キタサンブラック", "モーリス",
    "オルフェーヴル", "サトノダイヤモンド", "ゴールドシップ", "ジャスタウェイ",
    "ルーラーシップ", "リアルスティール", "サトノクラウン", "スワーヴリチャード",
]
BMS_NAMES = [
    "サンデーサイレンス", "キングカメハメハ", "ブライアンズタイム", "フレンチデピュティ",
    "スペシャルウィーク", "アグネスタキオン", "マンハッタンカフェ", "クロフネ",
    "ダンスインザダーク", "タニノギムレット", "ネオユニヴァース", "シンボリクリスエス",
]
MOTHER_NAMES = [
    "ジェンティルドンナ", "ブエナビスタ", "ウオッカ", "グランアレグリア",
    "アーモンドアイ", "リバティアイランド", "スターズオンアース", "クロノジェネシス",
    "ラッキーライラック", "ソダシ", "メイケイエール", "デアリングタクト",
    "レイパパレ", "サリオス", "エフフォーリア", "イクイノックス",
]
JOCKEY_NAMES = [
    ("武豊", "タケユタ���"), ("C.ルメール", "ルメール"), ("川田将雅", "カワタマサヒロ"),
    ("横山武史", "ヨコヤマタケシ"), ("松山弘平", "マツヤマコウヘイ"), ("戸崎圭太", "トサキケイ���"),
    ("M.デムーロ", "デムーロ"), ("坂井瑠星", "サカイリュウセイ"), ("岩田望来", "イワタミライ"),
    ("吉田隼人", "ヨシダハヤト"), ("福永祐一", "フクナガユウイチ"), ("浜中俊", "ハマナカスグル"),
    ("田辺裕信", "タナベヒロノブ"), ("三浦皇成", "ミウラコウセイ"), ("藤岡佑介", "フジオカユウスケ"),
]
TRAINER_NAMES = [
    ("矢作芳人", "ヤハギヨシヒト"), ("中内田充正", "ナカウチダミツマサ"),
    ("国枝栄", "クニエダサカエ"), ("堀宣行", "ホリノブユキ"),
    ("友道康夫", "トモミチヤスオ"), ("木村哲也", "キムラテツヤ"),
    ("藤原英昭", "フジワラヒデアキ"), ("手塚貴久", "テヅカタカヒサ"),
    ("池江泰寿", "イケエヤスヒサ"), ("須貝尚介", "スガイショウスケ"),
]
HORSE_PREFIXES = [
    "サトノ", "キタサン", "ラッキー", "ゴールド", "ダノン", "レイ", "ソング",
    "エア", "メジロ", "タイキ", "マイネル", "コスモ", "アドマイヤ", "ジャスタ",
    "ワグネリアン", "スワーヴ", "グラン", "エピ", "シュネル", "カフェ",
]
HORSE_SUFFIXES = [
    "ダイヤモンド", "ゴールド", "クラウン", "スター", "フォース", "レジェンド",
    "ブレイブ", "シャイン", "ドリーム", "ファイター", "アロー", "グローリー",
    "フェニックス", "サンダー", "マジック", "エース", "プリンセス", "クイーン",
]
VENUE_CODES = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10"]
VENUE_NAMES_MAP = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}
RACE_NAMES_BY_GRADE = {
    1: ["日本ダービー", "有馬記念", "天皇賞(秋)", "ジャパンカップ", "桜花賞", "皐月賞", "宝塚記念", "安田記念"],
    2: ["毎日王冠", "スプリングS", "京都記念", "中山記念", "阪神大賞典", "フローラS"],
    3: ["ラジオNIKKEI賞", "新潟記念", "函館記念", "七夕賞", "中京記念", "小倉記念"],
}

TRAINING_COURSES = {1: "坂路", 2: "W", 3: "芝", 4: "ダ"}


def gen_horse_name():
    return random.choice(HORSE_PREFIXES) + random.choice(HORSE_SUFFIXES)


def gen_time(distance: int, track_type: int) -> int:
    """走破タイム(1/10秒)を生成"""
    # 芝1600m基準: 約1:34.0 = 940
    base = {1: 0.58, 2: 0.60}  # 秒/m
    rate = base.get(track_type, 0.59)
    t = distance * rate + random.gauss(0, 2)
    return int(t * 10)


def gen_last_3f(finish_order: int) -> int:
    """上が��3F(1/10秒)"""
    base = 340 + random.randint(-10, 20)
    # 上位ほど速い傾向
    base += (finish_order - 1) * random.randint(1, 4)
    return base


def main():
    db = SessionLocal()
    try:
        # 既存データをクリア（FK制約を無視してTRUNCATE + シーケンスリセット）
        db.execute(text("""
            TRUNCATE training_times, odds_snapshots, horse_weights,
                     payouts, race_laps, race_entries, races, horses, jockeys, trainers
            RESTART IDENTITY CASCADE
        """))
        db.commit()
        print("既存データをクリアしました")

        # --- 騎手マスタ ---
        jockey_ids = []
        for i, (name_k, name_kana) in enumerate(JOCKEY_NAMES):
            belong = 4 if "ルメール" in name_k or "デムーロ" in name_k else random.choice([1, 2])
            db.execute(text("""
                INSERT INTO jockeys (jockey_code, name_kanji, name_kana, belong_code,
                    total_1st, total_2nd, total_3rd, total_races, birth_date, created_at, updated_at)
                VALUES (:code, :name, :kana, :belong, :w, :p, :s, :t, :bd, NOW(), NOW())
                RETURNING id
            """), {
                "code": f"{10001+i}", "name": name_k, "kana": name_kana,
                "belong": belong,
                "w": random.randint(50, 800), "p": random.randint(50, 600),
                "s": random.randint(50, 500), "t": random.randint(500, 5000),
                "bd": date(1980 + random.randint(0, 20), random.randint(1, 12), random.randint(1, 28)),
            })
            jockey_ids.append(db.execute(text("SELECT lastval()")).scalar())
        db.commit()
        print(f"騎手 {len(jockey_ids)}人 投入")

        # --- 調教師マスタ ---
        trainer_ids = []
        for i, (name_k, name_kana) in enumerate(TRAINER_NAMES):
            db.execute(text("""
                INSERT INTO trainers (trainer_code, name_kanji, name_kana, belong_code,
                    total_1st, total_races, created_at, updated_at)
                VALUES (:code, :name, :kana, :belong, :w, :t, NOW(), NOW())
                RETURNING id
            """), {
                "code": f"{20001+i}", "name": name_k, "kana": name_kana,
                "belong": random.choice([1, 2]),
                "w": random.randint(100, 1500), "t": random.randint(1000, 8000),
            })
            trainer_ids.append(db.execute(text("SELECT lastval()")).scalar())
        db.commit()
        print(f"調教師 {len(trainer_ids)}人 投入")

        # --- 馬マスタ（80頭） ---
        horse_ids = []
        horse_names = []
        used_names = set()
        for i in range(80):
            while True:
                name = gen_horse_name()
                if name not in used_names:
                    used_names.add(name)
                    break
            father = random.choice(SIRE_NAMES)
            mother = random.choice(MOTHER_NAMES)
            mf = random.choice(BMS_NAMES)
            sex = random.choices([1, 2, 3], weights=[50, 40, 10])[0]
            db.execute(text("""
                INSERT INTO horses (blood_reg_num, name_kana, name_eng, birth_date,
                    sex, father_name, father_code, mother_name, mother_code,
                    mother_father, mother_father_code,
                    producer_name, area_name, owner_name,
                    total_wins, total_races, total_earnings, created_at, updated_at)
                VALUES (:reg, :name, :eng, :bd, :sex,
                    :fn, :fc, :mn, :mc, :mf, :mfc,
                    :prod, :area, :owner, :tw, :tr, :te, NOW(), NOW())
            """), {
                "reg": f"20{20+i//20:02d}{i%20+1:05d}0",
                "name": name, "eng": name,
                "bd": date(2019 + random.randint(0, 4), random.randint(1, 12), random.randint(1, 28)),
                "sex": sex,
                "fn": father, "fc": f"F{i:05d}",
                "mn": mother, "mc": f"M{i:05d}",
                "mf": mf, "mfc": f"B{i:05d}",
                "prod": random.choice(["ノーザンファーム", "社台ファーム", "追分ファーム", "ダーレー・ジャパン"]),
                "area": random.choice(["安平町", "千歳市", "新冠町", "日高町"]),
                "owner": random.choice(["サンデーレーシング", "キャロットファーム", "シルクレーシング", "社台RH", "大塚亮一"]),
                "tw": random.randint(0, 10), "tr": random.randint(5, 40),
                "te": random.randint(500, 50000),
            })
            hid = db.execute(text("SELECT lastval()")).scalar()
            horse_ids.append(hid)
            horse_names.append(name)
        db.commit()
        print(f"馬 {len(horse_ids)}頭 投入")

        # --- レース生成（直近2ヶ月、3場開催 × 12R × 土日） ---
        today = date.today()
        race_dates = []
        # 過去8週の土日
        for w in range(8):
            sat = today - timedelta(days=today.weekday() + 2 + w * 7)
            sun = sat + timedelta(days=1)
            race_dates.append(sat)
            race_dates.append(sun)
        # 今日と明日も追加
        race_dates.append(today)
        race_dates.append(today + timedelta(days=1))
        race_dates = sorted(set(race_dates))

        race_count = 0
        entry_count = 0
        lap_count = 0
        payout_count = 0
        training_count = 0

        for rd in race_dates:
            # 3場開催
            venues = random.sample(VENUE_CODES, 3)
            for vi, vc in enumerate(venues):
                for race_num in range(1, 13):
                    # レース条件
                    track_type = random.choices([1, 2], weights=[60, 40])[0]
                    distances = {1: [1200, 1400, 1600, 1800, 2000, 2200, 2400, 2500, 3200],
                                 2: [1200, 1400, 1700, 1800, 2100]}
                    distance = random.choice(distances[track_type])
                    track_dir = random.choice([1, 2])
                    cond = random.choices([1, 2, 3, 4], weights=[60, 20, 15, 5])[0]
                    weather = random.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]
                    horse_count = random.randint(8, 18)

                    # グレード（ほとんど条件戦）
                    grade = random.choices(
                        [1, 2, 3, 5, 6, 7, 8, 9, 10],
                        weights=[1, 2, 3, 5, 8, 12, 20, 25, 24]
                    )[0]
                    is_handicap = random.random() < 0.15
                    is_female = random.random() < 0.08
                    is_special = grade <= 5

                    # レース名
                    if grade <= 3 and grade in RACE_NAMES_BY_GRADE:
                        rname = random.choice(RACE_NAMES_BY_GRADE[grade])
                    elif grade == 5:
                        rname = f"{VENUE_NAMES_MAP[vc]}特別"
                    elif is_special:
                        rname = f"{VENUE_NAMES_MAP[vc]}{race_num}R特別"
                    else:
                        rname = None

                    race_key = f"{rd.strftime('%Y%m%d')}{vc}{vi+1:02d}01{race_num:02d}"
                    prize_1st = {1: 200000, 2: 100000, 3: 70000, 5: 40000}.get(grade, random.randint(5000, 20000))

                    db.execute(text("""
                        INSERT INTO races (race_key, race_date, venue_code, kai, nichi, race_num,
                            race_name, grade, distance, track_type, track_dir, horse_count,
                            weather, track_cond, is_handicap, is_female_only, is_mixed, is_special, prize_1st,
                            created_at, updated_at)
                        VALUES (:rk, :rd, :vc, :kai, :nichi, :rn,
                            :rname, :grade, :dist, :tt, :td, :hc,
                            :w, :cond, :handi, :fem, false, :spe, :prize, NOW(), NOW())
                    """), {
                        "rk": race_key, "rd": rd, "vc": vc,
                        "kai": vi + 1, "nichi": 1, "rn": race_num,
                        "rname": rname, "grade": grade,
                        "dist": distance, "tt": track_type, "td": track_dir,
                        "hc": horse_count, "w": weather, "cond": cond,
                        "handi": is_handicap, "fem": is_female, "spe": is_special,
                        "prize": prize_1st,
                    })
                    race_id = db.execute(text("SELECT lastval()")).scalar()
                    race_count += 1

                    # --- ラップタイム ---
                    n_furlongs = distance // 200
                    avg_lap = gen_time(200, track_type)
                    for fi in range(n_furlongs):
                        # 前半速め、後半やや遅め
                        if fi < 3:
                            lt = avg_lap + random.randint(-5, 5) - 3
                        elif fi >= n_furlongs - 3:
                            lt = avg_lap + random.randint(-5, 5) + 2
                        else:
                            lt = avg_lap + random.randint(-5, 5)
                        db.execute(text("""
                            INSERT INTO race_laps (race_id, hallon_order, lap_time)
                            VALUES (:rid, :ho, :lt)
                        """), {"rid": race_id, "ho": fi + 1, "lt": max(100, lt)})
                        lap_count += 1

                    # --- 出走馬 ---
                    selected_horses = random.sample(range(len(horse_ids)), min(horse_count, len(horse_ids)))
                    # 着順をシャッフル
                    finish_orders = list(range(1, horse_count + 1))
                    random.shuffle(finish_orders)

                    is_past = rd < today  # 過去レースは結果あり

                    for ei, hi_idx in enumerate(selected_horses):
                        hid = horse_ids[hi_idx]
                        jid = random.choice(jockey_ids)
                        tid = random.choice(trainer_ids)
                        frame = (ei // 2) + 1 if horse_count > 8 else ei + 1
                        frame = min(frame, 8)
                        horse_num = ei + 1
                        wc = round(random.choice([54.0, 55.0, 56.0, 57.0, 58.0]) + random.gauss(0, 0.5), 1)
                        hw = random.randint(420, 540)
                        wd = random.choice([-8, -6, -4, -2, 0, 0, 2, 4, 6, 8])
                        odds = round(random.lognormvariate(2.0, 1.0), 1)
                        odds = max(1.1, min(odds, 200.0))
                        pop = ei + 1  # 暫定

                        fo = finish_orders[ei] if is_past else None
                        ft = gen_time(distance, track_type) + (fo - 1) * random.randint(1, 5) if fo else None
                        l3f = gen_last_3f(fo) if fo else None
                        c4 = random.randint(1, horse_count)
                        c3 = max(1, c4 + random.randint(-3, 3))
                        c2 = max(1, c3 + random.randint(-2, 2))
                        c1 = max(1, c2 + random.randint(-2, 2))
                        margin = random.randint(1, 10) if fo and fo > 1 else None

                        odds_p_min = round(odds * random.uniform(0.3, 0.6), 1) if odds < 50 else None
                        odds_p_max = round(odds_p_min * random.uniform(1.2, 2.5), 1) if odds_p_min else None

                        db.execute(text("""
                            INSERT INTO race_entries (race_id, horse_id, jockey_id, trainer_id,
                                horse_num, frame_num, weight_carry, age, sex,
                                horse_weight, weight_diff,
                                odds_win, odds_place_min, odds_place_max, popularity,
                                finish_order, finish_time, last_3f, margin,
                                corner_1, corner_2, corner_3, corner_4, abnormal_code,
                                created_at, updated_at)
                            VALUES (:rid, :hid, :jid, :tid,
                                :hn, :fn, :wc, :age, :sex,
                                :hw, :wd,
                                :odds, :opm, :opx, :pop,
                                :fo, :ft, :l3f, :margin,
                                :c1, :c2, :c3, :c4, 0, NOW(), NOW())
                        """), {
                            "rid": race_id, "hid": hid, "jid": jid, "tid": tid,
                            "hn": horse_num, "fn": frame, "wc": wc,
                            "age": random.randint(2, 7),
                            "sex": random.choice([1, 1, 1, 2, 2, 3]),
                            "hw": hw, "wd": wd,
                            "odds": odds, "opm": odds_p_min, "opx": odds_p_max,
                            "pop": pop,
                            "fo": fo, "ft": ft, "l3f": l3f, "margin": margin,
                            "c1": c1 if is_past else None, "c2": c2 if is_past else None,
                            "c3": c3 if is_past else None, "c4": c4 if is_past else None,
                        })
                        entry_id = db.execute(text("SELECT lastval()")).scalar()
                        entry_count += 1

                        # --- 調教データ（過去レースの馬の���） ---
                        if random.random() < 0.6:
                            for wb in [1, 2]:
                                ct = random.choice([1, 2])
                                db.execute(text("""
                                    INSERT INTO training_times (horse_id, race_id, training_date,
                                        weeks_before, course_type, distance, lap_time, last_3f, rank)
                                    VALUES (:hid, :rid, :td, :wb, :ct, :dist, :lt, :l3f, :rank)
                                """), {
                                    "hid": hid, "rid": race_id,
                                    "td": rd - timedelta(days=wb * 7 + random.randint(0, 2)),
                                    "wb": wb, "ct": ct,
                                    "dist": random.choice([800, 1000, 1200]),
                                    "lt": random.randint(480, 560),
                                    "l3f": random.randint(350, 400),
                                    "rank": random.choice(["A", "A", "B", "B", "B", "C"]),
                                })
                                training_count += 1

                    # --- 払��（過去レースのみ） ---
                    if is_past:
                        sorted_finish = sorted(selected_horses, key=lambda x: finish_orders[selected_horses.index(x)])
                        w1 = sorted_finish[0] + 1  # 馬番
                        w2 = sorted_finish[1] + 1
                        w3 = sorted_finish[2] + 1

                        payouts_data = [
                            (1, str(w1), random.randint(200, 5000), 1),
                            (2, str(w1), random.randint(100, 1500), 1),
                            (2, str(w2), random.randint(100, 2000), 2),
                            (2, str(w3), random.randint(100, 3000), 3),
                            (4, f"{min(w1,w2)}-{max(w1,w2)}", random.randint(300, 20000), 1),
                            (5, f"{min(w1,w2)}-{max(w1,w2)}", random.randint(200, 5000), 1),
                            (5, f"{min(w1,w3)}-{max(w1,w3)}", random.randint(300, 8000), 2),
                            (5, f"{min(w2,w3)}-{max(w2,w3)}", random.randint(400, 15000), 3),
                            (6, f"{w1}-{w2}", random.randint(500, 30000), 1),
                            (7, f"{'-'.join(str(x) for x in sorted([w1,w2,w3]))}", random.randint(1000, 100000), 1),
                            (8, f"{w1}-{w2}-{w3}", random.randint(3000, 500000), 1),
                        ]
                        for bt, combo, payout, pop in payouts_data:
                            db.execute(text("""
                                INSERT INTO payouts (race_id, bet_type, combination, payout, popularity)
                                VALUES (:rid, :bt, :combo, :payout, :pop)
                            """), {"rid": race_id, "bt": bt, "combo": combo, "payout": payout, "pop": pop})
                            payout_count += 1

                    # 50レースごとにコミット
                    if race_count % 50 == 0:
                        db.commit()
                        print(f"  {race_count}レース処理済み...")

        # 馬の通算成績を更新
        db.execute(text("""
            UPDATE horses SET
                total_wins = sub.wins,
                total_races = sub.races
            FROM (
                SELECT horse_id,
                    COUNT(*) AS races,
                    SUM(CASE WHEN finish_order = 1 THEN 1 ELSE 0 END) AS wins
                FROM race_entries
                WHERE finish_order IS NOT NULL
                GROUP BY horse_id
            ) sub
            WHERE horses.id = sub.horse_id
        """))

        # 人気を正しくセット（各レース内でオッズ順）
        db.execute(text("""
            UPDATE race_entries SET popularity = sub.pop
            FROM (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY race_id ORDER BY odds_win) AS pop
                FROM race_entries
            ) sub
            WHERE race_entries.id = sub.id
        """))

        db.commit()
        print(f"\n=== 投入完了 ===")
        print(f"レース: {race_count}")
        print(f"出走: {entry_count}")
        print(f"ラップ: {lap_count}")
        print(f"払戻: {payout_count}")
        print(f"調教: {training_count}")
        print(f"馬: {len(horse_ids)}")
        print(f"騎手: {len(jockey_ids)}")
        print(f"調教師: {len(trainer_ids)}")
        print(f"期間: {race_dates[0]} 〜 {race_dates[-1]}")

    except Exception as e:
        db.rollback()
        print(f"エラー: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
