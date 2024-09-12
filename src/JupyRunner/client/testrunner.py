import copy
from dataclasses import dataclass, field
import datetime
import traceback
from typing import Union, Dict, Any, Callable, List, Tuple
import functools
import ast
import re
import time, random, os


import pydocmaker as pyd


if __name__ == '__main__':
    import os, inspect, sys
    current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    sys.path.insert(0, parent_dir)
    print(parent_dir)

from JupyRunner.core import helpers

ALLOW_EVAL = os.environ.get('ALLOW_EVAL', True)

import sys
import io
# from contextlib import contextmanager

# @contextmanager
class LogStdOut:
    def __init__(self):
        self.buffer = io.StringIO()
        self.original_stdout = None

    def write(self, data):
        self.buffer.write(data)

    def __enter__(self):
        
        self.original_stdout = sys.stdout
        sys.stdout = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.original_stdout:
            sys.stdout = self.original_stdout
        return False  # Don't suppress exceptions
    
    def get(self):
        assert not self.original_stdout is None, 'Logger was not used yet!'
        return self.buffer.getvalue()


@dataclass(frozen=True)
class ActionResult():
    call:str = '',
    error_msg:str = ''
    call_result:Any = None
    success:bool = None
    checks_done:str=''
    stdout:str=''

    description:str = ''
    parent:Any = None

    def get(self, key:str, default=None):
        return getattr(self, key, default)

    
    def get_succes_info(self) -> str:
        return 'OK' if self.success else (self.error_msg.split(' ')[0] if self.error_msg else 'ERROR')
    
    def get_upload_files(self) -> Dict[str, bytes]:
        
        files = self.call_result.get('files', {}) if isinstance(self.call_result, dict) else {}

        for k in files:
            files[k] = files[k]
            
            if 'dataframe' in str(type(files[k])).lower() and hasattr(files[k], 'to_csv'):
                files[k] = files[k].to_csv()
            if 'array' in str(type(files[k])).lower():
                if 'np' not in locals():
                    import numpy as np
                output = io.StringIO()
                np.savetxt(output, files[k], delimiter=",")
                files[k] = output.getvalue()

            if hasattr(files[k], 'read'):
                files[k] = files[k].read()

            if isinstance(files[k], str):
                files[k] = files[k].encode()

            assert isinstance(files[k], bytes), 'ERROR: Only files of type byte are possible to upload!'
    
        return files
    
    def get_result_doc(self) -> pyd.DocBuilder:
        if isinstance(self.call_result, dict) and isinstance(self.call_result.get('doc', None), pyd.DocBuilder):
            return self.call_result.get('doc')
        elif isinstance(self.call_result, pyd.DocBuilder):
            return self.call_result
        else:
            return pyd.DocBuilder()

    def get_stdout(self, remove_colors=False):
        s = self.get('stdout', '')
        if remove_colors:
            s = re.sub(r"(?:\033\[95m|\033\[94m|\033\[92m|\033\[93m|\033\[91m|\033\[0m|\033\[1m|\033\[4m)", "", s)
        return f'{s}'
            

    def to_doc(self, no_call_info=False, hide_empty=False):
        
        txt = ''
        doc = pyd.DocBuilder()

        parts = []

        txt += (self.description + '\n\n' if self.description else '')

        for k in 'call error_msg checks_done success stdout'.split():
            if k == 'call' and no_call_info:
                continue
            v = helpers.limit_len(f'{getattr(self, k)}', 300)
            if k == 'success' or v or not hide_empty:
                txt += f'- **{k}**:  `{v}`\n'

        if isinstance(self.call_result, pyd.DocBuilder):
            txt += f'\n\n#### call_result:'
            parts += self.call_result

        handled = False
        if isinstance(self.call_result, dict):
            if isinstance(self.call_result.get('doc', None), pyd.DocBuilder):
                doc.add_md(txt)
                txt = f'\n\n#### call_result (doc):'
                parts += self.call_result.get('doc')
                handled = True

            if isinstance(self.call_result.get('files', None), dict):
                fun = lambda filename, file: f'   - `{filename}`: {type(file)=} length: {len(file) if hasattr(file, "__len__") else "unknown"}'
                txt += f'- **call_result (files to upload)**: \n'
                txt += '\n'.join([fun(k, v) for k, v in self.call_result.get('files', {}).items()])
                handled = True
        
        if not handled:
            
            if hide_empty and not self.call_result:
                pass
            else:
                txt += f'- **call_result**: '
                if self.call_result is None:
                    txt += 'null'
                elif isinstance(self.call_result, str):
                    txt += helpers.limit_len(self.call_result, 500)
                elif hasattr(self.call_result, '__len__'):
                    call_result = self.call_result
                    txt += f'object of {type(call_result)=} with length {len(call_result)=}... content hidden for brevity'
                else:
                    call_result = self.call_result
                    txt += f'object of {type(call_result)=}'
            
        doc.add_md(txt)
        doc.data += parts

        return doc
    



