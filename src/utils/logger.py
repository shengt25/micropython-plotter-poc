import logging
import sys


def setup_logger(name: str) -> logging.Logger:
    """
    Setup logger

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler - output to stdout (won't affect UI Console)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger
