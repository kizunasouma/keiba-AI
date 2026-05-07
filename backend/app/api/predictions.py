"""
予測API + バックテスト + 馬券シミュレーター

エンドポイント:
    GET /races/{race_key}/predict — AI予測（勝率・期待値）
    GET /backtest/summary — 回収率バックテスト（期間・券種・閾値指定・賭け金配分モード）
    GET /backtest/monthly — 月別回収率推移（賭け金配分モード対応）
    POST /simulate — 馬券シミュレーター（過去レースでの仮想購入・賭け金配分モード対応）
"""
from collections import defaultdict
from datetime import date
from enum import Enum
from functools import lru_cache
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.ml.features import build_prediction_features
from app.ml.model import get_model

# 予測結果のインメモリキャッシュ（race_key → (timestamp, response)）
_prediction_cache: dict[str, tuple[float, "PredictionResponse"]] = {}
_CACHE_TTL = 300  # 5分間キャッシュ


# ---------------------------------------------------------------------------
# 賭け金配分ロジック（ケリー基準 / 期待値比例）
# ---------------------------------------------------------------------------

class BetMode(str, Enum):
    """賭け金配分モード"""
    FLAT = "flat"                     # 均一100円（デフォルト）
    KELLY = "kelly"                   # フラクショナルケリー基準
    EV_PROPORTIONAL = "ev_proportional"  # 期待値比例


def calc_kelly_bet(
    win_prob: float,
    odds: float,
    bankroll: float,
    kelly_fraction: float = 0.25,
) -> float:
    """
    ケリー基準による賭け金計算
    f* = (p * b - q) / b  （フルケリー）
    実際の賭け金 = bankroll * f* * kelly_fraction

    Args:
        win_prob: AI推定勝率（0〜1）
        odds: 単勝オッズ
        bankroll: 仮想資金
        kelly_fraction: ケリー分数（デフォルト0.25 = 1/4ケリー）
    Returns:
        賭け金（100円単位に丸め）
    """
    if odds <= 1 or win_prob <= 0 or win_prob >= 1:
        return 0
    b = odds - 1
    q = 1 - win_prob
    kelly_f = (win_prob * b - q) / b
    kelly_f = max(0, kelly_f)
    if kelly_f == 0:
        return 0  # 負の期待値 → 賭けない
    bet = bankroll * kelly_f * kelly_fraction
    # 100円〜資金の5%に制限、100円単位に丸める
    bet = max(100, min(bet, bankroll * 0.05))
    bet = int(bet / 100) * 100
    return float(bet)


def calc_ev_proportional_bet(
    win_prob: float,
    odds: float,
    base_amount: float = 100,
) -> float:
    """
    期待値比例による賭け金計算
    EV = p * odds - 1 が正なら base_amount * (1 + EV * 3)

    Args:
        win_prob: AI推定勝率（0〜1）
        odds: 単勝オッズ
        base_amount: ベース金額（デフォルト100円）
    Returns:
        賭け金（100円単位に丸め）
    """
    ev = win_prob * odds - 1
    if ev <= 0:
        return 0  # EV負 → 賭けない
    bet = base_amount * (1 + ev * 3)  # EVに応じて1〜4倍
    bet = int(bet / 100) * 100
    bet = max(100, bet)
    return float(bet)


def calc_bet_amount(
    bet_mode: BetMode,
    win_prob: float,
    odds: float,
    bankroll: float = 100000,
    kelly_fraction: float = 0.25,
    base_amount: float = 100,
) -> float:
    """賭け金配分モードに応じた賭け金を返す"""
    if bet_mode == BetMode.KELLY:
        return calc_kelly_bet(win_prob, odds, bankroll, kelly_fraction)
    elif bet_mode == BetMode.EV_PROPORTIONAL:
        return calc_ev_proportional_bet(win_prob, odds, base_amount)
    else:
        return base_amount

router = APIRouter(tags=["predictions"])


# ---------------------------------------------------------------------------
# スキーマ
# ---------------------------------------------------------------------------

class BettingPlan(BaseModel):
    """購入プラン（ケリー基準ベース）"""
    bet_amount: int          # 推奨購入金額（100円単位）
    kelly_fraction: float    # ケリー分数
    edge: float              # エッジ（期待値）
    confidence: str          # 確信度（S/A/B/C）

class TicketPlan(BaseModel):
    """1枚の馬券購入プラン"""
    bet_type: str            # 券種名（単勝/複勝/馬連/ワイド/馬単/三連複/三連単）
    combination: str         # 組合せ（例: "3", "3-7", "3-7-12"）
    horses: list[int]        # 対象馬番リスト
    amount: int              # 購入金額（100円単位）
    estimated_odds: float    # 推定オッズ
    win_prob: float          # 的中確率（AI推定）
    expected_value: float    # 期待値
    confidence: str          # 確信度（S/A/B/C）
    reason: str              # 選択理由

class RaceBettingPlan(BaseModel):
    """レース全体の購入プラン"""
    tickets: list[TicketPlan]
    total_invest: int
    total_expected_return: float
    strategy_summary: str    # 戦略サマリー

class PredictionItem(BaseModel):
    entry_id: int
    horse_num: int
    horse_name: str | None
    jockey_name: str | None
    odds_win: float | None
    win_prob: float
    expected_value: float | None = None  # オッズ未確定時はNull
    win_prob_no_odds: float | None = None
    ev_no_odds: float | None = None
    recommendation: str
    ai_comment: str | None = None
    betting_plan: BettingPlan | None = None  # 購入プラン


class PredictionResponse(BaseModel):
    race_key: str
    model_available: bool
    model_type: str = "legacy"
    predictions: list[PredictionItem]
    race_betting_plan: RaceBettingPlan | None = None  # 全券種最適購入プラン
    total_invest: int = 0
    total_expected_return: float = 0
    message: str | None = None


class SimulateRequest(BaseModel):
    """馬券シミュレーションリクエスト"""
    race_keys: list[str]               # 対象レース一覧
    strategy: str = "ai_recommend"      # ai_recommend / favorite / value
    bet_type: str = "win"              # win / place / quinella / trio
    bet_amount: int = 100              # 1レースあたり賭け金（flatモード時）
    ev_threshold: float = 0.0          # 期待値閾値
    bet_mode: str = "flat"             # flat / kelly / ev_proportional
    kelly_fraction: float = 0.25       # ケリー分数（kellyモード用）
    bankroll: float = 100000           # 仮想資金（kellyモード用）


# ---------------------------------------------------------------------------
# AI予測
# ---------------------------------------------------------------------------

