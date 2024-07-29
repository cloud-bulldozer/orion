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
        self.dataframe["timestamp"] = self.dataframe["timestamp"].astype(int) // 10**9
        series= self.setup_series()
        change_points_by_metric = series.analyze().change_points

        # filter by direction
        for metric, changepoint_list in change_points_by_metric.items():
            for i in range(len(changepoint_list)-1, -1, -1):
                if ((self.metrics_config[metric]["direction"] == 1 and changepoint_list[i].stats.mean_1 > changepoint_list[i].stats.mean_2) or
                    (self.metrics_config[metric]["direction"] == -1 and changepoint_list[i].stats.mean_1 < changepoint_list[i].stats.mean_2) ):
                    del changepoint_list[i]

        return series, change_points_by_metric
