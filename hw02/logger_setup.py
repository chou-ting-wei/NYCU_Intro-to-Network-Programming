# logger_setup.py

import logging

def setup_logger(log_file):
    logger = logging.getLogger("LobbyServer")
    logger.setLevel(logging.DEBUG)
    
    # 創建文件處理器
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    
    # 創建控制台處理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # 創建日誌格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    # 添加處理器到日誌器
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

# logger_setup.py

# import logging

# def setup_logger(log_file):
#     logger = logging.getLogger("LobbyServer")
#     logger.setLevel(logging.INFO)
    
#     # 創建文件處理器
#     fh = logging.FileHandler(log_file)
#     fh.setLevel(logging.INFO)
    
#     # 創建日誌格式
#     formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
#     fh.setFormatter(formatter)
    
#     # 添加處理器到日誌記錄器
#     if not logger.handlers:
#         logger.addHandler(fh)
    
#     return logger
