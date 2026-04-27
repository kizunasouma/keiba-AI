"""
統計APIのテスト
"""


def test_get_sire_stats(client):
    """種牡馬別成績"""
    resp = client.get("/stats/sire")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_bms_stats(client):
    """母父別成績"""
    resp = client.get("/stats/bms")
    assert resp.status_code == 200


def test_get_frame_stats(client):
    """枠番別成績"""
    resp = client.get("/stats/frame")
    assert resp.status_code == 200


def test_get_popularity_stats(client):
    """人気別成績"""
    resp = client.get("/stats/popularity")
    assert resp.status_code == 200


def test_get_roi_by_odds(client):
    """オッズ帯別回収率"""
    resp = client.get("/stats/roi/by_odds")
    assert resp.status_code == 200


def test_get_roi_by_popularity(client):
    """人気別回収率"""
    resp = client.get("/stats/roi/by_popularity")
    assert resp.status_code == 200


def test_get_mining(client):
    """データマイニング"""
    resp = client.get("/stats/mining")
    assert resp.status_code == 200
