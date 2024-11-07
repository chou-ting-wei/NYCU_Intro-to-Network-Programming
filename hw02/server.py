# server.py

import asyncio
import json
import uuid
import config
from logger_setup import setup_logger
from auth import hash_password, verify_password
import socket
import random

logger = setup_logger(config.LOG_FILE)

# 全局用戶字典
# 格式: {username: hashed_password}
users = {}
users_lock = asyncio.Lock()

# 全局在線用戶字典
# 格式: {username: {"reader": reader, "writer": writer, "status": "idle"/"in_game"}}
online_users = {}
online_users_lock = asyncio.Lock()

# 全局遊戲房間字典
# 格式: {room_id: {"creator": username, "type": "public"/"private", "game_type": "rock_paper_scissors"/"tictactoe", "status": "Waiting"/"In Game", "players": [username1, username2], "game_server_ip": ip, "game_server_port": port}}
game_rooms = {}
game_rooms_lock = asyncio.Lock()

def build_response(status, message):
    """構建 JSON 格式的回應訊息"""
    return json.dumps({"status": status, "message": message}) + '\n'

async def send_message(writer, message):
    """發送 JSON 格式的訊息給客戶端"""
    try:
        writer.write(message.encode())
        await writer.drain()
    except Exception as e:
        logger.error(f"發送訊息失敗: {e}")

async def broadcast(message):
    """Broadcast a message to all online users."""
    async with online_users_lock:
        writers = [info["writer"] for info in online_users.values()]
    for writer in writers:
        await send_message(writer, message)


async def send_lobby_info(writer):
    """向特定用戶發送線上用戶和公開房間列表"""
    try:
        async with online_users_lock:
            users_data = [
                {"username": user, "status": info["status"]}
                for user, info in online_users.items()
            ]
        
        async with game_rooms_lock:
            public_rooms_data = [
                {
                    "room_id": r_id,
                    "creator": room["creator"],
                    "game_type": room["game_type"],
                    "status": room["status"]
                }
                for r_id, room in game_rooms.items()
                if room["type"] == "public" and room["status"] != "In Game"
            ]
        
        # 構建格式化的狀態訊息
        status_message = "=== 公開房間列表 ===\n"
        if not public_rooms_data:
            status_message += "無公開房間等待玩家。\n"
        else:
            for room in public_rooms_data:
                status_message += f"房間ID: {room['room_id']} | 創建者: {room['creator']} | 遊戲類型: {room['game_type']} | 狀態: {room['status']}\n"
        
        status_message += "=====================\n\n"
        status_message += "=== 在線用戶列表 ===\n"
        if not users_data:
            status_message += "無玩家在線。\n"
        else:
            for user in users_data:
                status_message += f"玩家: {user['username']} - 狀態: {user['status']}\n"
        status_message += "=====================\n"
        
        # 發送格式化的狀態訊息
        status_response = {
            "status": "status",
            "message": status_message
        }
        await send_message(writer, json.dumps(status_response) + '\n')
        logger.info("發送 SHOW_STATUS 訊息給用戶。")
    except Exception as e:
        logger.error(f"發送大廳信息失敗: {e}")

async def handle_register(params, writer):
    if len(params) != 2:
        await send_message(writer, build_response("error", "Invalid REGISTER command"))
        return
    username_reg, password_reg = params
    async with users_lock:
        if username_reg in users:
            await send_message(writer, build_response("error", "Username already exists"))
        else:
            hashed_password = hash_password(password_reg)
            users[username_reg] = hashed_password
            await send_message(writer, build_response("success", "REGISTER_SUCCESS"))
            logger.info(f"用戶註冊成功: {username_reg}")

async def handle_login(params, reader, writer):
    if len(params) != 2:
        await send_message(writer, build_response("error", "Invalid LOGIN command"))
        return
    username_login, password_login = params
    async with users_lock:
        if username_login not in users:
            await send_message(writer, build_response("error", "User does not exist"))
            return
        stored_password = users[username_login]
        if verify_password(stored_password, password_login):
            async with online_users_lock:
                if username_login in online_users:
                    await send_message(writer, build_response("error", "User already logged in"))
                    logger.warning(f"重複登入嘗試: {username_login}")
                    return
                else:
                    client_ip, client_port = writer.get_extra_info('peername')
                    online_users[username_login] = {
                        "reader": reader,
                        "writer": writer,
                        "status": "idle",
                        "ip": client_ip,
                        "port": client_port
                    }
            await send_message(writer, build_response("success", "LOGIN_SUCCESS"))
            await send_lobby_info(writer)
            # Broadcast updated online users list
            async with online_users_lock:
                users_data = [
                    {"username": user, "status": info["status"]}
                    for user, info in online_users.items()
                ]
            online_users_message = {
                "status": "update",
                "type": "online_users",
                "data": users_data
            }
            await broadcast(json.dumps(online_users_message) + '\n')
            logger.info(f"用戶登錄成功: {username_login}")
        else:
            await send_message(writer, build_response("error", "Incorrect password"))

