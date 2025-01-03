import asyncio
import json
import uuid
import config
from logger_setup import setup_logger
from auth import hash_password, verify_password
import random
import json
import os
import aiofiles

USERS_FILE = 'users.json'
GAMES_FILE = 'games.json'

games = {}
games_lock = asyncio.Lock()

logger = setup_logger(config.LOG_FILE)

users = {}
users_lock = asyncio.Lock()
online_users = {}
online_users_lock = asyncio.Lock()
game_rooms = {}
game_rooms_lock = asyncio.Lock()


async def load_games():
    global games
    games_data = {}
    if not os.path.exists(GAMES_FILE):
        async with aiofiles.open(GAMES_FILE, 'w') as f:
            await f.write(json.dumps(games_data))
        return games_data
    async with aiofiles.open(GAMES_FILE, 'r') as f:
        content = await f.read()
        if content:
            try:
                games_data = json.loads(content)
            except json.JSONDecodeError:
                games_data = {}
                await save_games()
    return games_data

async def save_games():
    global games
    async with aiofiles.open(GAMES_FILE, 'w') as f:
        data = json.dumps(games, indent=4)
        await f.write(data)
        logger.debug(f"Saved games: {data}")

async def handle_upload_game(params, username, reader, writer):
    global games
    if len(params) != 2:
        await send_message(writer, build_response("error", "Invalid UPLOAD_GAME command"))
        return
    game_name = params[0]
    game_description = params[1]
    try:
        await send_message(writer, build_response("ready", "Ready to receive game file", game_name=game_name))
        # data = await reader.readline()
        data = await reader.readuntil(b'\n')
        if not data:
            await send_message(writer, build_response("error", "No data received"))
            return
        message = data.decode().strip()
        message_json = json.loads(message)
        if 'file_size' not in message_json:
            await send_message(writer, build_response("error", "No file size provided"))
            return
        file_size = int(message_json['file_size'])
        file_content = await reader.readexactly(file_size)
        if not os.path.exists('games-server'):
            os.makedirs('games-server')
        file_path = os.path.join('games-server', game_name + '.py')
        logger.info(f"Saving game file to {file_path}")
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)
        async with games_lock:
            games[game_name] = {
                'publisher': username,
                'description': game_description,
                'file_name': game_name,
                'version': str(uuid.uuid4())
            }
            await save_games()
        await send_message(writer, build_response("success", f"UPLOAD_GAME_SUCCESS", game_name=game_name))
        logger.info(f"User {username} uploaded game {game_name}")
    except Exception as e:
        logger.error(f"Error while handling UPLOAD_GAME: {e}")
        await send_message(writer, build_response("error", "Failed to upload game"))


async def handle_list_own_games(username, writer):
    try:
        async with games_lock:
            user_games = {name: data for name, data in games.items() if data['publisher'] == username}
        if not user_games:
            await send_message(writer, build_response("success", "You have not published any games"))
            return
        games_list = []
        for name, data in user_games.items():
            games_list.append({
                'name': name,
                'description': data['description'],
                'version': data.get('version', 'N/A')
            })
        response = {
            "status": "success",
            "games": games_list
        }
        await send_message(writer, json.dumps(response) + '\n')
        logger.info(f"Sent list of own games to {username}")
        logger.debug(f"Own games: {games_list}")
    except Exception as e:
        logger.error(f"Error while handling LIST_OWN_GAMES: {e}")
        await send_message(writer, build_response("error", "Failed to list own games"))

async def handle_download_game_file(params, writer):
    if len(params) != 1:
        await send_message(writer, build_response("error", "Invalid DOWNLOAD_GAME_FILE command"))
        return
    game_name = params[0]
    try:
        file_path = os.path.join('games-server', game_name + '.py')
        logger.info(f"Sending game file {game_name}")
        if not os.path.exists(file_path):
            await send_message(writer, build_response("error", "Game file does not exist"))
            return
        file_size = os.path.getsize(file_path)
        file_transfer_message = {
            "status": "file_transfer",
            "game_name": game_name,
            "file_size": file_size
        }
        await send_message(writer, json.dumps(file_transfer_message) + '\n')
        await writer.drain()
        async with aiofiles.open(file_path, 'rb') as f:
            file_content = await f.read()
            writer.write(file_content)
            await writer.drain()
        logger.info(f"Sent game file {game_name}")
    except Exception as e:
        logger.error(f"Error while handling DOWNLOAD_GAME_FILE: {e}")
        await send_message(writer, build_response("error", "Failed to download game file"))


