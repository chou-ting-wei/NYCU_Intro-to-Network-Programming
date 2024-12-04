import asyncio
import json
import sys
import logging
import config
import os
import hashlib
import aiofiles
import aiofiles.os

logging.basicConfig(
    filename='client.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

peer_info = {
    "role": None,
    "peer_ip": None,
    "peer_port": None,
    "own_port": None,
    "game_name": None
}

COMMAND_ALIASES = {
    "REGISTER": ["REGISTER", "reg", "r"],
    "LOGIN": ["LOGIN", "login"],
    "LOGOUT": ["LOGOUT", "logout"],
    "CREATE_ROOM": ["CREATE_ROOM", "create", "c"],
    "JOIN_ROOM": ["JOIN_ROOM", "join", "j"],
    "INVITE_PLAYER": ["INVITE_PLAYER", "invite", "i"],
    "EXIT": ["EXIT", "exit", "quit", "q"],
    "HELP": ["HELP", "help", "h"],
    "SHOW_STATUS": ["SHOW_STATUS", "status", "s"],
    "MANAGE_INVITES": ["INV", "inv"],
    "LEAVE_ROOM": ["LEAVE_ROOM", "leave"],
    "START_GAME": ["START_GAME", "start", "st"],
    "UPLOAD_GAME": ["UPLOAD_GAME", "upload_game", "ug"],
    "LIST_OWN_GAMES": ["LIST_OWN_GAMES", "list_games", "lg"],
}

COMMANDS = [
    "reg <使用者名稱> <密碼> - 註冊新帳號",
    "login <使用者名稱> <密碼> - 登入帳號",
    "logout - 登出",
    "create <public/private> <rps/ttt/c4> - 創建房間",
    "join <房間ID> - 加入房間",
    "invite <使用者名稱> <房間ID> - 邀請玩家加入房間",
    "start - 開始遊戲（房主專用）",
    "leave - 離開當前房間",
    "inv - 查看和管理您的邀請",
    "upload_game <game_name> - 上傳遊戲文件",
    "list_games - 列出自己發布的遊戲",
    "exit - 離開客戶端",
    "help - 顯示可用指令列表",
    "status - 顯示當前狀態",
]

pending_invitations = []
username = None
user_folder = None
pending_uploads = {}
pending_upload_confirms = {}
pending_downloads = {}
room_info = {}

def get_username_hash(username):
    return hashlib.sha256(username.encode()).hexdigest()[:8] 

async def setup_user_directory(username):
    global user_folder
    username_hash = get_username_hash(username)
    user_folder = f"games-{username_hash}"
    peer_info_path = os.path.join(user_folder, "peer_info.json")
    try:
        if not await aiofiles.os.path.exists(user_folder):
            await aiofiles.os.makedirs(user_folder)
            print(f"已創建資料夾：{user_folder}")
            logging.info(f"已創建資料夾：{user_folder}")
        else:
            print(f"資料夾已存在：{user_folder}")
            logging.info(f"資料夾已存在：{user_folder}")
            
        if not await aiofiles.os.path.exists(peer_info_path):
            initial_peer_info = {
                "role": None,
                "peer_ip": None,
                "peer_port": None,
                "own_port": None,
                "game_name": None
            }
            async with aiofiles.open(peer_info_path, 'w') as f:
                await f.write(json.dumps(initial_peer_info, ensure_ascii=False, indent=4))
            print(f"已創建 peer_info.json 文件。")
            logging.info(f"已創建 peer_info.json 文件：{peer_info_path}")
        else:
            print(f"peer_info.json 文件已存在：{peer_info_path}")
            logging.info(f"peer_info.json 文件已存在：{peer_info_path}")
    except Exception as e:
        print(f"設定用戶資料夾時發生錯誤：{e}")
        logging.error(f"設定用戶資料夾時發生錯誤：{e}")
    return user_folder

def build_command(command, params):
    return json.dumps({"command": command.upper(), "params": params}) + '\n'

def build_response(status, message):
    return json.dumps({"status": status, "message": message}) + '\n'

async def send_command(writer, command, params):
    try:
        message = build_command(command, params)
        writer.write(message.encode())
        await writer.drain()
        logging.info(f"發送指令: {command} {' '.join(params)}")
    except Exception as e:
        print(f"發送指令時發生錯誤: {e}")
        logging.error(f"發送指令時發生錯誤: {e}")

async def send_message(writer, message):
    try:
        data = (json.dumps(message) + '\n').encode()
        writer.write(data)
        await writer.drain()
    except Exception as e:
        logging.error(f"發送訊息失敗: {e}")

async def handle_server_messages(reader, writer, game_in_progress, logged_in):
    while True:
        try:
            data = await reader.readline()
            if not data:
                print("\n伺服器已斷線。")
                logging.info("伺服器已斷線。")
                game_in_progress.value = False
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
                        print("\n伺服器：註冊成功。")
                    elif msg.startswith("LOGIN_SUCCESS"):
                        print("\n伺服器：登入成功。")
                        logged_in.value = True
                        parts = msg.split()
                        if len(parts) >= 2:
                            username = parts[1]
                            await setup_user_directory(username)
                    elif msg.startswith("LOGOUT_SUCCESS"):
                        print("\n伺服器：登出成功。")
                        logged_in.value = False
                    elif msg.startswith("CREATE_ROOM_SUCCESS"):
                        parts = msg.split()
                        room_id = parts[1]
                        game_name = parts[2] if len(parts) > 2 else 'unknown'
                        print(f"\n伺服器：房間創建成功，ID：{room_id}，遊戲類型：{game_name}")
                    elif msg.startswith("JOIN_ROOM_SUCCESS"):
                        parts = msg.split()
                        room_id = parts[1]
                        game_name = parts[2] if len(parts) > 2 else 'unknown'
                        print(f"\n伺服器：成功加入房間，ID：{room_id}，遊戲名稱：{game_name}")
                    elif msg.startswith("INVITE_SENT"):
                        print(f"\n伺服器：{msg}")
                    elif msg.startswith("UPLOAD_GAME_SUCCESS"):
                        game_name = message_json.get('game_name')
                        if game_name in pending_upload_confirms:
                            pending_upload_confirms[game_name].set_result(True)
                            # del pending_upload_confirms[game_name]
                        # print(f"遊戲 {game_name} 上傳成功。")
                    elif 'games' in message_json:
                        logging.info("收到遊戲列表。")
                        # logging.debug(f"遊戲列表：{message_json['games']}")
                        games_list = message_json['games']
                        print("\n您的遊戲列表：")
                        for game in games_list:
                            print(f"遊戲名稱：{game['name']}，描述：{game['description']}，版本：{game['version']}")
                    else:
                        msg = message_json.get("message", "")
                        print(f"\n伺服器：{msg}")
                elif status == "error":
                    print(f"\n錯誤：{msg}")
                elif status == "broadcast":
                    event = message_json.get("event")
                    if event == "user_login":
                        username = message_json.get("username")
                        print(f"\n[系統通知] 玩家 {username} 已登入。")
                    elif event == "user_logout":
                        username = message_json.get("username")
                        print(f"\n[系統通知] 玩家 {username} 已登出。")
                    elif event == "room_created":
                        room_id = message_json.get("room_id")
                        creator = message_json.get("creator")
                        game_name = message_json.get("game_name")
                        room_type = message_json.get("room_type")
                        print(f"\n[系統通知] 玩家 {creator} 創建了 {'公開' if room_type == 'public' else '私人'} 房間 {room_id}，遊戲類型：{game_name}")
                        room_info[room_id] = game_name

                elif status == "invite":
                    inviter = message_json.get("from")
                    room_id = message_json.get("room_id")
                    game_name = message_json.get("game_name", "未知")
                    invitation = {"inviter": inviter, "room_id": room_id}
                    pending_invitations.append(invitation)
                    room_info[room_id] = game_name
                    print(f"\n[邀請通知] 您收到來自 {inviter} 的房間 {room_id} 邀請，遊戲：{game_name}。使用 'inv' 指令來查看和管理您的邀請。")

                
                elif status == "invite_declined":
                    decline_from = message_json.get("from")
                    room_id = message_json.get("room_id")
                    print(f"\n玩家 {decline_from} 拒絕了您對房間 {room_id} 的邀請。")
                    logging.info(f"玩家 {decline_from} 拒絕邀請加入房間 {room_id}。")

                elif status == "file_transfer":
                    game_name = message_json.get("game_name")
                    file_size = int(message_json.get("file_size"))
                    if game_name in pending_downloads:
                        file_content = await reader.readexactly(file_size)
                        file_path = os.path.join(user_folder, game_name + ".py")
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(file_content)
                        pending_downloads[game_name].set_result(file_content)
                        del pending_downloads[game_name]
                        print(f"已下載遊戲檔案 {game_name}.py")
                    else:
                        print("收到未知的文件傳輸。")
            
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
                
                elif status == "p2p_info":
                    new_peer_info = {
                        "role": message_json.get("role"),
                        "peer_ip": message_json.get("peer_ip"),
                        "peer_port": message_json.get("peer_port"),
                        "own_port": message_json.get("own_port"),
                        "game_name": message_json.get("game_name")
                    }
                    await update_peer_info(new_peer_info)
                    peer_info = await read_peer_info()
                    
                    logging.debug(f"角色：{peer_info['role']}，對等方 IP：{peer_info['peer_ip']}，對等方 Port：{peer_info['peer_port']}，自身 Port：{peer_info['own_port']}，遊戲類型：{peer_info['game_name']}")
                    print(f"角色：{peer_info['role']}，對等方 IP：{peer_info['peer_ip']}，對等方 Port：{peer_info['peer_port']}，自身 Port：{peer_info['own_port']}")
                    
                    if None in [peer_info["role"], peer_info["peer_ip"], peer_info["peer_port"], peer_info["own_port"], peer_info["game_name"]]:
                        print("錯誤：收到不完整的 p2p_info 消息。")
                        logging.error("收到不完整的 p2p_info 消息。")
                        return
                    asyncio.create_task(initiate_game(peer_info["game_name"], game_in_progress, writer, user_folder))
                    game_in_progress.value = True
                
                elif status == "host_transfer":
                    new_host = message_json.get("new_host")
                    room_id = message_json.get("room_id")
                    if new_host == username:
                        print(f"\n[系統通知] 您已成為房間 {room_id} 的新房主。")
                    else:
                        print(f"\n[系統通知] 玩家 {new_host} 現在是房間 {room_id} 的房主。")
                
                elif status == "ready":
                    game_name = message_json.get('game_name')
                    if game_name in pending_uploads:
                        pending_uploads[game_name].set_result(True)
                        del pending_uploads[game_name]                
                elif status == "status":
                    print(f"\n{msg}")
                elif status == "info":
                    print(f"\n[系統通知] {msg}")
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
                elif status == "lobby_info":
                    public_rooms = message_json.get("public_rooms", [])
                    online_users = message_json.get("online_users", [])
                    display_public_rooms(public_rooms)
                    display_online_users(online_users)
                else:
                    print(f"\n伺服器：{message}")
            except json.JSONDecodeError:
                print(f"\n伺服器：{message}")
        except Exception as e:
            if not game_in_progress.value:
                print(f"\n接收伺服器資料時發生錯誤：{e}")
                logging.error(f"接收伺服器資料時發生錯誤：{e}")
                game_in_progress.value = False
            break

async def read_peer_info():
    global user_folder
    peer_info_path = os.path.join(user_folder, "peer_info.json")
    try:
        async with aiofiles.open(peer_info_path, 'r') as f:
            content = await f.read()
            return json.loads(content)
    except Exception as e:
        print(f"讀取 peer_info.json 時發生錯誤：{e}")
        logging.error(f"讀取 peer_info.json 時發生錯誤：{e}")
        return None

async def update_peer_info(new_info):
    global user_folder
    peer_info_path = os.path.join(user_folder, "peer_info.json")
    try:
        current_info = await read_peer_info()
        if current_info is None:
            current_info = {}
        current_info.update(new_info)
        async with aiofiles.open(peer_info_path, 'w') as f:
            await f.write(json.dumps(current_info, ensure_ascii=False, indent=4))
        logging.info(f"更新 peer_info.json：{new_info}")
    except Exception as e:
        print(f"更新 peer_info.json 時發生錯誤：{e}")
        logging.error(f"更新 peer_info.json 時發生錯誤：{e}")

async def initiate_game(game_name, game_in_progress, writer, user_folder):
    try:
        game_folder = user_folder if user_folder else 'games'  # 確保使用正確的遊戲目錄
        file_path = os.path.join(game_folder, game_name + ".py")
        print(f"正在執行遊戲 {game_name}...")
        if not os.path.exists(file_path):
            print(f"遊戲檔案 {game_name} 不存在。")
            logging.error(f"遊戲檔案 {game_name} 不存在於 {game_folder}。")
            return

        peer_info = await read_peer_info()
        if peer_info is None:
            print("錯誤：無法讀取 peer_info。")
            logging.error("無法讀取 peer_info。")
            return
        
        required_fields = ["role", "peer_ip", "peer_port", "own_port", "game_name"]
        missing_fields = [field for field in required_fields if peer_info.get(field) is None]
        if missing_fields:
            print(f"錯誤：peer_info 缺少字段：{', '.join(missing_fields)}")
            logging.error(f"peer_info 缺少字段：{', '.join(missing_fields)}")
            return

        game_globals = {}   
        game_globals['peer_info'] = peer_info
        try:
            async with aiofiles.open(file_path, 'r') as f:
                code = await f.read()
            exec(code, game_globals)
            if 'main' in game_globals and callable(game_globals['main']):
                await game_globals['main'](peer_info)
            else:
                print("遊戲腳本不包含 main() 函數。")
                logging.error("遊戲腳本不包含 main() 函數。")
        except Exception as e:
            print(f"讀取或執行遊戲腳本時發生錯誤：{e}")
            logging.error(f"讀取或執行遊戲腳本時發生錯誤：{e}")
    except Exception as e:
        print(f"遊戲執行時發生錯誤：{e}")
        logging.error(f"遊戲執行時發生錯誤：{e}")
    finally:
        game_in_progress.value = False
        await send_command(writer, "GAME_OVER", [])

def display_online_users(online_users):
    print("\n=== 在線用戶列表 ===")
    if not online_users:
        print("無玩家在線。")
    else:
        for user in online_users:
            name = user.get("username", "未知")
            status = user.get("status", "未知")
            print(f"玩家：{name} - 狀態：{status}")
    print("=====================")

def display_public_rooms(rooms):
    print("\n===== 房間列表 =====")
    if not rooms:
        print("無房間等待玩家。")
    else:
        for room in rooms:
            room_id = room.get("room_id", "未知")
            creator = room.get("creator", "未知")
            game_name = room.get("game_name", "未知")
            room_status = room.get("status", "未知")
            room_host = room.get("host", "未知")
            room_type = room.get("type", "未知")
            print(f"房間 ID：{room_id} | 類型：{room_type} | 創建者：{creator} | 房主：{room_host} | 遊戲類型：{game_name} | 狀態：{room_status}")
            room_info[room_id] = game_name
    print("=====================")

async def get_user_input(prompt):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt).strip().lower())

