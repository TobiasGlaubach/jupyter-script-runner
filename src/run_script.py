"""
Script runner for JupyRunner project.

This script provides functionality to run scripts stored in the database. 
It retrieves the script information, configures the database connection,
and delegates the actual script execution to the `scriptrunner.run_script` function.

The script also supports command-line arguments for specifying the script ID 
to run and controlling the logging verbosity level.
"""

import os
import argparse
import yaml

from JupyRunner.core import schema, api_interface, helpers, scriptrunner

log = helpers.log



def run(script_id):
    tstart = helpers.get_utcnow()

    PID = os.getpid()
    

    with open('config.yaml', 'r') as fp:
        config = yaml.safe_load(fp)

    helpers.set_loglevel(config)

    log.info(f'run_script with {PID=} and {script_id=} is starting')
    
    scriptrunner.setup(config)
    api_interface.setup(config)
    
    scriptrunner.start(config)
    api_interface.start(config)

    script = scriptrunner.run_script(script_id)
    scriptrunner.init_follow_up_script(script)


    tend = helpers.get_utcnow()
    td = tend - tstart

    log.info(f'run_script with {PID=} and {script_id=} has finished after: {td.days} days, {td.hours:02d}:{td.minutes:02d}:{td.seconds:02d}"')


if __name__ == "__main__":


    parser = argparse.ArgumentParser(description=__doc__)

    # parser.add_argument('--local_debug', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('--id', help='the id of the script to run')

    parser.add_argument('-vv', '--very-verbose', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('-v', '--verbose', help=argparse.SUPPRESS, action='store_true')

    args = parser.parse_args()

    if args.very_verbose:
        log.setLevel("TRACE")
    elif args.verbose:
        log.setLevel("DEBUG")
    else:
        log.setLevel("INFO")


    run(args.id)

