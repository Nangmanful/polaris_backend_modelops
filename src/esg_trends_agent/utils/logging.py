"""
==================================================================
[모듈명] utils/logging.py
로깅 설정

[모듈 목표]
1) 로거 설정
2) 파일 및 콘솔 핸들러 설정
==================================================================
"""

import logging
import os
from .config import Config


def setup_logger(name: str = "esg_agent") -> logging.Logger:
    """로거 설정

    Args:
        name: 로거 이름

    Returns:
        logging.Logger: 설정된 로거
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러
    log_file = Config.LOG_FILE
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "esg_agent") -> logging.Logger:
    """로거 반환

    Args:
        name: 로거 이름

    Returns:
        logging.Logger: 로거
    """
    return logging.getLogger(name)
