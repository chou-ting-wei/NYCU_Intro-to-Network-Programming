# game_server_tictactoe.py

import asyncio
import json
import sys
import logging

# 設定日誌
logging.basicConfig(
    filename='game_server_tictactoe.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # 設定為 DEBUG 級別以捕捉更多細節
)

BOARD_SIZE = 3

def initialize_board():
    """初始化 Tic-Tac-Toe 棋盤"""
    return [[' ' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

def display_board(board):
    """顯示 Tic-Tac-Toe 棋盤"""
    for i in range(BOARD_SIZE):
        row = ' | '.join(board[i])
        print(f" {row} ")
        if i < BOARD_SIZE - 1:
            print("---+---+---")

def check_winner(board, symbol):
    """檢查是否有玩家獲勝"""
    # 檢查行
    for row in board:
        if all(cell == symbol for cell in row):
            return True
    # 檢查列
    for col in range(BOARD_SIZE):
        if all(board[row][col] == symbol for row in range(BOARD_SIZE)):
            return True
    # 檢查對角線
    if all(board[i][i] == symbol for i in range(BOARD_SIZE)):
        return True
    if all(board[i][BOARD_SIZE - 1 - i] == symbol for i in range(BOARD_SIZE)):
        return True
    return False

async def send_message(writer, message):
    """發送 JSON 格式的訊息給客戶端"""
    try:
        writer.write((json.dumps(message) + '\n').encode())
        await writer.drain()
        logging.debug(f"發送訊息給玩家: {message}")
    except Exception as e:
        logging.error(f"發送訊息失敗: {e}")

async def handle_player(reader, writer, symbol, board):
    """處理單個玩家的選擇"""
    try:
        while True:
            data = await reader.readline()
            if not data:
                logging.warning(f"玩家 {symbol} 斷線。")
                return False  # 玩家斷線
            message = data.decode().strip()
            logging.debug(f"接收到玩家 {symbol} 的訊息: {message}")
            try:
                message_json = json.loads(message)
                move = message_json.get("move")
                if not move:
                    await send_message(writer, {"status": "error", "message": "Invalid move format."})
                    logging.warning(f"玩家 {symbol} 發送無效的移動格式。")
                    continue
                row, col = move.get("row"), move.get("col")
                if not (isinstance(row, int) and isinstance(col, int)):
                    await send_message(writer, {"status": "error", "message": "Row and column must be integers."})
                    logging.warning(f"玩家 {symbol} 發送非整數的移動位置。")
                    continue
                if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
                    await send_message(writer, {"status": "error", "message": "Move out of range."})
                    logging.warning(f"玩家 {symbol} 選擇的移動位置 ({row}, {col}) 超出範圍。")
                    continue
                if board[row][col] != ' ':
                    await send_message(writer, {"status": "error", "message": "Cell already occupied."})
                    logging.warning(f"玩家 {symbol} 選擇的移動位置 ({row}, {col}) 已被佔用。")
                    continue
                board[row][col] = symbol
                logging.info(f"玩家 {symbol} 選擇了位置 ({row}, {col})")
                return True  # 玩家成功選擇
            except json.JSONDecodeError:
                await send_message(writer, {"status": "error", "message": "Invalid message format."})
                logging.warning(f"玩家 {symbol} 發送無效的 JSON 格式訊息。")
    except Exception as e:
        logging.error(f"處理玩家 {symbol} 時發生錯誤: {e}")
        return False

async def handle_game(reader1, writer1, reader2, writer2, room_id):
    """處理兩位玩家的遊戲邏輯"""
    board = initialize_board()
    symbols = {'player1': 'X', 'player2': 'O'}
    players = {'player1': (reader1, writer1), 'player2': (reader2, writer2)}
    current_player = 'player1'
    winner = None
    move_count = 0

    logging.info(f"房間 {room_id} 開始遊戲。玩家1: {symbols['player1']}，玩家2: {symbols['player2']}")
    print(f"房間 {room_id} 開始遊戲。玩家1: {symbols['player1']}，玩家2: {symbols['player2']}")

    try:
        while True:
            reader, writer = players[current_player]
            await send_message(writer, {"status": "info", "message": "您的回合，請輸入 move (row col)."})
            logging.debug(f"提示玩家 {symbols[current_player]} 進行移動。")
            success = await handle_player(reader, writer, symbols[current_player], board)
            if not success:
                # 另一位玩家勝利
                other_player = 'player2' if current_player == 'player1' else 'player1'
                winner = other_player
                logging.info(f"玩家 {symbols[current_player]} 斷線，玩家 {symbols[other_player]} 獲勝。")
                break
            move_count += 1
            # 檢查是否有勝利者
            if check_winner(board, symbols[current_player]):
                winner = current_player
                logging.info(f"玩家 {symbols[current_player]} 獲勝！")
                break
            # 檢查是否平手
            if move_count == BOARD_SIZE * BOARD_SIZE:
                break
            # 切換玩家
            current_player = 'player2' if current_player == 'player1' else 'player1'
            logging.debug(f"切換到玩家 {symbols[current_player]} 進行移動。")

        # 準備結果訊息
        if winner:
            result = f"Player {symbols[winner]} Wins"
        else:
            result = "Draw"

        result_message = {
            "status": "result",
            "board": board,
            "result": result
        }

        # 發送結果給兩位玩家
        await send_message(writer1, result_message)
        await send_message(writer2, result_message)
        logging.info(f"房間 {room_id} 遊戲結果: {result}")

    except Exception as e:
        logging.error(f"處理房間 {room_id} 的遊戲時發生錯誤: {e}")
    finally:
        writer1.close()
        await writer1.wait_closed()
        writer2.close()
        await writer2.wait_closed()
        logging.info(f"房間 {room_id} 的遊戲連線已關閉。")

async def queue_player(reader, writer, room_id, game_type):
    """將玩家加入隊列，等待兩位玩家連接後開始遊戲"""
    addr = writer.get_extra_info('peername')
    logging.info(f"玩家連接來自 {addr}")
    print(f"玩家連接來自 {addr}")

    if not hasattr(queue_player, "player_queue"):
        queue_player.player_queue = {}

    if room_id not in queue_player.player_queue:
        queue_player.player_queue[room_id] = []

    queue_player.player_queue[room_id].append((reader, writer))
    logging.debug(f"玩家加入房間 {room_id} 的隊列。當前隊列長度: {len(queue_player.player_queue[room_id])}")

    if len(queue_player.player_queue[room_id]) == 2:
        reader1, writer1 = queue_player.player_queue[room_id][0]
        reader2, writer2 = queue_player.player_queue[room_id][1]
        logging.info(f"兩位玩家已連接到房間 {room_id}，開始遊戲。")
        print(f"兩位玩家已連接到房間 {room_id}，開始遊戲。")
        asyncio.create_task(handle_game(reader1, writer1, reader2, writer2, room_id))
        # 清空隊列
        queue_player.player_queue[room_id] = []
        logging.debug(f"房間 {room_id} 的隊列已清空。")

async def main():
    if len(sys.argv) != 4:
        print("用法: python game_server_tictactoe.py <host> <port> <room_id>")
        logging.error("啟動參數不足。")
        return
    host = sys.argv[1]
    try:
        port = int(sys.argv[2])
    except ValueError:
        print("Port 必須是一個整數。")
        logging.error("Port 參數非整數。")
        return
    room_id = sys.argv[3]

    try:
        server = await asyncio.start_server(
            lambda r, w: asyncio.create_task(queue_player(r, w, room_id, 'tictactoe')),
            host,
            port
        )
    except Exception as e:
        print(f"無法啟動伺服器: {e}")
        logging.error(f"無法啟動伺服器在 {host}:{port}，房間ID: {room_id}，錯誤: {e}")
        return

    addr = server.sockets[0].getsockname()
    logging.info(f"Tic-Tac-Toe 遊戲伺服器已啟動在 {addr}，房間ID: {room_id}")
    print(f"Tic-Tac-Toe 遊戲伺服器已啟動在 {addr}，房間ID: {room_id}")

    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        logging.info("遊戲伺服器被取消。")
    except Exception as e:
        logging.error(f"遊戲伺服器在運行時發生錯誤: {e}")
    finally:
        server.close()
        await server.wait_closed()
        logging.info("遊戲伺服器已關閉。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("遊戲伺服器透過鍵盤中斷關閉。")
        print("\n遊戲伺服器已關閉。")
    except Exception as e:
        logging.error(f"遊戲伺服器異常終止: {e}")
        print(f"遊戲伺服器異常終止: {e}")
