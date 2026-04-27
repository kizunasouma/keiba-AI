"""
購入フィルタ最適化バッチ
過去データでEV閾値・オッズ帯・レース条件の最適組合せを探索する
flat（均一100円）とkelly（フラクショナルケリー基準）の両方で回収率を比較

使い方:
    python scripts/optimize_filter.py
    python scripts/optimize_filter.py --years 3
    python scripts/optimize_filter.py --years 2 --bankroll 200000 --kelly-fraction 0.25
"""
import sys
import argparse
import logging
from pathlib import Path
from itertools import product

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def calc_kelly_bet(win_prob: float, odds: float, bankroll: float, kelly_fraction: float = 0.25) -> float:
    """ケリー基準による賭け金計算（optimize_filter用ローカル版）"""
    if odds <= 1 or win_prob <= 0 or win_prob >= 1:
        return 0
    b = odds - 1
    q = 1 - win_prob
    kelly_f = (win_prob * b - q) / b
    kelly_f = max(0, kelly_f)
    if kelly_f == 0:
        return 0
    bet = bankroll * kelly_f * kelly_fraction
    bet = max(100, min(bet, bankroll * 0.05))
    bet = int(bet / 100) * 100
    return float(bet)


def _evaluate_bets_flat(bets):
    """均一100円での回収率を計算"""
    invest = len(bets) * 100
    ret = sum(int(float(r["odds_win"]) * 100) for r in bets if r["finish_order"] == 1)
    hits = sum(1 for r in bets if r["finish_order"] == 1)
    roi = ret / invest * 100 if invest > 0 else 0
    return invest, ret, hits, roi


def _evaluate_bets_kelly(bets, bankroll: float, kelly_fraction: float):
    """ケリー基準での回収率を計算（動的資金管理）"""
    current_bankroll = bankroll
    total_invest = 0
    total_return = 0
    hits = 0
    actual_bets = 0

    for r in bets:
        odds = float(r["odds_win"])
        n = int(r["horse_count"]) if r["horse_count"] else 10
        win_prob = 1.0 / n  # 簡易勝率

        bet_amount = calc_kelly_bet(win_prob, odds, current_bankroll, kelly_fraction)
        if bet_amount <= 0:
            continue

        actual_bets += 1
        total_invest += bet_amount

        if r["finish_order"] == 1:
            payout = int(odds * bet_amount)
            total_return += payout
            hits += 1
            current_bankroll += payout - bet_amount
        else:
            current_bankroll -= bet_amount
            current_bankroll = max(current_bankroll, 1000)

    roi = total_return / total_invest * 100 if total_invest > 0 else 0
    return total_invest, total_return, hits, roi, actual_bets, current_bankroll