@router.get("/races/{race_key}/predict", response_model=PredictionResponse)
def predict_race(race_key: str, db: Session = Depends(get_db)):
    """指定レースの全出走馬に対して勝率・期待値を予測する"""
    # キャッシュチェック（TTL内なら即返却）
    now = time.time()
    if race_key in _prediction_cache:
        cached_time, cached_response = _prediction_cache[race_key]
        if now - cached_time < _CACHE_TTL:
            return cached_response

    model = get_model()

    if not model.is_trained:
        return PredictionResponse(
            race_key=race_key,
            model_available=False,
            predictions=[],
            message="モデルが未学習です。python scripts/train_model.py を実行してください。",
        )

    from app.ml.model import EnsembleModel
    is_ensemble = isinstance(model, EnsembleModel)

    df = build_prediction_features(db, race_key)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"レース {race_key} のデータが見つかりません")

    result_df = model.predict_with_ev(df)

    def _safe_str(v) -> str | None:
        """NaN/None/非文字列をNoneに変換"""
        if v is None:
            return None
        if isinstance(v, float) and (v != v):  # NaN check
            return None
        return str(v) if v else None

    predictions = [
        PredictionItem(
            entry_id=int(row["entry_id"]),
            horse_num=int(row["horse_num"]),
            horse_name=_safe_str(row.get("horse_name")),
            jockey_name=_safe_str(row.get("jockey_name")),
            odds_win=float(row["odds_win_raw"]) if row["odds_win_raw"] is not None and row["odds_win_raw"] == row["odds_win_raw"] else None,
            win_prob=round(float(row["win_prob"]), 4),
            expected_value=round(float(row["expected_value"]), 4) if row["expected_value"] == row["expected_value"] else None,
            win_prob_no_odds=round(float(row["win_prob_no_odds"]), 4) if "win_prob_no_odds" in row and row["win_prob_no_odds"] == row["win_prob_no_odds"] else None,
            ev_no_odds=round(float(row["ev_no_odds"]), 4) if "ev_no_odds" in row and row["ev_no_odds"] == row["ev_no_odds"] else None,
            recommendation=row["recommendation"],
        )
        for _, row in result_df.iterrows()
    ]

    # AI見解テキスト生成
    for pred in predictions:
        pred.ai_comment = _generate_ai_comment(pred, result_df, df)

    # 全券種最適購入プラン生成
    race_plan = _generate_race_betting_plan(predictions, db, race_key)

    # 個別馬の単勝購入プランも維持（後方互換）
    for pred in predictions:
        ticket = next((t for t in race_plan.tickets if t.bet_type == "単勝" and pred.horse_num in t.horses), None)
        if ticket:
            pred.betting_plan = BettingPlan(
                bet_amount=ticket.amount,
                kelly_fraction=0.0,
                edge=ticket.expected_value,
                confidence=ticket.confidence,
            )

    response = PredictionResponse(
        race_key=race_key,
        model_available=True,
        model_type="ensemble" if is_ensemble else "legacy",
        predictions=predictions,
        race_betting_plan=race_plan,
        total_invest=race_plan.total_invest,
        total_expected_return=race_plan.total_expected_return,
    )
    # キャッシュに保存（5分間有効）
    _prediction_cache[race_key] = (time.time(), response)
    return response


