/// <summary>
/// JV-Link C#ブリッジ — JVDTLab COMを呼び出し、stdoutにバイナリ出力
/// Python側(sync_jvlink.py)のパイプ読取と完全互換のフォーマット:
///   <4バイト長(big-endian)> + <Shift-JISレコード本体>
///   長さ0 = EOF マーカー
/// stderrにログ出力（進捗/エラー）
/// </summary>
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace JVLinkBridge;

class Program
{
    // JV-Link COM ProgID
    const string JVLINK_PROGID = "JVDTLab.JVLink";

    // レジストリパス（32bit COM用）
    const string REG_PATH = @"SOFTWARE\WOW6432Node\JRA-VAN Data Lab.\uid_pass";

    // パイプ出力バッファ（64KBごとにフラッシュ）
    const int FLUSH_THRESHOLD = 65536;

    static void Log(string msg)
    {
        Console.Error.WriteLine($"{DateTime.Now:yyyy-MM-dd HH:mm:ss,fff} [INFO] {msg}");
    }

    static void LogError(string msg)
    {
        Console.Error.WriteLine($"{DateTime.Now:yyyy-MM-dd HH:mm:ss,fff} [ERROR] {msg}");
    }

    static string ReadRegistry(string name)
    {
        try
        {
            using var key = Registry.LocalMachine.OpenSubKey(REG_PATH);
            return key?.GetValue(name)?.ToString() ?? "";
        }
        catch
        {
            return "";
        }
    }