def run_optimization(db, years: int = 2, bankroll: float = 100000, kelly_fraction: float = 0.25):
    """グリッドサーチで最適な購入フィルタを探索（flat + kelly 比較）"""

    logger.info(f"過去{years}年のデータで購入フィルタを最適化中...")
    logger.info(f"ケリー基準設定: 資金={bankroll:,.0f}円, 分数={kelly_fraction}")

    # 全レースの1番人気データを取得
    rows = db.execute(text("""
        WITH fav AS (
            SELECT
                r.race_key, r.race_date, r.track_type, r.grade,
                r.horse_count, r.is_handicap,
                re.odds_win, re.finish_order, re.popularity,
                ROW_NUMBER() OVER (PARTITION BY r.race_key ORDER BY re.odds_win ASC) AS rn
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE r.race_date >= CURRENT_DATE - :days
              AND re.finish_order IS NOT NULL
              AND re.odds_win IS NOT NULL
              AND re.odds_win > 0
        )
        SELECT * FROM fav WHERE rn = 1
        ORDER BY race_date, race_key
    """), {"days": years * 365}).mappings().all()

    if len(rows) < 100:
        logger.warning(f"データ不足: {len(rows)}件。最低100レース必要。")
        return

    logger.info(f"対象レース: {len(rows):,}件")

    # グリッドサーチパラメータ
    odds_ranges = [(1.0, 999), (1.5, 10), (2.0, 15), (3.0, 20), (5.0, 50), (10.0, 100)]
    head_counts = [None, (8, 99), (12, 99), (14, 99)]  # 頭数フィルタ
    track_types = [None, 1, 2]  # 全/芝/ダート

    best_flat_roi = 0
    best_flat_params = {}
    best_kelly_roi = 0
    best_kelly_params = {}
    flat_results = []
    kelly_results = []

    for (min_odds, max_odds), heads, tt in product(odds_ranges, head_counts, track_types):
        filtered = rows
        if tt:
            filtered = [r for r in filtered if r["track_type"] == tt]
        if heads:
            filtered = [r for r in filtered if r["horse_count"] and heads[0] <= r["horse_count"] <= heads[1]]

        bets = [r for r in filtered if min_odds <= float(r["odds_win"]) <= max_odds]

        if len(bets) < 20:
            continue

        label = {
            "odds": f"{min_odds}-{max_odds}",
            "track": {None: "全", 1: "芝", 2: "ダ"}.get(tt, "全"),
            "heads": f"{heads[0]}+" if heads else "全",
        }

        # --- flat（均一100円）---
        invest_f, ret_f, hits_f, roi_f = _evaluate_bets_flat(bets)
        flat_params = {
            **label,
            "bets": len(bets), "hits": hits_f,
            "roi": round(roi_f, 1),
            "hit_rate": round(hits_f / len(bets) * 100, 1),
        }
        flat_results.append(flat_params)
        if roi_f > best_flat_roi:
            best_flat_roi = roi_f
            best_flat_params = flat_params

        # --- kelly（フラクショナルケリー基準）---
        invest_k, ret_k, hits_k, roi_k, actual_bets_k, final_br = _evaluate_bets_kelly(
            bets, bankroll, kelly_fraction
        )
        if actual_bets_k < 10:
            continue
        kelly_params = {
            **label,
            "bets": actual_bets_k, "hits": hits_k,
            "roi": round(roi_k, 1),
            "hit_rate": round(hits_k / actual_bets_k * 100, 1) if actual_bets_k > 0 else 0,
            "final_bankroll": int(final_br),
            "growth": round((final_br / bankroll - 1) * 100, 1),
        }
        kelly_results.append(kelly_params)
        if roi_k > best_kelly_roi:
            best_kelly_roi = roi_k
            best_kelly_params = kelly_params

    # --- flat結果表示（ROI上位10）---
    flat_results.sort(key=lambda x: x["roi"], reverse=True)
    logger.info("")
    logger.info("=" * 75)
    logger.info("【均一100円】購入フィルタ最適化結果 TOP10")
    logger.info("=" * 75)
    logger.info(f"{'オッズ帯':>10} {'コース':>4} {'頭数':>4} {'賭数':>5} {'的中':>4} {'的中率':>6} {'回収率':>7}")
    logger.info("-" * 75)
    for r in flat_results[:10]:
        logger.info(
            f"{r['odds']:>10} {r['track']:>4} {r['heads']:>4} "
            f"{r['bets']:>5} {r['hits']:>4} {r['hit_rate']:>5.1f}% {r['roi']:>6.1f}%"
        )
    logger.info("")
    logger.info(f"最適フィルタ(flat): オッズ={best_flat_params.get('odds')} "
                f"コース={best_flat_params.get('track')} 頭数={best_flat_params.get('heads')} "
                f"→ 回収率={best_flat_roi:.1f}%")

    # --- kelly結果表示（ROI上位10）---
    kelly_results.sort(key=lambda x: x["roi"], reverse=True)
    logger.info("")
    logger.info("=" * 75)
    logger.info(f"【ケリー基準 ({kelly_fraction}倍)】購入フィルタ最適化結果 TOP10")
    logger.info("=" * 75)
    logger.info(f"{'オッズ帯':>10} {'コース':>4} {'頭数':>4} {'賭数':>5} {'的中':>4} {'的中率':>6} {'回収率':>7} {'最終資金':>10} {'増減率':>6}")
    logger.info("-" * 75)
    for r in kelly_results[:10]:
        logger.info(
            f"{r['odds']:>10} {r['track']:>4} {r['heads']:>4} "
            f"{r['bets']:>5} {r['hits']:>4} {r['hit_rate']:>5.1f}% {r['roi']:>6.1f}% "
            f"{r['final_bankroll']:>9,}円 {r['growth']:>+5.1f}%"
        )
    logger.info("")
    logger.info(f"最適フィルタ(kelly): オッズ={best_kelly_params.get('odds')} "
                f"コース={best_kelly_params.get('track')} 頭数={best_kelly_params.get('heads')} "
                f"→ 回収率={best_kelly_roi:.1f}% "
                f"最終資金={best_kelly_params.get('final_bankroll', 0):,}円")


