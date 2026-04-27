"""
JV-Link ブリッジスクリプト（32ビット Python 専用）

32ビット COM である JV-Link からデータを読み出し、
標準出力にバイナリで流す。64ビット Python の sync_jvlink.py から
subprocess 経由で呼び出される。

出力フォーマット:
    各レコードを <4バイト長(big-endian)> + <レコードバイト列> の形式で出力する。
    長さ 0 のチャンクは EOF を意味する。

使い方（直接呼び出しはしない。sync_jvlink.py 経由で使う）:
    python32 scripts/jvlink_bridge.py --dataspec RACE --fromtime 19860101000000 --option 4
"""
import argparse
import struct
import sys
import time
import logging

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

JVLINK_PROG_ID = "JVDTLab.JVLink.1"

# 利用キーは環境変数から読む（なければレジストリから自動取得）
import os

def _read_registry_str(key_path: str, value_name: str) -> str:
    """WOW6432Node のレジストリ値を読む（32ビット COM と同じレジストリハイブ）"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        val, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return str(val)
    except Exception:
        return ""

_REG_PATH = r"SOFTWARE\WOW6432Node\JRA-VAN Data Lab.\uid_pass"
SERVICE_KEY = os.environ.get("JVLINK_SERVICE_KEY") or _read_registry_str(_REG_PATH, "servicekey")
# ukey をソフトウェアIDとして使う（JVInit に必要）
SOFTWARE_ID = os.environ.get("JVLINK_SOFTWARE_ID") or _read_registry_str(_REG_PATH, "ukey")
SAVE_PATH   = os.environ.get("JVLINK_SAVE_PATH") or _read_registry_str(_REG_PATH, "savepath")


def run(dataspec: str, fromtime: str, option: int):
    import win32com.client

    try:
        jv = win32com.client.Dispatch(JVLINK_PROG_ID)
    except Exception as e:
        logger.error(f"COM オブジェクト生成失敗: {e}")
        sys.exit(1)

    # 初期化（ukey をソフトウェアIDとして渡す）
    logger.info(f"JVInit with SOFTWARE_ID={SOFTWARE_ID!r}")
    ret = jv.JVInit(SOFTWARE_ID or "")
    if ret < 0:
        logger.error(f"JVInit 失敗: {ret}")
        sys.exit(1)
    logger.info(f"JVInit: {ret}")

    # 利用キー設定
    # GUI（JV-Link設定.exe）でレジストリ設定済みの場合は呼ばなくてよい
    # 未設定の場合のみ呼ぶ（-100=形式不正, -101=設定済み/重複 はどちらも無視）
    if SERVICE_KEY:
        key = SERVICE_KEY.replace("-", "")  # ハイフンなし形式
        ret = jv.JVSetServiceKey(key)
        if isinstance(ret, tuple):
            ret = ret[0]
        logger.info(f"JVSetServiceKey: {ret}")

    # 保存パス設定
    if SAVE_PATH:
        jv.JVSetSavePath(SAVE_PATH)

    # データ取得要求
    # JVOpen は ByRef パラメータがあるため win32com はタプルで返す:
    # (ret, readcount, downloadcount, lastfiletimestamp)
    readcount = 0
    downloadcount = 0
    last_ts = ""
    result = jv.JVOpen(dataspec, fromtime, option, readcount, downloadcount, last_ts)
    if isinstance(result, tuple):
        ret, readcount, downloadcount, last_ts = result
    else:
        ret = result
    if ret < 0:
        logger.error(f"JVOpen 失敗: {ret} (dataspec={dataspec})")
        sys.exit(1)

    # ダウンロード待ち
    dl_total = downloadcount
    logger.info(f"readcount={readcount}, downloadcount={dl_total}")

    if dl_total > 0:
        timeout = 600
        elapsed = 0
        while elapsed < timeout:
            status = jv.JVStatus()
            if isinstance(status, tuple):
                status = status[0]
            if status < 0:
                logger.error(f"JVStatus エラー: {status}")
                sys.exit(1)
            if status >= dl_total:
                logger.info(f"ダウンロード完了: {status}/{dl_total}")
                break
            logger.info(f"ダウンロード中: {status}/{dl_total}")
            time.sleep(2)
            elapsed += 2
        else:
            logger.error("ダウンロードタイムアウト")
            sys.exit(1)

    # stdout をバイナリモードに切り替え
    import msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    buff_size = 110000
    record_count = 0

    # パイプ書き込みバッファ（複数レコードをまとめて1回のwriteで送出）
    output_buf = bytearray()
    FLUSH_THRESHOLD = 65536  # 64KB ごとにフラッシュ

    while True:
        buff = ""
        filename = ""
        result = jv.JVRead(buff, buff_size, filename)
        if isinstance(result, tuple):
            ret, buff = result[0], result[1]
        else:
            ret = result

        if ret == 0:
            break
        elif ret == -1:
            # ファイル切替 — バッファをフラッシュ（ファイル境界で区切る）
            if output_buf:
                sys.stdout.buffer.write(output_buf)
                output_buf = bytearray()
            continue
        elif ret < -1:
            logger.error(f"JVRead エラー: {ret}")
            break
        else:
            if isinstance(buff, str):
                data = buff.encode("cp932")
            else:
                data = bytes(buff)

            # バッファに追加（writeシステムコール削減）
            output_buf += struct.pack(">I", len(data))
            output_buf += data
            record_count += 1

            # バッファが閾値を超えたらフラッシュ
            if len(output_buf) >= FLUSH_THRESHOLD:
                sys.stdout.buffer.write(output_buf)
                output_buf = bytearray()

            if record_count % 5000 == 0:
                logger.info(f"読み出し中: {record_count} 件")

    # 残りバッファ + EOF マーカー
    output_buf += struct.pack(">I", 0)
    sys.stdout.buffer.write(output_buf)
    sys.stdout.buffer.flush()

    jv.JVClose()
    logger.info(f"完了: 合計 {record_count} 件")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataspec", required=True)
    parser.add_argument("--fromtime", required=True)
    parser.add_argument("--option", type=int, required=True)
    args = parser.parse_args()

    run(args.dataspec, args.fromtime, args.option)
