
# Scheduler (Background worker)
import redis
import json
import time
import subprocess

from JupyRunner.core import redis_interface, helpers
log = helpers.log


rapi = redis_interface.RedisApi()

while True:
    rapi.scheduler_tick()
    time.sleep(0.5)  # Check every 0.5 seconds (adjust as needed)


# Script Runner (Subscriber - same as before, no changes needed)