async def load_users():
    users_data = {}
    if not os.path.exists(USERS_FILE):
        async with aiofiles.open(USERS_FILE, 'w') as f:
            await f.write(json.dumps(users_data))
        return users_data
    async with aiofiles.open(USERS_FILE, 'r') as f:
        content = await f.read()
        if content:
            try:
                users_data = json.loads(content)
            except json.JSONDecodeError:
                users_data = {}
                await save_users()
    return users_data

async def save_users():
    async with aiofiles.open(USERS_FILE, 'w') as f:
        data = json.dumps(users, indent=4)
        await f.write(data)
        logger.debug(f"Saved users: {data}")

# def build_response(status, message):
#     return json.dumps({"status": status, "message": message}) + '\n'

def build_response(status, message, **kwargs):
    response = {"status": status, "message": message}
    response.update(kwargs)
    return json.dumps(response) + '\n'

async def send_message(writer, message):
    try:
        writer.write(message.encode())
        await writer.drain()
    except Exception as e:
        logger.error(f"發送訊息失敗: {e}")

async def broadcast(message):
    async with online_users_lock:
        writers = [info["writer"] for info in online_users.values()]
    for writer in writers:
        await send_message(writer, message)

async def broadcast_lobby_info():
    lobby_info = await get_lobby_info()
    message = json.dumps(lobby_info) + '\n'
    await broadcast(message)
    
async def get_lobby_info():
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
                "game_name": room["game_name"],
                "status": room["status"],
                "host": room["host"],
                "type": room["type"]
            }
            for r_id, room in game_rooms.items()
            # if room["type"] == "public" and room["status"] != "In Game"
            # if room["type"] == "public"
        ]
    
    lobby_info = {
        "status": "lobby_info",
        "public_rooms": public_rooms_data,
        "online_users": users_data
    }
    return lobby_info

async def send_lobby_info(writer):
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
                    "game_name": room["game_name"],
                    "status": room["status"],
                    "host": room["host"],
                    "type": room["type"]
                }
                for r_id, room in game_rooms.items()
                # if room["type"] == "public" and room["status"] != "In Game"
                # if room["type"] == "public"
            ]
        
        lobby_info = {
            "status": "lobby_info",
            "public_rooms": public_rooms_data,
            "online_users": users_data
        }
        await send_message(writer, json.dumps(lobby_info) + '\n')
        logger.info("發送 SHOW_STATUS 訊息給用戶。")
    except Exception as e:
        logger.error(f"發送大廳信息失敗: {e}")


async def handle_register(params, writer):
    global users
    if len(params) != 2:
        await send_message(writer, build_response("error", "Invalid REGISTER command"))
        return
    username_reg, password_reg = params
    if username_reg in users:
        await send_message(writer, build_response("error", "Username already exists"))
    else:
        hashed_password = hash_password(password_reg)
        async with users_lock:
            users[username_reg] = hashed_password
            await save_users()
        await send_message(writer, build_response("success", "REGISTER_SUCCESS"))
        logger.info(f"用戶註冊成功: {username_reg}")

async def handle_login(params, reader, writer):
    global users
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
            # await send_message(writer, build_response("success", "LOGIN_SUCCESS"))
            await send_message(writer, build_response("success", f"LOGIN_SUCCESS {username_login}"))
            await send_lobby_info(writer)
            async with online_users_lock:
                users_data = [
                    {"username": user, "status": info["status"]}
                    for user, info in online_users.items()
                ]
            login_message = {
                "status": "broadcast",
                "event": "user_login",
                "username": username_login
            }
            online_users_message = {
                "status": "update",
                "type": "online_users",
                "data": users_data
            }
            await broadcast(json.dumps(online_users_message) + '\n')
            await broadcast(json.dumps(login_message) + '\n')
            logger.info(f"用戶登錄成功: {username_login}")
        else:
            await send_message(writer, build_response("error", "Incorrect password"))

