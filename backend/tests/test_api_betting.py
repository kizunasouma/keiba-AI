"""
買い目計算APIのテスト
"""


def test_formation_quinella(client):
    """フォーメーション計算（馬連）"""
    resp = client.post("/betting/formation", json={
        "bet_type": "馬連",
        "first": [1, 2, 3],
        "second": [4, 5, 6],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "combinations" in data
    assert "count" in data


def test_box_trio(client):
    """ボックス計算（三連複）"""
    resp = client.post("/betting/box", json={
        "bet_type": "三連複",
        "horses": [1, 2, 3, 4],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0


def test_nagashi(client):
    """ながし計算"""
    resp = client.post("/betting/nagashi", json={
        "bet_type": "馬連",
        "axis": [1],
        "partners": [2, 3, 4, 5],
    })
    assert resp.status_code == 200


def test_kelly_criterion(client):
    """ケリー基準計算"""
    resp = client.get("/betting/kelly", params={
        "win_prob": 0.2,
        "odds": 8.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "kelly_fraction" in data
    assert "half_kelly" in data
    # 期待値プラスなのでケリー分数は正
    assert data["kelly_fraction"] > 0
