"""
Module to run orion in daemon mode
"""

import logging
import shutil
import os

from fastapi import FastAPI, File, UploadFile
from pkg.logrus import SingletonLogger

from . import runTest

app = FastAPI()
logger_instance = SingletonLogger(debug=logging.INFO).logger


@app.post("/daemon")
async def daemon(
    file: UploadFile = File(...),
    uuid: str = "",
    baseline: str = "",
    filter_changepoints="",
):
    """starts listening on port 8000 on url /daemon

    Args:
        file (UploadFile, optional): config file for the test. Defaults to File(...).

    Returns:
        json: json object of the changepoints and metrics
    """
    file_name, file_extension = os.path.splitext(file.filename)
    new_file_name = f"{file_name}_copy{file_extension}"
    with open(new_file_name, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    argDict = {
        "config": new_file_name,
        "output_path": "output.csv",
        "hunter_analyze": True,
        "output_format": "json",
        "uuid": uuid,
        "baseline": baseline,
    }
    filter_changepoints = (
        True if filter_changepoints == "true" else False # pylint: disable = R1719
    )
    result = runTest.run(**argDict)
    if filter_changepoints:
        for key, value in result.items():
            result[key] = list(filter(lambda x: x.get("is_changepoint", False), value))
    try:
        os.remove(new_file_name)
    except OSError as e:
        logger_instance.error("error %s", e.strerror)
    return result
