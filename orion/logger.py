"""
Logger as a common package
"""

import logging
import sys


class SingletonLogger:
    """Singleton logger to set logging at one single place

    Returns:
        _type_: _description_
    """

    instance = {}

    def __new__(cls, debug: int, name: str):
        if (not cls.instance) or name not in cls.instance:
            cls.instance[name] = cls._initialize_logger(debug, name)
        return cls.instance[name]

    @staticmethod
    def _initialize_logger(debug: int, name: str) -> logging.Logger:
        level = debug  # if debug else logging.INFO
        logger = logging.getLogger(name)
        logger.propagate = False
        if not logger.hasHandlers():
            logger.setLevel(level)
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(level)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)-10s - %(levelname)s - file: %(filename)s - line: %(lineno)d - %(message)s"  # pylint: disable = line-too-long
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    @classmethod
    def getLogger(cls, name: str) -> logging.Logger:
        """Return logger in instance

        Args:
            name (str): name of the logger

        Returns:
            logging.Logger: logger
        """
        return cls.instance.get(name, None)