    static int Main(string[] args)
    {
        // コマンドライン引数パース
        string dataspec = "RACE";
        string fromtime = "20000101000000";
        int option = 1;
        bool rtMode = false;   // リアルタイムモード（JVRTOpen使用）
        string rtKey = "";     // JVRTOpenのキー（YYYYMMDD or YYYYMMDDJJKKHHRR）

        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--dataspec" when i + 1 < args.Length:
                    dataspec = args[++i];
                    break;
                case "--fromtime" when i + 1 < args.Length:
                    fromtime = args[++i];
                    break;
                case "--option" when i + 1 < args.Length:
                    option = int.Parse(args[++i]);
                    break;
                case "--rt":
                    rtMode = true;
                    break;
                case "--rtkey" when i + 1 < args.Length:
                    rtKey = args[++i];
                    break;
            }
        }

        // レジストリから設定読取
        string softwareId = Environment.GetEnvironmentVariable("JVLINK_SOFTWARE_ID")
                            ?? ReadRegistry("ukey");
        string serviceKey = Environment.GetEnvironmentVariable("JVLINK_SERVICE_KEY")
                            ?? ReadRegistry("servicekey");
        string savePath = Environment.GetEnvironmentVariable("JVLINK_SAVE_PATH")
                          ?? ReadRegistry("savepath");

        Log($"JVLinkBridge C# 起動: dataspec={dataspec}, fromtime={fromtime}, option={option}, rt={rtMode}");

        // COM オブジェクト生成（late-binding で JVDTLab.JVLink を使用）
        dynamic? jv;
        try
        {
            var type = Type.GetTypeFromProgID(JVLINK_PROGID);
            if (type == null)
            {
                LogError($"COM ProgID '{JVLINK_PROGID}' が見つかりません。JV-Linkがインストールされていない可能性があります。");
                return 1;
            }
            jv = Activator.CreateInstance(type);
        }
        catch (Exception ex)
        {
            LogError($"COM オブジェクト生成失敗: {ex.Message}");
            return 1;
        }

        if (jv == null)
        {
            LogError("COM オブジェクトがnullです");
            return 1;
        }

        // JVInit（ソフトウェアID）
        Log($"JVInit with SOFTWARE_ID='{softwareId}'");
        int ret = jv.JVInit(softwareId ?? "");
        if (ret < 0)
        {
            LogError($"JVInit 失敗: {ret}");
            return 1;
        }
        Log($"JVInit: {ret}");

        // JVSetServiceKey（利用キー）— エラーでもJVOpenは通る場合があるため続行
        if (!string.IsNullOrEmpty(serviceKey))
        {
            string key = serviceKey.Replace("-", "");
            int skRet = jv.JVSetServiceKey(key);
            Log($"JVSetServiceKey: {skRet}");
        }

        // JVSetSavePath（保存パス）
        if (!string.IsNullOrEmpty(savePath))
        {
            jv.JVSetSavePath(savePath);
        }

        // データ取得要求（通常モード or リアルタイムモード）
        int readcount = 0;
        int downloadcount = 0;
        string lastTs = "";

        if (rtMode)
        {
            // === リアルタイムモード: JVRTOpen ===
            // keyが空の場合は本日の開催日単位で取得
            if (string.IsNullOrEmpty(rtKey))
            {
                rtKey = DateTime.Now.ToString("yyyyMMdd");
            }
            Log($"JVRTOpen: dataspec={dataspec}, key={rtKey}");
            ret = jv.JVRTOpen(dataspec, rtKey);
            if (ret < 0)
            {
                LogError($"JVRTOpen 失敗: {ret} (dataspec={dataspec}, key={rtKey})");
                var stdout = Console.OpenStandardOutput();
                stdout.Write(new byte[4], 0, 4);
                stdout.Flush();
                // -1 は該当データなし（正常系）
                return ret == -1 ? 0 : 1;
            }
            Log($"JVRTOpen 成功: ret={ret}");
        }
        else
        {
            // === 通常モード: JVOpen ===
            ret = jv.JVOpen(dataspec, fromtime, option, ref readcount, ref downloadcount, ref lastTs);
            if (ret < 0)
            {
                LogError($"JVOpen 失敗: {ret} (dataspec={dataspec})");
                var stdout = Console.OpenStandardOutput();
                stdout.Write(new byte[4], 0, 4);
                stdout.Flush();
                return ret == -1 ? 0 : 1;
            }
            Log($"readcount={readcount}, downloadcount={downloadcount}");

            // ダウンロード待ち
            if (downloadcount > 0)
            {
                int dlTotal = downloadcount;
                int timeout = 600;
                int elapsed = 0;
                while (elapsed < timeout)
                {
                    int status = jv.JVStatus();
                    if (status < 0)
                    {
                        LogError($"JVStatus エラー: {status}");
                        return 1;
                    }
                    if (status >= dlTotal)
                    {
                        Log($"ダウンロード完了: {status}/{dlTotal}");
                        break;
                    }
                    Log($"ダウンロード中: {status}/{dlTotal}");
                    System.Threading.Thread.Sleep(2000);
                    elapsed += 2;
                }
                if (elapsed >= timeout)
                {
                    LogError("ダウンロードタイムアウト");
                    return 1;
                }
            }
        }

        // stdoutをバイナリモードで開く
        var output = Console.OpenStandardOutput();
        var buffer = new MemoryStream();
        int recordCount = 0;

        // Shift-JIS エンコーディング
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        var cp932 = Encoding.GetEncoding(932);

        // JVRead ループ
        while (true)
        {
            string buff = "";
            string filename = "";
            ret = jv.JVRead(ref buff, 110000, ref filename);

            if (ret == 0)
            {
                // データ終了
                break;
            }
            else if (ret == -1)
            {
                // ファイル切替 — バッファフラッシュ
                if (buffer.Length > 0)
                {
                    buffer.WriteTo(output);
                    buffer.SetLength(0);
                }
                continue;
            }
            else if (ret < -1)
            {
                LogError($"JVRead エラー: {ret}");
                break;
            }
            else
            {
                // レコード取得成功
                byte[] data = cp932.GetBytes(buff);

                // 長さ（4バイト big-endian）+ レコード本体をバッファに追加
                byte[] lenBytes = BitConverter.GetBytes(data.Length);
                if (BitConverter.IsLittleEndian)
                    Array.Reverse(lenBytes);
                buffer.Write(lenBytes, 0, 4);
                buffer.Write(data, 0, data.Length);
                recordCount++;

                // 閾値超えたらフラッシュ
                if (buffer.Length >= FLUSH_THRESHOLD)
                {
                    buffer.WriteTo(output);
                    buffer.SetLength(0);
                }

                if (recordCount % 5000 == 0)
                {
                    Log($"読み出し中: {recordCount} 件");
                }
            }
        }

        // 残りバッファ + EOF マーカー（長さ0）
        buffer.Write(new byte[4], 0, 4);
        buffer.WriteTo(output);
        output.Flush();

        // JVClose
        try { jv.JVClose(); } catch { }

        Log($"完了: {recordCount} 件出力");
        return 0;
    }
}
