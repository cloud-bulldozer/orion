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
        series = self.setup_series()
        change_points_by_metric = series.analyze().change_points


        # Process if we have ack'ed regression
        ackSet = set()
        if len(self.options["ack"]) > 1 and self.options["ackMap"] is not None:
            for ack in self.options["ackMap"]["ack"]:
                pos = series.find_by_attribute("uuid",ack["uuid"])
                if len(pos) > 0 :
                    ackSet.add(str(pos[0]) + "_" + ack["metric"])

        # filter by direction and ack'ed issues
        for metric, changepoint_list in change_points_by_metric.items():
            for i in range(len(changepoint_list)-1, -1, -1):
                if ((self.metrics_config[metric]["direction"] == 1 and changepoint_list[i].stats.mean_1 > changepoint_list[i].stats.mean_2) or
                    (self.metrics_config[metric]["direction"] == -1 and changepoint_list[i].stats.mean_1 < changepoint_list[i].stats.mean_2) or
                    (str(changepoint_list[i].index) + "_" + changepoint_list[i].metric in ackSet) or
                    self.metrics_config[metric]["threshold"] > abs((changepoint_list[i].stats.mean_1 - changepoint_list[i].stats.mean_2)/changepoint_list[i].stats.mean_1)*100 ):
                    del changepoint_list[i]

        if [val for li in change_points_by_metric.values() for val in li]:
            self.regression_flag=True
        return series, change_points_by_metric
