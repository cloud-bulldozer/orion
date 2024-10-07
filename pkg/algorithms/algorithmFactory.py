"""
Algorithm Factory to choose avaiable algorithms
"""
from fmatch.matcher import Matcher
import pandas as pd
import pkg.constants as cnsts
from .edivisive import EDivisive
from .isolationforest import IsolationForestWeightedMean
from .cmr import CMR


class AlgorithmFactory: # pylint: disable= too-few-public-methods, too-many-arguments, line-too-long
    """Algorithm Factory to choose algorithm
    """
    def instantiate_algorithm(self, algorithm: str, matcher: Matcher, dataframe:pd.DataFrame, test: dict, options: dict, metrics_config: dict[str,dict]):
        """Algorithm instantiation method

        Args:
            algorithm (str): Name of the algorithm
            matcher (Matcher): Matcher class
            dataframe (pd.Dataframe): dataframe with data
            test (dict): test information dictionary

        Raises:
            ValueError: When invalid algo is chosen

        Returns:
            Algorithm : Algorithm
        """
        if algorithm == cnsts.EDIVISIVE:
            return EDivisive(matcher, dataframe, test, options, metrics_config)
        if algorithm == cnsts.ISOLATION_FOREST:
            return IsolationForestWeightedMean(matcher, dataframe, test, options, metrics_config)
        if algorithm == cnsts.CMR:
            return CMR(matcher, dataframe, test, options, metrics_config)
        raise ValueError("Invalid algorithm called")
