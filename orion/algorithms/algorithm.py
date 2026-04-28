"""Module for Generic Algorithm class"""

from abc import ABC, abstractmethod
import pandas as pd
from otava.series import Series, Metric


class Algorithm(ABC): # pylint: disable = too-many-arguments, too-many-instance-attributes
    """Generic Algorithm class for algorithm factory"""

    def __init__(
        self,
        dataframe: pd.DataFrame,
        test: dict,
        options: dict,
        metrics_config: dict[str, dict],
    ) -> None:
        self.dataframe = dataframe
        self.test = test
        self.options = options
        self.metrics_config = metrics_config
        self.regression_flag = False
        self._acked_logged = False
        self._cached_analysis = None

    def get_analysis_results(self):
        """Return (series, change_points_by_metric) from _analyze(),
        caching the result so _analyze() only runs once."""
        if self._cached_analysis is None:
            self._cached_analysis = self._analyze()
        return self._cached_analysis

    @abstractmethod
    def _analyze(self):
        """Analyze algorithm"""

    def setup_series(self) -> Series:
        """
        Returns apache_otava.Series
        """
        metrics = {
            column: Metric(value.get("direction", 1), 1.0)
            for column, value in self.metrics_config.items()
        }
        data = {column: self.dataframe[column] for column in self.metrics_config}
        attributes = {
            column: self.dataframe[column]
            for column in self.dataframe.columns
            if column in [self.test["uuid_field"], self.test["version_field"]]
        }
        series = Series(
            test_name=self.test["name"],
            branch=None,
            time=list(self.dataframe["timestamp"]),
            metrics=metrics,
            data=data,
            attributes=attributes,
        )

        return series
