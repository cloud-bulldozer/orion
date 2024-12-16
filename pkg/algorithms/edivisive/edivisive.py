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
        ackList = []
        if len(self.options["ack"]) > 1 :
            for ack in self.options["ackMap"]["ack"]:
                pos = series.find_by_attribute("uuid",ack["uuid"])
                ackList.append(
                    {"pos" : pos[0],
                     "metric" : ack["metric"]})

        # filter by direction
        for metric, changepoint_list in change_points_by_metric.items():
            for i in range(len(changepoint_list)-1, -1, -1):
                if ((self.metrics_config[metric]["direction"] == 1 and changepoint_list[i].stats.mean_1 > changepoint_list[i].stats.mean_2) or
                    (self.metrics_config[metric]["direction"] == -1 and changepoint_list[i].stats.mean_1 < changepoint_list[i].stats.mean_2) ):
                    del changepoint_list[i]

        # Filter ack'ed changes
        for metric, changepoint_list in change_points_by_metric.items():
            for i in range(len(changepoint_list)-1, -1, -1):
                for acked in ackList:
                    if len(changepoint_list) > 0 :
                        if (changepoint_list[i].index == acked["pos"] and changepoint_list[i].metric == acked["metric"]):
                            del changepoint_list[i]

        if [val for li in change_points_by_metric.values() for val in li]:
            self.regression_flag=True
        return series, change_points_by_metric