async def handle_logout(username, writer):
    user_removed = False
    async with online_users_lock:
        if username in online_users:
            del online_users[username]
            user_removed = True
    if user_removed:
        try:
            await send_message(writer, build_response("success", "LOGOUT_SUCCESS"))
        except Exception as e:
            logger.error(f"Failed to send logout success message to {username}: {e}")
        
        try:
            # Collect users_data without holding the lock during I/O
            async with online_users_lock:
                users_data = [
                    {"username": user, "status": info["status"]}
                    for user, info in online_users.items()
                ]
            # Handle leaving room
            await handle_leave_room(username, writer)
            logout_message = {
                "status": "broadcast",
                "event": "user_logout",
                "username": username
            }
            await broadcast(json.dumps(logout_message) + '\n')
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
    room_type, game_name = params
    if room_type not in ['public', 'private']:
        await send_message(writer, build_response("error", "Invalid room type"))
        return
    async with games_lock:
        if game_name not in games:
            await send_message(writer, build_response("error", "Game does not exist"))
            logger.error(f"Game {game_name} does not exist (CREATE_ROOM)")
            return
    # if game_name not in ['rock_paper_scissors', 'tictactoe', 'connectfour']:
    #     await send_message(writer, build_response("error", "Invalid game type"))
    #     return
    async with online_users_lock:
        if username in online_users:
            if online_users[username]["status"] == "in_room":
                await send_message(writer, build_response("error", "You are already in a room"))
                return
            online_users[username]["status"] = "in_room"
    room_id = str(uuid.uuid4())
    async with game_rooms_lock:
        game_rooms[room_id] = {
            'creator': username,
            'host': username,
            'type': room_type,
            'game_name': game_name,
            'status': 'Waiting',
            'players': [username],
            'invited_users': [],
            'capacity': 2
        }

    await send_message(writer, build_response("success", f"CREATE_ROOM_SUCCESS {room_id} {game_name}"))
    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_name": room["game_name"],
                "status": room["status"],
                "host": room["host"],
                "type": room["type"]
            }
            for r_id, room in game_rooms.items()
            # if room["type"] == "public" and room["status"] != "In Game"
            # if room["type"] == "public"
        ]
    public_rooms_message = {
        "status": "update",
        "type": "public_rooms",
        "data": public_rooms_data
    }
    await broadcast(json.dumps(public_rooms_message) + '\n')
    room_message = {
        "status": "broadcast",
        "event": "room_created",
        "room_id": room_id,
        "creator": username,
        "game_name": game_name,
        "room_type": room_type
    }
    await broadcast(json.dumps(room_message) + '\n')
    logger.info(f"用戶 {username} 創建房間: {room_id}")

    if game_name in ['rock_paper_scissors', 'tictactoe', 'connectfour']:
        logger.info(f"等待第二位玩家加入 {game_name.capitalize()} 房間: {room_id}")

async def handle_leave_room(username, writer):
    room_to_delete = None
    async with game_rooms_lock:
        for room_id, room in game_rooms.items():
            if username in room["players"]:
                room["players"].remove(username)
                if username == room["host"]:
                    if room["players"]:
                        room["host"] = room["players"][0]
                        host_transfer_message = {
                            "status": "host_transfer",
                            "room_id": room_id,
                            "new_host": room["host"]
                        }
                        async with online_users_lock:
                            if room["host"] in online_users:
                                new_host_writer = online_users[room["host"]]["writer"]
                                await send_message(new_host_writer, json.dumps(host_transfer_message) + '\n')
                        for player in room['players']:
                            if player != room['host'] and player in online_users:
                                player_writer = online_users[player]['writer']
                                await send_message(player_writer, build_response("info", f"Host has left the room. New host is {room['host']}"))
                    else:
                        room_to_delete = room_id
                if not room["players"] and not room["invited_users"]:
                    room_to_delete = room_id
                else:
                    async with online_users_lock:
                        for player in room['players']:
                            if player in online_users:
                                player_writer = online_users[player]['writer']
                                await send_message(player_writer, build_response("info", f"Player {username} has left the room"))
                break
        if room_to_delete:
            del game_rooms[room_to_delete]
            logger.info(f"Room {room_to_delete} has been deleted.")

    async with online_users_lock:
        if username in online_users:
            online_users[username]['status'] = 'idle'
    
    await send_message(writer, build_response("success", "LEAVE_ROOM_SUCCESS"))
    
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

    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_name": room["game_name"],
                "status": room["status"],
                "host": room["host"],
                "type": room["type"]
            }
            for r_id, room in game_rooms.items()
            # if room["type"] == "public"
        ]
    public_rooms_message = {
        "status": "update",
        "type": "public_rooms",
        "data": public_rooms_data
    }
    await broadcast(json.dumps(public_rooms_message) + '\n')

    logger.info(f"User {username} has left the room and is now idle.")

