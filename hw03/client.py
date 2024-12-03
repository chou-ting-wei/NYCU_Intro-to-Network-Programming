import asyncio
import json
import sys
import logging
import config

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
    "game_type": None
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
    "START_GAME": ["START_GAME", "start", "st"]
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
    "inv - 查看和管理您的邀請"
    "exit - 離開客戶端",
    "help - 顯示可用指令列表",
    "status - 顯示當前狀態"
]

pending_invitations = []

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
        data = json.dumps(message).encode()
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
                    elif msg.startswith("LOGOUT_SUCCESS"):
                        print("\n伺服器：登出成功。")
                        logged_in.value = False
                    elif msg.startswith("CREATE_ROOM_SUCCESS"):
                        parts = msg.split()
                        room_id = parts[1]
                        game_type = parts[2] if len(parts) > 2 else 'rps'
                        print(f"\n伺服器：房間創建成功，ID：{room_id}，遊戲類型：{game_type}")
                    elif msg.startswith("JOIN_ROOM_SUCCESS"):
                        parts = msg.split()
                        room_id = parts[1]
                        game_type = parts[2] if len(parts) > 2 else 'rps'
                        print(f"\n伺服器：成功加入房間，ID：{room_id}，遊戲類型：{game_type}")
                    elif msg.startswith("INVITE_SENT"):
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
                        game_type = message_json.get("game_type")
                        room_type = message_json.get("room_type")
                        print(f"\n[系統通知] 玩家 {creator} 創建了 {'公開' if room_type == 'public' else '私人'} 房間 {room_id}，遊戲類型：{game_type}")

                elif status == "invite":
                    inviter = message_json.get("from")
                    room_id = message_json.get("room_id")
                    invitation = {"inviter": inviter, "room_id": room_id}
                    pending_invitations.append(invitation)
                    print(f"\n[邀請通知] 您收到來自 {inviter} 的房間 {room_id} 邀請。使用 'inv' 指令來查看和管理您的邀請。")
                    # response = await get_user_input(f"\n您收到來自 {inviter} 的邀請，加入房間 {room_id}。接受嗎？(yes/no)：")
                    # if response == 'yes':
                    #     await send_command(writer, "ACCEPT_INVITE", [room_id])
                    #     logging.info(f"接受邀請加入房間：{room_id}")
                    # else:
                    #     await send_command(writer, "DECLINE_INVITE", [inviter, room_id])
                    #     print("已拒絕邀請。")
                    #     logging.info(f"拒絕邀請加入房間：{room_id}")
                elif status == "invite_declined":
                    decline_from = message_json.get("from")
                    room_id = message_json.get("room_id")
                    print(f"\n玩家 {decline_from} 拒絕了您對房間 {room_id} 的邀請。")
                    logging.info(f"玩家 {decline_from} 拒絕邀請加入房間 {room_id}。")

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
                    peer_info["role"] = message_json.get("role")
                    peer_info["peer_ip"] = message_json.get("peer_ip")
                    peer_info["peer_port"] = message_json.get("peer_port")
                    peer_info["own_port"] = message_json.get("own_port")
                    peer_info["game_type"] = message_json.get("game_type")
                    logging.debug(f"角色：{peer_info['role']}，對等方 IP：{peer_info['peer_ip']}，對等方 Port：{peer_info['peer_port']}，自身 Port：{peer_info['own_port']}，遊戲類型：{peer_info['game_type']}")
                    print(f"角色：{peer_info['role']}，對等方 IP：{peer_info['peer_ip']}，對等方 Port：{peer_info['peer_port']}，自身 Port：{peer_info['own_port']}")
                    asyncio.create_task(initiate_game(peer_info["game_type"], game_in_progress, writer))
                    game_in_progress.value = True
                elif status == "host_transfer":
                    new_host = message_json.get("new_host")
                    room_id = message_json.get("room_id")
                    if new_host == username:
                        print(f"\n[系統通知] 您已成為房間 {room_id} 的新房主。")
                    else:
                        print(f"\n[系統通知] 玩家 {new_host} 現在是房間 {room_id} 的房主。")
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

