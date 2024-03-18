"""
Module to run orion in daemon mode
"""
import shutil
import os

from fastapi import FastAPI, File, UploadFile
from pkg.logrus import SingletonLogger

from . import runTest

app = FastAPI()
logger_instance = SingletonLogger(debug=False).logger


@app.post("/daemon")
async def daemon(file: UploadFile = File(...)):
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
    result = runTest.run(new_file_name, "output.csv", True, "json")
    try:
        os.remove(new_file_name)
    except OSError as e:
        logger_instance.error("error %s", e.strerror)
    return result