async def handle_logout(username, writer):
    user_removed = False
    async with online_users_lock:
        if username in online_users:
            # Remove user from online users list
            del online_users[username]
            user_removed = True
    if user_removed:
        # Send logout success message to the client
        try:
            await send_message(writer, build_response("success", "LOGOUT_SUCCESS"))
        except Exception as e:
            logger.error(f"Failed to send logout success message to {username}: {e}")
        
        # Broadcast updated online users list
        try:
            # Collect users_data without holding the lock during I/O
            async with online_users_lock:
                users_data = [
                    {"username": user, "status": info["status"]}
                    for user, info in online_users.items()
                ]
            online_users_message = {
                "status": "update",
                "type": "online_users",
                "data": users_data
            }
            await broadcast(json.dumps(online_users_message) + '\n')
            logger.info(f"User logged out: {username}")
        except Exception as e:
            logger.error(f"Failed to broadcast updated online users list after logout: {e}")
    else:
        await send_message(writer, build_response("error", "User not logged in"))

async def handle_create_room(params, username, writer):
    if len(params) != 2:
        await send_message(writer, build_response("error", "Invalid CREATE_ROOM command"))
        return
    room_type, game_type = params
    if room_type not in ['public', 'private']:
        await send_message(writer, build_response("error", "Invalid room type"))
        return
    if game_type not in ['rock_paper_scissors', 'tictactoe', 'connectfour']:
        await send_message(writer, build_response("error", "Invalid game type"))
        return
    room_id = str(uuid.uuid4())
    async with game_rooms_lock:
        game_rooms[room_id] = {
            'creator': username,
            'type': room_type,
            'game_type': game_type,
            'status': 'Waiting',
            'players': [username]
        }
    # Update user's status to "in_room"
    async with online_users_lock:
        if username in online_users:
            online_users[username]["status"] = "in_room"
    await send_message(writer, build_response("success", f"CREATE_ROOM_SUCCESS {room_id} {game_type}"))
    # Broadcast updated public rooms list
    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_type": room["game_type"],
                "status": room["status"]
            }
            for r_id, room in game_rooms.items()
            if room["type"] == "public" and room["status"] != "In Game"
        ]
    public_rooms_message = {
        "status": "update",
        "type": "public_rooms",
        "data": public_rooms_data
    }
    await broadcast(json.dumps(public_rooms_message) + '\n')
    logger.info(f"用戶 {username} 創建房間: {room_id}")

    # 如果遊戲類型是 Rock-Paper-Scissors 或 Tic-Tac-Toe，暫不啟動遊戲伺服器，等待第二位玩家加入
    if game_type in ['rock_paper_scissors', 'tictactoe']:
        logger.info(f"等待第二位玩家加入 {game_type.capitalize()} 房間: {room_id}")

def get_random_p2p_port():
    """Returns a random port within the P2P port range specified in config."""
    return random.randint(config.P2P_PORT_RANGE[0], config.P2P_PORT_RANGE[1])

