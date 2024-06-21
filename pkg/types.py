from threading import Lock
class OptionMap:
    _option_map = {}
    _lock = Lock()

    @classmethod
    def set_map(cls, options):
        with cls._lock:
            cls._option_map = options

    @classmethod
    def set_option(cls, key, value):
        with cls._lock:
            cls._option_map[key] = value

    @classmethod
    def get_map(cls):
        with cls._lock:
            return dict(cls._option_map)

    @classmethod
    def get_option(cls, key):
        with cls._lock:
            return cls._option_map.get(key)
