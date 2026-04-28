"""Shared test fixtures and helpers."""

import logging
import pytest
from otava.series import ChangePoint
from otava.analysis import TTestStats

from orion.logger import SingletonLogger


@pytest.fixture(autouse=True)
def _init_logger():
    SingletonLogger(debug=logging.DEBUG, name="Orion")


def make_change_point(metric, index, mean_1=100.0, mean_2=200.0): # pylint: disable=missing-function-docstring
    return ChangePoint(
        metric=metric,
        index=index,
        qhat=0.0,
        time=0,
        stats=TTestStats(
            mean_1=mean_1,
            mean_2=mean_2,
            std_1=0.0,
            std_2=0.0,
            pvalue=1.0,
        ),
    )
