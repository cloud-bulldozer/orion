"""EDivisive Algorithm from hunter"""

# pylint: disable = line-too-long
from typing import Dict, List
import pandas as pd
from hunter.series import ChangePoint
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
                deleted = False
                if (self._has_changepoint(metric, changepoint_list, i) or
                    self._is_acked(ackSet, changepoint_list, i) or
                    self._is_under_threshold(metric, changepoint_list, i)):
                    deleted=True
                    del changepoint_list[i]
                if (not deleted and self.metrics_config[metric]["correlation"] != ""):
                    has_depending_changepoint = self._depending_metric_has_chagepoint(change_points_by_metric,
                                                                                      ackSet,
                                                                                      metric,
                                                                                      changepoint_list[i].index)
                    if not has_depending_changepoint:
                        del changepoint_list[i]

        if [val for li in change_points_by_metric.values() for val in li]:
            self.regression_flag=True
        return series, change_points_by_metric



    def _depending_metric_has_chagepoint(self, change_points_by_metric: Dict[str, List[ChangePoint]], ackSet, metric, index) -> bool:
        depending_metric = self.metrics_config[metric]["correlation"]
        context = self.metrics_config[metric]["context"]
        if depending_metric not in change_points_by_metric.keys():
            return False
        changepoint_list = change_points_by_metric[depending_metric]
        for i in range(len(changepoint_list)-1, -1, -1):
            if (changepoint_list[i].index >= index-context) and (changepoint_list[i].index <= index+context):
                if (self._has_changepoint(depending_metric, changepoint_list, i) or
                    self._is_acked(ackSet, changepoint_list, i) or
                    self._is_under_threshold(depending_metric, changepoint_list, i)):
                    return False
                return True
        return False


    def _is_under_threshold(self, metric, changepoint_list, i):
        return self.metrics_config[metric]["threshold"] > abs((changepoint_list[i].stats.mean_1 - changepoint_list[i].stats.mean_2)/changepoint_list[i].stats.mean_1)*100


    def _is_acked(self, ackSet, changepoint_list, i):
        return str(changepoint_list[i].index) + "_" + changepoint_list[i].metric in ackSet


    def _has_changepoint(self, metric, changepoint_list, i):
        return ((self.metrics_config[metric]["direction"] == 1 and changepoint_list[i].stats.mean_1 > changepoint_list[i].stats.mean_2) or
                (self.metrics_config[metric]["direction"] == -1 and changepoint_list[i].stats.mean_1 < changepoint_list[i].stats.mean_2))
