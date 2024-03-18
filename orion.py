"""
This is the cli file for orion, tool to detect regressions using hunter
"""

# pylint: disable = import-error
import logging
import sys
import click
import uvicorn
from pkg.logrus import SingletonLogger
from pkg.runTest import run

logger_instance = SingletonLogger(debug=False).logger


@click.group()
def cli(max_content_width=120):  # pylint: disable=unused-argument
    """
    cli function to group commands
    """


# pylint: disable=too-many-locals
@cli.command(name="cmd-mode")
@click.option("--config", default="config.yaml", help="Path to the configuration file")
@click.option(
    "--output-path", default="output.csv", help="Path to save the output csv file"
)
@click.option("--debug", default=False, is_flag=True, help="log level")
@click.option("--hunter-analyze", default=True, is_flag=True, help="run hunter analyze")
@click.option(
    "-o",
    "--output-format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Choose output format (json or text)",
)
def cmd_analysis(config, debug, output_path, hunter_analyze, output_format):
    """
    Orion runs on command line mode, and helps in detecting regressions

    \b
    Args:
        uuid (str): gather metrics based on uuid
        baseline (str): baseline uuid to compare against uuid (uuid must be set when using baseline)
        config (str): path to the config file
        debug (bool): lets you log debug mode
        output (str): path to the output csv file
        hunter_analyze (bool): turns on hunter analysis of gathered uuid(s) data
    """
    level = logging.DEBUG if debug else logging.INFO
    logger_instance.setLevel(level)
    logger_instance.info("🏹 Starting Orion in command-line mode")
    output = run(config, output_path, hunter_analyze, output_format)
    for test_name, result_table in output.items():
        print(test_name)
        print("-"*len(test_name))
        print(result_table)

        csv_name = kwargs["output"].split(".")[0]+"-"+test['name']+".csv"
        match.save_results(
            merged_df, csv_file_path=csv_name
        )

@cli.command(name="daemon-mode")
@click.option("--debug", default=False, is_flag=True, help="log level")
def rundaemon(debug):
    """
    Orion runs on daemon mode on port 8000
    \b
    """
    level = logging.DEBUG if debug else logging.INFO
    logger_instance.setLevel(level)
    logger_instance.info("🏹 Starting Orion in Daemon mode")
    uvicorn.run("pkg.daemon:app", port=8000)


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        cli.main(["--help"])
    else:
        cli.add_command(cmd_analysis)
        cli.add_command(rundaemon)
        cli()
