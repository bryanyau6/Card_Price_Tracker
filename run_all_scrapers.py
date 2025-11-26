# =========================================================
# Phase 3.4: 總指揮腳本 (Master Script) v7.7 - 自動維護版 + 超時保護
# Author: 電王
# 職責: 1. (新) 自動執行 archive_price_history.py 進行數據清理。
#       2. (舊) 按順序執行所有的 JPY-Only 價格爬蟲。
#
# Update v7.7: 新增超時保護機制，防止腳本無限卡住
# Update v7.6: 新增 socket 錯誤自動重試機制
# Update v7.5: 
# 1. (來自 v7.4) 採用手動匯率架構 (不再讀寫 F1 儲存格)。
# 2. (來自 v7.2) 修正 Windows 編碼問題 (PYTHONUTF8=1)。
# 3. 【核心】: 在所有爬蟲任務 *之前*，自動運行 archive_price_history.py。
# =========================================================

import subprocess
import sys
import time
from datetime import datetime
import os
import threading
# (v7.5 移除了 gspread 和 requests，因為 v7.4 已改為手動匯率)

def run_script(script_name):
    # 獲取當前腳本所在的目錄
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, script_name)
    
    command = [sys.executable, script_path]
    print(f"\n{'='*50}")
    print(f">> 正在啟動子腳本: {script_name}")
    print(f"{'='*50}\n")
    
    # --- [v7.7 新增] 設定超時時間（不同腳本不同時間）---
    if "mercadop" in script_name or "cardrush" in script_name:
        timeout_minutes = 60  # 大型爬蟲：60 分鐘
    elif "akiba" in script_name or "uniari" in script_name:
        timeout_minutes = 45  # 中型爬蟲：45 分鐘
    elif "archive" in script_name:
        timeout_minutes = 30  # 維護腳本：30 分鐘
    else:
        timeout_minutes = 40  # 預設：40 分鐘
    
    timeout_seconds = timeout_minutes * 60
    print(f">> ⏱️ 超時限制: {timeout_minutes} 分鐘\n")
    
    # --- [v7.6 新增] 最多重試 2 次 ---
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'

            socket_error_count = 0
            
            with subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                env=env,
                cwd=script_dir
            ) as process:
                start_time_script = time.time()
                last_output_time = {"value": time.time()}
                no_output_timeout = 600  # 10 分鐘沒輸出就認為卡住
                socket_error_counter = {"count": 0}
                stop_event = threading.Event()

                def stream_process_output():
                    try:
                        for line in iter(process.stdout.readline, ''):
                            if not line:
                                break
                            print(line, end='')
                            last_output_time["value"] = time.time()
                            if "socket.send() raised exception" in line:
                                socket_error_counter["count"] += 1
                                if socket_error_counter["count"] > 10:
                                    stop_event.set()
                                    break
                    except Exception:
                        stop_event.set()

                reader_thread = threading.Thread(target=stream_process_output, daemon=True)
                reader_thread.start()

                try:
                    while True:
                        if stop_event.is_set():
                            print(f"\n⚠️ 檢測到過多 socket 錯誤 ({socket_error_counter['count']})，終止腳本...")
                            process.kill()
                            break

                        if process.poll() is not None:
                            break

                        elapsed = time.time() - start_time_script
                        if elapsed > timeout_seconds:
                            print(f"\n\n⚠️⚠️⚠️ 超時警告 ⚠️⚠️⚠️")
                            print(f"腳本 {script_name} 已運行 {elapsed/60:.1f} 分鐘，超過限制 {timeout_minutes} 分鐘")
                            print("正在強制終止...")
                            process.kill()
                            raise TimeoutError(f"腳本運行超過 {timeout_minutes} 分鐘")

                        time_since_output = time.time() - last_output_time["value"]
                        if time_since_output > no_output_timeout:
                            print(f"\n\n⚠️⚠️⚠️ 無輸出超時警告 ⚠️⚠️⚠️")
                            print(f"腳本 {script_name} 已 {time_since_output/60:.1f} 分鐘沒有輸出，可能卡住")
                            print("正在強制終止...")
                            process.kill()
                            raise TimeoutError(f"腳本超過 {no_output_timeout/60:.0f} 分鐘沒有輸出")

                        time.sleep(0.5)

                except Exception:
                    process.kill()
                    raise
                finally:
                    reader_thread.join(timeout=5)

                socket_error_count = socket_error_counter["count"]

            # [v7.6] 如果是 socket 錯誤導致的失敗，且還有重試次數
            if socket_error_count > 10 and attempt < max_retries:
                print(f"\n{'='*50}")
                print(f"⚠️ 子腳本 {script_name} 因 socket 錯誤失敗")
                print(f"   正在進行第 {attempt + 2}/{max_retries + 1} 次重試...")
                print(f"   等待 15 秒後重新啟動...")
                print(f"{'='*50}\n")
                time.sleep(15)  # 等待 15 秒後重試
                continue
            
            if process.returncode != 0 and attempt < max_retries:
                print(f"\n{'='*50}")
                print(f"⚠️ 子腳本 {script_name} 執行失敗")
                print(f"   正在進行第 {attempt + 2}/{max_retries + 1} 次重試...")
                print(f"   等待 10 秒後重新啟動...")
                print(f"{'='*50}\n")
                time.sleep(10)
                continue
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, command)
                
            print(f"\n{'='*50}")
            print(f">> ✅ 子腳本 {script_name} 執行完畢。")
            print(f"{'='*50}\n")
            time.sleep(5) 
            return True
            
        except subprocess.CalledProcessError as e:
            if attempt < max_retries:
                print(f"\n{'='*50}")
                print(f"⚠️ 子腳本 {script_name} 執行失敗，準備重試...")
                print(f"   錯誤代碼: {e.returncode}")
                print(f"   正在進行第 {attempt + 2}/{max_retries + 1} 次重試...")
                print(f"{'='*50}\n")
                time.sleep(10)
                continue
            else:
                print(f"\n{'='*50}")
                print(f"❌ 錯誤: 子腳本 {script_name} 重試 {max_retries + 1} 次後仍失敗。")
                print(f"   錯誤代碼: {e.returncode}")
                print(f"{'='*50}\n")
                return False
        
        except TimeoutError as e:
            if attempt < max_retries:
                print(f"\n{'='*50}")
                print(f"⚠️ 子腳本 {script_name} 執行超時")
                print(f"   錯誤: {e}")
                print(f"   正在進行第 {attempt + 2}/{max_retries + 1} 次重試...")
                print(f"{'='*50}\n")
                time.sleep(10)
                continue
            else:
                print(f"\n{'='*50}")
                print(f"❌ 錯誤: 子腳本 {script_name} 重試 {max_retries + 1} 次後仍超時。")
                print(f"{'='*50}\n")
                return False
                
        except FileNotFoundError:
            print(f"\n{'='*50}")
            print(f"❌ 錯誤: 找不到腳本 {script_name}。")
            print(f"   請確保它和 run_all_scrapers.py 在同一個資料夾中。")
            print(f"{'='*50}\n")
            return False
            
        except Exception as e:
            if attempt < max_retries:
                print(f"\n{'='*50}")
                print(f"⚠️ 執行 {script_name} 時發生錯誤: {e}")
                print(f"   正在進行第 {attempt + 2}/{max_retries + 1} 次重試...")
                print(f"{'='*50}\n")
                time.sleep(10)
                continue
            else:
                print(f"\n{'='*50}")
                print(f"❌ 執行 {script_name} 時發生未預期錯誤: {e}")
                print(f"{'='*50}\n")
                return False
    
    return False  # 所有重試都失敗


