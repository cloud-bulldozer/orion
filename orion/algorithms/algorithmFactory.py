"""
Algorithm Factory to choose avaiable algorithms
"""
import pandas as pd
from orion.matcher import Matcher
import orion.constants as cnsts
from .edivisive import EDivisive
from .isolationforest import IsolationForestWeightedMean
from .cmr import CMR


class AlgorithmFactory: # pylint: disable= too-few-public-methods, too-many-arguments, line-too-long
    """Algorithm Factory to choose algorithm
    """
    def instantiate_algorithm(  # pylint: disable = too-many-arguments
            self,
            algorithm: str,
            matcher: Matcher,
            dataframe:pd.DataFrame,
            test: dict,
            options: dict,
            metrics_config: dict[str,dict],
            version_field: str = "ocpVersion",
            uuid_field: str = "uuid"
        ):
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
            return EDivisive(matcher, dataframe, test, options, metrics_config, version_field, uuid_field)
        if algorithm == cnsts.ISOLATION_FOREST:
            return IsolationForestWeightedMean(matcher, dataframe, test, options, metrics_config, version_field, uuid_field)
        if algorithm == cnsts.CMR:
            return CMR(matcher, dataframe, test, options, metrics_config, version_field, uuid_field)
        raise ValueError("Invalid algorithm called")