async def handle_user_input(reader, writer, game_in_progress, logged_in):
    while True:
        try:
            if game_in_progress.value:
                await asyncio.sleep(0.1)
                continue
            user_input = await get_user_input("輸入指令：")
            if not user_input:
                continue
            parts = user_input.split()
            if not parts:
                continue
            command_input = parts[0].lower()
            params = parts[1:]

            command = None
            for cmd, aliases in COMMAND_ALIASES.items():
                if command_input in [alias.lower() for alias in aliases]:
                    command = cmd
                    break

            if not command:
                print("未知的指令。請輸入 'help' 查看可用指令。")
                continue

            if command == "EXIT":
                print("正在退出...")
                logging.info("使用者選擇退出客戶端。")
                await send_command(writer, "LOGOUT", [])
                game_in_progress.value = False
                writer.close()
                await writer.wait_closed()
                break
            
            elif command == "HELP":
                print("\n可用的指令：")
                for cmd in COMMANDS:
                    print(cmd)
                print("")
                continue

            elif command == "REGISTER":
                if len(params) != 2:
                    print("用法：reg <使用者名稱> <密碼>")
                    continue
                await send_command(writer, "REGISTER", params)

            elif command == "LOGIN":
                if len(params) != 2:
                    print("用法：login <使用者名稱> <密碼>")
                    continue
                await send_command(writer, "LOGIN", params)

            elif command == "LOGOUT":
                if not logged_in.value:
                    print("尚未登入。")
                    continue
                await send_command(writer, "LOGOUT", [])

            elif command == "CREATE_ROOM":
                if len(params) != 2:
                    print("用法：create <public/private> <game_name>")
                    continue
                room_type = params[0]
                game_name = params[1]
                if user_folder is None:
                    print("尚未設定用戶專屬資料夾。")
                    logging.error("用戶專屬資料夾未設定。")
                    continue
                game_folder = user_folder
                file_path = os.path.join(game_folder, game_name + '.py')
                logging.debug(f"遊戲檔案路徑：{file_path}")
                if not os.path.exists(file_path):
                    print(f"遊戲檔案 {game_name}.py 不存在，正在從伺服器下載...")
                else:
                    print(f"遊戲檔案 {game_name}.py 已存在，更新中...")
                download_future = asyncio.get_event_loop().create_future()
                pending_downloads[game_name] = download_future
                await send_command(writer, "DOWNLOAD_GAME_FILE", [game_name])
                try:
                    await asyncio.wait_for(download_future, timeout=10)
                except asyncio.TimeoutError:
                    print("下載遊戲檔案超時。")
                    del pending_downloads[game_name]
                    continue
                except Exception as e:
                    print(f"下載遊戲檔案失敗：{e}")
                    del pending_downloads[game_name]
                    continue
                await send_command(writer, "CREATE_ROOM", [room_type, game_name])

            elif command == "JOIN_ROOM":
                if len(params) != 1:
                    print("用法：join <房間ID>")
                    continue
                room_id = params[0]
                if room_id not in room_info:
                    print("未知的房間ID，請先使用 'status' 指令查看可用房間。")
                    continue
                game_name = room_info[room_id]
                if user_folder is None:
                    print("尚未設定用戶專屬資料夾。")
                    logging.error("用戶專屬資料夾未設定。")
                    continue
                game_folder = user_folder
                file_path = os.path.join(game_folder, game_name + '.py')
                logging.debug(f"遊戲檔案路徑：{file_path}")
                if not os.path.exists(file_path):
                    print(f"遊戲檔案 {game_name}.py 不存在，正在從伺服器下載...")
                else:
                    print(f"遊戲檔案 {game_name}.py 已存在，更新中...")
                download_future = asyncio.get_event_loop().create_future()
                pending_downloads[game_name] = download_future
                await send_command(writer, "DOWNLOAD_GAME_FILE", [game_name])
                try:
                    await asyncio.wait_for(download_future, timeout=10)
                except asyncio.TimeoutError:
                    print("下載遊戲檔案超時。")
                    del pending_downloads[game_name]
                    continue
                except Exception as e:
                    print(f"下載遊戲檔案失敗：{e}")
                    del pending_downloads[game_name]
                    continue
                await send_command(writer, "JOIN_ROOM", [room_id])

            elif command == "INVITE_PLAYER":
                if len(params) != 2:
                    print("用法：invite <使用者名稱> <房間ID>")
                    continue
                await send_command(writer, "INVITE_PLAYER", params)

            elif command == "SHOW_STATUS":
                await send_command(writer, "SHOW_STATUS", [])

            elif command == "MANAGE_INVITES":
                if not pending_invitations:
                    print("您目前沒有任何待處理的邀請。")
                else:
                    print("\n=== 您的邀請列表 ===")
                    for idx, invite in enumerate(pending_invitations, start=1):
                        inviter = invite['inviter']
                        room_id = invite['room_id']
                        game_name = room_info.get(room_id, '未知')
                        print(f"{idx}. 來自 {inviter} 的房間 {room_id}，遊戲：{game_name}")
                    print("====================")
                    response = await get_user_input("輸入邀請編號以接受，或輸入 'no' 來返回：")
                    if response.isdigit():
                        index = int(response) - 1
                        if 0 <= index < len(pending_invitations):
                            invitation = pending_invitations.pop(index)
                            await send_command(writer, "ACCEPT_INVITE", [invitation['room_id']])
                            logging.info(f"接受邀請加入房間：{invitation['room_id']}")
                        else:
                            print("無效的邀請編號。")
                    else:
                        print("已返回。")
            elif command == "LEAVE_ROOM":
                if not logged_in.value:
                    print("尚未登入。")
                    continue
                await send_command(writer, "LEAVE_ROOM", [])
            elif command == "START_GAME":
                if not logged_in.value:
                    print("尚未登入。")
                    continue
                await send_command(writer, "START_GAME", [])
            elif command == "UPLOAD_GAME":
                if not logged_in.value:
                    print("尚未登入。")
                    continue
                if len(params) != 1:
                    print("用法：upload_game <game_file_name>")
                    continue
                game_file_name = params[0]
                game_description = await get_user_input("輸入遊戲描述：")
                if user_folder is None:
                    print("尚未設定用戶專屬資料夾。")
                    logging.error("用戶專屬資料夾未設定。")
                    continue
                game_folder = user_folder
                file_path = os.path.join(game_folder, game_file_name + '.py')
                if not os.path.exists(file_path):
                    print(f"遊戲檔案 {file_path} 不存在。")
                    continue
                upload_ready_future = asyncio.get_event_loop().create_future()
                pending_uploads[game_file_name] = upload_ready_future
                await send_command(writer, "UPLOAD_GAME", [game_file_name, game_description])
                try:
                    await asyncio.wait_for(upload_ready_future, timeout=10)
                except asyncio.TimeoutError:
                    print("伺服器未回應。")
                    del pending_uploads[game_file_name]
                    continue
                except Exception as e:
                    print(f"上傳遊戲時發生錯誤：{e}")
                    del pending_uploads[game_file_name]
                    continue
                try:
                    async with aiofiles.open(file_path, 'rb') as f:
                        file_content = await f.read()
                    file_size = len(file_content)
                    await send_message(writer, {'file_size': file_size})
                    await writer.drain() 
                    writer.write(file_content)
                    await writer.drain()
                    upload_confirm_future = asyncio.get_event_loop().create_future()
                    pending_upload_confirms[game_file_name] = upload_confirm_future
                    try:
                        await asyncio.wait_for(upload_confirm_future, timeout=10)
                        print("遊戲上傳成功。")
                        del pending_upload_confirms[game_file_name]
                        continue
                    except asyncio.TimeoutError:
                        print("伺服器未確認上傳結果。")
                        del pending_upload_confirms[game_file_name]
                        continue
                except Exception as e:
                    print(f"上傳遊戲時發生錯誤：{e}")
                    continue
            elif command == "LIST_OWN_GAMES":
                if not logged_in.value:
                    print("尚未登入。")
                    continue
                await send_command(writer, "LIST_OWN_GAMES", [])
            else:
                print("未知的指令。請輸入 'help' 查看可用指令。")
        except KeyboardInterrupt:
            print("\n正在退出...")
            logging.info("使用者透過鍵盤中斷退出客戶端。")
            await send_command(writer, "LOGOUT", [])
            game_in_progress.value = False
            writer.close()
            await writer.wait_closed()
            break
        except Exception as e:
            print(f"發送指令時發生錯誤：{e}")
            logging.error(f"發送指令時發生錯誤：{e}")
            game_in_progress.value = False
            writer.close()
            await writer.wait_closed()
            break

