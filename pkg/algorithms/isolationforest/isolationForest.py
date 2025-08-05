# pylint: disable = too-many-locals, line-too-long
"""The implementation module for Isolation forest and weighted mean"""
from sklearn.ensemble import IsolationForest
import pandas as pd
from fmatch.logrus import SingletonLogger
from hunter.series import  ChangePoint, ComparativeStats
from pkg.algorithms.algorithm import Algorithm


class IsolationForestWeightedMean(Algorithm):
    """Isolation forest with weighted mean

    Args:
        Algorithm (Algorithm): _description_
    """

    def _analyze(self):
        """Analyzing the data

        Args:
            dataframe (pd.DataFrame): _description_

        Returns:
            pd.Dataframe, pd.Dataframe: _description_
        """
        if not (pd.api.types.is_numeric_dtype(self.dataframe["timestamp"]) and self.dataframe["timestamp"].astype(int).min() > 1e9):
            self.dataframe["timestamp"] = pd.to_datetime(self.dataframe["timestamp"])
            self.dataframe["timestamp"] = self.dataframe["timestamp"].astype(int) // 10**9
        dataframe = self.dataframe.copy(deep=True)
        series = self.setup_series()

        logger_instance = SingletonLogger.getLogger("Orion")
        logger_instance.info("Starting analysis using Isolation Forest")
        metric_columns = self.metrics_config.keys()
        dataframe_with_metrics = dataframe[metric_columns]
        model = IsolationForest(contamination="auto", random_state=42)
        model.fit(dataframe_with_metrics)
        predictions = model.predict(dataframe_with_metrics)
        dataframe["is_anomaly"] = predictions
        anomaly_scores = model.decision_function(dataframe_with_metrics)
        # Add anomaly scores to the DataFrame
        dataframe["anomaly_score"] = anomaly_scores

        # Calculate moving average for each metric
        window_size = (5 if self.options.get("anomaly_window",None) is None else int(self.options.get("anomaly_window",None)))
        moving_averages = dataframe_with_metrics.rolling(window=window_size).mean()

        # Initialize percentage change columns for all metrics
        for feature in dataframe_with_metrics.columns:
            dataframe[f"{feature}_pct_change"] = 0.0

        change_points_by_metric={ k:[] for k in metric_columns }

        for idx, row in dataframe.iterrows():
            if row["is_anomaly"] == -1:
                for feature in metric_columns:
                    pct_change = (
                        (row[feature] - moving_averages.at[idx, feature])
                        / moving_averages.at[idx, feature]
                    ) * 100
                    if abs(pct_change) > (10 if self.options.get("min_anomaly_percent",None) is None else int(self.options.get("min_anomaly_percent",None))):
                        if (pct_change * self.metrics_config[feature]["direction"] > 0) or self.metrics_config[feature]["direction"]==0:
                            change_point = ChangePoint(metric=feature,
                                                       index=idx,
                                                       time=row['timestamp'],
                                                       stats=ComparativeStats(
                                                           mean_1=moving_averages.at[idx, feature],
                                                           mean_2=row[feature],
                                                           std_1=0,
                                                           std_2=0,
                                                           pvalue=1
                                                       ))
                            change_points_by_metric[feature].append(change_point)
        if [val for li in change_points_by_metric.values() for val in li]:
            self.regression_flag=True
        return series, change_points_by_metric
