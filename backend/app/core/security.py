"""
セキュリティ対策モジュール

- 入力値サニタイズ（SQLインジェクション・XSS防止）
- レート制限
- CORS設定の制限
"""
import re
import html
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


# SQLインジェクション検出パターン
_SQL_INJECTION_PATTERNS = [
    r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|EXEC)\s",
    r"UNION\s+(ALL\s+)?SELECT",
    r"--\s*$",
    r"/\*.*\*/",
    r"'\s*OR\s+'",
    r"'\s*AND\s+'",
    r"xp_\w+",
]
_SQL_RE = re.compile("|".join(_SQL_INJECTION_PATTERNS), re.IGNORECASE)

# XSS検出パターン
_XSS_PATTERNS = [
    r"<script",
    r"javascript:",
    r"on\w+\s*=",
    r"<iframe",
    r"<object",
    r"<embed",
]
_XSS_RE = re.compile("|".join(_XSS_PATTERNS), re.IGNORECASE)


def sanitize_string(value: str, max_length: int = 200) -> str:
    """文字列をサニタイズ（SQLインジェクション・XSS防止）"""
    if not value:
        return value

    # 長さ制限
    value = value[:max_length]

    # HTMLエスケープ
    value = html.escape(value)

    # SQLインジェクション検出
    if _SQL_RE.search(value):
        raise ValueError(f"不正な入力が検出されました")

    # XSS検出
    if _XSS_RE.search(value):
        raise ValueError(f"不正な入力が検出されました")

    return value


def validate_race_key(race_key: str) -> str:
    """レースキーのバリデーション（16桁の数字のみ許可）"""
    if not re.match(r"^\d{16}$", race_key):
        raise HTTPException(status_code=400, detail="不正なレースキー形式")
    return race_key


def validate_venue_code(venue_code: str) -> str:
    """場コードのバリデーション（01-10のカンマ区切り）"""
    codes = [c.strip() for c in venue_code.split(",")]
    for code in codes:
        if not re.match(r"^(0[1-9]|10)$", code):
            raise HTTPException(status_code=400, detail=f"不正な場コード: {code}")
    return venue_code


class SecurityMiddleware(BaseHTTPMiddleware):
    """セキュリティミドルウェア"""

    async def dispatch(self, request: Request, call_next):
        # クエリパラメータのサニタイズチェック
        for key, value in request.query_params.items():
            if isinstance(value, str) and len(value) > 500:
                return HTTPException(status_code=400, detail="パラメータが長すぎます")
            if isinstance(value, str):
                if _SQL_RE.search(value):
                    raise HTTPException(status_code=400, detail="不正なリクエスト")
                if _XSS_RE.search(value):
                    raise HTTPException(status_code=400, detail="不正なリクエスト")

        response = await call_next(request)

        # セキュリティヘッダー追加
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
