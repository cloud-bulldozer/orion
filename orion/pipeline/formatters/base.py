"""Base formatter ABC and registry for Orion pipeline output."""

from abc import ABC, abstractmethod

from orion.pipeline.contracts import CLIOptions, PRAnalysisResult, TransformedResult


class Formatter(ABC):
    """Base class for pipeline output formatters."""

    @abstractmethod
    def format(self, results: list[TransformedResult], options: CLIOptions) -> None:
        """Write formatted output to stdout or file (based on options.save_output_path)."""

    def format_pr(self, results: list[PRAnalysisResult], options: CLIOptions) -> None:
        """Write PR analysis output. Default raises NotImplementedError."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support PR analysis output"
        )


class FormatterRegistry:
    """Maps format names to Formatter instances."""

    def __init__(self) -> None:
        self._formatters: dict[str, Formatter] = {}

    def register(self, name: str, formatter: Formatter) -> None:
        """Register a formatter under the given name."""
        self._formatters[name] = formatter

    def get(self, name: str) -> Formatter:
        """Look up a formatter by name."""
        if name not in self._formatters:
            raise KeyError(f"No formatter registered for '{name}'")
        return self._formatters[name]
