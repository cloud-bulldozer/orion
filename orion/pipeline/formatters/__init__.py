"""Formatter classes for Orion output."""

from .base import BaseFormatter
from .json_formatter import JsonFormatter
from .text_formatter import TextFormatter
from .junit_formatter import JUnitFormatter
import orion.constants as cnsts


class FormatterFactory:
    """Factory for creating formatter instances."""

    @staticmethod
    def get_formatter(output_format: str) -> BaseFormatter:
        """Get a formatter instance for the given output format."""
        formatters = {
            cnsts.JSON: JsonFormatter,
            cnsts.TEXT: TextFormatter,
            cnsts.JUNIT: JUnitFormatter,
        }
        cls = formatters.get(output_format)
        if cls is None:
            raise ValueError(
                f"Unsupported output format: {output_format}"
            )
        return cls()