async def initiate_game(game_type, game_in_progress, writer):
    try:
        if game_type is None:
            raise ValueError("game_type 未定義")
        
        if game_type.lower() == 'rps' or game_type.lower() == 'rock_paper_scissors':
            if peer_info.get("role") == "host":
                await start_rps_game_as_host(peer_info.get("own_port"))
            elif peer_info.get("role") == "client":
                await start_rps_game_as_client(peer_info.get("peer_ip"), peer_info.get("peer_port"))
        elif game_type.lower() == 'ttt' or game_type.lower() == 'tictactoe':
            if peer_info.get("role") == "host":
                await start_tictactoe_game_as_host(peer_info.get("own_port"))
            elif peer_info.get("role") == "client":
                await start_tictactoe_game_as_client(peer_info.get("peer_ip"), peer_info.get("peer_port"))
        elif game_type.lower() == 'c4' or game_type.lower() == 'connectfour':
            if peer_info.get("role") == "host":
                await start_connectfour_game_as_host(peer_info.get("own_port"))
            elif peer_info.get("role") == "client":
                await start_connectfour_game_as_client(peer_info.get("peer_ip"), peer_info.get("peer_port"))
        else:
            logging.error("無效的遊戲類型")
            print("無效的遊戲類型")
    finally:
        game_in_progress.value = False
        await send_command(writer, "GAME_OVER", [])

ASCII_ART = {
    'rock': '''
        _______
    ---'   ____)
          (_____)
          (_____)
          (____)
    ---.__(___)
    ''',
    'paper': '''
         _______
    ---'    ____)____
               ______)
              _______)
             _______)
    ---.__________)
    ''',
    'scissors': '''
        _______
    ---'   ____)____
              ______)
           __________)
          (____)
    ---.__(___)
    '''
}

VALID_MOVES = ['rock', 'paper', 'scissors']

# -------------------------
# Rock-Paper-Scissors (RPS) 遊戲函數
# -------------------------

async def start_rps_game_as_host(own_port):
    server = await asyncio.start_server(handle_rps_client, '0.0.0.0', own_port)
    logging.info(f"等待客戶端連接於 {own_port} 作為 RPS 主機...")
    print(f"等待客戶端連接於 {own_port} 作為 RPS 主機...")
    
    global server_close_event
    server_close_event = asyncio.Event()

    async def stop_server():
        await server_close_event.wait()
        server.close()
        await server.wait_closed()
        print("遊戲伺服器已關閉。")

    async with server:
        await asyncio.gather(server.serve_forever(), stop_server())