def _parse_sleep_command(command):
  """Parses a sleep command and executes the corresponding action.

  Args:
    command: The sleep command string.

  Raises:
    ValueError: If the command is invalid.
  """

  match = re.match(r"^(sleep|wait) (\d+)(s|m|h)$", command.strip())
  if not match:
    raise ValueError("Invalid sleep command: {}".format(command))

  action, duration, unit = match.groups()
  duration = int(duration)

  if unit == "s":
    sleep_time = duration
  elif unit == "m":
    sleep_time = duration * 60
  elif unit == "h":
    sleep_time = duration * 60 * 60
  elif unit == "d":
    sleep_time = duration * 60 * 60 * 24
  else:
    raise ValueError("Invalid unit: {}".format(unit))

  return sleep_time



@dataclass()
class CallAction():
    fun:str
    args:list = field(default_factory=lambda: [])
    kwargs:dict = field(default_factory=lambda: {})
    result_handler:str = 'keep_local'
    
    kind:str='call'

    has_run:bool = False
    result:ActionResult = None
    
    description:str = ''

    def _run(self, gl, **kw):
        if gl is None:
            gl = (globals(), locals())

        fun, args, kwargs = copy.deepcopy(self.fun), self.args, self.kwargs
        
        kwargs = {**kwargs, **kw}

        if isinstance(fun, str):
            fun  = fun.strip()

            if (fun.endswith(')') and '(' in fun) or (fun.startswith('lambda') and ':' in fun):
                
                if not args and not kwargs and ALLOW_EVAL:
                    f = eval(fun, *gl)
                    return f() if hasattr(f, '__call__') else f
                else:
                    assert not args, 'can not call functions to literally evaluate with args. Use kwargs instead!'
                    try:
                        f = eval(fun, {}, kwargs)
                        return f() if hasattr(f, '__call__') else f
                    except (SyntaxError, ValueError) as e:
                        raise

            f = None
            parts = fun.split('.') # can be methods or similar!
            while parts:
                part = parts.pop(0)
                if f is None:
                    g, l = gl
                    f = g[part] if part in g else l[part]
                else:
                    f = getattr(f, part)
        else:
            f = fun

        assert hasattr(f, '__call__'), f'{fun=} (which evaluated to {f=} is not a callable!'
        return f(*args, **kwargs)
        
    def run(self, log_stdout=True, gl=None, **kwargs):
        if log_stdout:
            with LogStdOut() as logger:
                ret = self._run(gl, **kwargs)
                stdout = logger.get()
        else:
            ret = self._run(gl, **kwargs)
        

        call = f'{self.fun}'
        parts = []
        if self.args:
            parts += [a.__repr__() for a in self.args]
        if self.kwargs:
            parts += [f'"{key}"{v.__repr__()}' for key, v in self.kwargs]
        if parts:
            call += f'({", ".join(parts)})'
        dc = {'call': call, 'error_msg': '', 'stdout': stdout, 'call_result': ret, 'success': True}
        self.result = ActionResult(parent=self, **dc)
        self.has_run = True
        return self.result
    
    

