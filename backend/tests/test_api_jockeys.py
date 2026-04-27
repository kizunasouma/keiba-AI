"""
騎手APIのテスト
"""


def test_search_jockeys(client):
    """騎手名検索"""
    resp = client.get("/jockeys/search", params={"q": "武"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_jockey_detail(client, sample_jockey_id):
    """騎手詳細取得"""
    resp = client.get(f"/jockeys/{sample_jockey_id}")
    assert resp.status_code == 200


def test_get_jockey_stats(client, sample_jockey_id):
    """騎手の統計情報"""
    resp = client.get(f"/jockeys/{sample_jockey_id}/stats")
    assert resp.status_code == 200


def test_get_jockey_recent(client, sample_jockey_id):
    """騎手の直近成績"""
    resp = client.get(f"/jockeys/{sample_jockey_id}/recent")
    assert resp.status_code == 200
