# game_server_rps.py

import asyncio
import json
import sys
import logging

# 設定日誌
logging.basicConfig(
    filename='game_server_rps.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

# 定義可能的選擇
VALID_MOVES = ['rock', 'paper', 'scissors']

# 定義勝負邏輯
def determine_winner(move1, move2):
    if move1 == move2:
        return "Draw"
    elif (move1 == 'rock' and move2 == 'scissors') or \
         (move1 == 'paper' and move2 == 'rock') or \
         (move1 == 'scissors' and move2 == 'paper'):
        return "Player 1 Wins"
    else:
        return "Player 2 Wins"

async def handle_player(reader, writer, player_num, moves):
    addr = writer.get_extra_info('peername')
    logging.info(f"玩家 {player_num} 連接來自 {addr}")
    await send_message(writer, {"status": "info", "message": f"玩家 {player_num}，請選擇 rock, paper, 或 scissors:"})
    try:
        while True:
            data = await reader.readline()
            if not data:
                logging.info(f"玩家 {player_num} 斷線。")
                break
            message = data.decode().strip()
            try:
                message_json = json.loads(message)
                move = message_json.get("move", "").lower()
                if move in VALID_MOVES:
                    moves[player_num] = move
                    await send_message(writer, {"status": "info", "message": f"已收到您的選擇: {move}"})
                    logging.info(f"玩家 {player_num} 選擇了 {move}")
                    break
                else:
                    await send_message(writer, {"status": "error", "message": "無效的選擇，請重新輸入 rock, paper, 或 scissors."})
            except json.JSONDecodeError:
                # 如果訊息不是有效的 JSON 格式
                await send_message(writer, {"status": "error", "message": "無效的訊息格式。請重新輸入 rock, paper, 或 scissors."})
    except Exception as e:
        logging.error(f"處理玩家 {player_num} 時發生錯誤: {e}")
    finally:
        # 不立即關閉連線，等待確認訊息
        pass

async def send_message(writer, message):
    """發送 JSON 格式的訊息給客戶端"""
    try:
        writer.write((json.dumps(message) + '\n').encode())
        await writer.drain()
    except Exception as e:
        logging.error(f"發送訊息失敗: {e}")

async def receive_ack(reader, player_num, room_id):
    """接收客戶端的確認訊息"""
    try:
        data = await asyncio.wait_for(reader.readline(), timeout=10)
        if not data:
            logging.error(f"玩家 {player_num} 未回應確認訊息。")
            return False
        message = data.decode().strip()
        try:
            message_json = json.loads(message)
            if message_json.get("status") == "ack":
                logging.info(f"玩家 {player_num} 已確認收到遊戲結果。")
                return True
            else:
                logging.warning(f"玩家 {player_num} 發送了未知的確認訊息: {message}")
                return False
        except json.JSONDecodeError:
            logging.error(f"玩家 {player_num} 發送的確認訊息格式錯誤: {message}")
            return False
    except asyncio.TimeoutError:
        logging.error(f"玩家 {player_num} 確認訊息超時。")
        return False
    except Exception as e:
        logging.error(f"接收玩家 {player_num} 確認訊息時發生錯誤: {e}")
        return False

async def handle_game(reader1, writer1, reader2, writer2, room_id):
    """處理兩位玩家的遊戲邏輯"""
    moves = {}
    try:
        # 同時處理兩位玩家的選擇
        task1 = asyncio.create_task(handle_player(reader1, writer1, 1, moves))
        task2 = asyncio.create_task(handle_player(reader2, writer2, 2, moves))
        await asyncio.gather(task1, task2)

        # 如果兩位玩家都有選擇，決定勝負
        if len(moves) == 2:
            move1 = moves[1]
            move2 = moves[2]
            result = determine_winner(move1, move2)
            result_message = {
                "status": "result",
                "player1_move": move1,
                "player2_move": move2,
                "result": result
            }
            await send_message(writer1, result_message)
            await send_message(writer2, result_message)
            logging.info(f"房間 {room_id} 遊戲結果: {result}")

            # 等待兩位玩家的確認訊息
            ack1 = await receive_ack(reader1, 1, room_id)
            ack2 = await receive_ack(reader2, 2, room_id)

            if not ack1:
                logging.error(f"玩家 1 未正確確認收到結果。")
            if not ack2:
                logging.error(f"玩家 2 未正確確認收到結果。")
    except Exception as e:
        logging.error(f"房間 {room_id} 遊戲過程中發生錯誤: {e}")
    finally:
        # 在確保結果訊息已發送後，關閉連線
        writer1.close()
        await writer1.wait_closed()
        writer2.close()
        await writer2.wait_closed()

player_queue = {}

async def queue_player(reader, writer, room_id):
    """將玩家加入隊列，等待兩位玩家連接後開始遊戲"""
    addr = writer.get_extra_info('peername')
    logging.info(f"玩家連接來自 {addr}")
    print(f"玩家連接來自 {addr}")

    if room_id not in player_queue:
        player_queue[room_id] = []

    player_queue[room_id].append((reader, writer))

    if len(player_queue[room_id]) == 2:
        reader1, writer1 = player_queue[room_id][0]
        reader2, writer2 = player_queue[room_id][1]
        logging.info(f"兩位玩家已連接到房間 {room_id}，開始遊戲。")
        print(f"兩位玩家已連接到房間 {room_id}，開始遊戲。")
        asyncio.create_task(handle_game(reader1, writer1, reader2, writer2, room_id))
        # 清空隊列
        player_queue[room_id] = []

async def main():
    if len(sys.argv) != 4:
        print("用法: python game_server_rps.py <host> <port> <room_id>")
        return
    host = sys.argv[1]
    port = int(sys.argv[2])
    room_id = sys.argv[3]

    server = await asyncio.start_server(lambda r, w: asyncio.create_task(queue_player(r, w, room_id)), host, port)
    addr = server.sockets[0].getsockname()
    logging.info(f"Rock-Paper-Scissors 遊戲伺服器已啟動在 {addr}，房間ID: {room_id}")
    print(f"Rock-Paper-Scissors 遊戲伺服器已啟動在 {addr}，房間ID: {room_id}")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"遊戲伺服器異常終止: {e}")
