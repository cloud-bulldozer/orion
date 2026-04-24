"""
orion.constants

Module for storing constants across orion.
"""

EDIVISIVE="EDivisive"
ISOLATION_FOREST="IsolationForest"
JSON="json"
TEXT="text"
JUNIT="junit"
CMR="cmr"

# Window expansion: when a changepoint is in the first 5 points, we re-validate by
# fetching up to 5 more data points from the past. These values are fixed for consistency.
#
# CHANGEPOINT_BUFFER (5): Number of initial points considered the "buffer". In the Hunter
# algorithm, a minimum of 5 points prior and 5 after a point are needed to better include
# a point as a changepoint; we chose 5 for this buffer for that reason.
#
# EXPAND_POINTS (5): When expanding, we use unbounded lookback (no time window) and
# set lookback_size = current_points + 5 so we get up to 5 additional points from the
# past. Run frequency varies by team; unbounded + cap guarantees we take only what
# we need and don't depend on a fixed number of days.
#
CHANGEPOINT_BUFFER = 0
EXPAND_POINTS = 0
