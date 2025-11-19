"""
Algorithm Factory to choose avaiable algorithms
"""
import pandas as pd
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
            dataframe (pd.Dataframe): dataframe with data
            test (dict): test information dictionary
            options (dict): options for the run
            metrics_config (dict): metrics configuration
            version_field (str): field name for the version
            uuid_field (str): field name for the uuid
        Raises:
            ValueError: When invalid algo is chosen

        Returns:
            Algorithm : Algorithm
        """
        if algorithm == cnsts.EDIVISIVE:
            return EDivisive(dataframe, test, options, metrics_config, version_field, uuid_field)
        if algorithm == cnsts.ISOLATION_FOREST:
            return IsolationForestWeightedMean(dataframe, test, options, metrics_config, version_field, uuid_field)
        if algorithm == cnsts.CMR:
            return CMR(dataframe, test, options, metrics_config, version_field, uuid_field)
        raise ValueError("Invalid algorithm called")
