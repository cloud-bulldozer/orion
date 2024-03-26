"""
Logger for orion
"""

import logging
import sys


class SingletonLogger:
    """Singleton logger to set logging at one single place

    Returns:
        _type_: _description_
    """

    _instance = None

    def __new__(cls, debug):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._logger = cls._initialize_logger(debug)
        return cls._instance

    @staticmethod
    def _initialize_logger(debug):
        level = debug  # if debug else logging.INFO
        logger = logging.getLogger("Orion")
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - file: %(filename)s - line: %(lineno)d - %(message)s" # pylint: disable = line-too-long
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    @property
    def logger(self):
        """property to return logger, getter method

        Returns:
            _type_: _description_
        """
        return self._logger  # pylint: disable = no-member
