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
    _is_set = False

    @classmethod
    def set_map(cls, options):
        """set the option map to a dict
        """
        with cls._lock:
            if cls._is_set:
                raise ValueError("OptionMap is already set and cannot be modified")
            cls._option_map = options
            cls._is_set = True

    @classmethod
    def set_option(cls, key, value):
        """set the option value with key and value
        """
        with cls._lock:
            if cls._is_set:
                raise ValueError("OptionMap is already set and cannot be modified")
            cls._option_map[key] = value

    @classmethod
    def get_map(cls):
        """get the option map as dict
        """
        return dict(cls._option_map)

    @classmethod
    def get_option(cls, key):
        """get the option value with a key
        """
        return cls._option_map.get(key)
