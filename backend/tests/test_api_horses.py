"""
馬APIのテスト
"""


def test_search_horses(client):
    """馬名検索"""
    resp = client.get("/horses/search", params={"q": "ディープ"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_horse_detail(client, sample_horse_id):
    """馬詳細取得"""
    resp = client.get(f"/horses/{sample_horse_id}")
    assert resp.status_code == 200


def test_get_horse_results(client, sample_horse_id):
    """馬の出走成績"""
    resp = client.get(f"/horses/{sample_horse_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_horse_stats(client, sample_horse_id):
    """馬の統計情報"""
    resp = client.get(f"/horses/{sample_horse_id}/stats")
    assert resp.status_code == 200


def test_get_horse_not_found(client):
    """存在しない馬IDで404"""
    resp = client.get("/horses/999999999")
    assert resp.status_code == 404