async def handle_join_room(params, username, writer):
    if len(params) != 1:
        await send_message(writer, build_response("error", "Invalid JOIN_ROOM command"))
        return
    room_id = params[0]
    async with game_rooms_lock:
        if room_id not in game_rooms:
            await send_message(writer, build_response("error", "Room does not exist"))
            return
        room = game_rooms[room_id]
        if room['status'] == 'In Game':
            await send_message(writer, build_response("error", "Room is already in game"))
            return
        if len(room['players']) >= 2:
            await send_message(writer, build_response("error", "Room is full"))
            return
        if room['type'] == 'private' and username not in room['players']:
            await send_message(writer, build_response("error", "Cannot join a private room without invitation"))
            return
        if username in room['players']:
            await send_message(writer, build_response("error", "You are already in the room"))
            return
        room['players'].append(username)
    # Update user's status to "in_game"
    async with online_users_lock:
        if username in online_users:
            online_users[username]["status"] = "in_room"
    await send_message(writer, build_response("success", f"JOIN_ROOM_SUCCESS {room_id} {room['game_type']}"))
    
    if len(room['players']) == 2:
        async with game_rooms_lock:
            room['status'] = 'In Game'
            game_type = room['game_type']
            
            creator = room["players"][0]
            joiner = username
            async with online_users_lock:
                for player in room['players']:
                    if player in online_users:
                        online_users[player]["status"] = "in_game"
                
                # Retrieve creator and joiner info
                creator_info = online_users[creator]
                joiner_info = online_users[joiner]

                # Generate random ports for each role within the specified range
                creator_port = get_random_p2p_port()
                joiner_port = get_random_p2p_port()
                
                creator_message = {
                    "status": "p2p_info",
                    "role": "host",
                    "peer_ip": joiner_info["ip"],
                    "peer_port": joiner_port,
                    "own_port": creator_port,
                    "game_type": game_type
                }
                joiner_message = {
                    "status": "p2p_info",
                    "role": "client",
                    "peer_ip": creator_info["ip"],
                    "peer_port": creator_port,
                    "own_port": joiner_port,
                    "game_type": game_type
                }
                await send_message(creator_info["writer"], json.dumps(creator_message) + '\n')
                await send_message(joiner_info["writer"], json.dumps(joiner_message) + '\n')
        logger.info(f"遊戲伺服器資訊已發送給房間內玩家: {room_id}")

    # Broadcast updated public rooms list
    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_type": room["game_type"],
                "status": room["status"]
            }
            for r_id, room in game_rooms.items()
            if room["type"] == "public" and room["status"] != "In Game"
        ]
    public_rooms_message = {
        "status": "update",
        "type": "public_rooms",
        "data": public_rooms_data
    }
    await broadcast(json.dumps(public_rooms_message) + '\n')
    logger.info(f"用戶 {username} 加入房間: {room_id}")

async def handle_invite_player(params, username, writer):
    if len(params) != 2:
        await send_message(writer, build_response("error", "Invalid INVITE_PLAYER command"))
        return
    target_username, room_id = params
    async with game_rooms_lock:
        if room_id not in game_rooms:
            await send_message(writer, build_response("error", "Room does not exist"))
            return
        room = game_rooms[room_id]
        if room['creator'] != username:
            await send_message(writer, build_response("error", "Only room creator can invite players"))
            return
        if room['type'] != 'private':
            await send_message(writer, build_response("error", "Cannot invite players to a public room"))
            return
        if len(room['players']) >= 2:
            await send_message(writer, build_response("error", "Room is full"))
            return
    async with online_users_lock:
        if target_username not in online_users:
            await send_message(writer, build_response("error", "Target user not online"))
            return
        target_info = online_users[target_username]
        if target_info["status"] != "idle":
            await send_message(writer, build_response("error", "Target user is not idle"))
            return
        target_writer = target_info["writer"]
    try:
        invite_message = {
            "status": "invite",
            "from": username,
            "room_id": room_id
        }
        await send_message(target_writer, json.dumps(invite_message) + '\n')
        await send_message(writer, build_response("success", f"INVITE_SENT {target_username} {room_id}"))
        logger.info(f"User {username} invited {target_username} to join room: {room_id}")
    except Exception as e:
        logger.error(f"Failed to send invite to {target_username}: {e}")
        await send_message(writer, build_response("error", "Failed to send invite"))