async def handle_rps_client(reader, writer):
    try:
        print("RPS 客戶端已連接。")
        await rps_game_loop(reader, writer, "Host")
    except Exception as e:
        logging.error(f"RPS 主機錯誤：{e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def start_rps_game_as_client(peer_ip, peer_port, max_retries=10, retry_delay=2):
    writer = None
    retries = 0

    while retries < max_retries:
        try:
            print(f"正在連接到 {peer_ip}:{peer_port} 的 RPS 主機作為客戶端...（嘗試 {retries + 1}）")
            reader, writer = await asyncio.open_connection(peer_ip, peer_port)
            print("已成功連接到主機。")
            await rps_game_loop(reader, writer, "Client")
            break

        except ConnectionRefusedError:
            retries += 1
            if retries >= max_retries:
                logging.error(f"嘗試 {max_retries} 次後連接失敗。")
                print(f"嘗試 {max_retries} 次後連接失敗。正在退出...")
                return
            else:
                print(f"連接被拒絕，{retry_delay} 秒後重試...")
                await asyncio.sleep(retry_delay)

        except Exception as e:
            logging.error(f"啟動 RPS 客戶端模式時失敗：{e}")
            break

    if writer is not None:
        writer.close()
        await writer.wait_closed()

async def rps_game_loop(reader, writer, role):
    my_move = None
    opponent_move = None
    game_over = False

    while not game_over:
        if role == "Host":
            # Host move
            my_move = await get_rps_move("Host")
            await send_message(writer, {"move": my_move})
            print("等待對手的移動...")
            data = await reader.read(1024)
            if not data:
                print("對手已斷開連接。")
                game_over = True
                break
            try:
                message = json.loads(data.decode())
                opponent_move = message.get("move")
                if opponent_move not in VALID_MOVES:
                    print("收到無效的移動。")
                    continue
            except json.JSONDecodeError:
                print("收到無效的訊息。")
                continue
        else:
            # Client move
            print("等待對手的移動...")
            data = await reader.read(1024)
            if not data:
                print("對手已斷開連接。")
                game_over = True
                break
            try:
                message = json.loads(data.decode())
                opponent_move = message.get("move")
                if opponent_move not in VALID_MOVES:
                    print("收到無效的移動。")
                    continue
            except json.JSONDecodeError:
                print("收到無效的訊息。")
                continue
            my_move = await get_rps_move("Client")
            await send_message(writer, {"move": my_move})

        result = determine_rps_winner(my_move, opponent_move, role)
        display_rps_result(my_move, opponent_move, result, role)
        game_over = True
        server_close_event.set()

async def get_rps_move(player):
    while True:
        move = await get_user_input(f"玩家 {player}，請選擇 rock、paper 或 scissors：")
        move = move.strip().lower()
        if move in VALID_MOVES:
            print(ASCII_ART.get(move, ''))
            return move
        else:
            print("無效的選擇，請再試一次。")

def determine_rps_winner(my_move, opponent_move, role):
    if my_move == opponent_move:
        return "平局"
    elif (my_move == 'rock' and opponent_move == 'scissors') or \
         (my_move == 'paper' and opponent_move == 'rock') or \
         (my_move == 'scissors' and opponent_move == 'paper'):
        return f"玩家 {role} 獲勝"
    else:
        return f"玩家 {'Client' if role == 'Host' else 'Host'} 獲勝"

def display_rps_result(my_move, opponent_move, result, role):
    print("\n=== 遊戲結果 ===")
    print(f"您的移動：{my_move}")
    print(ASCII_ART.get(my_move, ''))
    print(f"對手的移動：{opponent_move}")
    print(ASCII_ART.get(opponent_move, ''))
    print(f"結果：{result}")
    print("================")

# -------------------------
# Tic-Tac-Toe (TTT) 遊戲函數
# -------------------------

async def start_tictactoe_game_as_host(own_port):
    server = await asyncio.start_server(handle_tictactoe_client, '0.0.0.0', own_port)
    logging.info(f"等待客戶端連接於 {own_port} 作為 Tic-Tac-Toe 主機...")
    print(f"等待客戶端連接於 {own_port} 作為 Tic-Tac-Toe 主機...")
    
    global server_close_event
    server_close_event = asyncio.Event()

    async def stop_server():
        await server_close_event.wait()
        server.close()
        await server.wait_closed()
        print("遊戲伺服器已關閉。")

    async with server:
        await asyncio.gather(server.serve_forever(), stop_server())

async def handle_tictactoe_client(reader, writer):
    try:
        print("Tic-Tac-Toe 客戶端已連接。")
        await tictactoe_game_loop(reader, writer, "Host")
    except Exception as e:
        logging.error(f"Tic-Tac-Toe 主機錯誤：{e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def start_tictactoe_game_as_client(peer_ip, peer_port, max_retries=10, retry_delay=2):
    writer = None
    retries = 0

    while retries < max_retries:
        try:
            print(f"正在連接到 {peer_ip}:{peer_port} 的 Tic-Tac-Toe 主機作為客戶端...（嘗試 {retries + 1}）")
            reader, writer = await asyncio.open_connection(peer_ip, peer_port)
            print("已成功連接到主機。")
            await tictactoe_game_loop(reader, writer, "Client")
            break

        except ConnectionRefusedError:
            retries += 1
            if retries >= max_retries:
                logging.error(f"嘗試 {max_retries} 次後連接失敗。")
                print(f"嘗試 {max_retries} 次後連接失敗。正在退出...")
                return
            else:
                print(f"連接被拒絕，{retry_delay} 秒後重試...")
                await asyncio.sleep(retry_delay)

        except Exception as e:
            logging.error(f"啟動 Tic-Tac-Toe 客戶端模式時失敗：{e}")
            break

    if writer is not None:
        writer.close()
        await writer.wait_closed()

async def tictactoe_game_loop(reader, writer, role):
    board = [' ' for _ in range(9)]
    my_symbol = 'X' if role == "Host" else 'O'
    opponent_symbol = 'O' if role == "Host" else 'X'
    current_turn = 'X'  # 'X' moves first
    game_over = False

    while not game_over:
        display_board(board)
        if current_turn == my_symbol:
            move = await get_tictactoe_move(board, my_symbol)
            board[move] = my_symbol
            await send_message(writer, {"move": move})
        else:
            print("等待對手的移動...")
            data = await reader.read(1024)
            if not data:
                print("對手已斷開連接。")
                game_over = True
                break
            message = json.loads(data.decode())
            move = message.get("move")
            board[move] = opponent_symbol

        if check_winner(board, my_symbol):
            display_board(board)
            print(f"玩家 {my_symbol} 獲勝!")
            game_over = True
            server_close_event.set()
        elif check_winner(board, opponent_symbol):
            display_board(board)
            print(f"玩家 {opponent_symbol} 獲勝!")
            game_over = True
            server_close_event.set()
        elif ' ' not in board:
            display_board(board)
            print("平局!")
            game_over = True
            server_close_event.set()
        else:
            # Switch turns
            current_turn = opponent_symbol if current_turn == my_symbol else my_symbol

def display_board(board):
    print("\n當前棋盤：")
    display = [str(i+1) if cell == ' ' else cell for i, cell in enumerate(board)]
    print(f" {display[0]} | {display[1]} | {display[2]} ")
    print("---+---+---")
    print(f" {display[3]} | {display[4]} | {display[5]} ")
    print("---+---+---")
    print(f" {display[6]} | {display[7]} | {display[8]} ")
    print("")

async def get_tictactoe_move(board, player):
    while True:
        try:
            move = int(await get_user_input(f"玩家 {player}，請輸入您的移動 (1-9)：")) - 1
            if 0 <= move <= 8 and board[move] == ' ':
                return move
            else:
                print("無效的移動，請再試一次。")
        except ValueError:
            print("請輸入 1 到 9 之間的數字。")

def check_winner(board, player):
    win_conditions = [
        [0,1,2], [3,4,5], [6,7,8],  # rows
        [0,3,6], [1,4,7], [2,5,8],  # columns
        [0,4,8], [2,4,6]            # diagonals
    ]
    return any(all(board[pos] == player for pos in condition) for condition in win_conditions)

# -------------------------
# Connect Four (C4) 遊戲函數
# -------------------------

async def start_connectfour_game_as_host(own_port):
    server = await asyncio.start_server(handle_connectfour_client, '0.0.0.0', own_port)
    logging.info(f"等待客戶端連接於 {own_port} 作為 Connect Four 主機...")
    print(f"等待客戶端連接於 {own_port} 作為 Connect Four 主機...")
    
    global server_close_event
    server_close_event = asyncio.Event()

    async def stop_server():
        await server_close_event.wait()
        server.close()
        await server.wait_closed()
        print("遊戲伺服器已關閉。")

    async with server:
        await asyncio.gather(server.serve_forever(), stop_server())

async def handle_connectfour_client(reader, writer):
    try:
        print("Connect Four 客戶端已連接。")
        await connectfour_game_loop(reader, writer, "Host")
    except Exception as e:
        logging.error(f"Connect Four 主機錯誤：{e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def start_connectfour_game_as_client(peer_ip, peer_port, max_retries=10, retry_delay=2):
    writer = None
    retries = 0

    while retries < max_retries:
        try:
            print(f"正在連接到 {peer_ip}:{peer_port} 的 Connect Four 主機作為客戶端...（嘗試 {retries + 1}）")
            reader, writer = await asyncio.open_connection(peer_ip, peer_port)
            print("已成功連接到主機。")
            await connectfour_game_loop(reader, writer, "Client")
            break

        except ConnectionRefusedError:
            retries += 1
            if retries >= max_retries:
                logging.error(f"嘗試 {max_retries} 次後連接失敗。")
                print(f"嘗試 {max_retries} 次後連接失敗。正在退出...")
                return
            else:
                print(f"連接被拒絕，{retry_delay} 秒後重試...")
                await asyncio.sleep(retry_delay)

        except Exception as e:
            logging.error(f"啟動 Connect Four 客戶端模式時失敗：{e}")
            break

    if writer is not None:
        writer.close()
        await writer.wait_closed()

async def connectfour_game_loop(reader, writer, role):
    board = [[' ' for _ in range(7)] for _ in range(6)]
    my_symbol = 'X' if role == "Host" else 'O'
    opponent_symbol = 'O' if role == "Host" else 'X'
    current_turn = 'X'  # 'X' 總是先手
    game_over = False

    while not game_over:
        display_connectfour_board(board)
        if current_turn == my_symbol:
            column = await get_connectfour_move(board, my_symbol)
            if column == -1:
                print("該欄已滿，請選擇另一個欄位。")
                continue
            row = place_piece(board, column, my_symbol)
            await send_message(writer, {"column": column})
        else:
            print("等待對手的移動...")
            data = await reader.read(1024)
            if not data:
                print("對手已斷開連接。")
                game_over = True
                break
            try:
                message = json.loads(data.decode())
                column = message.get("column")
                if column is not None and 0 <= column <= 6 and board[0][column] == ' ':
                    row = place_piece(board, column, opponent_symbol)
                else:
                    print("收到無效的移動。")
                    continue
            except json.JSONDecodeError:
                print("收到無效的訊息。")
                continue

        if check_connectfour_winner(board, row, column, my_symbol):
            display_connectfour_board(board)
            print(f"玩家 {my_symbol} 獲勝!")
            game_over = True
            server_close_event.set()
        elif check_connectfour_winner(board, row, column, opponent_symbol):
            display_connectfour_board(board)
            print(f"玩家 {opponent_symbol} 獲勝!")
            game_over = True
            server_close_event.set()
        elif all(board[0][col] != ' ' for col in range(7)):
            display_connectfour_board(board)
            print("平局!")
            game_over = True
            server_close_event.set()
        else:
            # Switch turns
            current_turn = opponent_symbol if current_turn == my_symbol else my_symbol

def display_connectfour_board(board):
    print("\n當前棋盤：")
    for row in board:
        print('|'.join(row))
        print('-' * 13)
    print('0 1 2 3 4 5 6\n')

async def get_connectfour_move(board, player):
    while True:
        try:
            column_input = await get_user_input(f"玩家 {player}，請輸入要放置的列號 (0-6)：")
            column = int(column_input)
            if 0 <= column <= 6 and board[0][column] == ' ':
                return column
            else:
                print("無效的列號，請再試一次。")
        except ValueError:
            print("請輸入 0 到 6 之間的數字。")

def place_piece(board, column, player):
    for row in reversed(range(6)):
        if board[row][column] == ' ':
            board[row][column] = player
            return row
    print("該欄已滿。")
    return -1  # Invalid move

def check_connectfour_winner(board, row, column, player):
    directions = [(0,1), (1,0), (1,1), (1,-1)]
    for dx, dy in directions:
        count = 1
        for dir in [1, -1]:
            x, y = row, column
            while True:
                x += dir * dx
                y += dir * dy
                if 0 <= x < 6 and 0 <= y < 7 and board[x][y] == player:
                    count += 1
                else:
                    break
        if count >= 4:
            return True
    return False

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

def display_public_rooms(public_rooms):
    print("\n=== 公開房間列表 ===")
    if not public_rooms:
        print("無公開房間等待玩家。")
    else:
        for room in public_rooms:
            room_id = room.get("room_id", "未知")
            creator = room.get("creator", "未知")
            game_type = room.get("game_type", "未知")
            room_status = room.get("status", "未知")
            room_host = room.get("host", "未知")
            print(f"房間 ID：{room_id} | 創建者：{creator} | 房主：{room_host} | 遊戲類型：{game_type} | 狀態：{room_status}")
    print("=====================")

async def get_user_input(prompt):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt).strip().lower())

async def handle_user_input(writer, game_in_progress, logged_in):
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
                    print("用法：create <public/private> <rps/ttt/c4>")
                    continue
                # 支持遊戲類型的縮寫
                game_type = params[1].lower()
                if game_type in ['rps', 'rock_paper_scissors']:
                    params[1] = 'rock_paper_scissors'
                elif game_type in ['ttt', 'tictactoe']:
                    params[1] = 'tictactoe'
                elif game_type in ['c4', 'connectfour']:
                    params[1] = 'connectfour'
                else:
                    print("無效的遊戲類型。可用遊戲：rps、ttt、c4")
                    continue
                await send_command(writer, "CREATE_ROOM", params)

            elif command == "JOIN_ROOM":
                if len(params) != 1:
                    print("用法：join <房間ID>")
                    continue
                await send_command(writer, "JOIN_ROOM", params)

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
                        print(f"{idx}. 來自 {invite['inviter']} 的房間 {invite['room_id']}")
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
    asyncio.create_task(handle_user_input(writer, game_in_progress, logged_in))

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