# client_game_tictactoe.py

import asyncio
import json
import sys
import logging

# 設定日誌
logging.basicConfig(
    filename='client_game_tictactoe.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

BOARD_SIZE = 3

def initialize_board():
    return [[' ' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

def display_board(board):
    print("\n=== Tic-Tac-Toe ===")
    for i in range(BOARD_SIZE):
        row = ' | '.join(board[i])
        print(f" {row} ")
        if i < BOARD_SIZE - 1:
            print("---+---+---")
    print("===================\n")

async def send_message(writer, message):
    """發送 JSON 格式的訊息給遊戲伺服器"""
    try:
        writer.write((json.dumps(message) + '\n').encode())
        await writer.drain()
    except Exception as e:
        logging.error(f"發送訊息失敗: {e}")

async def receive_messages(reader, writer, board, game_over_event):
    """接收來自遊戲伺服器的訊息"""
    try:
        while True:
            data = await reader.readline()
            if not data:
                print("\n遊戲伺服器斷線。")
                logging.info("遊戲伺服器斷線。")
                game_over_event.set()
                break
            message = data.decode().strip()
            logging.debug(f"接收到訊息: {message}")  # 新增日誌
            if not message:
                continue
            try:
                message_json = json.loads(message)
                status = message_json.get("status")
                if status == "info":
                    print(f"\n伺服器訊息: {message_json.get('message')}")
                elif status == "error":
                    print(f"\n錯誤: {message_json.get('message')}")
                elif status == "result":
                    print("\n=== 遊戲結果 ===")
                    display_board(message_json.get("board", board))
                    print(f"結果: {message_json.get('result')}")
                    print("================")
                    logging.info("遊戲結束。")
                    # 發送確認訊息
                    ack_message = {"status": "ack"}
                    await send_message(writer, ack_message)
                    logging.info("發送確認訊息: ack")
                    game_over_event.set()
                    break
                else:
                    print(f"\n伺服器: {message}")
            except json.JSONDecodeError:
                print(f"\n伺服器: {message}")
    except Exception as e:
        logging.error(f"接收遊戲伺服器訊息時發生錯誤: {e}")

async def send_move(writer, board, symbol):
    """讓玩家選擇並發送動作"""
    while True:
        try:
            move = input("請輸入您的位置 (格式: row col, 例如: 1 1): ").strip()
            parts = move.split()
            if len(parts) != 2:
                print("輸入格式錯誤，請使用 'row col' 格式。")
                continue
            row, col = int(parts[0]), int(parts[1])
            if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
                print("位置超出範圍，請重新輸入。")
                continue
            if board[row][col] != ' ':
                print("該位置已被佔用，請重新輸入。")
                continue
            message = {"move": {"row": row, "col": col}}
            await send_message(writer, message)
            logging.info(f"發送選擇: {row}, {col}")
            break
        except ValueError:
            print("請輸入有效的數字。")
            continue
        except Exception as e:
            print(f"發送選擇時發生錯誤: {e}")
            logging.error(f"發送選擇時發生錯誤: {e}")
            break

async def main():
    if len(sys.argv) != 4:
        print("用法: python client_game_tictactoe.py <host> <port> <room_id>")
        return
    host = sys.argv[1]
    port = int(sys.argv[2])
    room_id = sys.argv[3]

    try:
        reader, writer = await asyncio.open_connection(host, port)
        print(f"成功連接到房間 {room_id} 的遊戲伺服器。")
        logging.info(f"成功連接到遊戲伺服器 {host}:{port}，房間ID: {room_id}")
    except ConnectionRefusedError:
        print("連線被拒絕，請確認遊戲伺服器是否正在運行。")
        logging.error("連線被拒絕，請確認遊戲伺服器是否正在運行。")
        return
    except Exception as e:
        print(f"無法連接到遊戲伺服器: {e}")
        logging.error(f"無法連接到遊戲伺服器: {e}")
        return

    board = initialize_board()
    game_over_event = asyncio.Event()

    # 啟動接收訊息的協程
    asyncio.create_task(receive_messages(reader, writer, board, game_over_event))

    # 玩家符號
    symbol = 'X'  # 假設玩家1是 'X'

    # 遊戲循環
    while not game_over_event.is_set():
        display_board(board)
        await send_move(writer, board, symbol)
        # 等待伺服器回應
        await asyncio.sleep(0.1)

    # 關閉連線
    writer.close()
    await writer.wait_closed()
    print("遊戲結束，連線已關閉。")
    logging.info("遊戲結束，連線已關閉。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"遊戲客戶端異常終止: {e}")
        logging.error(f"遊戲客戶端異常終止: {e}")
