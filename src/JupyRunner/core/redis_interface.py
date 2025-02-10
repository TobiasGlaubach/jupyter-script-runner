
import time
import json
import datetime
import asyncio

import redis
import redis.asyncio as aredis

import os, inspect, sys
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if __name__ == '__main__':
    print(parent_dir)
    sys.path.insert(0, parent_dir)

from JupyRunner.core import helpers


    
channel_script_prepare = "script_prepare"
channel_script_start = "script_start"
channel_script_scheduleing = "scheduled_tasks"
channel_script_cancle = "script_cancle"
channel_user_feedback_new = "user_feedback_new"
channel_user_feedback_reply = "user_feedback_reply"


def _get_messages(pubsub, timeout):
    while msg := pubsub.get_message(timeout=timeout):
        if not msg:
            break
        if msg and msg["type"] == "message":
            yield msg['data'].decode('utf-8')

class RedisApi(object):
    def __init__(self, host=None, port = None) -> None:
        if host is None:
            host = "redis"
        if port is None:
            port = 6379
            

        self.r = redis.Redis(host=host, port=port)


    def schedule_script(self, script_id, execution_time_unix_s):
        """Schedules a script for execution at a specified time.

        Args:
            script_id (int): The ID of the script to be scheduled. Must be greater than 0.
            execution_time (datetime.datetime or str): The time at which the script should be executed.
                If a datetime object is provided, it will be converted to a Unix timestamp.
                If a string is provided, it should be in Zulu time format (YYYY-MM-DDTHH:MM:SSZ).

        Returns:
            bool: True if the script was successfully scheduled, False otherwise.

        Raises:
            AssertionError: If script_id is not of type int or is less than or equal to 0.
        """
        assert isinstance(script_id, int) and script_id > 0, 'script_id must be of type int and > 0'

        if isinstance(execution_time_unix_s, datetime.datetime):
            execution_time_unix_s = time.mktime(execution_time_unix_s.timetuple())
        elif isinstance(execution_time_unix_s, str):
            execution_time_unix_s = time.mktime(helpers.parse_zulutime(execution_time_unix_s))

        execution_time_ms = int(execution_time_unix_s * 1000)
        self.r.zadd(channel_script_scheduleing, {script_id: execution_time_ms})
        helpers.log.info(f'Scheduled script {script_id=} start for {execution_time_ms=}')
        return True


    def modify_script_starttime(self, script_id, new_execution_time):
        """simply wraps schedule_script, as zadd in redis also updates"""
        return self.schedule_script(script_id, new_execution_time)


    def trigger_script_prepare(self, script_id):
        res = self.r.publish(channel_script_prepare, script_id)  # Publish to channel
        helpers.log.info(f'Queued script prepare for {script_id=}')
        return res
        

    def trigger_script_start(self, script_id):
        self.r.publish(channel_script_start, script_id)  # Publish to channel
        res =  self.r.zrem(channel_script_scheduleing, script_id) # Remove from scheduled tasks (one-time execution)
        helpers.log.info(f'Queued script start for {script_id=}')
        return res
        
    def trigger_script_cancle(self, script_id):
        res = self.r.publish(channel_script_cancle, script_id)  # Publish to channel
        helpers.log.info(f'Queued script cancle for {script_id=}')
        return res
        


    def scheduler_tick(self, now = None):
        if now is None:
            now = int(time.time() * 1000)

        tasks_to_run = self.r.zrangebyscore(channel_script_scheduleing, 0, now) # Get tasks with past or current execution time
        for script_id in tasks_to_run:
            try:
                self.trigger_script_start(script_id)
            except Exception as e:
                helpers.log.error(f"Error processing scheduled task: {e}")
    
    def subscribe_channel(self, channel_name):
        pubsub = self.r.pubsub()
        pubsub.subscribe(channel_name)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_name}"')
        return pubsub
    
    def publish_to_channel(self, channel_name, msg):
        if isinstance(msg, dict):
            msg = json.dumps(msg)
        elif not isinstance(msg, str):
            msg = msg.model_dump_json()
        return self.r.publish(channel_name, msg)


    def subscribe_script_start(self):
        pubsub = self.r.pubsub()
        pubsub.subscribe(channel_script_start)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_script_start}"')
        return pubsub
    
    def subscribe_script_cancle(self):
        pubsub = self.r.pubsub()
        pubsub.subscribe(channel_script_cancle)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_script_cancle}"')
        return pubsub
    
        
    def subscribe_script_prepare(self):
        pubsub = self.r.pubsub()
        pubsub.subscribe(channel_script_prepare)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_script_prepare}"')
        return pubsub

    def get_messages(self, pubsub, timeout=0.1) -> list:
        ret = list(_get_messages(pubsub, timeout))
        helpers.log.debug(f'get_messages({pubsub.channels}) --> N={len(ret)} messages')
        return ret

    def subscribe_user_feedback(self):
        pubsub = self.r.pubsub()
        pubsub.subscribe(channel_user_feedback_new)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_user_feedback_new}"')
        return pubsub

    def subscribe_user_feedback_reply(self):
        pubsub = self.r.pubsub()
        pubsub.subscribe(channel_user_feedback_reply)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_user_feedback_reply}"')
        return pubsub
    
    def decode_model_json(self, message, decode_type):
        try:
            return decode_type.model_validate_json(message["data"])
        except json.JSONDecodeError:
            helpers.log.error("Invalid JSON received.")
        except Exception as e: # Catch any Pydantic validation errors
            helpers.log.error(f"Pydantic Validation Error: {e}")

    def send_user_feedback(self, msg):
        if not isinstance(msg, str):
            msg = msg.model_dump_json()
        return self.r.publish(channel_user_feedback_new, msg)

    async def listen_pubsub_async(self, pubsub, t_sleep=0.05, decode_type=None):
        while True:
            msg = await asyncio.to_thread(pubsub.get_message)  # Bridge to async
            if msg and msg["type"] == "message":
                if decode_type is None:
                    yield msg['data'].decode('utf-8')    
                else:
                    yield self.decode_model_json(msg)
            await asyncio.sleep(t_sleep) # Small delay to avoid busy waiting

    def listen_pubsub(self, pubsub, decode_type='json'):
        for msg in pubsub.listen():
            if msg and msg["type"] == "message":
                if decode_type == 'json' or decode_type == 'dict':
                    yield json.loads(msg['data'].decode('utf-8'))
                elif not decode_type is None:
                    yield self.decode_model_json(msg)
                else:
                    yield msg['data'].decode('utf-8')



