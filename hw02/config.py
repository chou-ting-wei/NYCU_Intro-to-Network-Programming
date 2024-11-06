# config.py

# Lobby Server 的配置
HOST = '127.0.0.1'  # 伺服器主機地址
PORT = 15000        # 伺服器監聽的 Port

# 資料庫配置
# DATABASE = 'lobby.db'

# 日誌文件
LOG_FILE = 'server.log'

# 遊戲伺服器配置
GAME_SERVER_RPS_SCRIPT = 'game_server_rps.py'            # RPS 遊戲伺服器腳本名稱
GAME_SERVER_TICTACTOE_SCRIPT = 'game_server_tictactoe.py'  # Tic-Tac-Toe 遊戲伺服器腳本名稱
GAME_SERVER_MESSAGE_PORT = 16000                        # 遊戲伺服器發送訊息到 Lobby Server 的 Port
GAME_SERVER_BASE_PORT = 20000  # 遊戲伺服器的基礎 Port（動態分配從此 Port 開始）
GAME_SERVER_PORT_RANGE = (20000, 21000)  # Port 範圍

# 客戶端配置
CLIENT_GAME_RPS_SCRIPT = '/Users/twchou/Coding/GitHub/NYCU_Intro-to-Network-Programming/hw02/client_game_rps.py'  # RPS 遊戲客戶端腳本名稱
CLIENT_GAME_TICTACTOE_SCRIPT = '/Users/twchou/Coding/GitHub/NYCU_Intro-to-Network-Programming/hw02/client_game_tictactoe.py'