async def handle_accept_invite(params, username, writer):
    if len(params) != 1:
        await send_message(writer, build_response("error", "Invalid ACCEPT_INVITE command"))
        return
    room_id = params[0]
    async with game_rooms_lock:
        if room_id not in game_rooms:
            await send_message(writer, build_response("error", "Room does not exist"))
            return
        room = game_rooms[room_id]
        if room['status'] == 'In Game':
            await send_message(writer, build_response("error", "Room is already in game"))
            return
        if len(room['players']) >= 2:
            await send_message(writer, build_response("error", "Room is full"))
            return
        if room['type'] != 'private':
            await send_message(writer, build_response("error", "Cannot accept invite to a public room"))
            return
        if username in room['players']:
            await send_message(writer, build_response("error", "You are already in the room"))
            return
        room['players'].append(username)
    # Update user's status to "in_room"
    async with online_users_lock:
        if username in online_users:
            online_users[username]["status"] = "in_room"
    await send_message(writer, build_response("success", f"JOIN_ROOM_SUCCESS {room_id} {room['game_type']}"))
    
    # Now, check if we have 2 players and start the game
    if len(room['players']) == 2:
        async with game_rooms_lock:
            room['status'] = 'In Game'
            game_type = room['game_type']
            creator = room["players"][0]
            joiner = username
            async with online_users_lock:
                for player in room['players']:
                    if player in online_users:
                        online_users[player]["status"] = "in_game"
                # Retrieve creator and joiner info
                creator_info = online_users[creator]
                joiner_info = online_users[joiner]
                # Generate random ports for each role within the specified range
                creator_port = get_random_p2p_port()
                joiner_port = get_random_p2p_port()
                creator_message = {
                    "status": "p2p_info",
                    "role": "host",
                    "peer_ip": joiner_info["ip"],
                    "peer_port": joiner_port,
                    "own_port": creator_port,
                    "game_type": game_type
                }
                joiner_message = {
                    "status": "p2p_info",
                    "role": "client",
                    "peer_ip": creator_info["ip"],
                    "peer_port": creator_port,
                    "own_port": joiner_port,
                    "game_type": game_type
                }
                await send_message(creator_info["writer"], json.dumps(creator_message) + '\n')
                await send_message(joiner_info["writer"], json.dumps(joiner_message) + '\n')
            logger.info(f"Game server info sent to players in room: {room_id}")
    # Broadcast updated public rooms list
    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_type": room["game_type"],
                "status": room["status"]
            }
            for r_id, room in game_rooms.items()
            if room["type"] == "public" and room["status"] != "In Game"
        ]
    public_rooms_message = {
        "status": "update",
        "type": "public_rooms",
        "data": public_rooms_data
    }
    await broadcast(json.dumps(public_rooms_message) + '\n')
    logger.info(f"User {username} accepted invite to join room: {room_id}")

async def handle_decline_invite(params, username, writer):
    if len(params) != 2:
        await send_message(writer, build_response("error", "Invalid DECLINE_INVITE command"))
        return
    inviter_username, room_id = params
    # Notify the inviter that the invite was declined
    async with online_users_lock:
        if inviter_username in online_users:
            inviter_info = online_users[inviter_username]
            inviter_writer = inviter_info["writer"]
            decline_message = {
                "status": "invite_declined",
                "from": username,
                "room_id": room_id
            }
            await send_message(inviter_writer, json.dumps(decline_message) + '\n')
            logger.info(f"User {username} declined invitation from {inviter_username} to room: {room_id}")
    await send_message(writer, build_response("success", f"DECLINE_INVITE_SUCCESS {room_id}"))


async def handle_show_status(writer):
    """處理 SHOW_STATUS 指令，發送格式化的公開房間和在線用戶列表"""
    try:
        async with online_users_lock:
            users_data = [
                {"username": user, "status": info["status"]}
                for user, info in online_users.items()
            ]
        
        async with game_rooms_lock:
            public_rooms_data = [
                {
                    "room_id": r_id,
                    "creator": room["creator"],
                    "game_type": room["game_type"],
                    "status": room["status"]
                }
                for r_id, room in game_rooms.items()
                if room["type"] == "public" and room["status"] != "In Game"
            ]
        
        # 構建格式化的狀態訊息
        status_message = "=== 公開房間列表 ===\n"
        if not public_rooms_data:
            status_message += "無公開房間等待玩家。\n"
        else:
            for room in public_rooms_data:
                status_message += f"房間ID: {room['room_id']} | 創建者: {room['creator']} | 遊戲類型: {room['game_type']} | 狀態: {room['status']}\n"
        
        status_message += "=====================\n\n"
        status_message += "=== 在線用戶列表 ===\n"
        if not users_data:
            status_message += "無玩家在線。\n"
        else:
            for user in users_data:
                status_message += f"玩家: {user['username']} - 狀態: {user['status']}\n"
        status_message += "=====================\n"
        
        # 發送格式化的狀態訊息
        status_response = {
            "status": "status",
            "message": status_message
        }
        await send_message(writer, json.dumps(status_response) + '\n')
        logger.info("發送 SHOW_STATUS 訊息給用戶。")
    except Exception as e:
        logger.error(f"處理 SHOW_STATUS 時發生錯誤: {e}")
        await send_message(writer, build_response("error", "Failed to retrieve status"))

