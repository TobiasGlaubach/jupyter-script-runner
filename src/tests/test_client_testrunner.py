import time
import pytest

import datetime


import os, inspect, sys
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
if __name__ == '__main__':
    # print(parent_dir)
    sys.path.insert(0, parent_dir)


from JupyRunner.client.testrunner import TestRunner


def test_client_testrunner_minimal(session):
    

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

    runner = TestRunner.construct(tests, 
                                  on_setup=startup_routine, 
                                  on_teardown=teardown_routine)
    
    runner.locals_dc = locals()
    runner.locals_dc['get_user_feedback'] = get_user_feedback

    runner.run()

    print('-'*100)
    print(runner.get_errors())
    print('-'*100)
    for self in runner.results:
        print(self)


if __name__ == '__main__':
    test_client_testrunner_minimal()