# --- [主執行流程 v7.5] ---
if __name__ == "__main__":
    start_time = datetime.now()
    print(f"======= 價格爬蟲總指揮系統 (OP + UA + VG + DM) v7.7 (自動維護版 + 超時保護) 已啟動 =======")
    print(f"開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("!! 匯率模式: 手動 (將使用 Card_Search!F1 中您輸入的值) !!")
    
    all_success = True

    # --- 【v7.5 新增】維護任務 ---
    print("\n======= [階段 1/2: 系統維護] =======")
    if not run_script("archive_price_history.py"):
        all_success = False # 如果維護失敗，設為 False

    # --- 階段 2: 價格爬取 ---
    if all_success: # <--- 只有在維護成功時，才繼續執行爬取
        print("\n======= [階段 2/2: 價格爬取 (10 個任務)] =======")
        
        # --- 任務 1: OP 售價 ---
        if not run_script("price_scraper_mercadop.py"):
            all_success = False

        # --- 任務 2: OP 買取價 (主列表) ---
        if all_success:
            if not run_script("price_scraper_akiba.py"): 
                all_success = False
                
        # --- 任務 3: OP 買取價 (新彈) ---
        if all_success:
            if not run_script("price_scraper_akiba_op_new.py"):
                all_success = False

        # --- 任務 4: UA 售價 ---
        if all_success:
            if not run_script("price_scraper_uniari.py"):
                all_success = False

        # --- 任務 5: UA 買取價 (主列表) ---
        if all_success:
            if not run_script("price_scraper_akiba_ua.py"):
                all_success = False
                
        # --- 任務 6: UA 買取價 (新彈) ---
        if all_success:
            if not run_script("price_scraper_akiba_ua_new.py"):
                all_success = False
                
        # --- 任務 7: VG 售價 (Card Rush) ---
        if all_success:
            if not run_script("price_scraper_cardrush_vg.py"):
                all_success = False
                
        # --- 任務 8: VG 買取價 (Card Rush Media) ---
        if all_success:
            if not run_script("price_scraper_cardrush_vg_buy.py"):
                all_success = False

        # --- 任務 9: DM 售價 (Card Rush) ---
        if all_success:
            if not run_script("price_scraper_cardrush_dm.py"):
                all_success = False
                
        # --- 任務 10: DM 買取價 (Card Rush Media) ---
        if all_success:
            if not run_script("price_scraper_cardrush_dm_kaitori.py"):
                all_success = False
    
    else:
        # 如果 all_success 在維護階段就失敗了
        print("\n======= ❌ 系統維護 (archive_price_history.py) 失敗，所有爬取任務已中止。 =======")

    # --- 總結 ---
    end_time = datetime.now()
    if all_success:
        print(f"======= 🎉🎉🎉 總指揮系統 (OP + UA + VG + DM) 任務全部完成！ 🎉🎉🎉 =======")
    else:
        print(f"======= ❌ 總指揮系統任務執行中斷。請檢查日誌。 =======")
        
    print(f"結束時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"總耗時: {end_time - start_time}")