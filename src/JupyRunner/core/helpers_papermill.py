

# pylint: disable=protected-access,missing-function-docstring,too-few-public-methods,missing-class-docstring

import ast
import itertools
import os
import unittest
import inspect
import sys
import datetime
import json
import glob
import hashlib
import papermill as pm


# path was needed for local testing
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
# print(parent_dir)
sys.path.insert(0, parent_dir)
# print(sys.path)




from JupyRunner.core.helpers import make_zulustr, parse_zulutime, get_utcnow, log
from JupyRunner.core import schema
log = log




def get_info(p):
    tlast_change = os.path.getmtime(p)
    dtlast_change = make_zulustr(datetime.datetime.fromtimestamp(tlast_change))
    with open(p,'rb') as f:
        info = {
        'script_name': os.path.basename(p),
        'script_version': hashlib.md5(f.read()).hexdigest() + '_' + dtlast_change
        }

    try:
        info['params'] = pm.inspect_notebook(p)
    except Exception as err:
        log.error('ERROR while inspecting notebook: ' + info['script_name'])
        log.error(err)
        info['params'] = {'ERROR': str(err)}
    return info


def get_params(dc, as_dict=True, to_skip = 'dbserver_uri script_id experiment_id analysis_id'):
    """get the parameters as basic param dict to use for starting a script

    Args:
        dc (dict): the papermill type parameter dict
        scriptype (str, optional): . Defaults to 'experiments'.

    Returns:
        dict: param dict to use for starting a script
    """

    if 'script_name' in dc and 'params' in dc and 'script_version' in dc:
        dc = dc['params']

    if isinstance(to_skip, str):
        to_skip = to_skip.split()
        
    if as_dict:
        if len(dc) == 1 and 'ERROR' in dc:
            return dc
        
        
        ret = {}
        for k, v in dc.items():
            try:
                vv = ast.literal_eval(v['default'])
            except Exception as err:
                vv = {
                    'info': 'evaluating the input paramater string failed!',
                    'variable_name': v['name'],
                    'res':'ERROR', 
                    'cause': 'ast.literal_eval failed!',
                    'eval_str': v['default'],
                    'hint': 'The string or node provided for parameters must be self contained and only consist of the following Python literal structures: strings, bytes, numbers, tuples, lists, dicts, sets, booleans, and None'
                }
            ret[v['name']] = vv
        return ret

    def parse_default(s):
        try:
            return json.dumps(ast.literal_eval(s))
        except Exception as err:
            return json.dumps(None)

    def get_param(v, is_last):
        vv = parse_default(v['default'].replace("'", '"'))
        s = '   "{}": {}'.format(v['name'],  vv)
        if not is_last:
            s += ','
        if not is_last:
            s += '\n'
        return s
    
    txt = '{\n'
    for i, v in enumerate(dc.values()):
        is_last = i+1 == len(dc)
        if not v['name'] in to_skip:
            txt += get_param(v, is_last)
    txt = txt.rstrip('\n')
    txt = txt.rstrip(',')
    txt += '\n}'
    r_json = txt
    
    return r_json



def get_info(p):
    """for a single ipynb file get the papermill params, script_version, and script_name

    Args:
        p (str): path of the ipynb file to check

    Returns:
        dict: params (see pm.inspect_notebook for info), script_version, and script_name
    """
    tlast_change = os.path.getmtime(p)
    dtlast_change = make_zulustr(datetime.datetime.fromtimestamp(tlast_change))
    with open(p,'rb') as f:
        info = {
        'script_name': os.path.basename(p),
        'script_version': hashlib.md5(f.read()).hexdigest() + '_' + dtlast_change
        }

    try:
        info['params'] = pm.inspect_notebook(p)
    except Exception as err:
        log.error('ERROR while inspecting notebook: ' + info['script_name'])
        log.error(err)
        info['params'] = {'ERROR': str(err)}
    return info
        
        
def get_repo_scripts(repo_dir, ext='.ipynb'):
    """crawl a directory with ipynb scripts in and get the papermill info for each of them

    Args:
        repo_dir (str): the path to the directory to crawl

    Returns:
        dict of dicts: pathname for each file as key and get_info
    """
    #config =  MeerTest.core.config.get_config()
    result = [y for x in os.walk(repo_dir) for y in glob.glob(os.path.join(x[0], '*' + ext))]
    return {p:get_info(p) for p in result if not p.endswith('-checkpoint.ipynb')}