def run_multi_ticket_optimization(db, years: int = 2, bankroll: float = 100000, kelly_fraction: float = 0.25):
    """
    券種別フィルタ最適化（単勝/複勝/馬連/三連複）
    各券種の特性に合わせた最適パラメータを探索する
    """
    logger.info("=" * 75)
    logger.info("【券種別】購入フィルタ最適化")
    logger.info("=" * 75)

    # --- 単勝 ---
    logger.info("\n■ 単勝（1番人気）")
    run_optimization(db, years, bankroll, kelly_fraction)

    # --- 複勝 ---
    logger.info("\n■ 複勝（1-3番人気）")
    _optimize_place(db, years)

    # --- 馬連 ---
    logger.info("\n■ 馬連（1-2番人気のBOX）")
    _optimize_quinella(db, years)

    # --- 三連複 ---
    logger.info("\n■ 三連複（1-3番人気のBOX）")
    _optimize_trio(db, years)


def _optimize_place(db, years: int):
    """複勝フィルタ最適化（1-3着的中の回収率）"""
    rows = db.execute(text("""
        SELECT
            r.race_key, r.race_date, r.track_type, r.horse_count,
            re.odds_win, re.odds_place_min, re.odds_place_max,
            re.finish_order, re.popularity
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE r.race_date >= CURRENT_DATE - :days
          AND re.finish_order IS NOT NULL
          AND re.popularity BETWEEN 1 AND 3
          AND re.odds_win IS NOT NULL
          AND re.odds_win > 0
        ORDER BY r.race_date, r.race_key
    """), {"days": years * 365}).mappings().all()

    if len(rows) < 100:
        logger.warning(f"データ不足: {len(rows)}件")
        return

    # 人気別に集計
    for pop in [1, 2, 3]:
        pop_rows = [r for r in rows if r["popularity"] == pop]
        if not pop_rows:
            continue
        hits = sum(1 for r in pop_rows if r["finish_order"] and r["finish_order"] <= 3)
        # 複勝オッズの平均で回収率概算
        place_odds = []
        for r in pop_rows:
            if r["finish_order"] and r["finish_order"] <= 3:
                pmin = float(r["odds_place_min"] or 0)
                pmax = float(r["odds_place_max"] or 0)
                avg_odds = (pmin + pmax) / 2 if pmin > 0 else 1.2
                place_odds.append(avg_odds)
        invest = len(pop_rows) * 100
        ret = sum(int(o * 100) for o in place_odds) if place_odds else 0
        roi = ret / invest * 100 if invest > 0 else 0
        hit_rate = hits / len(pop_rows) * 100 if pop_rows else 0
        logger.info(
            f"  {pop}番人気: {len(pop_rows):>5}件 的中{hits:>4}件 "
            f"的中率{hit_rate:>5.1f}% 回収率{roi:>6.1f}%"
        )

    # 芝/ダート別
    for tt_name, tt_val in [("芝", 1), ("ダ", 2)]:
        tt_rows = [r for r in rows if r["track_type"] == tt_val and r["popularity"] == 1]
        if len(tt_rows) < 20:
            continue
        hits = sum(1 for r in tt_rows if r["finish_order"] and r["finish_order"] <= 3)
        invest = len(tt_rows) * 100
        place_odds = []
        for r in tt_rows:
            if r["finish_order"] and r["finish_order"] <= 3:
                pmin = float(r["odds_place_min"] or 0)
                pmax = float(r["odds_place_max"] or 0)
                place_odds.append((pmin + pmax) / 2 if pmin > 0 else 1.2)
        ret = sum(int(o * 100) for o in place_odds) if place_odds else 0
        roi = ret / invest * 100 if invest > 0 else 0
        logger.info(
            f"  1番人気({tt_name}): {len(tt_rows):>5}件 的中{hits:>4}件 "
            f"回収率{roi:>6.1f}%"
        )