async def main():
    server_ip = input(f"輸入伺服器 IP（預設：{config.HOST}）：").strip()
    server_ip = server_ip if server_ip else config.HOST
    server_port_input = input(f"輸入伺服器 port（預設：{config.PORT}）：").strip()
    try:
        server_port = int(server_port_input) if server_port_input else config.PORT
    except ValueError:
        print("無效的 port 輸入。使用預設 port 15000。")
        server_port = config.PORT

    try:
        reader, writer = await asyncio.open_connection(server_ip, server_port)
        print("成功連接到大廳伺服器。")
        logging.info(f"成功連接到伺服器 {server_ip}:{server_port}")
    except ConnectionRefusedError:
        print("連線被拒絕，請確認伺服器是否正在運行。")
        logging.error("連線被拒絕，請確認伺服器是否正在運行。")
        return
    except Exception as e:
        print(f"無法連接到伺服器：{e}")
        logging.error(f"無法連接到伺服器：{e}")
        return

    game_in_progress = type('', (), {'value': False})()
    logged_in = type('', (), {'value': False})()

    asyncio.create_task(handle_server_messages(reader, writer, game_in_progress, logged_in))
    asyncio.create_task(handle_user_input(reader, writer, game_in_progress, logged_in))

    print("\n可用的指令：")
    for cmd in COMMANDS:
        print(cmd)
    print("")

    await asyncio.Future()

    print("客戶端已關閉。")
    logging.info("客戶端已關閉。")
    sys.exit()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"客戶端異常終止：{e}")
        logging.error(f"客戶端異常終止：{e}")