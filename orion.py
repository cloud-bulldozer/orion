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
@click.option("--uuid", default="", help="UUID to use as base for comparisons")
@click.option("--baseline", default="", help="Baseline UUID(s) to to compare against uuid")
def cmd_analysis(**kwargs):
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
    level = logging.DEBUG if kwargs['debug'] else logging.INFO
    logger_instance = SingletonLogger(debug=level).logger
    logger_instance.info("🏹 Starting Orion in command-line mode")
    output = run(**kwargs)
    for test_name, result_table in output.items():
        print(test_name)
        print("="*len(test_name))
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
    logger_instance = SingletonLogger(debug=level).logger
    logger_instance.info("🏹 Starting Orion in Daemon mode")
    uvicorn.run("pkg.daemon:app", port=8000)


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        cli.main(["--help"])
    else:
        cli.add_command(cmd_analysis)
        cli.add_command(rundaemon)
        cli()
