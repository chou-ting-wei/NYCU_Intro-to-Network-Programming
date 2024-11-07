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

COMMANDS = [
    "REGISTER <username> <password> - 註冊新帳號",
    "LOGIN <username> <password> - 登入帳號",
    "LOGOUT - 登出",
    "CREATE_ROOM <public/private> <rock_paper_scissors/tictactoe/connectfour> - 創建房間",
    "JOIN_ROOM <room_id> - 加入房間",
    "INVITE_PLAYER <username> <room_id> - 邀請玩家加入房間",
    "EXIT - 離開客戶端",
    "HELP - 顯示可用指令列表",
    "SHOW_STATUS - 顯示當前狀態"
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

async def handle_server_messages(reader, writer, game_in_progress, logged_in):
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
                        logged_in.value = True
                    elif msg.startswith("LOGOUT_SUCCESS"):
                        print("\n伺服器: LOGOUT_SUCCESS")
                        logged_in.value = False
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
                    response = await get_user_input(f"\nYou have received an invitation from {inviter} to join room {room_id}. Accept? (yes/no): ")
                    if response == 'yes':
                        await send_command(writer, "ACCEPT_INVITE", [room_id])
                        logging.info(f"Accepted invite to join room: {room_id}")
                    else:
                        await send_command(writer, "DECLINE_INVITE", [inviter, room_id])
                        print("Invitation declined.")
                        logging.info(f"Declined invite to join room: {room_id}")
                elif status == "invite_declined":
                    decline_from = message_json.get("from")
                    room_id = message_json.get("room_id")
                    print(f"\nPlayer {decline_from} declined your invitation to room {room_id}.")
                    logging.info(f"Player {decline_from} declined invitation to room {room_id}.")

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
                    asyncio.create_task(initiate_game(peer_info["game_type"], game_in_progress, writer))
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

async def initiate_game(game_type, game_in_progress, writer):
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
        elif game_type.lower() == 'connectfour':
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

async def start_tictactoe_game_as_host(own_port):
    """Starts Tic-Tac-Toe game as the host"""
    server = await asyncio.start_server(handle_tictactoe_client, '0.0.0.0', own_port)
    logging.info(f"Waiting for client connection at {own_port} as the Tic-Tac-Toe host...")
    print(f"Waiting for client connection at {own_port} as the Tic-Tac-Toe host...")

    global server_close_event
    server_close_event = asyncio.Event()

    async def stop_server():
        await server_close_event.wait()
        server.close()
        await server.wait_closed()
        print("Game server has been shut down.")

    async with server:
        await asyncio.gather(server.serve_forever(), stop_server())

async def handle_tictactoe_client(reader, writer):
    """Handles Tic-Tac-Toe game logic for the host"""
    try:
        print("Tic-Tac-Toe client connected.")
        await tictactoe_game_loop(reader, writer, "Host")
    except Exception as e:
        logging.error(f"Tic-Tac-Toe host error: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def start_tictactoe_game_as_client(peer_ip, peer_port, max_retries=10, retry_delay=2):
    writer = None
    retries = 0

    while retries < max_retries:
        try:
            print(f"Connecting to the Tic-Tac-Toe host at {peer_ip}:{peer_port} as a client... (Attempt {retries + 1})")
            reader, writer = await asyncio.open_connection(peer_ip, peer_port)
            print("Connected to the host")
            await tictactoe_game_loop(reader, writer, "Client")

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
            logging.error(f"Failed to start Tic-Tac-Toe client mode: {e}")
            break

    if writer is not None:
        writer.close()
        await writer.wait_closed()

async def tictactoe_game_loop(reader, writer, role):
    """Main game loop for Tic-Tac-Toe"""
    board = [' ' for _ in range(9)]
    my_symbol = 'X' if role == "Host" else 'O'
    opponent_symbol = 'O' if role == "Host" else 'X'
    current_turn = 'X'  # 'X' always starts first
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
                print("對手斷開連接。")
                game_over = True
                break
            message = json.loads(data.decode())
            move = message.get("move")
            board[move] = opponent_symbol

        # Check for a winner or a tie
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

# def display_board(board):
#     """Displays the Tic-Tac-Toe board"""
#     print("\nCurrent Board:")
#     print(f" {board[0]} | {board[1]} | {board[2]} ")
#     print("---+---+---")
#     print(f" {board[3]} | {board[4]} | {board[5]} ")
#     print("---+---+---")
#     print(f" {board[6]} | {board[7]} | {board[8]} ")
#     print("")

def display_board(board):
    """Displays the Tic-Tac-Toe board with numbers for empty cells"""
    print("\nCurrent Board:")
    display = [str(i+1) if cell == ' ' else cell for i, cell in enumerate(board)]
    print(f" {display[0]} | {display[1]} | {display[2]} ")
    print("---+---+---")
    print(f" {display[3]} | {display[4]} | {display[5]} ")
    print("---+---+---")
    print(f" {display[6]} | {display[7]} | {display[8]} ")
    print("")

async def get_tictactoe_move(board, player):
    """Gets a valid move from the player"""
    while True:
        try:
            move = int(await get_user_input(f"Player {player}, enter your move (1-9): ")) - 1
            if 0 <= move <= 8 and board[move] == ' ':
                return move
            else:
                print("Invalid move. Try again.")
        except ValueError:
            print("Please enter a number between 1 and 9.")

def check_winner(board, player):
    """Checks if the player has won"""
    win_conditions = [
        [0,1,2], [3,4,5], [6,7,8],  # Rows
        [0,3,6], [1,4,7], [2,5,8],  # Columns
        [0,4,8], [2,4,6]            # Diagonals
    ]
    return any(all(board[pos] == player for pos in condition) for condition in win_conditions)

# -------------------------
# Connect Four Game Functions
# -------------------------

async def start_connectfour_game_as_host(own_port):
    """Starts Connect Four game as the host"""
    server = await asyncio.start_server(handle_connectfour_client, '0.0.0.0', own_port)
    logging.info(f"Waiting for client connection at {own_port} as the Connect Four host...")
    print(f"Waiting for client connection at {own_port} as the Connect Four host...")

    global server_close_event
    server_close_event = asyncio.Event()

    async def stop_server():
        await server_close_event.wait()
        server.close()
        await server.wait_closed()
        print("Game server has been shut down.")

    async with server:
        await asyncio.gather(server.serve_forever(), stop_server())

async def handle_connectfour_client(reader, writer):
    """Handles Connect Four game logic for the host"""
    try:
        print("Connect Four client connected.")
        await connectfour_game_loop(reader, writer, "Host")
    except Exception as e:
        logging.error(f"Connect Four host error: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def start_connectfour_game_as_client(peer_ip, peer_port, max_retries=10, retry_delay=2):
    """Starts Connect Four game as the client, retrying until the server is ready"""
    writer = None
    retries = 0

    while retries < max_retries:
        try:
            print(f"Connecting to the Connect Four host at {peer_ip}:{peer_port} as a client... (Attempt {retries + 1})")
            reader, writer = await asyncio.open_connection(peer_ip, peer_port)
            print("Connected to the host")
            await connectfour_game_loop(reader, writer, "Client")
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
            logging.error(f"Failed to start Connect Four client mode: {e}")
            break

    if writer is not None:
        writer.close()
        await writer.wait_closed()

async def connectfour_game_loop(reader, writer, role):
    """Main game loop for Connect Four"""
    board = [[' ' for _ in range(7)] for _ in range(6)]
    my_symbol = 'X' if role == "Host" else 'O'
    opponent_symbol = 'O' if role == "Host" else 'X'
    current_turn = 'X'  # 'X' always starts first
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
                print("對手斷開連接。")
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

        # Check for a winner or a tie
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
    """Displays the Connect Four board with column numbers"""
    print("\nCurrent Board:")
    for row in board:
        print('|'.join(row))
        print('-' * 13)
    print('0 1 2 3 4 5 6\n')

async def get_connectfour_move(board, player):
    """Gets a valid column from the player"""
    while True:
        try:
            column_input = await get_user_input(f"Player {player}, enter column (0-6): ")
            column = int(column_input)
            if 0 <= column <= 6 and board[0][column] == ' ':
                return column
            else:
                print("Invalid column. Try again.")
        except ValueError:
            print("Please enter a number between 0 and 6.")

def place_piece(board, column, player):
    """Places a piece in the chosen column and returns the row index"""
    for row in reversed(range(6)):
        if board[row][column] == ' ':
            board[row][column] = player
            return row
    print("該欄已滿。")
    return -1  # Indicates the column is full

def check_connectfour_winner(board, row, column, player):
    """Checks if the player has won in Connect Four"""
    directions = [(0,1), (1,0), (1,1), (1,-1)]  # Horizontal, Vertical, Diagonal /
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

async def handle_user_input(writer, game_in_progress, logged_in):
    """處理用戶輸入的協程函數"""
    while True:
        try:
            if game_in_progress.value:
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
                print("")
                continue

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
                if not logged_in.value:
                    print("Not logged in.")
                    continue
                await send_command(writer, "LOGOUT", [])

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
    server_ip = input(f"輸入伺服器 IP (預設: {config.HOST}): ").strip()
    server_ip = server_ip if server_ip else config.HOST
    server_port_input = input(f"輸入伺服器 port (預設: {config.PORT}): ").strip()
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
        print(f"無法連接到伺服器: {e}")
        logging.error(f"無法連接到伺服器: {e}")
        return

    game_in_progress = type('', (), {'value': False})()
    logged_in = type('', (), {'value': False})()

    asyncio.create_task(handle_server_messages(reader, writer, game_in_progress, logged_in))
    asyncio.create_task(handle_user_input(writer, game_in_progress, logged_in))

    # 顯示可用指令列表一次
    print("\n可用的指令:")
    for cmd in COMMANDS:
        print(cmd)
    print("")  # 空行

    # 等待停止事件
    await asyncio.Future()

    print("客戶端已關閉。")
    logging.info("客戶端已關閉。")
    sys.exit()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"客戶端異常終止: {e}")
        logging.error(f"客戶端異常終止: {e}")