@dataclass()
class CallAndCheckAction():
    fun:str
    expected:str
    abort_on_fail:bool = False
    reduction_by:str = 'all'
    fail_msg:str = None
    result_handler:str = 'keep_local'
    args:list = field(default_factory=lambda: [])
    kwargs:dict = field(default_factory=lambda: {})

    has_run:bool = False
    result:ActionResult = None

    description:str = ''

    kind:str='check'

    def _call(self, gl, **kwargs):
        return CallAction(fun = self.fun, args=self.args, kwargs={**self.kwargs, **kwargs})._run(gl)


    def _check(self, actual, expected, abort_on_fail, reduction_by, fail_msg):

        # assert isinstance(what, str), f'ERROR: "what" must be of type string but was {type(what)=}, {what=}'

        assert reduction_by is None or isinstance(reduction_by, str), f'ERROR: "reduction_by" must be of type string but was {type(reduction_by)=}, {reduction_by=}'
        assert fail_msg is None or isinstance(fail_msg, str), f'ERROR: "fail_msg" must be of type string but was {type(fail_msg)=}, {fail_msg=}'

        if not expected:
            expected = 'True'

        if isinstance(expected, (list, tuple)) and len(expected) == 2: #  range
            low, high = min(expected), max(expected)
            expected = f'{low} <= act <= {high}'
        
        if isinstance(expected, (int, float, complex)):
            expected = str(expected)

        assert expected and isinstance(expected, str), f'ERROR: "expected" must be of type string and contain a string, but was {type(expected)=}, {expected=}'

        if expected.lower() == 'true':
            expected = 'True if act else False'

        if expected.lower() == 'false':
            expected = 'True if not act else False'

        if expected.lower() == 'success' or expected.lower() == 'ok':
            expected = 'act.get("success", act.get("ok")) in ["ok", "success", True, 1]'
    
        if not isinstance(actual, (str, dict)) and hasattr(actual, '__len__') and reduction_by:
            if not 'np' in globals():
                import numpy as np
            assert isinstance(reduction_by, str), f'ERROR: "reduction_by" must be of type string but was {type(reduction_by)=}, {reduction_by=}'
            reduction_fun = getattr(np, reduction_by)
            act = reduction_fun(actual)
        else:
            act = actual

        if not [k for k in '< > = in is'.split() if k in expected]:
            expected = '==' + expected

        tester = expected.strip()
        if not 'act' in tester:
            tester = 'act ' + tester

        aa = f'{act=} (which was reduced by "{reduction_by}")' if act != actual else f'{act=}'
        chk_msg = f'Check for "{tester}" with {aa}'

        if not fail_msg:
            # ee = f'"{expected}" (which evaluated to "{e}")' if e != expected else f'"{e}"'
            func = self.fun
            fail_msg = chk_msg + f' failed (from {func=})'
        
        try:
            ret = eval(tester, {}, dict(act=act))
        except (SyntaxError, ValueError, TypeError) as error:
            helpers.log.error(f'eval with {tester=} and {act=} for caller {self.fun=} raised an error {error=}')
            raise
            
        if abort_on_fail:
            assert ret, 'FAIL: ' + fail_msg
            return '', chk_msg
        else:
            return asserte(ret, 'FAIL: ' + fail_msg), chk_msg


    def _run(self, gl, **kwargs):
        
        expected, abort_on_fail, reduction_by, fail_msg, result_handler = self.expected, self.abort_on_fail, self.reduction_by, self.fail_msg, self.result_handler
        
        result = self._call(gl=gl, **kwargs)
        
        if expected is None:
            expected = ''

        err = ''
        checks = ''

        if isinstance(result, dict) and isinstance(expected, dict):
            keys = list(expected.keys())
        else:
            err, checks = self._check(actual=result, expected=expected, abort_on_fail=abort_on_fail, reduction_by=reduction_by, fail_msg=fail_msg)
            keys = []
        
        for k in keys:
            res = result.get(k, result) if isinstance(result, dict) else result
            ex = expected.get(k, expected) if isinstance(expected, dict) else expected
            aof = abort_on_fail.get(k, abort_on_fail) if isinstance(abort_on_fail, dict) else abort_on_fail
            rb = reduction_by.get(k, reduction_by) if isinstance(reduction_by, dict) else reduction_by
            fm = fail_msg.get(k, fail_msg) if isinstance(fail_msg, dict) else fail_msg
            e, c = self._check(actual=res, expected=ex, abort_on_fail=aof, reduction_by=rb, fail_msg=fm)
            err += e + '\n'
            checks += c + '\n'

        return {'error_msg': err, 'checks_done': checks, 'call_result': result, 'success': False if err else True}

    def run(self, gl=None, log_stdout=True, **kwargs):
        if log_stdout:
            with LogStdOut() as logger:
                ret = self._run(gl, **kwargs)
                ret['stdout'] = logger.get()
        else:
            ret = self._run(gl, **kwargs)
        
        
        call = f'{self.fun}'
        parts = []
        if self.args:
            parts += [a.__repr__() for a in self.args]
        if self.kwargs:
            parts += [f'"{key}"{v.__repr__()}' for key, v in self.kwargs]
        if parts:
            call += f'({", ".join(parts)})'
        
        ret['call'] = call
        self.result = ActionResult(parent=self, **ret)
        self.has_run = True
        return self.result



