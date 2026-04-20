"""Pipeline error hierarchy for Orion."""


class PipelineError(Exception):
    """Base error for all pipeline stages."""


class ValidationError(PipelineError):
    """Raised when config parsing or connectivity checks fail."""


class GatheringError(PipelineError):
    """Raised when data fetching from ES/OpenSearch fails."""


class AnalysisError(PipelineError):
    """Raised when algorithm execution fails."""


class TransformationError(PipelineError):
    """Raised when post-analysis transformation fails."""


class FormatterError(PipelineError):
    """Raised when output formatting fails."""
