# pylint: disable = R0903, E0211
"""
Generate datasource factory
"""
from datetime import datetime
from typing import Any, Dict
from fmatch.matcher import Matcher
from fmatch.splunk_matcher import SplunkMatcher
from fmatch.logrus import SingletonLogger
from .perfscale import PerfscaleDatasource
from .telco import TelcoDatasource


class DatasourceFactory:
    """Datasource Factory implementation
    """
    def instantiate_datasource(self, datasource:str,
                                    test: Dict[str, Any],
                                    options: Dict[str, Any],
                                    start_timestamp: datetime):
        """Sets the datasource type

        Args:
            datasource (str): _description_
            test (Dict[str, Any]): _description_
            options (Dict[str, Any]): _description_
            start_timestamp (datetime): _description_

        Returns:
            Datasource: _description_
        """
        logger_instance = SingletonLogger.getLogger("Orion")
        if datasource["type"]=="perfscale":
            match = Matcher(
                index=test["index"],
                level=logger_instance.level,
                ES_URL=datasource["ES_SERVER"],
                verify_certs=False,
            )
            return PerfscaleDatasource(test, match, options, start_timestamp), match
        if datasource["type"]=="telco":
            match = SplunkMatcher(
                host= datasource.get("host"),
                port= datasource.get("port"),
                username= datasource.get("username"),
                password= datasource.get("password"),
                indice=datasource.get("indice")
            )
            return TelcoDatasource(test, match, options, start_timestamp), match
        return None, None
        