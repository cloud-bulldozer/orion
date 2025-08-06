"""CMR - Comparing Mean Responses Algorithm"""

# pylint: disable = line-too-long
import pandas as pd
import numpy

from hunter.series import  ChangePoint, ComparativeStats
from orion.logger import SingletonLogger
from orion.algorithms.algorithm import Algorithm


class CMR(Algorithm):
    """Implementation of the CMR algorithm
    Will Combine metrics into 2 lines and compare with a tolerancy to set pass fail

    Args:
        Algorithm (Algorithm): Inherits
    """


    def _analyze(self):
        """Analyze the dataframe with meaning any previous data and generate percent change with a current uuid

        Returns:
            series: data series that contains attributes and full dataframe
            change_points_by_metric: list of ChangePoints
        """
        logger_instance = SingletonLogger.getLogger("Orion")
        logger_instance.info("Starting analysis using CMR")
        if not (pd.api.types.is_numeric_dtype(self.dataframe["timestamp"]) and self.dataframe["timestamp"].astype(int).min() > 1e9):
            self.dataframe["timestamp"] = pd.to_datetime(self.dataframe["timestamp"])
            self.dataframe["timestamp"] = self.dataframe["timestamp"].astype(int) // 10**9

        if len(self.dataframe.index) == 1:
            series= self.setup_series()
            series.data = self.dataframe
            return series, {}
        # if larger than 2 rows, need to get the mean of 0 through -2
        self.dataframe = self.combine_and_average_runs(self.dataframe)

        series= self.setup_series()

        df, change_points_by_metric = self.run_cmr(self.dataframe)
        series.data= df
        return series, change_points_by_metric


    def run_cmr(self, dataframe_list: pd.DataFrame):
        """
        Generate the percent difference in a 2 row dataframe

        Args:
            dataframe_list (pd.DataFrame): data frame of all data to compare on

        Returns:
            pd.Dataframe, dict[metric_name, ChangePoint]: Returned data frame and change points
        """
        metric_columns = self.metrics_config.keys()
        change_points_by_metric={ k:[] for k in metric_columns }

        for column in metric_columns:

            change_point = ChangePoint(metric=column,
                                            index=1,
                                            time=0,
                                            stats=ComparativeStats(
                                                mean_1=dataframe_list[column][0],
                                                mean_2=dataframe_list[column][1],
                                                std_1=0,
                                                std_2=0,
                                                pvalue=1
                                            ))
            change_points_by_metric[column].append(change_point)

        # based on change point generate pass/fail
        return dataframe_list, change_points_by_metric

    def combine_and_average_runs(self, dataFrame: pd.DataFrame):
        """
        If more than 1 previous run, mean data together into 1 single row
        Combine with current run into 1 data frame (current run being -1 index)

        Args:
            dataFrame (pd.DataFrame): data to combine into 2 rows

        Returns:
            pd.Dataframe: data frame of most recent run and averaged previous runs
        """
        i = 0

        last_row = dataFrame.tail(1)
        dF = dataFrame[:-1]
        data2 = {}

        metric_columns = list(dataFrame.columns)
        for column in metric_columns:

            if isinstance(dF.loc[0, column], (numpy.float64, numpy.int64)):
                mean = dF[column].mean()
                data2[column] = [mean]
            else:
                column_list = dF[column].tolist()
                non_numeric_joined_list = ','.join(column_list)
                data2[column] = [non_numeric_joined_list]
            i += 1
        df2 = pd.DataFrame(data2)

        result = pd.concat([df2, last_row], ignore_index=True)
        return result
