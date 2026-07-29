"""Statistical confidence indicators for changepoints."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConfidenceResult:
    """Statistical confidence for a single changepoint."""

    p_value: Optional[float]
    cohens_d: Optional[float]
    confidence_label: str
    sufficient_data: bool
    sample_size_before: int
    sample_size_after: int


def _map_label(p_value, cohens_d):
    """Map p-value and Cohen's d to a human-readable confidence label."""
    if p_value >= 0.05:
        return "Noise (trivial shift)"
    if cohens_d >= 0.8:
        return "Likely real (large shift)"
    if cohens_d >= 0.5:
        return "Likely real (moderate shift)"
    if cohens_d >= 0.2:
        return "Possible (small shift)"
    return "Statistically significant but trivial"
