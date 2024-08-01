"""
Module to run orion in daemon mode
"""

import json
import os
from typing import Any
from fastapi import FastAPI, HTTPException
import pkg_resources
from fmatch.logrus import SingletonLogger
from pkg.config import load_config
import pkg.constants as cnsts

from . import runTest

app = FastAPI()
logger_instance = SingletonLogger.getLogger("Orion")


@app.get("/daemon/changepoint")
async def daemon_changepoint( # pylint: disable = R0913
    version: str = "4.17",
    uuid: str = "",
    baseline: str = "",
    filter_changepoints : str = "",
    test_name : str = "small-scale-cluster-density",
    lookback: str = None,
    convert_tinyurl: str = "False",
) -> (dict[str, str] | dict[Any, Any]):
    """starts listening on port 8000 on url /daemon

    Args:
        file (UploadFile, optional): config file for the test. Defaults to File(...).

    Returns:
        json: json object of the changepoints and metrics
    """
    parameters = {"version": version}
    config_file_name=f"{test_name}.yml"
    config_path = pkg_resources.resource_filename("configs", config_file_name)
    option_arguments = {
        "config": config_file_name,
        "save_data_path": "output.csv",
        "hunter_analyze": True,
        "anomaly_detection": False,
        "output_format": cnsts.JSON,
        "uuid": uuid,
        "lookback":lookback,
        "baseline": baseline,
        "configMap": load_config(config_path, parameters),
        "convert_tinyurl": convert_tinyurl.lower() not in "false",
    }
    filter_changepoints = (
        True if filter_changepoints == "true" else False  # pylint: disable = R1719
    )
    result = runTest.run(**option_arguments)
    result = {k:json.loads(v) for k,v in result.items()}
    if result is None:
        return {"Error":"No UUID with given metadata"}
    if filter_changepoints:
        for key, value in result.items():
            result[key] = list(filter(lambda x: x.get("is_changepoint", False), value))
    return result


@app.get("/daemon/options")
async def get_options() -> Any:
    """Lists all the tests available in daemon mode

    Raises:
        HTTPException: Config not found
        HTTPException: cannot find files for config

    Returns:
        config: list of files
    """
    config_dir = pkg_resources.resource_filename("configs", "")
    if not os.path.isdir(config_dir):
        raise HTTPException(status_code=404, detail="Config directory not found")
    try:
        files = [
            os.path.splitext(file)[0]
            for file in os.listdir(config_dir)
            if file != "__init__.py"
            and not file.endswith(".pyc")
            and file != "__pycache__"
        ]
        return {"options": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/daemon/anomaly")
async def daemon_anomaly( # pylint: disable = R0913, R0914
    version: str = "4.17",
    uuid: str = "",
    baseline: str = "",
    filter_points: str = "",
    test_name: str = "small-scale-cluster-density",
    anomaly_window: int = 5,
    min_anomaly_percent: int = 10,
    lookback: str = None,
    convert_tinyurl: str = "False",
):
    """starts listening on port 8000 on url /daemon

    Args:
        file (UploadFile, optional): config file for the test. Defaults to File(...).

    Returns:
        json: json object of the changepoints and metrics
    """
    parameters = {"version": version}
    config_file_name=test_name+".yml"
    config_path = pkg_resources.resource_filename("configs", config_file_name)
    option_arguments = {
        "config": config_file_name,
        "save_data_path": "output.csv",
        "hunter_analyze": False,
        "anomaly_detection": True,
        "output_format": cnsts.JSON,
        "uuid": uuid,
        "lookback":lookback,
        "baseline": baseline,
        "configMap": load_config(config_path, parameters),
        "anomaly_window": int(anomaly_window),
        "min_anomaly_percent":int(min_anomaly_percent),
        "convert_tinyurl": convert_tinyurl.lower() not in "false",
    }
    filter_points = (
        True if filter_points == "true" else False  # pylint: disable = R1719
    )
    result = runTest.run(**option_arguments)
    result = {k:json.loads(v) for k,v in result.items()}
    if result is None:
        return {"Error":"No UUID with given metadata"}
    if filter_points:
        for key, value in result.items():
            result[key] = list(filter(lambda x: x.get("is_changepoint", False), value))
    return result