def dict2action(dc):
    if isinstance(dc, str) and (dc.strip().startswith('wait') or dc.strip().startswith('sleep')):
        return CallAction(**{'fun':'time.sleep', 'args': [_parse_sleep_command(dc)]})
    elif isinstance(dc, str):
        return CallAction(**{'fun': dc})
    elif dc.get('kind') == "check" or dc.get('fun') and dc.get('expected'):
        # most likely a check object
        return CallAndCheckAction(**dc)
    elif dc.get('kind') == "call" or dc.get('fun'):
        return CallAction(**dc)
    elif dc.get('kind') == "wait" or 'duration_s' in dc:
        return CallAction(**{'fun':'time.sleep', 'args': [dc.get('duration_s')]})
    else:
        raise KeyError(f'unknown input type. Either give "kind" and set it to any of "call", or "check" or give some proper input {dc=}')







@dataclass()
class TestCaseDefinition():
    name:str=''
    actions:List[Union[CallAction, CallAndCheckAction]]=field(default_factory=lambda: [])
    before_actions:list=field(default_factory=lambda: [])
    after_actions:list=field(default_factory=lambda: [])
    description:str=''
    results:List[ActionResult]=field(default_factory=lambda: [])
    n_repeat:int = 1

    abort_on:str='error' # 'error' for abort on error 'fail' for abort on failed testcase '' or None for no abort on either

    has_run:bool=False

    t_start:datetime.datetime=None
    t_end:datetime.datetime=None

    description:str = ''


    @staticmethod
    def construct(k, dc):

        if isinstance(dc, list):
            dc = {'actions': dc}

        assert k, f'ERROR: "Testcase" has no key (name / ID)! {k=} {dc=}'
        assert dc, f'ERROR: "Testcase" is None or empty! {dc=}'
        assert dc.get('actions'), f'ERROR: "testcase {k}" has no actions!'


        kw = {k:v for k, v in dc.items()}

        if dc.get('before_actions'):
            kw['before_actions'] = [dict2action(v) for v in dc['before_actions']]
        
        kw['actions'] = [dict2action(v) for v in dc['actions']]

        if dc.get('after_actions'):
            kw['after_actions'] = [dict2action(v) for v in dc['after_actions']]

        name = dc.get('name')
        kw['name'] = k if not name else f'{k}: {name}'
        return TestCaseDefinition(**kw)

    def get_stdout(self, remove_colors=True):
        x = [res.get_stdout() for name, res in self.results]
        return ''.join([xx for xx in x if xx])
    
    def get_errors(self):
        err = ''
        for name, res in self.results:
            e = res.get('error_msg', '')
            if e:
                err += f'{name}: {e}\n\n'
        return err
    
    def _run(self, gl, log_stdout=True):
        assert not self.has_run, f'This testcase {self.name=} has already run!'
        self.results = []

        for i in range(self.n_repeat):
            self.t_start = datetime.datetime.utcnow()
            for i, action in enumerate(self.before_actions, 1):
                if not action:
                    continue
                a = action.run(gl=gl, t_start=self.t_start, log_stdout=log_stdout)        
                self.results.append((f'before_actions_{i}', a))
            
            for i, action in enumerate(self.actions, 1):
                if not action:
                    continue
                a = action.run(gl=gl)
                self.results.append((f'actions_{i}', a))

            self.t_end = datetime.datetime.utcnow()

            for i, action in enumerate(self.after_actions, 1):
                if not action:
                    continue
                a = action.run(gl=gl, t_start=self.t_start, t_end=self.t_end, results = self.results, log_stdout=log_stdout)
                self.results.append((f'after_actions_{i}', a))
            
            return self.results


    
    def run(self, gl=None, log_stdout=True):

        print_color((('-'*20) + ''  + self.name + ' ' + '-'*20).ljust(100, '-'), 'bold')
        print_color(self.name + ' --> RUNNING...', 'blue')

        try:
            
            self._run(gl=gl)
            self.has_run = True
            
            if self.last_result.error_msg:
                print_color(self.name + ' --> FAIL', 'red')
            else:
                print_color(self.name + ' --> OK', 'green')


        except Exception as err_obj:   
            if not self.abort_on:
                print_color(self.name + ' --> FAIL', 'red')
                s = 'ERROR while executing:\n' + traceback.format_exc()
                print_color(s, 'red')
                self.results.append((f'ERROR', s))
            else:
                raise
        finally:
            self.has_run = True


    @property
    def last_result(self) -> ActionResult:
        assert self.results or self.has_run, f'no results exist (yet) {self.has_run=}'
        return self.results[-1][-1]

    @property
    def last_result_key(self):
        return self.results[-1][0]
    
    def did_succeed(self):
        return False if self.get_errors() else True
    
    def wasSuccessful(self):
        """same as did_success but this is the same name as pytest uses so I keep it like this"""
        return self.did_succeed()

    def get_succes_info(self) -> str:
        assert self.results or self.has_run, f'no results exist (yet) {self.has_run=}'
        errs = self.get_errors()
        return 'PASS' if self.did_succeed() else ('ERROR' if 'ERR' in errs else ('FAIL' if 'FAIL' in errs else 'ERROR?'))
    
    def get_files_to_upload(self) -> Dict[str, bytes]:
        assert self.results or self.has_run, f'no results exist (yet) {self.has_run=}'
        ret = {}
        for name, r in self.results:
            dci = r.get_upload_files()
            duplicate_filenames = [k for k in dci if k in ret]
            assert not duplicate_filenames, f'ERROR the following filenames were found to be duplicates {duplicate_filenames=}'
            ret.update(dci)
        return ret

    def to_doc(self, verbosity_level=1):
        
        txt = ''
        doc = pyd.DocBuilder()

        txt += '___\n\n'
        txt += f'#### Testcase `{self.name}`: Overall result: --> **{self.get_succes_info()}**\n\n'

        txt += (self.description + '\n\n' if self.description else '')

        if verbosity_level < 2:
            txt += "**ACTIONS**:"
            doc.add_md(txt)
            helper = lambda i, a: f'{i: 3.0f}. {a.kind.ljust(5)}: {a.fun.ljust(25)} --> {a.result.get_succes_info()}'
            txt = '\n'.join([helper(i, a) for i, a in enumerate(self.actions)])
            doc.add_pre(txt)


        if verbosity_level == 1:
            errs = self.get_errors()
            if errs: 
                doc.add_md("\n\n **ERRORS:**\n\n")
                doc.add_pre(errs)

            parts = pyd.DocBuilder()
            for name, r in self.results:
                std = r.get_stdout(remove_colors = True)
                doci = r.get_result_doc()
                files = r.get_upload_files()                
                
                c = helpers.limit_len(r.call, 120)

                if std or doci or files: parts.add_md(f'Output for: `{c}` ("{name}")')
                if std: parts.add_pre(std)
                if doci: parts += doci
                if files:
                    fun = lambda filename, file: f'- `{filename}`: {type(file)=} length: {len(file) if hasattr(file, "__len__") else "unknown"}'
                    t = f'The call of "{c}" (also) generated N={len(files)} files to be uploaded to the server.'
                    if len(files) < 10:
                        t += '\n\n' + '\n'.join([fun(k, v) for k, v in files.items()])    
                    parts.add_md(t)

            if parts:
                doc.add_md("\n\n **OUTPUT:**\n\n")
                doc += parts

        

        if verbosity_level >= 2:
            doc.add_md(f'Given below is the detailed information on the actions which were run')
            for rname, r in self.results:
                doc.add_md(f'##### Action: *{rname}*\n\n')
                doc += r.to_doc()

        doc.add_md(f'\n\n<<< END OF TESTCASE: "{self.name}" >>> ')

        return doc