def _generate_race_betting_plan(
    predictions: list[PredictionItem],
    db: Session,
    race_key: str,
    bankroll: float = 100000,
) -> RaceBettingPlan:
    """
    全券種（単勝/複勝/馬連/ワイド/馬単/三連複/三連単）から
    AIが最適な買い目を選択し、ケリー基準で金額を配分する。
    """
    tickets: list[TicketPlan] = []

    # 勝率順にソート
    sorted_preds = sorted(predictions, key=lambda p: p.win_prob, reverse=True)
    # EV+の馬
    ev_plus = [p for p in sorted_preds if p.expected_value is not None and p.expected_value > 0 and p.odds_win and p.odds_win > 1]
    # 上位馬（複勝圏候補）
    top_n = sorted_preds[:5]  # 上位5頭

    # 各馬の勝率辞書
    prob_map = {p.horse_num: p.win_prob for p in predictions}
    odds_map = {p.horse_num: (p.odds_win or 50.0) for p in predictions}

    # === 1. 単勝 ===
    for p in ev_plus[:3]:  # EV+上位3頭まで
        ev = p.win_prob * p.odds_win - 1
        bet = _kelly_bet(p.win_prob, p.odds_win, bankroll, ev)
        if bet > 0:
            tickets.append(TicketPlan(
                bet_type="単勝", combination=str(p.horse_num),
                horses=[p.horse_num], amount=bet,
                estimated_odds=p.odds_win, win_prob=round(p.win_prob, 4),
                expected_value=round(ev, 4),
                confidence=_ev_to_confidence(ev),
                reason=f"AI勝率{p.win_prob*100:.1f}%に対しオッズ{p.odds_win:.1f}倍",
            ))

    # === 2. 複勝 ===
    for p in top_n[:3]:
        # 複勝確率 ≈ 上位3着以内確率（勝率の約2.5倍で近似）
        place_prob = min(p.win_prob * 2.5, 0.95)
        # 複勝オッズ推定（単勝の1/3〜1/4）
        place_odds = max((p.odds_win or 10) * 0.3, 1.1)
        ev = place_prob * place_odds - 1
        if ev > 0:
            bet = _kelly_bet(place_prob, place_odds, bankroll, ev)
            if bet > 0:
                tickets.append(TicketPlan(
                    bet_type="複勝", combination=str(p.horse_num),
                    horses=[p.horse_num], amount=bet,
                    estimated_odds=round(place_odds, 1), win_prob=round(place_prob, 4),
                    expected_value=round(ev, 4),
                    confidence=_ev_to_confidence(ev),
                    reason=f"複勝圏{place_prob*100:.0f}%。堅い軸として",
                ))

    # === 3. 馬連・ワイド・馬単 ===
    if len(top_n) >= 2:
        for i in range(min(3, len(top_n))):
            for j in range(i + 1, min(4, len(top_n))):
                h1, h2 = top_n[i], top_n[j]
                # 馬連確率 ≈ P(1着h1)*P(2着h2|h1勝) + P(1着h2)*P(2着h1|h2勝)
                p1 = h1.win_prob
                p2 = h2.win_prob
                # 条件付き2着確率の近似
                p_quinella = p1 * (p2 / (1 - p1)) + p2 * (p1 / (1 - p2))
                p_quinella = min(p_quinella, 0.5)

                # 馬連オッズ推定
                quinella_odds = max(1 / p_quinella * 0.75, 1.5) if p_quinella > 0 else 100
                ev_q = p_quinella * quinella_odds - 1
                if ev_q > -0.1:  # 軽いマイナスEVでも候補に入れる
                    bet = _kelly_bet(p_quinella, quinella_odds, bankroll, ev_q) if ev_q > 0 else 100
                    if ev_q > 0 and bet > 0:
                        tickets.append(TicketPlan(
                            bet_type="馬連", combination=f"{h1.horse_num}-{h2.horse_num}",
                            horses=[h1.horse_num, h2.horse_num], amount=bet,
                            estimated_odds=round(quinella_odds, 1), win_prob=round(p_quinella, 4),
                            expected_value=round(ev_q, 4),
                            confidence=_ev_to_confidence(ev_q),
                            reason=f"上位{i+1}位×{j+1}位の組合せ",
                        ))

                # ワイド確率（3着以内に2頭）
                pp1 = min(p1 * 2.5, 0.95)
                pp2 = min(p2 * 2.5, 0.95)
                p_wide = pp1 * pp2 * 0.8  # 独立でない分を補正
                p_wide = min(p_wide, 0.6)
                wide_odds = max(1 / p_wide * 0.75, 1.1) if p_wide > 0 else 50
                ev_w = p_wide * wide_odds - 1
                if ev_w > 0:
                    bet = _kelly_bet(p_wide, wide_odds, bankroll, ev_w)
                    if bet > 0:
                        tickets.append(TicketPlan(
                            bet_type="ワイド", combination=f"{h1.horse_num}-{h2.horse_num}",
                            horses=[h1.horse_num, h2.horse_num], amount=bet,
                            estimated_odds=round(wide_odds, 1), win_prob=round(p_wide, 4),
                            expected_value=round(ev_w, 4),
                            confidence=_ev_to_confidence(ev_w),
                            reason=f"堅い2頭のワイド。的中率{p_wide*100:.0f}%",
                        ))

        # 馬単（1着固定→2着）
        if top_n[0].win_prob > 0.12:
            h1 = top_n[0]
            for h2 in top_n[1:3]:
                p_exacta = h1.win_prob * (h2.win_prob / (1 - h1.win_prob))
                exacta_odds = max(1 / p_exacta * 0.75, 3.0) if p_exacta > 0 else 200
                ev_e = p_exacta * exacta_odds - 1
                if ev_e > 0:
                    bet = _kelly_bet(p_exacta, exacta_odds, bankroll, ev_e)
                    if bet > 0:
                        tickets.append(TicketPlan(
                            bet_type="馬単", combination=f"{h1.horse_num}→{h2.horse_num}",
                            horses=[h1.horse_num, h2.horse_num], amount=bet,
                            estimated_odds=round(exacta_odds, 1), win_prob=round(p_exacta, 4),
                            expected_value=round(ev_e, 4),
                            confidence=_ev_to_confidence(ev_e),
                            reason=f"本命{h1.horse_num}番の1着固定",
                        ))

    # === 4. 三連複 ===
    if len(top_n) >= 3:
        for i in range(min(2, len(top_n))):
            for j in range(i + 1, min(4, len(top_n))):
                for k in range(j + 1, min(5, len(top_n))):
                    h1, h2, h3 = top_n[i], top_n[j], top_n[k]
                    # 三連複確率（3頭が全て3着以内）
                    pp1 = min(h1.win_prob * 2.5, 0.95)
                    pp2 = min(h2.win_prob * 2.5, 0.90)
                    pp3 = min(h3.win_prob * 2.5, 0.85)
                    p_trio = pp1 * pp2 * pp3 * 0.5  # 相関補正
                    p_trio = min(p_trio, 0.3)
                    trio_odds = max(1 / p_trio * 0.75, 5.0) if p_trio > 0 else 500
                    ev_t = p_trio * trio_odds - 1
                    if ev_t > 0:
                        bet = _kelly_bet(p_trio, trio_odds, bankroll, ev_t)
                        if bet > 0:
                            nums = sorted([h1.horse_num, h2.horse_num, h3.horse_num])
                            tickets.append(TicketPlan(
                                bet_type="三連複",
                                combination=f"{nums[0]}-{nums[1]}-{nums[2]}",
                                horses=nums, amount=bet,
                                estimated_odds=round(trio_odds, 1), win_prob=round(p_trio, 4),
                                expected_value=round(ev_t, 4),
                                confidence=_ev_to_confidence(ev_t),
                                reason=f"上位馬3頭の三連複",
                            ))

    # === 5. 三連単 ===
    if len(top_n) >= 3 and top_n[0].win_prob > 0.15:
        h1 = top_n[0]
        for h2 in top_n[1:3]:
            for h3 in top_n[1:4]:
                if h2.horse_num == h3.horse_num:
                    continue
                p_trifecta = (h1.win_prob
                              * (h2.win_prob / (1 - h1.win_prob))
                              * (h3.win_prob / (1 - h1.win_prob - h2.win_prob + 0.001)))
                p_trifecta = min(p_trifecta, 0.1)
                trifecta_odds = max(1 / p_trifecta * 0.75, 10.0) if p_trifecta > 0 else 1000
                ev_tf = p_trifecta * trifecta_odds - 1
                if ev_tf > 0.1:  # 三連単はEV高め要求
                    bet = _kelly_bet(p_trifecta, trifecta_odds, bankroll, ev_tf)
                    if bet > 0:
                        tickets.append(TicketPlan(
                            bet_type="三連単",
                            combination=f"{h1.horse_num}→{h2.horse_num}→{h3.horse_num}",
                            horses=[h1.horse_num, h2.horse_num, h3.horse_num],
                            amount=bet,
                            estimated_odds=round(trifecta_odds, 1),
                            win_prob=round(p_trifecta, 4),
                            expected_value=round(ev_tf, 4),
                            confidence=_ev_to_confidence(ev_tf),
                            reason=f"本命{h1.horse_num}番の1着固定三連単",
                        ))

    # EV順でソートし、上位の買い目を選択
    tickets.sort(key=lambda t: t.expected_value, reverse=True)

    # 合計購入額が資金の30%を超えないよう調整
    max_total = bankroll * 0.30
    selected: list[TicketPlan] = []
    running_total = 0
    for t in tickets:
        if running_total + t.amount > max_total:
            # 残りの枠に収まるよう金額調整
            remaining = int((max_total - running_total) / 100) * 100
            if remaining >= 100:
                t.amount = remaining
                selected.append(t)
                running_total += remaining
            break
        selected.append(t)
        running_total += t.amount

    total_invest = sum(t.amount for t in selected)
    total_er = sum(t.amount * (1 + t.expected_value) for t in selected)

    # 戦略サマリー生成
    bet_types = list(set(t.bet_type for t in selected))
    if not selected:
        summary = "EV+の買い目なし。見送り推奨"
    elif len(bet_types) == 1:
        summary = f"{bet_types[0]}集中戦略。{len(selected)}点/{total_invest:,}円"
    else:
        summary = f"{'/'.join(bet_types)}の分散戦略。{len(selected)}点/{total_invest:,}円"

    return RaceBettingPlan(
        tickets=selected,
        total_invest=total_invest,
        total_expected_return=round(total_er, 0),
        strategy_summary=summary,
    )


def _kelly_bet(win_prob: float, odds: float, bankroll: float, ev: float) -> int:
    """ケリー基準で購入金額を計算（100円単位）"""
    if odds <= 1 or win_prob <= 0:
        return 0
    b = odds - 1
    q = 1 - win_prob
    full_kelly = max(0, (win_prob * b - q) / b)
    if full_kelly == 0:
        return 0

    # 確信度に応じたケリー分数
    if ev > 0.5:
        frac = 0.25
    elif ev > 0.2:
        frac = 0.20
    elif ev > 0.05:
        frac = 0.15
    else:
        frac = 0.10

    bet = bankroll * full_kelly * frac
    bet = max(100, min(bet, bankroll * 0.10))
    return int(bet / 100) * 100


def _ev_to_confidence(ev: float) -> str:
    """EV値から確信度を返す"""
    if ev > 0.5:
        return "S"
    elif ev > 0.2:
        return "A"
    elif ev > 0.05:
        return "B"
    return "C"


