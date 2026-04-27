"""
ヘルスチェックAPIのテスト
"""


def test_health_check(client):
    """アプリが生存していることを確認"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_db_health_check(client):
    """DBへの接続が正常であることを確認"""
    resp = client.get("/health/db")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
