# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

#Ignore pylint: disable=too-few-public-methods
"""Module for Report class"""
from collections import OrderedDict
from enum import Enum, unique
from typing import List, Dict, Any, Tuple
import json
from tabulate import tabulate

from otava.main import OtavaError
from otava.series import ChangePointGroup, Series
from otava.util import format_timestamp, insert_multiple, remove_common_prefix


@unique
class ReportType(Enum):
    """Report type enum"""
    LOG = "log"
    JSON = "json"
    REGRESSIONS_ONLY = "regressions_only"

    def __str__(self):
        return self.value


class Report:
    """Report class"""
    __series: Series
    __change_points: List[ChangePointGroup]
    __column_group_size: int

    def __init__(
        self,
        series: Series,
        change_points: List[ChangePointGroup],
        column_group_size: int = 5,
    ):
        self.__series = series
        self.__change_points = change_points
        self.__column_group_size = column_group_size

    @staticmethod
    def __column_widths(log: List[str]) -> Tuple[List[List[int]], List[int]]:
        """Return (column widths per table, line index of 'time' header per table).
        Each table's widths come from the line immediately after the header line
        that contains the keyword 'time'."""
        width_groups = []
        time_indexes = []
        i = 0
        prev_blank = True
        while i < len(log):
            line = log[i]
            is_blank = line.strip() == ""
            if is_blank:
                prev_blank = True
                i += 1
                continue
            if prev_blank and "time" in line and i + 1 < len(log):
                time_indexes.append(i)
                next_line = log[i + 1]
                width_groups.append([len(c) for c in next_line.split(None)])
                i += 2
                prev_blank = False
            else:
                prev_blank = False
                i += 1
        return width_groups, time_indexes

    @staticmethod
    def __increment_time_indexes_after(
        time_indexes: List[int], group_index: int, amount: int = 1
    ) -> None:
        """Add amount to each time_index from group_index+1 to the last (in place).
        Use after inserting lines so subsequent group header indices stay correct."""
        for j in range(group_index + 1, len(time_indexes)):
            time_indexes[j] += amount


    def produce_report(self, test_name: str, report_type: ReportType):
        """Produce report based on report type"""
        match report_type:
            case ReportType.LOG:
                return self.__format_log_annotated()
            case ReportType.JSON:
                return self.__format_json(test_name)
            case ReportType.REGRESSIONS_ONLY:
                return self.__format_regressions_only(test_name)
            case _:
                raise OtavaError(f"Unknown report type: {report_type}")


    def __format_log(self) -> Tuple[List[Dict[str, Any]], str]:
        """Format log"""
        time_column = [format_timestamp(ts, False) for ts in self.__series.time]
        metrics = list(self.__series.data.keys())
        metrics_len = len(metrics)

        tables = []
        column_groups = []
        for i in range(0, metrics_len, self.__column_group_size):
            metric_group = metrics[i : i + self.__column_group_size]
            group_data = {k: self.__series.data[k] for k in metric_group}
            column_groups.append(group_data)
            table = {"time": time_column, **self.__series.attributes, **group_data}
            headers = list(
                OrderedDict.fromkeys(
                    ["time", *self.__series.attributes, *remove_common_prefix(metric_group)]
                )
            )
            tables.append(tabulate(table, headers=headers))
        return column_groups, "\n\n".join(tables)


    def __format_log_annotated(self) -> str:
        """Returns test log with change points marked as horizontal lines"""
        column_groups, tables = self.__format_log()
        lines = tables.split("\n")
        col_width_groups, time_indexes = self.__column_widths(lines)

        for group_index, column_group in enumerate(column_groups):
            col_widths = col_width_groups[group_index] \
                if group_index < len(col_width_groups) else []
            time_index = time_indexes[group_index] if group_index < len(time_indexes) else 0
            columns = list(
                OrderedDict.fromkeys(["time", *self.__series.attributes, *column_group])
            )
            separators = []
            indexes = []
            for cp in self.__change_points:
                index = cp.index
                separator = ""
                info = ""
                for col_index, col_name in enumerate(columns):
                    col_width = col_widths[col_index] if col_index < len(col_widths) else 0
                    change = [c for c in cp.changes if c.metric == col_name]
                    if change:
                        change = change[0]
                        change_percent = change.forward_change_percent()
                        separator += "·" * col_width + "  "
                        info += f"{change_percent:+.1f}%".rjust(col_width) + "  "
                    else:
                        separator += " " * (col_width + 2)
                        info += " " * (col_width + 2)
                if info.strip() != "":
                    indexes.append(index)
                    separators.append(f"{separator}\n{info}\n{separator}")
            if len(indexes) > 0:
                lines = lines[:2+time_index] + \
                    insert_multiple(lines[2+time_index:], separators, indexes)
                self.__increment_time_indexes_after(time_indexes, group_index)
        return "\n".join(lines)


    def __format_json(self, test_name: str) -> str:
        """Format change points as JSON"""
        return json.dumps({test_name: [cpg.to_json(rounded=True) for cpg in self.__change_points]})


    def __format_regressions_only(self, test_name: str) -> str:
        """Format regressions only"""
        output = []
        for cpg in self.__change_points:
            regressions = []
            for cp in cpg.changes:
                metric = self.__series.metrics[cp.metric]
                if metric.direction * cp.forward_change_percent() < 0:
                    regressions.append(
                        (
                            cp.metric,
                            cp.stats.mean_1,
                            cp.stats.mean_2,
                            cp.stats.forward_rel_change() * 100.0,
                        )
                    )

            if regressions:
                output.append(format_timestamp(cpg.time, False))
                output.extend(
                    [
                        f"    {args[0]:16}:\t{args[1]:#8.3g}\
\t--> {args[2]:#8.3g}\t({args[3]:+6.1f}%)" \
                        for args in regressions
                    ]
                )

        if output:
            return f"Regressions in {test_name}:" + "\n" + "\n".join(output)

        return f"No regressions found in {test_name}."