def _generate_ai_comment(pred: PredictionItem, result_df, feature_df) -> str:
    """
    AI見解テキストを特徴量ベースで自動生成する。
    各馬について「直近成績・コース適性・脚質・騎手・調教・斤量・血統・タイム」
    の多軸から詳細な分析コメントを生成。全馬に見解を付与する。
    """
    row = feature_df[feature_df["entry_id"] == pred.entry_id]
    if row.empty:
        return "データ不足のため分析不可"

    r = row.iloc[0]
    sections = []  # 各セクションの文を格納

    # === 1. 直近成績 ===
    avg_finish = r.get("recent_avg_finish", 5.0)
    win_count = int(r.get("recent_win_count", 0) or 0)
    avg_5 = r.get("recent_5_avg_finish", 5.0)
    best_5 = int(r.get("recent_5_best_finish", 5) or 5)

    if avg_finish <= 1.5:
        sections.append(f"【好調】直近3走平均{avg_finish:.1f}着と絶好調。勢いは本物")
    elif avg_finish <= 3.0:
        sections.append(f"【好調】直近3走平均{avg_finish:.1f}着で安定上位。{win_count}勝")
    elif avg_finish <= 5.0:
        sections.append(f"【普通】直近3走平均{avg_finish:.1f}着。掲示板圏内だが勝ちきれず")
    elif avg_finish <= 8.0:
        sections.append(f"【低調】直近3走平均{avg_finish:.1f}着。近走は精彩を欠く")
    else:
        sections.append(f"【不振】直近3走平均{avg_finish:.1f}着と大敗続き。巻き返しは困難")

    if best_5 == 1:
        sections.append(f"直近5走で勝利あり（最高{best_5}着）")
    elif best_5 <= 3:
        sections.append(f"直近5走の最高着順は{best_5}着。複勝圏の実績あり")

    # === 2. コース適性 ===
    same_dist = r.get("same_distance_win_rate", 0) or 0
    same_track = r.get("same_track_win_rate", 0) or 0
    same_venue = r.get("same_venue_win_rate", 0) or 0

    course_parts = []
    if same_dist > 0.2:
        course_parts.append(f"同距離帯勝率{same_dist*100:.0f}%")
    elif same_dist > 0.1:
        course_parts.append(f"同距離帯勝率{same_dist*100:.0f}%（まずまず）")
    if same_track > 0.2:
        course_parts.append(f"同コース勝率{same_track*100:.0f}%")
    if same_venue > 0.15:
        course_parts.append(f"同会場での好走歴あり（勝率{same_venue*100:.0f}%）")
    if course_parts:
        sections.append("【コース適性】" + "、".join(course_parts))
    elif same_dist == 0 and same_track == 0:
        sections.append("【コース適性】同条件での実績なし。未知数")

    # === 3. 脚質・展開 ===
    corner4 = r.get("recent_avg_corner4", 8.0) or 8.0
    corner1 = r.get("recent_avg_corner1", 8.0) or 8.0
    corner_imp = r.get("recent_corner_improvement", 0) or 0
    pace = r.get("race_pace_score", 50) or 50

    if corner4 <= 2:
        style = "逃げ・番手"
        style_detail = "前に行って粘り込むタイプ"
    elif corner4 <= 4:
        style = "先行"
        style_detail = "好位から抜け出す王道の競馬"
    elif corner4 <= 7:
        style = "差し"
        style_detail = "中団から末脚を活かす"
    else:
        style = "追込"
        style_detail = "後方一気の脚質。展開次第"

    pace_text = "ハイペース" if pace > 65 else "スローペース" if pace < 35 else "平均ペース"
    sections.append(f"【脚質】{style}。{style_detail}。{pace_text}予想")

    if corner_imp > 3:
        sections.append("コーナーで大きく順位を上げる末脚が武器")
    elif corner_imp < -2:
        sections.append("コーナーで順位を下げる傾向。位置取りに不安")

    # === 4. 騎手・調教師 ===
    jwin = r.get("jockey_win_rate", 0) or 0
    twin = r.get("trainer_win_rate", 0) or 0
    jchange = int(r.get("jockey_change", 0) or 0)
    combo = r.get("jockey_horse_combo_rate", 0) or 0

    jockey_parts = []
    if jwin > 0.15:
        jockey_parts.append(f"騎手勝率{jwin*100:.1f}%のトップジョッキー")
    elif jwin > 0.08:
        jockey_parts.append(f"騎手勝率{jwin*100:.1f}%")
    else:
        jockey_parts.append(f"騎手勝率{jwin*100:.1f}%と低め")
    if twin > 0.12:
        jockey_parts.append(f"調教師勝率{twin*100:.1f}%で厩舎力高い")
    if jchange == 1:
        jockey_parts.append("今回乗り替わり")
    if combo > 0.2:
        jockey_parts.append(f"このコンビの相性良好（勝率{combo*100:.0f}%）")
    sections.append("【騎手/厩舎】" + "。".join(jockey_parts))

    # === 5. 調教 ===
    t_score = r.get("training_rating_score", 50) or 50
    t_3f = r.get("training_last_3f", 0) or 0
    t_days = int(r.get("training_days_before", 0) or 0)

    if t_score > 70:
        sections.append(f"【調教】高評価（偏差値{t_score:.0f}）。仕上がり良好")
    elif t_score > 55:
        sections.append(f"【調教】普通（偏差値{t_score:.0f}）。平均的な仕上がり")
    elif t_score > 0:
        sections.append(f"【調教】低調（偏差値{t_score:.0f}）。状態面に不安")

    # === 6. 斤量 ===
    wc = r.get("weight_carry", 0) or 0
    wcd = r.get("weight_carry_diff", 0) or 0
    wcpk = r.get("weight_carry_per_kg", 0) or 0

    weight_parts = []
    if wcd < -2:
        weight_parts.append(f"斤量{wc:.0f}kg（レース内比-{abs(wcd):.1f}kg）で軽量有利")
    elif wcd > 2:
        weight_parts.append(f"斤量{wc:.0f}kg（レース内比+{wcd:.1f}kg）でトップハンデ")
    if wcpk > 0.13:
        weight_parts.append("体重比の負荷がやや大きい")
    if weight_parts:
        sections.append("【斤量】" + "。".join(weight_parts))

    # === 7. 血統 ===
    lineage_apt = r.get("lineage_track_aptitude", 0) or 0
    lineage_cond = r.get("lineage_cond_rate", 0) or 0

    if lineage_apt > 0.15:
        sections.append(f"【血統】馬場適性の高い血統（適性値{lineage_apt*100:.0f}%）")
    elif lineage_apt > 0.08:
        sections.append("【血統】馬場への適性は平均的")
    if lineage_cond > 0.15:
        sections.append("馬場状態との相性良好")

    # === 8. タイム指数 ===
    best_si = r.get("recent_best_speed_index", 0) or 0
    avg_si = r.get("recent_avg_speed_index", 0) or 0
    si_std = r.get("recent_speed_index_std", 0) or 0

    if best_si > 65:
        sections.append(f"【指数】最高SP指数{best_si:.1f}は上位。地力あり")
    elif best_si > 50:
        sections.append(f"【指数】最高SP指数{best_si:.1f}。平均的な能力")
    elif best_si > 0:
        sections.append(f"【指数】最高SP指数{best_si:.1f}。能力面で見劣り")

    if si_std > 10:
        sections.append("走りにムラがあり安定感に欠ける")
    elif si_std < 3 and avg_si > 50:
        sections.append("安定したパフォーマンスが強み")

    # === 9. 総合判定 ===
    if pred.win_prob > 0.15:
        sections.append("【総合】勝率{:.1f}%。有力候補".format(pred.win_prob * 100))
    elif pred.win_prob > 0.08:
        sections.append("【総合】勝率{:.1f}%。上位争い可能".format(pred.win_prob * 100))
    elif pred.win_prob > 0.04:
        sections.append("【総合】勝率{:.1f}%。穴馬として一考".format(pred.win_prob * 100))
    else:
        sections.append("【総合】勝率{:.1f}%。厳しい評価".format(pred.win_prob * 100))

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# バックテスト（単勝ベース + 券種別）
# ---------------------------------------------------------------------------

