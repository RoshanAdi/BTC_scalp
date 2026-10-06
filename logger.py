import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

def setup_logging(log_file: str = "trading_bot.log", level: str = "INFO"):
    """Setup logging configuration with rotation"""
    
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Rotating File handler - keeps last 1000 lines approximately (5 files x 200KB each)
    # Average log line ~200 bytes, so 200KB ≈ 1000 lines
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=200 * 1024,  # 200KB per file
        backupCount=5  # Keep 5 backup files (total ~1000 lines)
    )
    file_handler.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
