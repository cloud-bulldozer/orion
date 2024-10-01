"""EDivisive Algorithm from hunter"""

# pylint: disable = line-too-long
import pandas as pd
from pkg.algorithms.algorithm import Algorithm


class EDivisive(Algorithm):
    """Implementation of the EDivisive algorithm using hunter

    Args:
        Algorithm (Algorithm): Inherits
    """


    def _analyze(self):
        self.dataframe["timestamp"] = pd.to_datetime(self.dataframe["timestamp"])
        self.dataframe["timestamp"] = self.dataframe["timestamp"].astype(int)
        first_timestamp = self.dataframe["timestamp"].dropna().iloc[0]
        if first_timestamp > 1_000_000_000_000:
            self.dataframe["timestamp"] = self.dataframe["timestamp"].astype('int64') // 10**9
        else:
            self.dataframe["timestamp"] = self.dataframe["timestamp"].astype('int64')
        series= self.setup_series()
        change_points_by_metric = series.analyze().change_points

        # filter by direction
        for metric, changepoint_list in change_points_by_metric.items():
            for i in range(len(changepoint_list)-1, -1, -1):
                if ((self.metrics_config[metric]["direction"] == 1 and changepoint_list[i].stats.mean_1 > changepoint_list[i].stats.mean_2) or
                    (self.metrics_config[metric]["direction"] == -1 and changepoint_list[i].stats.mean_1 < changepoint_list[i].stats.mean_2) ):
                    del changepoint_list[i]
        if [val for li in change_points_by_metric.values() for val in li]:
            self.regression_flag=True
        return series, change_points_by_metric
