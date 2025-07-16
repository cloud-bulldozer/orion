"""
Algorithm Factory to choose avaiable algorithms
"""

from fmatch.matcher import Matcher
import pandas as pd
import pkg.constants as cnsts
from .edivisive import EDivisive
from .isolationforest import IsolationForestWeightedMean
from .cmr import CMR


class AlgorithmFactory:  # pylint: disable= too-few-public-methods, too-many-arguments, line-too-long
    """Algorithm Factory to choose algorithm"""

    def instantiate_algorithm(
        self,
        algorithm: str,
        matcher: Matcher,
        dataframe: pd.DataFrame,
        orion_config: dict,
        options: dict,
    ):
        """Algorithm instantiation method

        Args:
            algorithm (str): Name of the algorithm
            matcher (Matcher): Matcher class
            dataframe (pd.Dataframe): dataframe with data
            orion_config (dict): Orion configuration
            options (dict): options dictionary
        Raises:
            ValueError: When invalid algo is chosen

        Returns:
            Algorithm : Algorithm
        """
        metrics_config = self._get_metrics_config(orion_config)
        if algorithm == cnsts.EDIVISIVE:
            return EDivisive(matcher, dataframe, options, orion_config, metrics_config)
        if algorithm == cnsts.ISOLATION_FOREST:
            return IsolationForestWeightedMean(
                matcher, dataframe, options, orion_config
            )
        if algorithm == cnsts.CMR:
            return CMR(matcher, dataframe, options, orion_config)
        raise ValueError("Invalid algorithm called")


    def _get_metrics_config(self, orion_config):
        """Get metrics configuration dict

        Args:
            config (dict): orion configuration

        Returns:
            dict: metrics configuration dictionary
        """
        metrics_config = {}
        for cfg in orion_config["metrics"]:
            metrics_config[cfg["name"]] = cfg
        return metrics_config