@router.get("/backtest/summary")
def backtest_summary(
    days: int = Query(30, le=365, description="過去N日間（date_from未指定時に使用）"),
    ev_threshold: float = Query(0.0, description="期待値閾値"),
    min_odds: float = Query(1.0, description="最低オッズ"),
    max_odds: float = Query(999.0, description="最高オッズ"),
    track_type: int | None = Query(None, description="1=芝,2=ダート"),
    grade: int | None = Query(None, description="グレード"),
    bet_mode: BetMode = Query(BetMode.FLAT, description="賭け金配分: flat/kelly/ev_proportional"),
    kelly_fraction: float = Query(0.25, ge=0.01, le=1.0, description="ケリー分数（1/4ケリー=0.25）"),
    bankroll: float = Query(100000, ge=1000, description="仮想資金（ケリー基準用）"),
    date_from: str | None = Query(None, description="開始日（YYYY-MM-DD）"),
    date_to: str | None = Query(None, description="終了日（YYYY-MM-DD）"),
    db: Session = Depends(get_db),
):
    """回収率バックテスト（フィルター対応・賭け金配分モード対応）"""
    where_extra = ""
    params: dict = {"days": days}
    if date_from:
        where_extra += " AND r.race_date >= :date_from"
        params["date_from"] = date_from
    if date_to:
        where_extra += " AND r.race_date <= :date_to"
        params["date_to"] = date_to
    if track_type:
        where_extra += " AND r.track_type = :track_type"
        params["track_type"] = track_type
    if grade:
        where_extra += " AND r.grade = :grade"
        params["grade"] = grade

    rows = db.execute(sql_text(f"""
        SELECT r.race_key, r.race_date, r.race_name, r.race_num, r.venue_code,
               r.horse_count, r.distance, r.track_type,
               re.horse_num, re.finish_order, re.odds_win, re.popularity
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE r.race_date >= CURRENT_DATE - :days
          AND re.finish_order IS NOT NULL AND re.finish_order > 0
          AND re.odds_win IS NOT NULL AND re.odds_win > 0
          {where_extra}
        ORDER BY r.race_date, r.race_key, re.horse_num
    """), params).mappings().all()

    if not rows:
        return {
            "days": days, "bet_mode": bet_mode.value,
            "total_races": 0, "total_bets": 0, "roi": 0, "hit_rate": 0, "daily": [],
        }

    # レースごとに集計
    from itertools import groupby
    daily = defaultdict(lambda: {"invest": 0, "ret": 0, "bets": 0, "hits": 0})
    total_bets = total_invest = total_return = total_hits = 0
    skipped_by_mode = 0
    race_count = 0
    current_bankroll = bankroll
    bet_history: list[dict] = []  # 的中履歴

    VENUE_NAME = {'01':'札幌','02':'函館','03':'福島','04':'新潟','05':'東京',
                  '06':'中山','07':'中京','08':'京都','09':'阪神','10':'小倉'}

    for rk, entries_iter in groupby(rows, key=lambda r: r["race_key"]):
        entries = list(entries_iter)
        race_count += 1
        # オッズ順でソート（人気順の代替）
        by_odds = sorted(entries, key=lambda x: float(x["odds_win"]))
        meta = entries[0]  # レース情報
        venue = VENUE_NAME.get(meta["venue_code"], meta["venue_code"])
        race_label = f"{venue}{meta['race_num']}R"
        dt = str(meta["race_date"])

        # 人気別の概算勝率（バックテスト用）
        pop_win_rates = {1: 0.33, 2: 0.19, 3: 0.13, 4: 0.10, 5: 0.07,
                         6: 0.05, 7: 0.04, 8: 0.03}

        # === 単勝: 1-3番人気で最もEV+の馬 ===
        candidates = by_odds[:3]  # 上位3頭を候補に
        best_candidate = None
        best_ev = -999
        for cand in candidates:
            c_odds = float(cand["odds_win"])
            c_pop = int(cand.get("popularity", 1) or 1)
            c_wp = pop_win_rates.get(c_pop, 0.02)
            c_ev = c_wp * c_odds - 1
            if c_ev > best_ev:
                best_ev = c_ev
                best_candidate = cand
        best = best_candidate or by_odds[0]
        odds = float(best["odds_win"])
        win_prob = 0.0  # 複勝計算でも参照するため事前定義
        if odds >= min_odds and odds <= max_odds:
            pop = int(best.get("popularity", 1) or 1)
            win_prob = pop_win_rates.get(pop, 0.02)
            ev = win_prob * odds - 1
            if ev >= ev_threshold:
                bet_amount = calc_bet_amount(bet_mode, win_prob, odds, current_bankroll, kelly_fraction)
                if bet_amount > 0:
                    is_hit = best["finish_order"] == 1
                    payout = int(odds * bet_amount) if is_hit else 0
                    total_bets += 1; total_invest += bet_amount
                    daily[dt]["invest"] += bet_amount; daily[dt]["bets"] += 1
                    bet_history.append({
                        "race_key": rk, "race_date": dt, "race_label": race_label,
                        "race_name": meta.get("race_name") or "",
                        "bet_type": "単勝", "combination": str(int(best["horse_num"])),
                        "horse_num": int(best["horse_num"]), "odds": odds, "popularity": pop,
                        "bet_amount": int(bet_amount), "finish_order": int(best["finish_order"]),
                        "payout": payout, "profit": payout - int(bet_amount), "hit": is_hit,
                    })
                    if is_hit:
                        total_return += payout; total_hits += 1
                        daily[dt]["ret"] += payout; daily[dt]["hits"] += 1
                        if bet_mode == BetMode.KELLY: current_bankroll += payout - bet_amount
                    else:
                        if bet_mode == BetMode.KELLY:
                            current_bankroll -= bet_amount
                            current_bankroll = max(current_bankroll, 1000)

        # === 複勝: 1番人気 ===
        if odds >= min_odds:
            place_prob = min(win_prob * 2.5, 0.95) if win_prob > 0 else 0.3
            place_odds = max(odds * 0.3, 1.1)
            place_ev = place_prob * place_odds - 1
            if place_ev >= ev_threshold * 0.5:  # 複勝は閾値緩め
                place_bet = calc_bet_amount(bet_mode, place_prob, place_odds, current_bankroll, kelly_fraction)
                if place_bet > 0:
                    is_place = best["finish_order"] <= 3
                    place_payout = int(place_odds * place_bet) if is_place else 0
                    total_bets += 1; total_invest += place_bet
                    daily[dt]["invest"] += place_bet; daily[dt]["bets"] += 1
                    bet_history.append({
                        "race_key": rk, "race_date": dt, "race_label": race_label,
                        "race_name": meta.get("race_name") or "",
                        "bet_type": "複勝", "combination": str(int(best["horse_num"])),
                        "horse_num": int(best["horse_num"]), "odds": round(place_odds, 1),
                        "popularity": pop, "bet_amount": int(place_bet),
                        "finish_order": int(best["finish_order"]),
                        "payout": place_payout, "profit": place_payout - int(place_bet),
                        "hit": is_place,
                    })
                    if is_place:
                        total_return += place_payout; total_hits += 1
                        daily[dt]["ret"] += place_payout; daily[dt]["hits"] += 1
                        if bet_mode == BetMode.KELLY: current_bankroll += place_payout - place_bet
                    else:
                        if bet_mode == BetMode.KELLY:
                            current_bankroll -= place_bet
                            current_bankroll = max(current_bankroll, 1000)

        # === 馬連: 1-2番人気 ===
        if len(by_odds) >= 2:
            h1, h2 = by_odds[0], by_odds[1]
            o1, o2 = float(h1["odds_win"]), float(h2["odds_win"])
            p1 = pop_win_rates.get(int(h1.get("popularity", 1) or 1), 0.02)
            p2 = pop_win_rates.get(int(h2.get("popularity", 2) or 2), 0.02)
            q_prob = p1 * (p2 / (1 - p1)) + p2 * (p1 / (1 - p2))
            q_odds = max(1 / q_prob * 0.75, 2.0) if q_prob > 0 else 50
            q_ev = q_prob * q_odds - 1
            if q_ev >= ev_threshold:
                q_bet = calc_bet_amount(bet_mode, q_prob, q_odds, current_bankroll, kelly_fraction)
                if q_bet > 0:
                    top2 = sorted([int(h1["finish_order"]), int(h2["finish_order"])])
                    is_q_hit = top2 == [1, 2]
                    q_payout = int(q_odds * q_bet) if is_q_hit else 0
                    combo = f"{int(h1['horse_num'])}-{int(h2['horse_num'])}"
                    total_bets += 1; total_invest += q_bet
                    daily[dt]["invest"] += q_bet; daily[dt]["bets"] += 1
                    bet_history.append({
                        "race_key": rk, "race_date": dt, "race_label": race_label,
                        "race_name": meta.get("race_name") or "",
                        "bet_type": "馬連", "combination": combo,
                        "horse_num": int(h1["horse_num"]), "odds": round(q_odds, 1),
                        "popularity": int(h1.get("popularity", 1) or 1),
                        "bet_amount": int(q_bet), "finish_order": int(h1["finish_order"]),
                        "payout": q_payout, "profit": q_payout - int(q_bet), "hit": is_q_hit,
                    })
                    if is_q_hit:
                        total_return += q_payout; total_hits += 1
                        daily[dt]["ret"] += q_payout; daily[dt]["hits"] += 1
                        if bet_mode == BetMode.KELLY: current_bankroll += q_payout - q_bet
                    else:
                        if bet_mode == BetMode.KELLY:
                            current_bankroll -= q_bet
                            current_bankroll = max(current_bankroll, 1000)

    roi = round(total_return / total_invest * 100, 1) if total_invest > 0 else 0
    hit_rate = round(total_hits / total_bets * 100, 1) if total_bets > 0 else 0
    avg_bet = round(total_invest / total_bets) if total_bets > 0 else 0

    result = {
        "days": days, "ev_threshold": ev_threshold,
        "bet_mode": bet_mode.value,
        "total_races": race_count, "total_bets": total_bets,
        "total_invest": int(total_invest), "total_return": int(total_return),
        "profit": int(total_return - total_invest),
        "roi": roi, "hit_rate": hit_rate,
        "avg_bet": avg_bet,
        "daily": [{"date": d, **v} for d, v in sorted(daily.items())],
        "bet_history": sorted(bet_history, key=lambda x: (-x.get("profit", 0), x["race_date"])),
    }

    # ケリー基準の追加情報
    if bet_mode == BetMode.KELLY:
        result["kelly_fraction"] = kelly_fraction
        result["initial_bankroll"] = int(bankroll)
        result["final_bankroll"] = int(current_bankroll)
        result["bankroll_growth"] = round((current_bankroll / bankroll - 1) * 100, 1)
        result["skipped_negative_ev"] = skipped_by_mode
    elif bet_mode == BetMode.EV_PROPORTIONAL:
        result["skipped_negative_ev"] = skipped_by_mode

    return result


