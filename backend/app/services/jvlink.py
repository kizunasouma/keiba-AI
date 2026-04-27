"""
JV-Link連携サービス
Windows の ActiveX COM サービスである JV-Link を PyWin32 経由で呼び出す

【前提条件】
- JV-Link がインストール済みであること（JRA-VAN Data Lab. SDK）
- pywin32 がインストール済みであること（pip install pywin32）
- JRA-VAN の利用キー（17桁）を .env に設定済みであること
"""
import logging
from typing import Generator

from app.core.config import settings

logger = logging.getLogger(__name__)

# JV-Link の ProgID（COM サービスの識別子）
JVLINK_PROG_ID = "JVDTLab.JVLink.1"


class JVLinkError(Exception):
    """JV-Link 呼び出しエラー"""
    pass


class JVLinkClient:
    """
    JV-Link COM サービスのラッパークラス
    with 文で使うことでリソースの自動解放ができる

    使い方:
        with JVLinkClient() as jv:
            for record in jv.read_stored_data("RACE", "20240101000000", option=1):
                print(record)
    """

    def __init__(self):
        self._jv = None

    def __enter__(self):
        self._init()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._close()
        return False

    def _init(self):
        """JV-Link を初期化する"""
        try:
            import win32com.client
        except ImportError:
            raise JVLinkError(
                "pywin32 がインストールされていません。"
                "`pip install pywin32` を実行してください。"
            )

        try:
            self._jv = win32com.client.Dispatch(JVLINK_PROG_ID)
        except Exception as e:
            raise JVLinkError(
                f"JV-Link の COM オブジェクト生成に失敗しました。"
                f"JV-Link がインストールされているか確認してください。\n{e}"
            )

        # 初期化
        ret = self._jv.JVInit(settings.jvlink_software_id)
        if ret < 0:
            raise JVLinkError(f"JVInit 失敗: エラーコード {ret}")

        # 利用キーを設定（レジストリ未設定の場合のみ有効）
        if settings.jvlink_service_key and settings.jvlink_service_key != "UNKNOWN":
            ret = self._jv.JVSetServiceKey(settings.jvlink_service_key)
            if ret < 0:
                raise JVLinkError(f"JVSetServiceKey 失敗: エラーコード {ret}")

        # 保存パスを設定（指定がある場合のみ）
        if settings.jvlink_save_path:
            ret = self._jv.JVSetSavePath(settings.jvlink_save_path)
            if ret < 0:
                raise JVLinkError(f"JVSetSavePath 失敗: エラーコード {ret}")

        logger.info("JV-Link 初期化完了")

    def _close(self):
        """JV-Link 読み込みを終了する"""
        if self._jv is not None:
            try:
                self._jv.JVClose()
            except Exception:
                pass
            self._jv = None

    def read_stored_data(
        self,
        dataspec: str,
        fromtime: str,
        option: int = 1,
    ) -> Generator[bytes, None, None]:
        """
        蓄積系データを読み出すジェネレータ

        Args:
            dataspec: データ種別ID（例: "RACE", "DIFN"）
            fromtime: 読み出し開始時刻（YYYYMMDDhhmmss 形式）
            option: 1=通常, 2=今週, 3/4=セットアップ

        Yields:
            bytes: 1レコード分のデータ（Shift-JIS）
        """
        if self._jv is None:
            raise JVLinkError("JV-Link が初期化されていません")

        # データ取得要求
        readcount = 0
        downloadcount = 0
        last_ts = ""
        ret = self._jv.JVOpen(dataspec, fromtime, option, readcount, downloadcount, last_ts)
        if ret < 0:
            raise JVLinkError(f"JVOpen 失敗: エラーコード {ret} (dataspec={dataspec})")

        # ダウンロード完了を待つ
        dl_total = self._jv.downloadcount if hasattr(self._jv, 'downloadcount') else 0
        logger.info(f"ダウンロード開始: 対象ファイル数={self._jv.readcount}, DL必要数={dl_total}")
        self._wait_download()

        # 1行ずつ読み出す
        buff_size = 110000  # 最大レコード長に余裕を持たせたサイズ
        while True:
            buff = ""
            filename = ""
            ret = self._jv.JVRead(buff, buff_size, filename)

            if ret == 0:
                # EOF：全ファイル読み終わり
                break
            elif ret == -1:
                # ファイル切替：次のファイルへ
                continue
            elif ret < -1:
                # エラー
                raise JVLinkError(f"JVRead 失敗: エラーコード {ret}")
            else:
                # 正常読み出し：Shift-JIS バイト列として yield
                yield buff.encode("cp932") if isinstance(buff, str) else buff

    def _wait_download(self, timeout_sec: int = 300):
        """
        JVStatus をポーリングしてダウンロード完了を待つ

        Args:
            timeout_sec: 最大待機秒数（デフォルト5分）
        """
        import time

        # downloadcount が 0 の場合はダウンロード不要
        dl_count = self._jv.downloadcount if hasattr(self._jv, 'downloadcount') else 0
        if dl_count == 0:
            return

        elapsed = 0
        interval = 1  # 1秒ごとにポーリング
        while elapsed < timeout_sec:
            status = self._jv.JVStatus()
            if status < 0:
                raise JVLinkError(f"JVStatus エラー: {status}")
            if status >= dl_count:
                logger.info(f"ダウンロード完了: {status}/{dl_count}")
                return
            logger.debug(f"ダウンロード中: {status}/{dl_count}")
            time.sleep(interval)
            elapsed += interval

        raise JVLinkError(f"ダウンロードタイムアウト（{timeout_sec}秒）")