def get_random_p2p_port():
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

    async with online_users_lock:
        if username in online_users:
            online_users[username]["status"] = "in_room"
    await send_message(writer, build_response("success", f"JOIN_ROOM_SUCCESS {room_id} {room['game_name']}"))

    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_name": room["game_name"],
                "status": room["status"],
                "host": room["host"],
                "type": room["type"]
            }
            for r_id, room in game_rooms.items()
            # if room["type"] == "public" and room["status"] != "In Game"
            # if room["type"] == "public"
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
    async with online_users_lock:
        if target_username not in online_users:
            await send_message(writer, build_response("error", "Target user not online"))
            return
        target_info = online_users[target_username]
        if target_info["status"] != "idle":
            await send_message(writer, build_response("error", "Target user is not idle"))
            return
        target_writer = target_info["writer"]
    async with game_rooms_lock:
        if room_id not in game_rooms:
            await send_message(writer, build_response("error", "Room does not exist"))
            return
        room = game_rooms[room_id]
        if room['host'] != username:
            await send_message(writer, build_response("error", "Only room host can invite players"))
            return
        if room['type'] != 'private':
            await send_message(writer, build_response("error", "Cannot invite players to a public room"))
            return
        if len(room['players']) >= 2:
            await send_message(writer, build_response("error", "Room is full"))
            return
        if target_username in room['invited_users']:
            await send_message(writer, build_response("error", f"{target_username} has already been invited"))
            return
        if target_username in room['players']:
            await send_message(writer, build_response("error", f"{target_username} is already in the room"))
            return
        room['invited_users'].append(target_username)
    
    try:
        invite_message = {
            "status": "invite",
            "from": username,
            "room_id": room_id,
            "game_name": room['game_name']
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
            await send_message(writer, build_response("error", "The room no longer exists"))
            return
        room = game_rooms[room_id]
        if room['status'] == 'In Game':
            await send_message(writer, build_response("error", "The room is already in game"))
            return
        if len(room['players']) >= 2:
            await send_message(writer, build_response("error", "The room is full"))
            return
        if room['type'] != 'private':
            await send_message(writer, build_response("error", "Cannot accept invite to a public room"))
            return
        if username in room['players']:
            await send_message(writer, build_response("error", "You are already in the room"))
            return
        if username not in room['invited_users']:
            await send_message(writer, build_response("error", "You have not been invited to this room"))
            return
        if len(room['players']) >= room['capacity']:
            await send_message(writer, build_response("error", "The room is full"))
            return
        
        room['invited_users'].remove(username)
        room['players'].append(username)

    async with online_users_lock:
        if username in online_users:
            online_users[username]["status"] = "in_room"
    await send_message(writer, build_response("success", f"JOIN_ROOM_SUCCESS {room_id} {room['game_name']}"))

    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_name": room["game_name"],
                "status": room["status"],
                "host": room["host"],
                "type": room["type"]
            }
            for r_id, room in game_rooms.items()
            # if room["type"] == "public" and room["status"] != "In Game"
            # if room["type"] == "public"
        ]
    public_rooms_message = {
        "status": "update",
        "type": "public_rooms",
        "data": public_rooms_data
    }
    await broadcast(json.dumps(public_rooms_message) + '\n')
    logger.info(f"User {username} accepted invite to join room: {room_id}")

