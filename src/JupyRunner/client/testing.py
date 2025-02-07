
import functools
import datetime
import traceback
import time


# helper function instead of assert
def asserte(err, to_test, message, do_print=True):
    if not to_test:
        if do_print:
            print_color('Testcondition failed. Message: ' + message, 'red')
        return err + 'ERROR: ' + message + '\n'
    else:
        return err
    



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
    if print.do_log:
        print.log.append(msg)
    _print(f"{color}{msg}{colors.BLACK}")

def print(*args, **kwargs):
    if print.do_log:
        print.log.append(''.join([str(arg) for arg in args]))
    _print(*args, **kwargs)

print.log = []
print.do_log = False

results = []

def get_default_print():
    return _print


def clear_cache():
    
    global results
    
    res = [r for r in results]
    printlog = [l for l in print.log]

    print.log.clear()
    results.clear()
    print.do_log = False

    return res, printlog
        
def reset():
    clear_cache()
    
def get_summary(results, t_script_start, t_script_end, do_print = True):

    if do_print:
        print('=' * 100)
        print_color(f'FINISHED!\nTESTED N={len(results)} testcases between {t_script_start}...{t_script_end}', 'bold')

        print('RESULTS:')
        print('-' * 60)

    lines = []
    has_err = False
    err_s = ''
    for i, (test_name, err_str) in enumerate(results):
        if err_str:
            has_err = True
            c = 'red'
            res = ' --> FAIL!'
        else:
            c = 'green'
            res = ' --> PASS!'
        
        line = 'TESTCASE No. {: 4.0f} | {} |> {}'.format(i, test_name.ljust(35), res)
        lines.append(line)
        
        if err_str:
            err_s += line + '\n'

        if do_print:
            print_color(line, c)
    
    if do_print:
        print('=' * 100)
    return lines, err_s


def testcase(_func=None, *, test_name='', func_to_get_chan_values=None, expected_chan_values=None, n_repeat=1, doc=None, results_in = None, user_info_cb=None):

    def decorator_name(func):
        @functools.wraps(func)
        def wrapper():
            if results_in:
                _results = results_in
            else:
                global results
                _results = results

            def user_info(s, color=None):
                try:
                    if user_info_cb:
                        if not color in 'black blue green red'.split():
                            color = None                    
                        return user_info_cb(s, color=color)
                except Exception as err:
                    pass

            for i in range(n_repeat):
                print.log.clear()
                print.do_log = True

                fname = 'TESTCASE No. {: 4d} | "{}"'.format(len(_results), func.__name__)
                if n_repeat > 1:
                    fname += f' run no. {i: 4d}'

                if test_name:
                    fname += f' | "{test_name}"'
                    
                name = func.__name__ if not test_name else test_name

                print_color((('-'*20) + ' RUNNING ' + fname).ljust(100, '-'), 'bold')
                user_info((('-'*10) + ' RUNNING Testcase ' + fname).ljust(100, '-'), 'blue')

                print_color(fname + 'running...', 'blue')

                t_start = datetime.datetime.utcnow()
                time.sleep(0.1)
                

                try:
                    
                    # RUN the Testcase
                    
                    err = func()

                    assert not err is None, 'every testcase need to return an error string. Please return "" (empty string) if you have no error '
                    if err is None:
                        err = ''
                    
                    
                except Exception as err_obj:   
                    print_color(fname + '--> FAIL', 'red')
                    user_info(fname + '--> FAIL', 'red')
                    s = 'ERROR while executing:\n' + traceback.format_exc()
                    print_color(s, 'red')
                    # ADD TO RESULTS
                    _results.append((name, s))
                    if not doc is None:
                        doc.add_md('#### ' + fname + '\n this is the individual test output while running the test:\n\n', chapter='Testcases')
                        doc.add_pre(s, chapter='Testcases')
                    return 
                
                if err:
                    print_color(fname + '--> FAIL', 'red')
                    user_info(fname + '--> FAIL', 'red')
                else:
                    print_color(fname + '--> OK', 'green')
                    user_info(fname + '--> OK', 'green')

                time.sleep(0.1)
                t_end = datetime.datetime.utcnow()

                # ---------------
                # TEST ERROR CHANNELS
                # ---------------
                if expected_chan_values and func_to_get_chan_values:
                    print_color(fname + 'testing for channel errors...', 'blue')

                    chans = func_to_get_chan_values(expected_chan_values.keys(), t_start, t_end)
                    err_chans = [c for c in expected_chan_values if expected_chan_values[c](chans[c]) ]

                    if err_chans:
                        err += 'Error on channel(s): ' + ', '.join(err_chans) + '\n'
                        print_color(fname + '--> FAIL', 'red')
                        user_info(fname + '--> FAIL', 'red')
                    else:
                        print_color(fname + '--> OK', 'green')
                        user_info(fname + '--> OK', 'green')
                
                print_color((('-'*10) + ' DONE ' + ('-'*10)).ljust(100, '-'), 'header')
                user_info((('-'*10) + ' DONE ' + ('-'*10)).ljust(100, '-'), 'blue')

                if err:
                    s = fname + '--> FAILED!'
                    s += '\n' + err

                    print_color(s, 'red')
                    print_color('-'*100, 'red')

                    user_info(s, 'red')
                    user_info('-'*100, 'red')

                else:
                    s = fname + '--> SUCCESS!'
                    print_color(s, 'green')
                    print_color('-'*100, 'green')
                    
                    user_info(s, 'green')
                    user_info('-'*100, 'green')
                    
                print.do_log = False
                txt = '\n'.join(print.log)
                    
                    
                if not doc is None:
                    doc.add_md('#### ' + fname + '\n this is the individual test output while running the test:\n\n', chapter='Testcases')
                    
                    for c in colors_dc.values():
                        txt = txt.replace(c, '')
                    doc.add_pre(txt, chapter='Testcases')
                    # doc.add_kw('verbatim', '\n'.join(print_color.log), chapter='Testcases')


                # ADD TO RESULTS
                _results.append((name, err))

        return wrapper
    
    if _func is None:
        return decorator_name                      # 2
    else:
        return decorator_name(_func)               # 3
    
    