def _optimize_quinella(db, years: int):
    """馬連フィルタ最適化（1-2番人気BOXの回収率）"""
    from app.models.race import Payout
    rows = db.execute(text("""
        SELECT
            r.race_key, r.race_date, r.track_type, r.horse_count,
            p.bet_type, p.combination, p.payout
        FROM payouts p
        JOIN races r ON r.id = p.race_id
        WHERE r.race_date >= CURRENT_DATE - :days
          AND p.bet_type = 4
        ORDER BY r.race_date
    """), {"days": years * 365}).mappings().all()

    # 各レースの1-2番人気を取得
    fav_rows = db.execute(text("""
        SELECT
            r.race_key, re.horse_num, re.popularity, r.track_type, r.horse_count
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE r.race_date >= CURRENT_DATE - :days
          AND re.popularity IN (1, 2)
          AND re.finish_order IS NOT NULL
        ORDER BY r.race_key, re.popularity
    """), {"days": years * 365}).mappings().all()

    # レースごとに1-2番人気の馬番を取得
    race_favs = {}
    race_info = {}
    for r in fav_rows:
        rk = r["race_key"]
        if rk not in race_favs:
            race_favs[rk] = []
            race_info[rk] = {"track_type": r["track_type"], "horse_count": r["horse_count"]}
        race_favs[rk].append(r["horse_num"])

    # 馬連払戻と照合
    payouts_by_race = {}
    for p in rows:
        rk = p["race_key"]
        payouts_by_race[rk] = {
            "combination": p["combination"],
            "payout": int(p["payout"]) if p["payout"] else 0,
        }

    total = 0
    hits = 0
    total_return = 0
    for rk, favs in race_favs.items():
        if len(favs) < 2:
            continue
        total += 1
        if rk in payouts_by_race:
            combo = payouts_by_race[rk].get("combination", "")
            # 1-2番人気の組み合わせが的中しているか確認
            f1, f2 = sorted(favs[:2])
            combo_key = f"{f1:02d}{f2:02d}"
            if combo and combo_key in combo:
                hits += 1
                total_return += payouts_by_race[rk]["payout"]

    invest = total * 100
    roi = total_return / invest * 100 if invest > 0 else 0
    hit_rate = hits / total * 100 if total > 0 else 0
    logger.info(
        f"  1-2人気BOX: {total:>5}件 的中{hits:>4}件 "
        f"的中率{hit_rate:>5.1f}% 回収率{roi:>6.1f}%"
    )


def _optimize_trio(db, years: int):
    """三連複フィルタ最適化（1-3番人気BOXの回収率）"""
    rows = db.execute(text("""
        SELECT
            r.race_key, r.race_date, r.track_type, r.horse_count,
            p.bet_type, p.combination, p.payout
        FROM payouts p
        JOIN races r ON r.id = p.race_id
        WHERE r.race_date >= CURRENT_DATE - :days
          AND p.bet_type = 6
        ORDER BY r.race_date
    """), {"days": years * 365}).mappings().all()

    # 各レースの1-3番人気を取得
    fav_rows = db.execute(text("""
        SELECT
            r.race_key, re.horse_num, re.popularity
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE r.race_date >= CURRENT_DATE - :days
          AND re.popularity IN (1, 2, 3)
          AND re.finish_order IS NOT NULL
        ORDER BY r.race_key, re.popularity
    """), {"days": years * 365}).mappings().all()

    race_favs = {}
    for r in fav_rows:
        rk = r["race_key"]
        if rk not in race_favs:
            race_favs[rk] = []
        race_favs[rk].append(r["horse_num"])

    payouts_by_race = {}
    for p in rows:
        payouts_by_race[p["race_key"]] = {
            "combination": p["combination"],
            "payout": int(p["payout"]) if p["payout"] else 0,
        }

    total = 0
    hits = 0
    total_return = 0
    for rk, favs in race_favs.items():
        if len(favs) < 3:
            continue
        total += 1
        if rk in payouts_by_race:
            combo = payouts_by_race[rk].get("combination", "")
            f1, f2, f3 = sorted(favs[:3])
            combo_key = f"{f1:02d}{f2:02d}{f3:02d}"
            if combo and combo_key in combo:
                hits += 1
                total_return += payouts_by_race[rk]["payout"]

    invest = total * 100
    roi = total_return / invest * 100 if invest > 0 else 0
    hit_rate = hits / total * 100 if total > 0 else 0
    logger.info(
        f"  1-3人気BOX: {total:>5}件 的中{hits:>4}件 "
        f"的中率{hit_rate:>5.1f}% 回収率{roi:>6.1f}%"
    )


def main():
    parser = argparse.ArgumentParser(description="購入フィルタ最適化（flat + ケリー基準比較）")
    parser.add_argument("--years", type=int, default=2, help="過去N年のデータを使用")
    parser.add_argument("--bankroll", type=float, default=100000, help="ケリー基準の仮想資金（デフォルト10万円）")
    parser.add_argument("--kelly-fraction", type=float, default=0.25, help="ケリー分数（デフォルト0.25=1/4ケリー）")
    parser.add_argument("--multi-ticket", action="store_true", help="券種別フィルタ最適化も実行")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.multi_ticket:
            run_multi_ticket_optimization(db, args.years, args.bankroll, args.kelly_fraction)
        else:
            run_optimization(db, args.years, args.bankroll, args.kelly_fraction)
    finally:
        db.close()


if __name__ == "__main__":
    main()
