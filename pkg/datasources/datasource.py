# pylint: disable = R0903, E0211
""" 
Generic Datasource implementation
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any

class Datasource(ABC):
    """Generic method for Datasource

    Args:
        ABC (_type_): _description_
    """

    def __init__(self, test: Dict[str, Any],
                        match: Any,
                        options: Dict[str, Any],
                        start_timestamp: datetime,):
        self.test = test
        self.match = match
        self.options = options
        self.start_timestamp = start_timestamp

    @abstractmethod
    def process_test(self):
        """Unimplemented process test function
        """
