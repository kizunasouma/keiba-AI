"""
レースAPIのテスト
"""
import pytest


def test_get_races_default(client):
    """レース一覧取得（デフォルト）"""
    resp = client.get("/races")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_races_with_date_filter(client):
    """日付フィルタ付きレース一覧"""
    resp = client.get("/races", params={"date_from": "2026-04-01", "date_to": "2026-04-12"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_races_with_venue_filter(client):
    """場コードフィルタ付きレース一覧"""
    resp = client.get("/races", params={"venue_code": "05"})
    assert resp.status_code == 200


def test_get_races_with_track_type_filter(client):
    """コース種別フィルタ"""
    resp = client.get("/races", params={"track_type": 1})
    assert resp.status_code == 200


def test_get_races_with_limit(client):
    """リミット指定"""
    resp = client.get("/races", params={"limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 5


def test_get_race_detail(client, sample_race_key):
    """レース詳細取得"""
    resp = client.get(f"/races/{sample_race_key}")
    assert resp.status_code == 200
    data = resp.json()
    assert "race_key" in data


def test_get_race_entries(client, sample_race_key):
    """出走馬一覧取得"""
    resp = client.get(f"/races/{sample_race_key}/entries")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_race_laps(client, sample_race_key):
    """ラップタイム取得"""
    resp = client.get(f"/races/{sample_race_key}/laps")
    assert resp.status_code == 200


def test_get_race_payouts(client, sample_race_key):
    """払戻情報取得"""
    resp = client.get(f"/races/{sample_race_key}/payouts")
    assert resp.status_code == 200


def test_get_race_detail_invalid_key(client):
    """不正なレースキーでエラー"""
    resp = client.get("/races/invalid_key")
    assert resp.status_code == 400


def test_get_race_detail_not_found(client):
    """存在しないレースキーで404"""
    resp = client.get("/races/9999999999999999")
    assert resp.status_code == 404
