# client.py

import asyncio
import json
import sys
import subprocess
import logging
import config  # 確保導入 config 模組
import platform

# 設定日誌
logging.basicConfig(
    filename='client.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

# 可用的指令列表
COMMANDS = [
    "REGISTER <username> <password> - 註冊新帳號",
    "LOGIN <username> <password> - 登入帳號",
    "LOGOUT - 登出",
    "CREATE_ROOM <public/private> <rock_paper_scissors/tictactoe> - 創建房間",
    "JOIN_ROOM <room_id> - 加入房間",
    "INVITE_PLAYER <username> <room_id> - 邀請玩家加入房間",
    "EXIT - 離開客戶端",
    "HELP - 顯示可用指令列表",
    "SHOW_STATUS - 顯示當前狀態"  # 新增 show status 指令
]

def build_command(command, params):
    """構建 JSON 格式的指令"""
    return json.dumps({"command": command.upper(), "params": params}) + '\n'

def build_response(status, message):
    """構建 JSON 格式的回應訊息"""
    return json.dumps({"status": status, "message": message}) + '\n'

async def send_command(writer, command, params):
    """發送指令到伺服器的協程函數"""
    try:
        message = build_command(command, params)
        writer.write(message.encode())
        await writer.drain()
        logging.info(f"發送指令: {command} {' '.join(params)}")
    except Exception as e:
        print(f"發送指令時發生錯誤: {e}")
        logging.error(f"發送指令時發生錯誤: {e}")

async def send_message(writer, message):
    """發送訊息給伺服器"""
    try:
        writer.write(message.encode())
        await writer.drain()
    except Exception as e:
        logging.error(f"發送訊息失敗: {e}")

async def handle_server_messages(reader, writer, stop_event, game_event):
    """接收伺服器訊息的協程函數"""
    while not stop_event.is_set():
        try:
            data = await reader.readline()
            if not data:
                print("\n伺服器斷線。")
                logging.info("伺服器斷線。")
                stop_event.set()
                break
            message = data.decode().strip()
            if not message:
                continue
            try:
                message_json = json.loads(message)
                status = message_json.get("status")
                msg = message_json.get("message", "")
                
                if status == "success":
                    if msg.startswith("REGISTER_SUCCESS"):
                        print("\n伺服器: REGISTER_SUCCESS")
                    elif msg.startswith("LOGIN_SUCCESS"):
                        print("\n伺服器: LOGIN_SUCCESS")
                        # 在登入成功後，等待伺服器發送更新訊息
                    elif msg.startswith("LOGOUT_SUCCESS"):
                        print("\n伺服器: LOGOUT_SUCCESS")
                    elif msg.startswith("CREATE_ROOM_SUCCESS"):
                        parts = msg.split()
                        room_id = parts[1]
                        print(f"\n伺服器: CREATE_ROOM_SUCCESS {room_id}")
                    elif msg.startswith("JOIN_ROOM_SUCCESS"):
                        parts = msg.split()
                        room_id = parts[1]
                        game_type = parts[2] if len(parts) > 2 else 'rock_paper_scissors'
                        print(f"\n伺服器: JOIN_ROOM_SUCCESS {room_id} {game_type}")
                        # 啟動遊戲客戶端與遊戲伺服器連線
                        asyncio.create_task(initiate_game(room_id, game_type, game_event))
                    elif msg.startswith("INVITE_SENT"):
                        print(f"\n伺服器: {msg}")
                elif status == "error":
                    print(f"\n錯誤: {msg}")
                elif status == "invite":
                    inviter = message_json.get("from")
                    room_id = message_json.get("room_id")
                    response = await get_user_input(f"\n您收到來自 {inviter} 的房間 {room_id} 邀請。是否接受？(yes/no): ")
                    if response == 'yes':
                        await send_command(writer, "ACCEPT_INVITE", [room_id])
                        logging.info(f"接受邀請加入房間: {room_id}")
                    else:
                        print("已拒絕邀請。")
                        logging.info(f"拒絕邀請加入房間: {room_id}")
                elif status == "update":
                    update_type = message_json.get("type")
                    if update_type == "online_users":
                        online_users = message_json.get("data", [])
                        display_online_users(online_users)
                    elif update_type == "public_rooms":
                        public_rooms = message_json.get("data", [])
                        display_public_rooms(public_rooms)
                    elif update_type == "room_status":
                        room_id = message_json.get("room_id")
                        status_update = message_json.get("status")
                        print(f"\n房間 {room_id} 狀態更新為 {status_update}")
                elif status == "game_server_info":
                    # 接收到遊戲伺服器的連接資訊，啟動遊戲客戶端
                    room_id = message_json.get("room_id")
                    game_server_ip = message_json.get("game_server_ip")
                    game_server_port = message_json.get("game_server_port")
                    game_type = message_json.get("game_type")
                    print(f"\n伺服器: 遊戲即將開始！遊戲伺服器位於 {game_server_ip}:{game_server_port}")
                    # 啟動遊戲客戶端並傳遞遊戲伺服器的 IP 和 port
                    asyncio.create_task(initiate_game_with_server(game_server_ip, game_server_port, room_id, game_type, game_event))
                elif status == "status":
                    # 處理 SHOW_STATUS 指令的回應，直接顯示格式化訊息
                    print(f"\n{msg}")
                else:
                    print(f"\n伺服器: {message}")
            except json.JSONDecodeError:
                print(f"\n伺服器: {message}")
        except Exception as e:
            if not stop_event.is_set():
                print(f"\n接收伺服器資料時發生錯誤: {e}")
                logging.error(f"接收伺服器資料時發生錯誤: {e}")
                stop_event.set()
            break

async def initiate_game(room_id, game_type, game_event):
    """啟動對應的遊戲客戶端"""
    try:
        if game_type == 'rock_paper_scissors':
            # 當收到 JOIN_ROOM_SUCCESS 時，不啟動遊戲客戶端，等待伺服器發送 game_server_info
            pass
        elif game_type == 'tictactoe':
            # 同樣等待伺服器發送 game_server_info
            pass
        else:
            print(f"未知的遊戲類型: {game_type}")
            logging.error(f"未知的遊戲類型: {game_type}")
    except Exception as e:
        print(f"啟動遊戲客戶端時發生錯誤: {e}")
        logging.error(f"啟動遊戲客戶端時發生錯誤: {e}")

async def initiate_game_with_server(game_server_ip, game_server_port, room_id, game_type, game_event):
    """啟動對應的遊戲客戶端並連接到遊戲伺服器"""
    try:
        if game_type == 'rock_paper_scissors':
            if platform.system() == "Darwin":  # macOS
                subprocess.Popen([
                    "osascript", "-e",
                    f'tell application "Terminal" to do script "python3 {config.CLIENT_GAME_RPS_SCRIPT} {game_server_ip} {game_server_port} {room_id}"'
                ])
            elif platform.system() == "Windows":
                subprocess.Popen([
                    "cmd.exe", "/c", "start",
                    "python", config.CLIENT_GAME_RPS_SCRIPT, game_server_ip, str(game_server_port), room_id
                ])
            elif platform.system() == "Linux":
                subprocess.Popen([
                    "gnome-terminal", "--", "python3", config.CLIENT_GAME_RPS_SCRIPT, game_server_ip, str(game_server_port), room_id
                ])
            else:
                print("Unsupported OS for opening a new terminal.")
                logging.error("Unsupported OS for opening a new terminal.")
        elif game_type == 'tictactoe':
            if platform.system() == "Darwin":  # macOS
                subprocess.Popen([
                    "osascript", "-e",
                    f'tell application "Terminal" to do script "python3 {config.CLIENT_GAME_TICTACTOE_SCRIPT} {game_server_ip} {game_server_port} {room_id}"'
                ])
            elif platform.system() == "Windows":
                subprocess.Popen([
                    "cmd.exe", "/c", "start",
                    "python", config.CLIENT_GAME_TICTACTOE_SCRIPT, game_server_ip, str(game_server_port), room_id
                ])
            elif platform.system() == "Linux":
                subprocess.Popen([
                    "gnome-terminal", "--", "python3", config.CLIENT_GAME_TICTACTOE_SCRIPT, game_server_ip, str(game_server_port), room_id
                ])
            else:
                print("Unsupported OS for opening a new terminal.")
                logging.error("Unsupported OS for opening a new terminal.")
        else:
            print(f"Unsupported game type: {game_type}")
            logging.error(f"Unsupported game type: {game_type}")
    except FileNotFoundError:
        print(f"遊戲客戶端檔案未找到: {config.CLIENT_GAME_RPS_SCRIPT}")
        logging.error(f"遊戲客戶端檔案未找到: {config.CLIENT_GAME_RPS_SCRIPT}")
    except Exception as e:
        print(f"啟動遊戲客戶端時發生錯誤: {e}")
        logging.error(f"啟動遊戲客戶端時發生錯誤: {e}")

def display_online_users(online_users):
    """顯示在線用戶列表"""
    print("\n=== 在線用戶列表 ===")
    if not online_users:
        print("無玩家在線。")
    else:
        for user in online_users:
            name = user.get("username", "未知")
            status = user.get("status", "未知")
            print(f"玩家: {name} - 狀態: {status}")
    print("=====================")

def display_public_rooms(public_rooms):
    """顯示公開房間列表"""
    print("\n=== 公開房間列表 ===")
    if not public_rooms:
        print("無公開房間等待玩家。")
    else:
        for room in public_rooms:
            room_id = room.get("room_id", "未知")
            creator = room.get("creator", "未知")
            game_type = room.get("game_type", "未知")
            room_status = room.get("status", "未知")
            print(f"房間ID: {room_id} | 創建者: {creator} | 遊戲類型: {game_type} | 狀態: {room_status}")
    print("=====================")

async def get_user_input(prompt):
    """使用 asyncio 的 run_in_executor 來處理阻塞式的 input"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt).strip().lower())

async def handle_user_input(writer, stop_event, game_event):
    """處理用戶輸入的協程函數"""
    while not stop_event.is_set():
        try:
            if game_event.is_set():
                # 遊戲進行中，不接受其他指令
                await asyncio.sleep(0.1)
                continue
            user_input = await get_user_input("輸入指令: ")
            if not user_input:
                continue
            parts = user_input.split()
            command = parts[0].upper()
            params = parts[1:]

            if command == "EXIT":
                print("正在退出...")
                logging.info("使用者選擇退出客戶端。")
                # 嘗試登出
                await send_command(writer, "LOGOUT", [])
                stop_event.set()
                writer.close()
                await writer.wait_closed()
                break

            elif command == "HELP":
                print("\n可用的指令:")
                for cmd in COMMANDS:
                    print(cmd)
                print("")  # 空行
                continue  # 不發送到伺服器

            elif command == "REGISTER":
                if len(params) != 2:
                    print("用法: REGISTER <username> <password>")
                    continue
                await send_command(writer, "REGISTER", params)

            elif command == "LOGIN":
                if len(params) != 2:
                    print("用法: LOGIN <username> <password>")
                    continue
                await send_command(writer, "LOGIN", params)

            elif command == "LOGOUT":
                await send_command(writer, "LOGOUT", [])
                # 此處不設置 username，因為伺服器會處理

            elif command == "CREATE_ROOM":
                if len(params) != 2:
                    print("用法: CREATE_ROOM <public/private> <rock_paper_scissors/tictactoe>")
                    continue
                await send_command(writer, "CREATE_ROOM", params)

            elif command == "JOIN_ROOM":
                if len(params) != 1:
                    print("用法: JOIN_ROOM <room_id>")
                    continue
                await send_command(writer, "JOIN_ROOM", params)

            elif command == "INVITE_PLAYER":
                if len(params) != 2:
                    print("用法: INVITE_PLAYER <username> <room_id>")
                    continue
                await send_command(writer, "INVITE_PLAYER", params)

            elif command == "SHOW_STATUS":
                await send_command(writer, "SHOW_STATUS", [])

            else:
                print("未知的指令。請重試。")
        except KeyboardInterrupt:
            print("\n正在退出...")
            logging.info("使用者透過鍵盤中斷退出客戶端。")
            # 嘗試登出
            await send_command(writer, "LOGOUT", [])
            stop_event.set()
            writer.close()
            await writer.wait_closed()
            break
        except Exception as e:
            print(f"發送指令時發生錯誤: {e}")
            logging.error(f"發送指令時發生錯誤: {e}")
            stop_event.set()
            writer.close()
            await writer.wait_closed()
            break

async def main():
    server_ip = input("輸入伺服器 IP (預設: 127.0.0.1): ").strip()
    server_ip = server_ip if server_ip else '127.0.0.1'
    server_port_input = input("輸入伺服器 port (預設: 15000): ").strip()
    try:
        server_port = int(server_port_input) if server_port_input else 15000
    except ValueError:
        print("無效的 port 輸入。使用預設 port 15000。")
        server_port = 15000

    try:
        reader, writer = await asyncio.open_connection(server_ip, server_port)
        print("成功連接到大廳伺服器。")
        logging.info(f"成功連接到伺服器 {server_ip}:{server_port}")
    except ConnectionRefusedError:
        print("連線被拒絕，請確認伺服器是否正在運行。")
        logging.error("連線被拒絕，請確認伺服器是否正在運行。")
        return
    except Exception as e:
        print(f"無法連接到伺服器: {e}")
        logging.error(f"無法連接到伺服器: {e}")
        return

    stop_event = asyncio.Event()
    game_event = asyncio.Event()  # 用於標誌遊戲是否進行中

    # 啟動接收訊息的協程
    asyncio.create_task(handle_server_messages(reader, writer, stop_event, game_event))

    # 啟動處理用戶輸入的協程
    asyncio.create_task(handle_user_input(writer, stop_event, game_event))

    # 顯示可用指令列表一次
    print("\n可用的指令:")
    for cmd in COMMANDS:
        print(cmd)
    print("")  # 空行

    # 等待停止事件
    await stop_event.wait()

    print("客戶端已關閉。")
    logging.info("客戶端已關閉。")
    sys.exit()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"客戶端異常終止: {e}")
        logging.error(f"客戶端異常終止: {e}")