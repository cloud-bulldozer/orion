"""
Module to store types
"""
from threading import Lock
class OptionMap:
    """class to store command line arguments

    Returns:
        _type_: _description_
    """
    _option_map = {}
    _lock = Lock()

    @classmethod
    def set_map(cls, options):
        """set the option map to a dict
        """
        with cls._lock:
            cls._option_map = options

    @classmethod
    def set_option(cls, key, value):
        """set the option value with key and value
        """
        with cls._lock:
            cls._option_map[key] = value

    @classmethod
    def get_map(cls):
        """get the option map as dict
        """
        with cls._lock:
            return dict(cls._option_map)

    @classmethod
    def get_option(cls, key):
        """get the option value with a key
        """
        with cls._lock:
            return cls._option_map.get(key)
