"""Original E-Divisive Algorithm from apache_otava"""

from otava.series import AnalysisOptions
from orion.algorithms.edivisive.edivisive import EDivisive


class OrigEDivisive(EDivisive):
    """Original E-Divisive algorithm variant.

    Overrides the analysis options to use the original E-Divisive
    changepoint detection method instead of the default Hunter-based one.

    Args:
        EDivisive: Inherits from EDivisive
    """

    def _get_analysis_options(self):
        options = AnalysisOptions()
        options.orig_edivisive = True
        return options
