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

peer_info = {
    "role": None,
    "peer_ip": None,
    "peer_port": None,
    "own_port": None,
    "game_type": None
}

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
        writer.write(message.encode())
        await writer.drain()
    except Exception as e:
        logging.error(f"發送訊息失敗: {e}")

async def handle_server_messages(reader, writer, game_in_progress):
    """接收伺服器訊息的協程函數"""
    while True:
        try:
            data = await reader.readline()
            if not data:
                print("\n伺服器斷線。")
                logging.info("伺服器斷線。")
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
                        print("\n伺服器: REGISTER_SUCCESS")
                    elif msg.startswith("LOGIN_SUCCESS"):
                        print("\n伺服器: LOGIN_SUCCESS")
                        # 在登入成功後，等待伺服器發送更新訊息
                    elif msg.startswith("LOGOUT_SUCCESS"):
                        print("\n伺服器: LOGOUT_SUCCESS")
                    elif msg.startswith("CREATE_ROOM_SUCCESS"):
                        parts = msg.split()
                        room_id = parts[1]
                        game_type = parts[2] if len(parts) > 2 else 'rock_paper_scissors'
                        print(f"\n伺服器: CREATE_ROOM_SUCCESS {room_id} {game_type}")
                    elif msg.startswith("JOIN_ROOM_SUCCESS"):
                        parts = msg.split()
                        room_id = parts[1]
                        game_type = parts[2] if len(parts) > 2 else 'rock_paper_scissors'
                        print(f"\n伺服器: JOIN_ROOM_SUCCESS {room_id} {game_type}")
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
                elif status == "p2p_info":
                    peer_info["role"] = message_json.get("role")
                    peer_info["peer_ip"] = message_json.get("peer_ip")
                    peer_info["peer_port"] = message_json.get("peer_port")
                    peer_info["own_port"] = message_json.get("own_port")
                    peer_info["game_type"] = message_json.get("game_type")
                    logging.debug(f"Role: {peer_info['role']}, Peer IP: {peer_info['peer_ip']}, Peer Port: {peer_info['peer_port']}, Own Port: {peer_info['own_port']}, Game Type: {peer_info['game_type']}")
                    print(f"Role: {peer_info['role']}, Peer IP: {peer_info['peer_ip']}, Peer Port: {peer_info['peer_port']}, Own Port: {peer_info['own_port']}")
                    asyncio.create_task(initiate_game(peer_info["game_type"], game_in_progress))
                    game_in_progress.value = True
                elif status == "status":
                    print(f"\n{msg}")
                else:
                    print(f"\n伺服器: {message}")
            except json.JSONDecodeError:
                print(f"\n伺服器: {message}")
        except Exception as e:
            if not game_in_progress.value:
                print(f"\n接收伺服器資料時發生錯誤: {e}")
                logging.error(f"接收伺服器資料時發生錯誤: {e}")
                game_in_progress.value = False
            break

async def initiate_game(game_type, game_in_progress):
    """Initiates the game based on role and establishes P2P connection."""
    try:
        if game_type is None:
            raise ValueError("game_type is not defined")
        
        if game_type.lower() == 'rock_paper_scissors':
            if peer_info.get("role") == "host":
                await start_rps_game_as_host(peer_info.get("own_port"))
            elif peer_info.get("role") == "client":
                await start_rps_game_as_client(peer_info.get("peer_ip"), peer_info.get("peer_port"))
        elif game_type.lower() == 'tictactoe':
            if peer_info.get("role") == "host":
                await start_tictactoe_game_as_host(peer_info.get("own_port"))
            elif peer_info.get("role") == "client":
                await start_tictactoe_game_as_client(peer_info.get("peer_ip"), peer_info.get("peer_port"))
        else:
            logging.error("無效的遊戲類型")
            print("無效的遊戲類型")
    finally:
        game_in_progress.value = False

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

host_move = None
client_move = None

