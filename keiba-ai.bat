@echo off
title 競馬AI予測
chcp 65001 >nul 2>&1

REM バッチファイルの場所を基準にプロジェクトルートを設定
set "PROJECT_ROOT=%~dp0"
REM 末尾の \ を除去
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

echo.
echo   ========================================
echo     競馬AI予測  起動中...
echo   ========================================
echo.

REM Docker Desktop 確認
echo   [1/3] Docker 確認中...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [エラー] Docker Desktop が起動していません。
    echo   Docker Desktop を起動してから再度実行してください。
    echo.
    pause
    exit /b 1
)
echo   [1/3] Docker ... OK

REM DBコンテナ起動 + ヘルスチェック
echo   [2/3] データベース起動中...
docker start keiba_db >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [エラー] keiba_db コンテナの起動に失敗しました。
    echo   docker-compose up -d で作成済みか確認してください。
    echo.
    pause
    exit /b 1
)

REM PostgreSQL のヘルスチェック（最大30秒、2秒間隔）
setlocal enabledelayedexpansion
set "DB_READY=0"
for /L %%i in (1,1,15) do (
    if "!DB_READY!"=="0" (
        docker exec keiba_db pg_isready -U postgres >nul 2>&1
        if not errorlevel 1 (
            set "DB_READY=1"
        ) else (
            ping -n 3 127.0.0.1 >nul 2>&1
        )
    )
)
if "!DB_READY!"=="0" (
    echo.
    echo   [警告] データベースの応答確認がタイムアウトしました（30秒）。
    echo   起動を続行しますが、接続エラーが発生する場合があります。
    echo.
) else (
    echo   [2/3] データベース ... OK
)
endlocal

REM Electron起動（相対パスを使用）
echo   [3/3] アプリ起動中...
echo.

cd /d "%PROJECT_ROOT%\frontend"
node node_modules\electron\cli.js .

echo.
echo   アプリを終了しました。
ping -n 4 127.0.0.1 >nul 2>&1