@dataclass()
class TestRunner():

    testcases:List[TestCaseDefinition] = field(default_factory=lambda: [])
    on_setup:List[Union[CallAction, CallAndCheckAction]]=field(default_factory=lambda: [])
    on_teardown:List[Union[CallAction, CallAndCheckAction]]=field(default_factory=lambda: [])
    results:List[Tuple[str, ActionResult]] = field(default_factory=lambda: [])
    
    globals_dc:Dict[str, Any] = field(default_factory=lambda :{})
    locals_dc:Dict[str, Any] = field(default_factory=lambda :{})

    description:str = ''

    t_start:datetime.datetime=None
    t_end:datetime.datetime=None

    log_stdout = True
    has_run = False

    # def __init__(self) -> None:
    #     self.doc:Any = None
    #     self.testcases = []
    #     self.on_setup = []
    #     self.on_teardown = []
    #     self.results =[]
    #     self.had_error = False
    
    @staticmethod
    def construct(testcases:dict, on_setup=None, on_teardown=None, **kw):
        if not on_setup:
            on_setup = []
        if not on_teardown:
            on_teardown = []

        assert testcases, f'ERROR: "testcases" is None or empty! {testcases=}'
        assert isinstance(on_setup, list), f'ERROR: "on_setup" must be of type list but was {type(on_setup)=}, {on_setup=}'
        assert isinstance(on_teardown, list), f'ERROR: "on_teardown" must be of type list but was {type(on_teardown)=}, {on_teardown=}'

        _ons = [dict2action(oo) for oo in on_setup if oo]
        _ont = [dict2action(oo) for oo in on_teardown if oo]
        if isinstance(testcases, list):
            testcases = {f'Testcase_{i}':v for i, v in enumerate(testcases, 1) if v}

        _tests = [TestCaseDefinition.construct(k, v) for k, v in testcases.items() if v]
        assert _tests, f'ERROR: "testcases" is None or empty! {_tests=}'

        return TestRunner(on_setup=_ons, testcases=_tests, on_teardown=_ont, **kw)
    
    def get_files_to_upload(self) -> Dict[str, bytes]:
        assert self.results or self.has_run, f'no results exist (yet) {self.has_run=}'
        ret = {}
        for name, r in self.results:
            dci = r.get_upload_files()
            duplicate_filenames = [k for k in dci if k in ret]
            assert not duplicate_filenames, f'ERROR the following filenames were found to be duplicates {duplicate_filenames=}'
            ret.update(dci)
        return ret
    
    def get_errors(self):
        err = ''
        for name, res in self.results:
            e = res.get('error_msg', '')
            if e:
                err += f'{name}: {e}\n'
        return err
    
    def _run(self, name, action_or_test):
        if not action_or_test:
            return
        g = self.globals_dc if self.globals_dc else globals()
        l = self.locals_dc if self.locals_dc else locals()
        

        action_or_test.run(gl=(g,l), log_stdout = self.log_stdout)

        if isinstance(action_or_test, TestCaseDefinition):
            self.results += [(f'Testcase:{action_or_test.name}:{action_name}', r) for action_name, r in action_or_test.results]
        else:
            self.results += [((name), action_or_test.run(gl=(g,l)))]

    def run(self, force_overwrite=False):
        assert not self.has_run or force_overwrite, f'testrunner has already run. Please set force_overwrite to True to allow a rerun'

        
        self.results = []
        self.t_start = helpers.get_utcnow()
        for i, action in enumerate(self.on_setup, 1):
            self._run(f'on_startup:action_{i}', action)
            if action:
                name, last_action_result = self.results[-1]
                assert not last_action_result.error_msg, f'ERROR during startup! {name=} {last_action_result=}'

        
        for test in self.testcases:
            self._run(test.name, test)
            

        for i, action in enumerate(self.on_teardown, 1):
            self._run(f'on_teardown:action_{i}', action)
            if action:
                name, last_action_result = self.results[-1]
                assert not last_action_result.error_msg, f'ERROR during teardown! {name=} {last_action_result=}'

        self.t_end = helpers.get_utcnow()
        self.has_run = True
        
        return self.results

        
    def write_report(self, doc=None):
        assert self.has_run, 'testrunner has not run yet, but write_report was called...'
        if doc is None:
            doc = pyd.DocBuilder()
        
        doc.add_chapter('Test Results from TestRunner')
        
        doc.add_md(f'### On Start of Testrun\n\n')
        onsr = [tpl for tpl in self.results if tpl[0].startswith('on_startup')]
        if onsr:
            for k, action in onsr:
                doc.add_md(f'\n\n#### Action: *{k}* `{action.call}`\n\n')
                doc += action.to_doc(no_call_info=True, hide_empty=True)
        else:
            doc.add_md('No special action was perfomed on startup')
        
        doc.add_md('___\n\n')

        doc.add_md(f'### Testcases:\n\n')
        for test in self.testcases:
            doc += test.to_doc()

        doc.add_md('___\n\n')

        doc.add_md(f'### On End of Testrun\n\n')
        ontr = [tpl for tpl in self.results if tpl[0].startswith('on_teardown')]
        if ontr:
            for k, action in ontr:
                doc.add_md(f'\n\n#### Action: *{k}* `{action.call}`\n\n')
                doc += action.to_doc(no_call_info=True, hide_empty=True)
        else:
            doc.add_md('No special action was perfomed on shutdown')
        
        
        return doc
            
    def to_doc(self, doc=None):
        return self.write_report(doc)

                

    def pprint(self):
                
        print('=' * 100)
        
        duration = self.t_end - self.t_start
        print_color(f'FINISHED!\nTESTED N={len(self.testcases)} testcases between {self.t_start}...{self.t_end} ({duration})', 'bold')

        print('RESULTS:')
        print('-' * 60)

        err_s = ''
        for i, test in enumerate(self.testcases):
            err_s = test.get_errors()
            if err_s:
                c = 'red'
                res = ' --> FAIL!'
            else:
                c = 'green'
                res = ' --> PASS!'
            
            line = 'TESTCASE No. {: 4.0f} | {} |> {}'.format(i, test.name.ljust(35), res)

            print_color(line, c)

        print('=' * 100)


class colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    BLACK = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

colors_dc = {
    'header': colors.HEADER,
    'blue': colors.OKBLUE,
    'green': colors.OKGREEN,
    'warn': colors.WARNING,
    'red': colors.FAIL,
    'black': colors.BLACK,
    'bold': colors.BOLD,
    'underline': colors.UNDERLINE
}

_print = print

def print_color(msg, color='red'):
    if isinstance(color, str):
        color = colors_dc[color]
    if getattr(print, 'do_log', False):
        print.log.append(msg)
    _print(f"{color}{msg}{colors.BLACK}")


# helper function instead of assert
def asserte(to_test, message, do_print=True):
    if not to_test:
        if do_print:
            print_color('Testcondition failed. Message: ' + message, 'red')
        return message
    else:
        return ''





if __name__ == "__main__":


    def get_user_feedback(msg):
        # function to mock a user feedback
        feedback = {'request': msg, 'response': f"dummy response at {datetime.datetime.utcnow().isoformat()}", 'success': True, "error": ""}
        return feedback
    
    startup_routine =  [
        'wait 2s'
    ]

    tests = {
        'dummy_testcase': [
            
            {"fun": "time.sleep(1)"},
            {"fun": "lambda: 'ON'", "expected": "'ON'", "abort_on_fail": True},
            {"fun": "random.randint(0, 10)", "expected": "<5", "abort_on_fail": False},
            {"fun": "time.sleep(1)"},
            {"fun": "get_user_feedback('Please Check Meerstetter firmware version and configuration settings.')", "expected": "success", "abort_on_fail": False},
            {"fun": "random.randint(-5, 5)", "expected": "-4 < act < 10", "abort_on_fail": False},
            {"fun": "random.randint(-5, 5)", "expected": (-4, 10), "abort_on_fail": False},
        ]
    }

    teardown_routine = [
        'wait 2s'
    ]

    runner = TestRunner.construct(tests, on_setup=startup_routine, on_teardown=teardown_routine)
    runner.run()

    print('-'*100)
    print(runner.get_errors())
    print('-'*100)
    for self in runner.results:
        print(self)