async def handle_p2p_client(reader, writer):
    """Handles incoming P2P client connections and game communication"""
    global host_move, client_move
    try:
        print("P2P connection established")
        
        # Reset moves for a new game
        host_move, client_move = None, None

        # Host chooses their move first
        if peer_info["role"] == "host":
            host_move = await get_move("Host")
            # await send_message(writer, {"move": host_move, "player": "Host"})

        # Process incoming messages
        await receive_messages(reader, writer)
        
    except Exception as e:
        logging.error(f"P2P connection error: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def receive_messages(reader, writer):
    """Receives and processes messages from the game server or peer"""
    global host_move, client_move
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                print("\nConnection closed by the server.")
                logging.info("Connection closed by the server.")
                break
            message = data.decode().strip()
            logging.debug(f"Received message: {message}")
            if message:
                try:
                    message_json = json.loads(message)
                    player = message_json.get("player")
                    move = message_json.get("move")
                    
                    if message_json.get("status") == "result":
                        display_result(message_json)
                    
                    # Capture moves based on role
                    if player == "Host":
                        host_move = move
                    elif player == "Client":
                        client_move = move
                    
                    # Once both moves are in, determine and broadcast the result
                    if host_move and client_move:
                        result = determine_winner(host_move, client_move)
                        result_message = {
                            "status": "result",
                            "player1_move": host_move,
                            "player2_move": client_move,
                            "result": result
                        }
                        
                        # Send result to both players
                        await send_message(writer, result_message)
                        display_result(result_message)
                        
                        # Reset moves for a new game if needed
                        host_move, client_move = None, None
                        server_close_event.set()
                        break
                except json.JSONDecodeError:
                    print(f"\nUnable to decode message: {message}")
    except Exception as e:
        logging.error(f"Error receiving messages: {e}")
        
def determine_winner(move1, move2):
    """Determines the game result"""
    if move1 == move2:
        return "Draw"
    elif (move1 == 'rock' and move2 == 'scissors') or \
         (move1 == 'paper' and move2 == 'rock') or \
         (move1 == 'scissors' and move2 == 'paper'):
        return "Host Wins"
    else:
        return "Client Wins"


async def start_rps_game_as_host(own_port):
    # Start server and listen on specified port
    server = await asyncio.start_server(handle_p2p_client, '0.0.0.0', own_port)
    
    """Starts RPS game as the host and shuts down after game ends"""
    logging.info(f"Waiting for client connection at {own_port} as the Rock-Paper-Scissors host...")
    print(f"Waiting for client connection at {own_port} as the Rock-Paper-Scissors host...")
    
    # Create an event to signal server shutdown
    global server_close_event
    server_close_event = asyncio.Event()

    async def stop_server():
        await server_close_event.wait()  # Wait until the game ends
        server.close()
        await server.wait_closed()
        print("Game server has been shut down.")

    # Start the server and shutdown coroutine
    async with server:
        await asyncio.gather(server.serve_forever(), stop_server())

async def start_rps_game_as_client(peer_ip, peer_port, max_retries=10, retry_delay=2):
    """Starts RPS game as the client, retrying until the server is ready"""
    writer = None
    retries = 0

    while retries < max_retries:
        try:
            print(f"Connecting to the Rock-Paper-Scissors host at {peer_ip}:{peer_port} as a client... (Attempt {retries + 1})")
            reader, writer = await asyncio.open_connection(peer_ip, peer_port)
            print("Connected to the host")

            # Get and send player's move
            player_move = await get_move("Client")
            await send_message(writer, {"move": player_move, "player": "Client"})

            # Wait for game result
            await receive_messages(reader, writer)
            break  # Exit the loop if the connection is successful

        except ConnectionRefusedError:
            retries += 1
            if retries >= max_retries:
                logging.error(f"Failed to connect after {max_retries} attempts")
                print(f"Failed to connect after {max_retries} attempts. Exiting...")
                return
            else:
                print(f"Connection refused, retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)

        except Exception as e:
            logging.error(f"Failed to start Rock-Paper-Scissors client mode: {e}")
            break

    if writer is not None:
        writer.close()
        await writer.wait_closed()


async def send_message(writer, message):
    """Send a message to the server"""
    try:
        data = json.dumps(message).encode()
        writer.write(data)
        await writer.drain()
    except Exception as e:
        logging.error(f"Error sending message: {e}")

def display_result(result_message):
    """Displays the game result"""
    print("\n=== Game Result ===")
    print(f"Host chose: {result_message.get('player1_move')}")
    print(ASCII_ART.get(result_message.get('player1_move'), ''))
    print(f"Client chose: {result_message.get('player2_move')}")
    print(ASCII_ART.get(result_message.get('player2_move'), ''))
    print(f"Result: {result_message.get('result')}")
    print("================")

async def get_move(player_name):
    """Prompts the player to choose a move"""
    while True:
        move = input(f"{player_name}, choose rock, paper, or scissors: ").strip().lower()
        if move in VALID_MOVES:
            print(ASCII_ART.get(move, ''))
            return move
        else:
            print("Invalid choice, please try again.")

# -------------------------
# Tic-Tac-Toe Game Functions
# -------------------------

async def start_tictactoe_game_as_host(peer_port):
    print(f"作為 Tic-Tac-Toe 主機等待客戶端連接在 {peer_port}...")
    # Placeholder for Tic-Tac-Toe server logic
    # Example: Implement server-specific logic for Tic-Tac-Toe here
    # You could set up a Tic-Tac-Toe board and manage moves received from the client

async def start_tictactoe_game_as_client(peer_ip, peer_port, room_id):
    try:
        print(f"作為 Tic-Tac-Toe 客戶端，連接到主機 {peer_ip}:{peer_port}...")
        # await asyncio.sleep(2)
        reader, writer = await asyncio.open_connection(peer_ip, peer_port)
        print("已連接至主機")

        # Send session token to host for verification
        session_data = json.dumps({"session_token": room_id})
        writer.write(session_data.encode())
        await writer.drain()
        print("已發送 session token 以進行驗證")

        # Perform game-specific actions for Tic-Tac-Toe
        # Placeholder for Tic-Tac-Toe client logic
        # Example: Display and make moves on a Tic-Tac-Toe board
        
    except Exception as e:
        print(f"無法啟動 Tic-Tac-Toe 客戶端模式: {e}")
        logging.error(f"無法啟動 Tic-Tac-Toe 客戶端模式: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

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

async def handle_user_input(writer, game_in_progress):
    """處理用戶輸入的協程函數"""
    while True:
        try:
            if game_in_progress.value:
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
                await send_command(writer, "LOGOUT", [])
                game_in_progress.value = False
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
            await send_command(writer, "LOGOUT", [])
            game_in_progress.value = False
            writer.close()
            await writer.wait_closed()
            break
        except Exception as e:
            print(f"發送指令時發生錯誤: {e}")
            logging.error(f"發送指令時發生錯誤: {e}")
            game_in_progress.value = False
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

    game_in_progress = type('', (), {'value': False})() 

    asyncio.create_task(handle_server_messages(reader, writer, game_in_progress))
    asyncio.create_task(handle_user_input(writer, game_in_progress))

    # 顯示可用指令列表一次
    print("\n可用的指令:")
    for cmd in COMMANDS:
        print(cmd)
    print("")  # 空行

    # 等待停止事件
    await asyncio.Future()  # 保持事件迴圈運行，直到手動關閉

    print("客戶端已關閉。")
    logging.info("客戶端已關閉。")
    sys.exit()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"客戶端異常終止: {e}")
        logging.error(f"客戶端異常終止: {e}")