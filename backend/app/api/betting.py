"""
買い目計算API — フォーメーション/ボックス/ながし計算・AI推奨買い目・コスト計算
"""
import itertools
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/betting", tags=["betting"])


# --- リクエスト/レスポンス型 ---

class FormationRequest(BaseModel):
    """フォーメーション計算リクエスト"""
    bet_type: str  # "馬連","ワイド","馬単","三連複","三連単"
    first: list[int]   # 1着候補の馬番リスト
    second: list[int]  # 2着候補の馬番リスト
    third: list[int] = []  # 3着候補（三連系のみ）
    amount: int = 100  # 1点あたり金額


class BoxRequest(BaseModel):
    """ボックス計算リクエスト"""
    bet_type: str
    horses: list[int]  # 選択馬番
    amount: int = 100


class NagashiRequest(BaseModel):
    """ながし計算リクエスト"""
    bet_type: str
    axis: list[int]    # 軸馬
    partners: list[int]  # 相手馬
    amount: int = 100


class BetResult(BaseModel):
    combinations: list[str]  # 買い目一覧（例: "3-7", "3-7-12"）
    count: int               # 点数
    total_cost: int          # 合計金額


# --- 組み合わせ計算 ---

def _calc_formation(bet_type: str, first: list[int], second: list[int], third: list[int]) -> list[str]:
    """フォーメーションの組み合わせを計算"""
    combos: set[str] = set()

    if bet_type in ("馬連", "ワイド"):
        # 順不同2頭
        for a in first:
            for b in second:
                if a != b:
                    key = "-".join(str(x) for x in sorted([a, b]))
                    combos.add(key)
    elif bet_type == "馬単":
        # 順序あり2頭
        for a in first:
            for b in second:
                if a != b:
                    combos.add(f"{a}-{b}")
    elif bet_type == "三連複":
        # 順不同3頭
        for a in first:
            for b in second:
                for c in third:
                    if len({a, b, c}) == 3:
                        key = "-".join(str(x) for x in sorted([a, b, c]))
                        combos.add(key)
    elif bet_type == "三連単":
        # 順序あり3頭
        for a in first:
            for b in second:
                for c in third:
                    if len({a, b, c}) == 3:
                        combos.add(f"{a}-{b}-{c}")
    return sorted(combos)


def _calc_box(bet_type: str, horses: list[int]) -> list[str]:
    """ボックスの組み合わせを計算"""
    combos: list[str] = []
    if bet_type in ("馬連", "ワイド"):
        for pair in itertools.combinations(sorted(horses), 2):
            combos.append("-".join(str(x) for x in pair))
    elif bet_type == "馬単":
        for pair in itertools.permutations(horses, 2):
            combos.append("-".join(str(x) for x in pair))
    elif bet_type == "三連複":
        for trio in itertools.combinations(sorted(horses), 3):
            combos.append("-".join(str(x) for x in trio))
    elif bet_type == "三連単":
        for trio in itertools.permutations(horses, 3):
            combos.append("-".join(str(x) for x in trio))
    return sorted(combos)


def _calc_nagashi(bet_type: str, axis: list[int], partners: list[int]) -> list[str]:
    """ながし（軸→相手）の組み合わせを計算"""
    combos: list[str] = []
    if bet_type in ("馬連", "ワイド"):
        for a in axis:
            for p in partners:
                if a != p:
                    key = "-".join(str(x) for x in sorted([a, p]))
                    if key not in combos:
                        combos.append(key)
    elif bet_type == "馬単":
        # 軸を1着固定
        for a in axis:
            for p in partners:
                if a != p:
                    combos.append(f"{a}-{p}")
    elif bet_type == "三連複":
        # 軸1頭 + 相手から2頭
        for a in axis:
            for pair in itertools.combinations(partners, 2):
                if a not in pair:
                    key = "-".join(str(x) for x in sorted([a, *pair]))
                    if key not in combos:
                        combos.append(key)
    elif bet_type == "三連単":
        # 軸を1着固定、相手から2着3着
        for a in axis:
            for pair in itertools.permutations(partners, 2):
                if a not in pair:
                    combos.append(f"{a}-{pair[0]}-{pair[1]}")
    return sorted(combos)


# --- エンドポイント ---

@router.post("/formation", response_model=BetResult)
def calc_formation(req: FormationRequest):
    """フォーメーション組み合わせ計算"""
    combos = _calc_formation(req.bet_type, req.first, req.second, req.third)
    return BetResult(combinations=combos, count=len(combos), total_cost=len(combos) * req.amount)


@router.post("/box", response_model=BetResult)
def calc_box(req: BoxRequest):
    """ボックス組み合わせ計算"""
    combos = _calc_box(req.bet_type, req.horses)
    return BetResult(combinations=combos, count=len(combos), total_cost=len(combos) * req.amount)


@router.post("/nagashi", response_model=BetResult)
def calc_nagashi(req: NagashiRequest):
    """ながし組み合わせ計算"""
    combos = _calc_nagashi(req.bet_type, req.axis, req.partners)
    return BetResult(combinations=combos, count=len(combos), total_cost=len(combos) * req.amount)


@router.get("/kelly")
def calc_kelly(
    win_prob: float = Query(..., description="予測勝率(0〜1)"),
    odds: float = Query(..., description="オッズ"),
):
    """ケリー基準で最適賭け金比率を算出"""
    if win_prob <= 0 or win_prob >= 1 or odds <= 1:
        return {"kelly_fraction": 0, "expected_value": 0, "recommended": False}

    b = odds - 1
    q = 1 - win_prob
    f = (win_prob * b - q) / b
    ev = win_prob * odds - 1

    return {
        "kelly_fraction": round(max(0, f), 4),
        "expected_value": round(ev, 4),
        "recommended": ev > 0,
        "half_kelly": round(max(0, f / 2), 4),  # ハーフケリー（リスク半減）
    }