# ---------------------------------------------------------------------------
# 条件別バックテスト（v5追加）
# ---------------------------------------------------------------------------

@router.get("/backtest/breakdown")
def backtest_breakdown(
    days: int = Query(90, le=365, description="過去N日間"),
    db: Session = Depends(get_db),
):
    """
    条件別バックテスト分析（1番人気の回収率を複数軸で分解）
    - トラック別（芝/ダート）
    - グレード別
    - 距離帯別（短距離/マイル/中距離/長距離）
    - 馬場状態別
    - 頭数別
    - 会場別
    """
    rows = db.execute(sql_text("""
        SELECT r.race_key, r.race_date, r.track_type, r.grade,
               r.distance, r.track_cond, r.horse_count, r.venue_code,
               re.odds_win, re.finish_order, re.popularity
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE r.race_date >= CURRENT_DATE - :days
          AND re.finish_order IS NOT NULL AND re.finish_order > 0
          AND re.odds_win IS NOT NULL AND re.odds_win > 0
          AND re.odds_win > 0
          AND re.popularity = 1
        ORDER BY r.race_date
    """), {"days": days}).mappings().all()

    def _calc_roi(data):
        """データリストからROIを計算"""
        if not data:
            return {"count": 0, "hits": 0, "hit_rate": 0, "roi": 0}
        invest = len(data) * 100
        hits = sum(1 for r in data if r["finish_order"] == 1)
        ret = sum(int(float(r["odds_win"]) * 100) for r in data if r["finish_order"] == 1)
        return {
            "count": len(data),
            "hits": hits,
            "hit_rate": round(hits / len(data) * 100, 1) if data else 0,
            "roi": round(ret / invest * 100, 1) if invest > 0 else 0,
        }

    # トラック別
    track_breakdown = {}
    for label, val in [("芝", 1), ("ダート", 2)]:
        filtered = [r for r in rows if r["track_type"] == val]
        track_breakdown[label] = _calc_roi(filtered)

    # グレード別
    grade_breakdown = {}
    for label, val in [("G1", 1), ("G2", 2), ("G3", 3), ("OP/L", 5), ("条件戦", 10)]:
        if val == 10:
            filtered = [r for r in rows if r["grade"] and r["grade"] >= 10]
        else:
            filtered = [r for r in rows if r["grade"] == val]
        if filtered:
            grade_breakdown[label] = _calc_roi(filtered)

    # 距離帯別
    dist_breakdown = {}
    for label, lo, hi in [("短距離", 0, 1400), ("マイル", 1401, 1800),
                          ("中距離", 1801, 2200), ("長距離", 2201, 9999)]:
        filtered = [r for r in rows if lo <= (r["distance"] or 0) <= hi]
        if filtered:
            dist_breakdown[label] = _calc_roi(filtered)

    # 馬場状態別
    cond_breakdown = {}
    cond_labels = {1: "良", 2: "稍重", 3: "重", 4: "不良"}
    for val, label in cond_labels.items():
        filtered = [r for r in rows if r["track_cond"] == val]
        if filtered:
            cond_breakdown[label] = _calc_roi(filtered)

    # 頭数別
    head_breakdown = {}
    for label, lo, hi in [("少頭数(≤8)", 0, 8), ("中頭数(9-13)", 9, 13),
                          ("多頭数(14+)", 14, 99)]:
        filtered = [r for r in rows if lo <= (r["horse_count"] or 0) <= hi]
        if filtered:
            head_breakdown[label] = _calc_roi(filtered)

    # 会場別
    venue_names = {
        "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
        "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
    }
    venue_breakdown = {}
    for code, name in venue_names.items():
        filtered = [r for r in rows if r["venue_code"] == code]
        if filtered:
            venue_breakdown[name] = _calc_roi(filtered)

    return {
        "days": days,
        "total": _calc_roi(rows),
        "by_track": track_breakdown,
        "by_grade": grade_breakdown,
        "by_distance": dist_breakdown,
        "by_condition": cond_breakdown,
        "by_head_count": head_breakdown,
        "by_venue": venue_breakdown,
    }