class AsyncRedisApi(object):
    def __init__(self, host=None, port=None) -> None:
        if host is None:
            host = "redis"
        if port is None:
            port = 6379

        self.r = aredis.Redis(host=host, port=port)

    async def schedule_script(self, script_id, execution_time_unix_s):
        assert isinstance(script_id, int) and script_id > 0, 'script_id must be of type int and > 0'

        if isinstance(execution_time_unix_s, datetime.datetime):
            execution_time_unix_s = time.mktime(execution_time_unix_s.timetuple())
        elif isinstance(execution_time_unix_s, str):
            execution_time_unix_s = time.mktime(helpers.parse_zulutime(execution_time_unix_s))

        execution_time_ms = int(execution_time_unix_s * 1000)
        await self.r.zadd(channel_script_scheduleing, {script_id: execution_time_ms})
        helpers.log.info(f'Scheduled script {script_id=} start for {execution_time_ms=}')
        return True

    async def modify_script_starttime(self, script_id, new_execution_time):
        return await self.schedule_script(script_id, new_execution_time)

    async def trigger_script_prepare(self, script_id):
        res = await self.r.publish(channel_script_prepare, script_id)
        helpers.log.info(f'Queued script prepare for {script_id=}')
        return res

    async def trigger_script_start(self, script_id):
        await self.r.publish(channel_script_start, script_id)
        res = await self.r.zrem(channel_script_scheduleing, script_id)
        helpers.log.info(f'Queued script start for {script_id=}')
        return res

    async def trigger_script_cancle(self, script_id):
        res = await self.r.publish(channel_script_cancle, script_id)
        helpers.log.info(f'Queued script cancle for {script_id=}')
        return res

    async def scheduler_tick(self, now=None):
        if now is None:
            now = int(time.time() * 1000)

        tasks_to_run = await self.r.zrangebyscore(channel_script_scheduleing, 0, now)
        for script_id in tasks_to_run:
            try:
                await self.trigger_script_start(script_id)
            except Exception as e:
                helpers.log.error(f"Error processing scheduled task: {e}")

    async def subscribe_channel(self, channel_name):
        pubsub = self.r.pubsub()
        await pubsub.subscribe(channel_name)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_name}"')
        return pubsub

    async def publish_to_channel(self, channel_name, msg):
        if isinstance(msg, dict):
            msg = json.dumps(msg)
        elif not isinstance(msg, str):
            msg = msg.model_dump_json()
        return await self.r.publish(channel_name, msg)

    async def subscribe_script_start(self):
        pubsub = self.r.pubsub()
        await pubsub.subscribe(channel_script_start)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_script_start}"')
        return pubsub

    async def subscribe_script_cancle(self):
        pubsub = self.r.pubsub()
        await pubsub.subscribe(channel_script_cancle)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_script_cancle}"')
        return pubsub

    async def subscribe_script_prepare(self):
        pubsub = self.r.pubsub()
        await pubsub.subscribe(channel_script_prepare)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_script_prepare}"')
        return pubsub

    async def get_messages(self, pubsub, timeout=0.1) -> list:
        ret = []
        while True:
            msg = await pubsub.get_message(timeout=timeout)
            if not msg:
                break
            if msg and msg["type"] == "message":
                ret.append(msg['data'].decode('utf-8'))
        helpers.log.debug(f'get_messages({pubsub.channels}) --> N={len(ret)} messages')
        return ret

    async def subscribe_user_feedback(self):
        pubsub = self.r.pubsub()
        await pubsub.subscribe(channel_user_feedback_new)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_user_feedback_new}"')
        return pubsub

    async def subscribe_user_feedback_reply(self):
        pubsub = self.r.pubsub()
        await pubsub.subscribe(channel_user_feedback_reply)
        helpers.log.info(f'Success: subscribed to Redis channel. "{channel_user_feedback_reply}"')
        return pubsub

    async def decode_model_json(self, message, decode_type):
        try:
            return decode_type.model_validate_json(message["data"])
        except json.JSONDecodeError:
            helpers.log.error("Invalid JSON received.")
        except Exception as e:
            helpers.log.error(f"Pydantic Validation Error: {e}")

    async def send_user_feedback(self, msg):
        if not isinstance(msg, str):
            msg = msg.model_dump_json()
        return await self.r.publish(channel_user_feedback_new, msg)

    async def listen_pubsub_async(self, pubsub, decode_type=None):
        async for msg in pubsub.listen():
            if msg and msg["type"] == "message":
                if decode_type is None:
                    yield msg['data'].decode('utf-8')
                else:
                    yield await self.decode_model_json(msg, decode_type)
            

if __name__ == '__main__':
    
    # r = redis.Redis(host='localhost', port=6379, db=0)
    # print(r.ping())

    rapi = RedisApi('localhost')

    pubsub = rapi.subscribe_script_start()
    # Trigger a new dummy script start
    rapi.trigger_script_start(123)

    

    for message in pubsub.listen():
        print(message)
        if message['type'] == 'message':
            script_id = message['data'].decode('utf-8')
            helpers.log.info(f'Received script start event for {script_id=}')
            break

    rapi.trigger_script_start(124)
    print(rapi.get_messages(pubsub))