async def handle_start_game(username, writer):
    async with game_rooms_lock:
        room_found = False
        for room_id, room in game_rooms.items():
            if username in room["players"]:
                room_found = True
                if username != room["host"]:
                    await send_message(writer, build_response("error", "Only the host can start the game"))
                    return
                if len(room["players"]) < room['capacity']:
                    await send_message(writer, build_response("error", "Cannot start game: the room is not full"))
                    return
                room['status'] = 'In Game'
                game_name = room['game_name']
                host_player = username
                other_player = None
                for player in room["players"]:
                    if player != host_player:
                        other_player = player
                        break
                if not other_player:
                    await send_message(writer, build_response("error", "No other player in room"))
                    return

                async with online_users_lock:
                    for player in room['players']:
                        if player in online_users:
                            online_users[player]["status"] = "in_game"

                    host_info = online_users[host_player]
                    other_info = online_users[other_player]
                    host_port = get_random_p2p_port()
                    other_port = get_random_p2p_port()
                    host_message = {
                        "status": "p2p_info",
                        "role": "host",
                        "peer_ip": other_info["ip"],
                        "peer_port": other_port,
                        "own_port": host_port,
                        "game_name": game_name
                    }
                    other_message = {
                        "status": "p2p_info",
                        "role": "client",
                        "peer_ip": host_info["ip"],
                        "peer_port": host_port,
                        "own_port": other_port,
                        "game_name": game_name
                    }
                    await send_message(host_info["writer"], json.dumps(host_message) + '\n')
                    await send_message(other_info["writer"], json.dumps(other_message) + '\n')
                logger.info(f"Game server info sent to players in room: {room_id}")
                break
        if not room_found:
            await send_message(writer, build_response("error", "You are not in a room"))

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

    async with game_rooms_lock:
        if room_id in game_rooms:
            room = game_rooms[room_id]
            if username in room['invited_users']:
                room['invited_users'].remove(username)
    await send_message(writer, build_response("success", f"DECLINE_INVITE_SUCCESS {room_id}"))

async def handle_show_status(writer):
    try:
        await send_lobby_info(writer)
        logger.info("發送 SHOW_STATUS 訊息給用戶。")
    except Exception as e:
        logger.error(f"處理 SHOW_STATUS 時發生錯誤: {e}")
        await send_message(writer, build_response("error", "Failed to retrieve status"))


async def handle_game_over(username):
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

    async with game_rooms_lock:
        public_rooms_data = [
            {
                "room_id": r_id,
                "creator": room["creator"],
                "game_name": room["game_name"],
                "status": room["status"],
                "host": room["host"],
                "type": room["type"]
            }
            for r_id, room in game_rooms.items()
            # if room["type"] == "public" and room["status"] != "In Game"
            # if room["type"] == "public"
        ]
    public_rooms_message = {
        "status": "update",
        "type": "public_rooms",
        "data": public_rooms_data
    }
    await broadcast(json.dumps(public_rooms_message) + '\n')

    logger.info(f"User {username} has ended the game and is now idle.")

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    logger.info(f"來自 {addr} 的新連接")
    username = None
    try:
        while True:
            data = await reader.readline()
            if not data:
                # Client disconnected
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

                elif command == "LEAVE_ROOM":
                    if username:
                        await handle_leave_room(username, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))
                
                elif command == "START_GAME":
                    if username:
                        await handle_start_game(username, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))

                elif command == "UPLOAD_GAME":
                    if username:
                        await handle_upload_game(params, username, reader, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))
                elif command == "LIST_OWN_GAMES":
                    if username:
                        await handle_list_own_games(username, writer)
                    else:
                        await send_message(writer, build_response("error", "Not logged in"))
                elif command == "DOWNLOAD_GAME_FILE":
                    if username:
                        await handle_download_game_file(params, writer)
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
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            logger.error(f"在關閉與客戶端 {addr} 時發生錯誤: {e}")


async def main():  
    global users
    users = await load_users()
    global games
    games = await load_games()
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