"""
AI予測・バックテストAPIのテスト
"""
import pytest


# ---------------------------------------------------------------------------
# バックテスト
# ---------------------------------------------------------------------------

def test_backtest_summary_returns_statistics(client):
    """バックテストサマリーが統計情報を含むレスポンスを返す"""
    resp = client.get("/backtest/summary", params={"days": 30})
    assert resp.status_code == 200
    data = resp.json()
    # 必須フィールドの存在確認
    assert "total_races" in data
    assert "total_bets" in data
    assert "total_invest" in data
    assert isinstance(data["total_races"], int)
    assert data["total_races"] >= 0


def test_backtest_monthly_returns_list(client):
    """月別バックテストがリスト形式で返る"""
    resp = client.get("/backtest/monthly")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_backtest_with_kelly_mode(client):
    """ケリーモードでのバックテストが正常に動作する"""
    resp = client.get("/backtest/summary", params={
        "days": 30,
        "bet_mode": "kelly",
        "kelly_fraction": 0.25,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "total_invest" in data


# ---------------------------------------------------------------------------
# AI予測
# ---------------------------------------------------------------------------

def test_predict_race_returns_prediction_structure(client, sample_race_key):
    """レース予測がモデル状態に応じた正しい構造を返す"""
    resp = client.get(f"/races/{sample_race_key}/predict")
    assert resp.status_code == 200
    data = resp.json()

    # 共通フィールド
    assert "race_key" in data
    assert "model_available" in data
    assert isinstance(data["model_available"], bool)
    assert "predictions" in data
    assert isinstance(data["predictions"], list)

    if data["model_available"]:
        # モデル学習済みの場合: 予測結果の構造検証
        assert len(data["predictions"]) > 0
        pred = data["predictions"][0]
        assert "horse_num" in pred
        assert "win_prob" in pred
        assert 0 <= pred["win_prob"] <= 1
    else:
        # モデル未学習の場合: メッセージが返る
        assert "message" in data


def test_predict_race_invalid_key_returns_404(client):
    """存在しないレースキーで404が返る"""
    resp = client.get("/races/9999999999999999/predict")
    assert resp.status_code == 404


def test_simulate_betting_returns_result(client, sample_race_key):
    """馬券シミュレーターが結果を返す"""
    resp = client.post("/simulate", json={
        "race_keys": [sample_race_key],
        "strategy": "ai_recommend",
        "bet_type": "win",
        "bet_mode": "flat",
        "bankroll": 100000,
    })
    # モデル未学習時は200でも空結果を返す設計
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