# ---------------------------------------------------------------------------
# 月別回収率推移
# ---------------------------------------------------------------------------

@router.get("/backtest/monthly")
def backtest_monthly(
    months: int = Query(12, le=60, description="過去N ヶ月"),
    bet_mode: BetMode = Query(BetMode.FLAT, description="賭け金配分: flat/kelly/ev_proportional"),
    kelly_fraction: float = Query(0.25, ge=0.01, le=1.0, description="ケリー分数"),
    bankroll: float = Query(100000, ge=1000, description="仮想資金"),
    db: Session = Depends(get_db),
):
    """月別の回収率推移（賭け金配分モード対応）"""

    # flatモードは従来の高速SQLで処理
    if bet_mode == BetMode.FLAT:
        rows = db.execute(sql_text("""
            WITH ranked AS (
                SELECT
                    r.race_key,
                    TO_CHAR(r.race_date, 'YYYY-MM') AS ym,
                    re.horse_num, re.finish_order, re.odds_win,
                    ROW_NUMBER() OVER (PARTITION BY r.race_key ORDER BY re.odds_win ASC) AS rn
                FROM race_entries re
                JOIN races r ON r.id = re.race_id
                WHERE r.race_date >= CURRENT_DATE - (:months * 30)
                  AND re.finish_order IS NOT NULL
                  AND re.odds_win IS NOT NULL
                  AND re.odds_win > 0
            )
            SELECT ym,
                COUNT(DISTINCT race_key) AS races,
                COUNT(*) FILTER (WHERE rn = 1) AS bets,
                COUNT(*) FILTER (WHERE rn = 1 AND finish_order = 1) AS hits,
                SUM(CASE WHEN rn = 1 THEN 100 ELSE 0 END) AS invest,
                SUM(CASE WHEN rn = 1 AND finish_order = 1 THEN ROUND(odds_win * 100) ELSE 0 END) AS ret
            FROM ranked
            GROUP BY ym
            ORDER BY ym
        """), {"months": months}).mappings().all()

        result = []
        for r in rows:
            invest = int(r["invest"] or 0)
            ret = int(r["ret"] or 0)
            bets = int(r["bets"] or 0)
            hits = int(r["hits"] or 0)
            result.append({
                "month": r["ym"],
                "races": r["races"],
                "bets": bets, "hits": hits,
                "invest": invest, "return": ret,
                "roi": round(ret / invest * 100, 1) if invest > 0 else 0,
                "hit_rate": round(hits / bets * 100, 1) if bets > 0 else 0,
                "bet_mode": "flat",
            })
        return result

    # ケリー基準 / EV比例はPython側で賭け金を動的に計算
    rows = db.execute(sql_text("""
        WITH ranked AS (
            SELECT
                r.race_key,
                TO_CHAR(r.race_date, 'YYYY-MM') AS ym,
                r.horse_count,
                re.horse_num, re.finish_order, re.odds_win,
                ROW_NUMBER() OVER (PARTITION BY r.race_key ORDER BY re.odds_win ASC) AS rn
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE r.race_date >= CURRENT_DATE - (:months * 30)
              AND re.finish_order IS NOT NULL
              AND re.odds_win IS NOT NULL
              AND re.odds_win > 0
        )
        SELECT ym, race_key, horse_count, horse_num, finish_order, odds_win
        FROM ranked WHERE rn = 1
        ORDER BY ym, race_key
    """), {"months": months}).mappings().all()

    # 月別に集計
    from itertools import groupby
    monthly_data: dict[str, dict] = {}
    current_bankroll = bankroll

    for row in rows:
        ym = row["ym"]
        odds = float(row["odds_win"])
        n = int(row["horse_count"]) if row["horse_count"] else 10
        win_prob = 1.0 / n  # 簡易勝率

        # 賭け金計算
        bet_amount = calc_bet_amount(
            bet_mode=bet_mode,
            win_prob=win_prob,
            odds=odds,
            bankroll=current_bankroll,
            kelly_fraction=kelly_fraction,
        )

        if bet_amount <= 0:
            continue

        if ym not in monthly_data:
            monthly_data[ym] = {"races": 0, "bets": 0, "hits": 0, "invest": 0, "ret": 0}

        monthly_data[ym]["races"] += 1
        monthly_data[ym]["bets"] += 1
        monthly_data[ym]["invest"] += bet_amount

        if row["finish_order"] == 1:
            payout = int(odds * bet_amount)
            monthly_data[ym]["ret"] += payout
            monthly_data[ym]["hits"] += 1
            if bet_mode == BetMode.KELLY:
                current_bankroll += payout - bet_amount
        else:
            if bet_mode == BetMode.KELLY:
                current_bankroll -= bet_amount
                current_bankroll = max(current_bankroll, 1000)

    result = []
    for ym in sorted(monthly_data.keys()):
        d = monthly_data[ym]
        invest = int(d["invest"])
        ret = int(d["ret"])
        result.append({
            "month": ym,
            "races": d["races"],
            "bets": d["bets"],
            "hits": d["hits"],
            "invest": invest,
            "return": ret,
            "roi": round(ret / invest * 100, 1) if invest > 0 else 0,
            "hit_rate": round(d["hits"] / d["bets"] * 100, 1) if d["bets"] > 0 else 0,
            "bet_mode": bet_mode.value,
        })
    return result


# ---------------------------------------------------------------------------
# 馬券シミュレーター
# ---------------------------------------------------------------------------

