
#!/usr/bin/python3
""" 
generates the default file pathes etc
"""


# import datetime
import os

import re
import dateutil.parser, datetime, time

from pathlib import Path

import tempfile
from pathlib import Path

from JupyRunner.core import helpers, helpers_papermill

log = helpers.log

default_dir_data = ''
default_dir_repo = ''
home = str(Path.home())
timeformat_str = '%Y%m%d_%H%M'


################################################################################################
################################################################################################
################################################################################################

# from https://stackoverflow.com/questions/9532499/check-whether-a-path-is-valid-in-python-without-creating-a-file-at-the-paths-ta

import errno, os, sys

# Sadly, Python fails to provide the following magic number for us.
ERROR_INVALID_NAME = 123
'''
Windows-specific error code indicating an invalid pathname.

See Also
----------
https://docs.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-
    Official listing of all such codes.
'''

def is_pathname_valid(pathname: str) -> bool:
    '''
    `True` if the passed pathname is a valid pathname for the current OS;
    `False` otherwise.
    '''
    # If this pathname is either not a string or is but is empty, this pathname
    # is invalid.
    try:
        if not isinstance(pathname, str) or not pathname:
            return False

        # Strip this pathname's Windows-specific drive specifier (e.g., `C:\`)
        # if any. Since Windows prohibits path components from containing `:`
        # characters, failing to strip this `:`-suffixed prefix would
        # erroneously invalidate all valid absolute Windows pathnames.
        _, pathname = os.path.splitdrive(pathname)

        # Directory guaranteed to exist. If the current OS is Windows, this is
        # the drive to which Windows was installed (e.g., the "%HOMEDRIVE%"
        # environment variable); else, the typical root directory.
        root_dirname = os.environ.get('HOMEDRIVE', 'C:') \
            if sys.platform == 'win32' else os.path.sep
        assert os.path.isdir(root_dirname)   # ...Murphy and her ironclad Law

        # Append a path separator to this directory if needed.
        root_dirname = root_dirname.rstrip(os.path.sep) + os.path.sep

        # Test whether each path component split from this pathname is valid or
        # not, ignoring non-existent and non-readable path components.
        for pathname_part in pathname.split(os.path.sep):
            try:
                os.lstat(root_dirname + pathname_part)
            # If an OS-specific exception is raised, its error code
            # indicates whether this pathname is valid or not. Unless this
            # is the case, this exception implies an ignorable kernel or
            # filesystem complaint (e.g., path not found or inaccessible).
            #
            # Only the following exceptions indicate invalid pathnames:
            #
            # * Instances of the Windows-specific "WindowsError" class
            #   defining the "winerror" attribute whose value is
            #   "ERROR_INVALID_NAME". Under Windows, "winerror" is more
            #   fine-grained and hence useful than the generic "errno"
            #   attribute. When a too-long pathname is passed, for example,
            #   "errno" is "ENOENT" (i.e., no such file or directory) rather
            #   than "ENAMETOOLONG" (i.e., file name too long).
            # * Instances of the cross-platform "OSError" class defining the
            #   generic "errno" attribute whose value is either:
            #   * Under most POSIX-compatible OSes, "ENAMETOOLONG".
            #   * Under some edge-case OSes (e.g., SunOS, *BSD), "ERANGE".
            except OSError as exc:
                if hasattr(exc, 'winerror'):
                    if exc.winerror == ERROR_INVALID_NAME:
                        return False
                elif exc.errno in {errno.ENAMETOOLONG, errno.ERANGE}:
                    return False
    # If a "TypeError" exception was raised, it almost certainly has the
    # error message "embedded NUL character" indicating an invalid pathname.
    except TypeError as exc:
        return False
    # If no exception was raised, all path components and hence this
    # pathname itself are valid. (Praise be to the curmudgeonly python.)
    else:
        return True
    # If any other exception was raised, this is an unrelated fatal issue
    # (e.g., a bug). Permit this exception to unwind the call stack.
    #
    # Did we mention this should be shipped with Python already?



################################################################################################
################################################################################################
################################################################################################




def setup(config):
    global default_dir_repo, default_dir_data
    default_dir_data = config['pathes']['default_dir_meas']
    default_dir_repo = config['pathes']['default_dir_repo']


    # _log.info(f'         expanduser: "{os.expanduser("~")}"')
    log.info(f'              $HOME: "{home}"')
    log.info(f'                CWD: "{os.getcwd()}"')
    log.info(f'    Writing data to: "{default_dir_data}" can_write={os.access(default_dir_data, os.W_OK)}')
    log.info(f'    Writing repo to: "{default_dir_repo}" can_write={os.access(default_dir_repo, os.W_OK)}')


def start(config):
        
    mkdir(default_dir_data, verbose=True)
    mkdir(default_dir_repo, verbose=True)



def _get_absolute_paths_by_extension(directory, extension):

    file_paths = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(extension):
                file_path = os.path.join(root, file)
                file_paths.append(file_path)
    return file_paths 


def get_scripts_in_repo(extension='.ipynb'):
    return list(helpers_papermill.get_repo_scripts(default_dir_repo, extension).keys())

    # return _get_absolute_paths_by_extension(default_dir_repo, extension)

def get_id_data_from_path(s):
    """helper function to get id from a path

        e.G.:
            '.../20220613_0616_IDD_1_...' 
                -> 1 (int)
    """
    r = re.findall(r"IDD_[0-9]+", s)    
    return int(r[-1][4:]) if r else None
    

def mkdir(pth, raise_ex=False, verbose=False):
    try:
        if not os.path.exists(pth):
            if verbose:
                log.info('Creating dir because it does not exist: ' + pth)
            os.makedirs(pth, exist_ok=True)
            path = Path(pth)
            path.mkdir(parents=True, exist_ok=True)
            return str(path).replace('\\', '/').replace('//', '/')

    except Exception as err:
        log.error(err)
        if raise_ex:
            raise
    return None

def join(*parts):
    return os.path.join(*parts).replace('\\', '/').replace('//', '/')



def get_time_from_pth(p):
    return datetime.datetime.strptime(p, timeformat_str).replace(tzinfo=datetime.timezone.utc)

def mk_out_dir(dir, is_exp):
    _mkdir = lambda p: mkdir(p, raise_ex=True)

    pths = []
    pths.append(mkdir(dir))
    if is_exp:
        pths.append(_mkdir(join(dir, 'data')))
    return pths


def get_script_save_filepath(dtime:datetime.datetime, experiment_id:int, device_id:str, experiment_name:str, make_dir=False):
    fulldir = get_script_save_dir(dtime, experiment_id, device_id, experiment_name, make_dir=make_dir)
    fname = fulldir.split('/')[-1] + '.ipynb'
    fullpath = join(fulldir, fname)
    return fullpath


def get_script_save_dir(dtime:datetime.datetime, experiment_id:int, device_id:str, experiment_name:str, tag:str=None, make_dir=False):
    time = dtime.strftime(timeformat_str)
    tag = ('_' + tag.strip().replace(' ', '')) if tag else ''
    subdir = f"{device_id}/{time}_{experiment_id}_{device_id}_s_{experiment_name}{tag}"
    fulldir = join(default_dir_data, subdir)
    if make_dir:
        mkdir(fulldir, raise_ex=True)
    return fulldir


