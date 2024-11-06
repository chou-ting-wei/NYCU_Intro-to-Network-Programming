# client_game_rps.py

import asyncio
import json
import sys
import logging

# 設定日誌
logging.basicConfig(
    filename='client_game_rps.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

VALID_MOVES = ['rock', 'paper', 'scissors']

# 定義文字圖像
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

async def send_message(writer, message):
    """發送 JSON 格式的訊息給遊戲伺服器"""
    try:
        writer.write((json.dumps(message) + '\n').encode())
        await writer.drain()
    except Exception as e:
        logging.error(f"發送訊息失敗: {e}")

async def receive_messages(reader, writer):
    """接收來自遊戲伺服器的訊息"""
    try:
        while True:
            data = await reader.readline()
            if not data:
                print("\n遊戲伺服器斷線。")
                logging.info("遊戲伺服器斷線。")
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
                    print(f"玩家1 選擇: {message_json.get('player1_move')}")
                    print(ASCII_ART.get(message_json.get('player1_move'), ''))
                    print(f"玩家2 選擇: {message_json.get('player2_move')}")
                    print(ASCII_ART.get(message_json.get('player2_move'), ''))
                    print(f"結果: {message_json.get('result')}")
                    print("================")
                    logging.info("遊戲結束。")
                    # 發送確認訊息
                    ack_message = {"status": "ack"}
                    await send_message(writer, ack_message)
                    logging.info("發送確認訊息: ack")
                    break  # 遊戲結束，退出接收迴圈
                else:
                    print(f"\n伺服器: {message}")
            except json.JSONDecodeError:
                print(f"\n伺服器: {message}")
    except Exception as e:
        logging.error(f"接收遊戲伺服器訊息時發生錯誤: {e}")

async def send_move(writer):
    """讓玩家選擇並發送動作"""
    while True:
        move = input("請選擇 rock, paper, 或 scissors: ").strip().lower()
        if move in VALID_MOVES:
            message = {"move": move}
            await send_message(writer, message)
            logging.info(f"發送選擇: {move}")
            print(ASCII_ART.get(move, ''))
            break
        else:
            print("無效的選擇，請重新輸入。")
            logging.warning(f"玩家輸入無效的選擇: {move}")

async def main():
    if len(sys.argv) != 4:
        print("用法: python client_game_rps.py <host> <port> <room_id>")
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

    # 啟動接收訊息的協程
    receive_task = asyncio.create_task(receive_messages(reader, writer))

    # 發送選擇動作
    await send_move(writer)

    # 等待接收遊戲結果
    await receive_task

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