@router.post("/simulate")
def simulate_betting(req: SimulateRequest, db: Session = Depends(get_db)):
    """過去レースで仮想購入した場合の回収率をシミュレーション（賭け金配分モード対応）"""
    if not req.race_keys:
        return {"total_bets": 0, "roi": 0, "details": []}

    # 賭け金配分モードを解決
    try:
        mode = BetMode(req.bet_mode)
    except ValueError:
        mode = BetMode.FLAT

    # 対象レースのデータ取得
    rows = db.execute(sql_text("""
        SELECT r.race_key, r.race_date, r.race_name, r.venue_code,
               r.horse_count,
               re.horse_num, re.finish_order, re.odds_win, re.popularity
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE r.race_key = ANY(:keys)
          AND re.finish_order IS NOT NULL
          AND re.odds_win IS NOT NULL
        ORDER BY r.race_key, re.horse_num
    """), {"keys": req.race_keys}).mappings().all()

    from itertools import groupby
    details = []
    total_invest = total_return = total_hits = 0
    skipped_by_mode = 0
    current_bankroll = req.bankroll

    for rk, entries in groupby(rows, key=lambda r: r["race_key"]):
        entries = list(entries)
        if not entries:
            continue

        n = int(entries[0].get("horse_count") or len(entries))

        # 戦略に応じて購入対象を決定
        if req.strategy == "favorite":
            targets = [min(entries, key=lambda x: float(x["odds_win"]))]
        elif req.strategy == "value":
            targets = [e for e in entries if 10 <= float(e["odds_win"]) <= 50]
        else:
            targets = [min(entries, key=lambda x: float(x["odds_win"]))]

        for t in targets:
            odds = float(t["odds_win"])
            win_prob = 1.0 / n  # 簡易勝率
            ev = win_prob * odds - 1
            if ev < req.ev_threshold:
                continue

            # 賭け金配分モードに応じた金額を計算
            bet_amount = calc_bet_amount(
                bet_mode=mode,
                win_prob=win_prob,
                odds=odds,
                bankroll=current_bankroll,
                kelly_fraction=req.kelly_fraction,
                base_amount=float(req.bet_amount),
            )

            if bet_amount <= 0:
                skipped_by_mode += 1
                continue

            is_hit = t["finish_order"] == 1
            payout = int(odds * bet_amount) if is_hit else 0
            total_invest += bet_amount
            total_return += payout
            if is_hit:
                total_hits += 1
                if mode == BetMode.KELLY:
                    current_bankroll += payout - bet_amount
            else:
                if mode == BetMode.KELLY:
                    current_bankroll -= bet_amount
                    current_bankroll = max(current_bankroll, 1000)

            details.append({
                "race_key": rk,
                "race_date": str(entries[0]["race_date"]),
                "race_name": entries[0].get("race_name"),
                "horse_num": t["horse_num"],
                "odds": odds,
                "finish_order": t["finish_order"],
                "bet": int(bet_amount),
                "payout": payout,
                "profit": payout - int(bet_amount),
            })

    roi = round(total_return / total_invest * 100, 1) if total_invest > 0 else 0
    hit_rate = round(total_hits / len(details) * 100, 1) if details else 0

    result = {
        "strategy": req.strategy,
        "bet_type": req.bet_type,
        "bet_mode": mode.value,
        "total_bets": len(details),
        "total_invest": int(total_invest),
        "total_return": int(total_return),
        "profit": int(total_return - total_invest),
        "roi": roi,
        "hit_rate": hit_rate,
        "details": details,
    }

    # ケリー基準の追加情報
    if mode == BetMode.KELLY:
        result["kelly_fraction"] = req.kelly_fraction
        result["initial_bankroll"] = int(req.bankroll)
        result["final_bankroll"] = int(current_bankroll)
        result["bankroll_growth"] = round((current_bankroll / req.bankroll - 1) * 100, 1)
        result["skipped_negative_ev"] = skipped_by_mode
    elif mode == BetMode.EV_PROPORTIONAL:
        result["skipped_negative_ev"] = skipped_by_mode

    return result


# ---------------------------------------------------------------------------
# 予測精度モニタリング（v5追加）
# ---------------------------------------------------------------------------

@router.get("/backtest/accuracy")
def prediction_accuracy_monitor(
    days: int = Query(30, le=365, description="過去N日間"),
    db: Session = Depends(get_db),
):
    """
    予測精度モニタリングダッシュボード
    - 1番人気の的中率推移（日別）
    - オッズ帯別の的中率
    - 回収率の移動平均
    """
    rows = db.execute(sql_text("""
        SELECT
            r.race_date,
            re.odds_win,
            re.finish_order,
            re.popularity,
            r.horse_count,
            r.track_type
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE r.race_date >= CURRENT_DATE - :days
          AND re.finish_order IS NOT NULL AND re.finish_order > 0
          AND re.odds_win IS NOT NULL AND re.odds_win > 0
          AND re.odds_win > 0
          AND re.popularity = 1
        ORDER BY r.race_date
    """), {"days": days}).mappings().all()

    if not rows:
        return {"days": days, "total": 0, "daily": [], "by_odds_band": [], "moving_avg": []}

    # 日別集計
    daily_stats = defaultdict(lambda: {"races": 0, "hits": 0, "invest": 0, "ret": 0})
    for r in rows:
        dt = str(r["race_date"])
        daily_stats[dt]["races"] += 1
        daily_stats[dt]["invest"] += 100
        if r["finish_order"] == 1:
            daily_stats[dt]["hits"] += 1
            daily_stats[dt]["ret"] += int(float(r["odds_win"]) * 100)

    daily = []
    for dt in sorted(daily_stats.keys()):
        d = daily_stats[dt]
        daily.append({
            "date": dt,
            "races": d["races"],
            "hits": d["hits"],
            "hit_rate": round(d["hits"] / d["races"] * 100, 1) if d["races"] > 0 else 0,
            "roi": round(d["ret"] / d["invest"] * 100, 1) if d["invest"] > 0 else 0,
        })

    # 7日移動平均
    moving_avg = []
    for i in range(len(daily)):
        window = daily[max(0, i - 6):i + 1]
        total_races = sum(w["races"] for w in window)
        total_hits = sum(w["hits"] for w in window)
        moving_avg.append({
            "date": daily[i]["date"],
            "hit_rate_7d": round(total_hits / total_races * 100, 1) if total_races > 0 else 0,
        })

    # オッズ帯別集計
    odds_bands = [
        ("1.0-1.9", 1.0, 2.0), ("2.0-2.9", 2.0, 3.0), ("3.0-4.9", 3.0, 5.0),
        ("5.0-9.9", 5.0, 10.0), ("10.0+", 10.0, 9999),
    ]
    by_odds = []
    for label, lo, hi in odds_bands:
        band_rows = [r for r in rows if lo <= float(r["odds_win"]) < hi]
        if band_rows:
            hits = sum(1 for r in band_rows if r["finish_order"] == 1)
            invest = len(band_rows) * 100
            ret = sum(int(float(r["odds_win"]) * 100) for r in band_rows if r["finish_order"] == 1)
            by_odds.append({
                "band": label,
                "count": len(band_rows),
                "hits": hits,
                "hit_rate": round(hits / len(band_rows) * 100, 1),
                "roi": round(ret / invest * 100, 1) if invest > 0 else 0,
            })

    total_hits = sum(1 for r in rows if r["finish_order"] == 1)
    total_invest = len(rows) * 100
    total_ret = sum(int(float(r["odds_win"]) * 100) for r in rows if r["finish_order"] == 1)

    return {
        "days": days,
        "total": len(rows),
        "total_hits": total_hits,
        "overall_hit_rate": round(total_hits / len(rows) * 100, 1) if rows else 0,
        "overall_roi": round(total_ret / total_invest * 100, 1) if total_invest > 0 else 0,
        "daily": daily,
        "moving_avg": moving_avg,
        "by_odds_band": by_odds,
    }