async def handle_game_over(username):
    # Update user's status to "idle"
    async with online_users_lock:
        if username in online_users:
            online_users[username]["status"] = "idle"

    room_to_delete = None
    async with game_rooms_lock:
        for room_id, room in game_rooms.items():
            if username in room["players"]:
                room["players"].remove(username)
                if len(room["players"]) == 0:
                    room_to_delete = room_id
                else:
                    # If room still has players, update its status to "Waiting"
                    room["status"] = "Waiting"
                break
        if room_to_delete:
            del game_rooms[room_to_delete]

    # Broadcast updated online users list
    async with online_users_lock:
        users_data = [
            {"username": user, "status": info["status"]}
            for user, info in online_users.items()
        ]
    online_users_message = {
        "status": "update",
        "type": "online_users",
        "data": users_data
    }
    await broadcast(json.dumps(online_users_message) + '\n')

    # Broadcast updated public rooms list
    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_type": room["game_type"],
                "status": room["status"]
            }
            for r_id, room in game_rooms.items()
            if room["type"] == "public" and room["status"] != "In Game"
        ]
    public_rooms_message = {
        "status": "update",
        "type": "public_rooms",
        "data": public_rooms_data
    }
    await broadcast(json.dumps(public_rooms_message) + '\n')

    logger.info(f"User {username} has ended the game and is now idle.")

async def handle_client(reader, writer):
    """處理每個客戶端連線的函數"""
    addr = writer.get_extra_info('peername')
    logger.info(f"來自 {addr} 的新連接")
    username = None
    try:
        while True:
            data = await reader.readline()
            if not data:
                # 客戶端斷線
                break
            try:
                message = data.decode().strip()
                if not message:
                    continue
                message_json = json.loads(message)
                command = message_json.get("command", "").upper()
                params = message_json.get("params", [])

                if command == "REGISTER":
                    await handle_register(params, writer)

                elif command == "LOGIN":
                    await handle_login(params, reader, writer)
                    if len(params) >= 1:
                        username = params[0]

                elif command == "LOGOUT":
                    if username:
                        await handle_logout(username, writer)
                        username = None
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))

                elif command == "CREATE_ROOM":
                    if username:
                        await handle_create_room(params, username, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))

                elif command == "JOIN_ROOM":
                    if username:
                        await handle_join_room(params, username, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))

                elif command == "INVITE_PLAYER":
                    if username:
                        await handle_invite_player(params, username, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))

                elif command == "ACCEPT_INVITE":
                    if username:
                        await handle_accept_invite(params, username, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))

                elif command == "DECLINE_INVITE":
                    if username:
                        await handle_decline_invite(params, username, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))

                elif command == "GAME_OVER":
                    if username:
                        await handle_game_over(username)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))
                
                elif command == "SHOW_STATUS":
                    if username:
                        await handle_show_status(writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))

                else:
                    await send_message(writer, build_response("error", "Unknown command"))

            except json.JSONDecodeError:
                await send_message(writer, build_response("error", "Invalid message format"))
            except Exception as e:
                logger.error(f"處理訊息時發生錯誤: {e}")
                await send_message(writer, build_response("error", "Server error"))
    except Exception as e:
        logger.error(f"處理客戶端 {addr} 時發生錯誤: {e}")
    finally:
        if username:
            user_removed = False
            async with online_users_lock:
                if username in online_users:
                    del online_users[username]
                    user_removed = True
            if user_removed:
                # Broadcast updated online users list
                try:
                    async with online_users_lock:
                        users_data = [
                            {"username": user, "status": info["status"]}
                            for user, info in online_users.items()
                        ]
                    online_users_message = {
                        "status": "update",
                        "type": "online_users",
                        "data": users_data
                    }
                    await broadcast(json.dumps(online_users_message) + '\n')
                    logger.info(f"User disconnected: {username}")
                except Exception as e:
                    logger.error(f"Failed to broadcast updated online users list after disconnection: {e}")
        writer.close()
        await writer.wait_closed()


async def main():  
    server = await asyncio.start_server(handle_client, config.HOST, config.PORT)

    addr = server.sockets[0].getsockname()
    logger.info(f"Lobby Server 正在運行在 {addr}")

    async with server:
        try:
            await server.serve_forever()
        except KeyboardInterrupt:
            logger.info("接收到鍵盤中斷，正在關閉伺服器...")
        finally:
            server.close()
            await server.wait_closed()
            logger.info("伺服器已關閉。")

if __name__ == "__main__":
    asyncio.run(main())