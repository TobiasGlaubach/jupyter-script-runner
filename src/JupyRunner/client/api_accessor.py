
import hashlib
import io
import mimetypes
import time
import requests, datetime, enum, re, dateutil, sys
import os

from typing import Any, Dict, List, Union



if __name__ == '__main__':
    import os, inspect, sys
    current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) 
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    print(parent_dir)
    sys.path.insert(0, parent_dir)
    

from JupyRunner.core.helpers import limit_len, logging, log, make_zulustr, parse_zulutime, iso_now, get_primary_ip, get_sys_id, get_uid
from JupyRunner.core.redis_interface import RedisApi


log_parent = log
log = log_parent.getChild('jpy_client')
log.setLevel(logging.INFO)

rapi = None


class BaseAPIClient:
    """
    Implementation of the BaseAPIClient using Requests.
    """

    def __init__(self, base_url:str=None, none_on_404 = False, session=None):
        """
        Initializes a new BaseAPIClient instance.

        Args:
            base_url (str, optional): The base URL for API requests.
            session (requests.Session, optional): An existing Requests session object.
        """
        self.base_url = base_url
        self.session = session or requests.Session()

        self.base_url = base_url
        self.none_on_404 = none_on_404
        self.session = requests.Session()

    def _url(self, endpoint):
        return f"{self.base_url.rstrip('/')}/{str(endpoint).lstrip('/')}".rstrip('/')
    
    def _json(self, dc):
        if isinstance(dc, dict):
            return {k:self._json(d) for k, d in dc.items()}
        elif isinstance(dc, list):
            return [self._json(d) for d in dc]
        elif isinstance(dc, (datetime.datetime, datetime.date)):
            return make_zulustr(dc, remove_ms=False)
        elif issubclass(type(dc), (enum.IntEnum, enum.StrEnum)):
            return dc.name
        else:
            return dc

    def validate(self, inp, outp):
        for key, v in inp.items():
            assert key in outp, f'{key=} is missing in response! {outp=}'
            if key == 'last_time_changed':
                assert inp[key] < outp[key], f'last_time_changed <= before {inp[key]=} < {outp[key]=}'
            elif isinstance(inp[key], str) and isinstance(outp[key], str) and parse_zulutime(inp[key]) and parse_zulutime(outp[key]):
                vin, vout = inp[key], outp[key]
                vin = parse_zulutime(vin)
                vout = parse_zulutime(vout)
                assert vin == vout, f'{key=} was not updated! {vin=} != {vout=}'
            elif isinstance(inp[key], dict) and isinstance(outp[key], dict):
                pass # dont check for dict update
            else:
                assert inp[key] == outp[key], f'{key=} was not updated! {inp[key]=} != {outp[key]=}'
        return outp
    

        
    def get(self, endpoint, params=None, headers=None, ret_raw=False):
        url = self._url(endpoint)
        log.debug(f'GET: {url} {params=}')
        response = self.session.get(url, params=params, headers=headers)
        if response.status_code == 404 and self.none_on_404:
            return None
        
        response.raise_for_status() 
        return response if ret_raw else response.json()
        
    def put(self, endpoint, json=None, headers=None, ret_raw=False):
        url = self._url(endpoint)
        json = self._json(json)
        s = f'{json=}'
        log.debug(f'PUT: {url} {limit_len(s, 200)}')
        response = self.session.put(url, json=json, headers=headers)
        response.raise_for_status()  # Raise an exception for error responses

        if ret_raw: 
            return response
        resp = response.json()
        self.validate(json, resp)
        return resp


    def post(self, endpoint, json=None, headers=None, files=None, ret_raw=False):
        url = self._url(endpoint)
        json = self._json(json)
        s = f'{json=}'
        log.debug(f'POST: {url} {limit_len(s, 200)}')
        response = self.session.post(url, json=json, headers=headers, files=files)
        response.raise_for_status()  # Raise an exception for error responses
        if ret_raw: 
            return response
        resp = response.json()
        self.validate(json, resp)
        return resp
        

    def patch(self, endpoint, json:Dict[str, Any]|None=None, headers=None, ret_raw=False):
        url = self._url(endpoint)
        s = f'{json=}'
        log.debug(f'PATCH: {url} {limit_len(s, 200)}')
        response = requests.patch(url, json=json, headers=headers)
        response.raise_for_status()  # Raise an exception for error responses
        if ret_raw: 
            return response
        resp = response.json()
        self.validate(json, resp)
        return resp
    


class ServerApi(object):
    def __init__(self, base_url, none_on_404=False, script_id=None, script_uid=None, device_id=None) -> None:
        self.script_id = script_id
        self.api = BaseAPIClient(base_url, none_on_404)
        self.script_uid = script_uid
        self.device_id = device_id
    
    def set_script_uid(self, script_out_path=None, script_name=None, script_version=None, fallback_random=False ):
        if script_out_path:
            self.script_uid = os.path.splitext(os.path.basename(script_out_path))[0]
        elif script_name and script_version:
            self.script_uid = f'{script_name}_{script_version}_{get_uid()[-4:]}'
        elif script_name:
            self.script_uid = f'{script_name}_{round(time.time())}_{get_uid()[-4:]}'
        elif fallback_random:
            self.script_uid = get_uid(self, self.script_id)
        else:
            self.script_uid = None

    def set_prop_remote(self, **kwargs):
        return self.api.patch(f'script/{self.script_id}', **kwargs)

    def set_script_uid_from_outfile(self, script_out_path):
        self.script_uid = os.path.splitext(os.path.basename(script_out_path))[0]

    def ping(self):
        r = self.api.get(f'/ping', ret_raw=True)
        return r.text
    
    def get_device(self, device_id):
        assert device_id, 'device_id can not be None or empty!'
        return self.api.get(f'device/{device_id}')
    
    def get_script(self, script_id=None):
        if script_id is None:
            script_id = self.script_id
        assert script_id, 'script_id can not be None or empty!'
        return self.api.get(f'script/{script_id}')

    def get_script_full(self, script_id=None):
        if script_id is None:
            script_id = self.script_id

        assert script_id, 'script_id can not be None or empty!'
        return self.api.get(f'script_full/{script_id}')

    def comment_append(self, text, script_id=None):
        """
        Append a comment to a script.

        Parameters:
        text (str): The text of the comment.
        script_id (int, optional): The ID of the script. If not provided, the current script_id is used.

        Returns:
        Response: The response from the API.
        """
        if script_id is None:
            script_id = self.script_id
        return self.api.post(f'comment/script/{script_id}', json=dict(text=text))

    def comment_append_device(self, text, device_id=None):
        """
        Append a comment to a device.

        Parameters:
        text (str): The text of the comment.
        device_id (int, optional): The ID of the device.

        Returns:
        Response: The response from the API.
        """
        return self.api.post(f'comment/device/{device_id}', json=dict(text=text))

    def comment_append_datafile(self, text, datafile_id=None):
        """
        Append a comment to a datafile.

        Parameters:
        text (str): The text of the comment.
        datafile_id (int, optional): The ID of the datafile.

        Returns:
        Response: The response from the API.
        """
        return self.api.post(f'comment/datafile/{datafile_id}', json=dict(text=text))
    
    def upload_file(self, script_id=None, filename:str='', byte_data:bytes=b'', mimetype=None):
        """Uploads a file to a script.

        This method uploads a file to a script using the provided byte data.

        Args:
            script_id (str): The ID of the script to upload the file to.
            filename (str): The name of the file to upload.
            byte_data (bytes): The file data as a bytes object.
            mimetype (str, optional): The MIME type of the file. If not provided,
                it will be guessed based on the filename extension. Defaults to None.

        Returns:
            Any: The response object from the upload request. The specific type
                will depend on the API implementation, but it typically contains
                information about the upload status and any errors that might have occurred.

        Raises:
            TypeError: If `byte_data` is not a bytes object or `filename` is not a string.
        """
        if script_id is None:
            script_id = self.script_id

        assert script_id, 'script_id can not be None or empty!'

        route = f'/action/script/{script_id}/upload/files'

        if isinstance(byte_data, str):
            byte_data = byte_data.encode()
        
        assert byte_data and isinstance(byte_data, bytes), f'need to give non empty bytes object as byte_data but got {type(byte_data)=} with {byte_data=}'
        assert filename and isinstance(filename, str), f'need to give non empty str object as filename but got {type(filename)=} with {filename=}'

        if not mimetype:
            mime, _ = mimetypes.guess_type(filename.split(".")[-1])
            mimetype = 'application/octet-stream' if mime is None else mime

        # Send the request with bytes as a file
        files = {'files': (filename, io.BytesIO(byte_data), mimetype)}

        return self.api.post(route, files=files, ret_raw=True).json()
            

    def upload_files(self, script_id=None, files:Dict[str, Union[str, bytes]]=None):
        """Uploads multiple files to a script.

        This method uploads a dictionary of files to a script. Keys in the dictionary
        represent filenames, and values can be either bytes objects containing the file
        data or strings. If a string is provided, it will be encoded before upload.

        Args:
            script_id (str): The ID of the script to upload the files to.
            files (Dict[str, Union[str, bytes]]): A dictionary mapping filenames (str) to
                file data as bytes objects or strings.

        Returns:
            Any: The response object from the upload request. The specific type
                will depend on the API implementation, but it typically contains
                information about the upload status and any errors that might have occurred.

        Raises:
            ValueError: If any value in the `files` dictionary is not a bytes object
                or a string.
        """
        if script_id is None:
            script_id = self.script_id
        assert script_id, 'script_id can not be None or empty!'

        route = f'/action/script/{script_id}/upload/files'

        assert files and isinstance(files, dict), f'need to give non empty str object as filename but got {type(filename)=} with {filename=}'


        tuples = []
        if isinstance(files, dict):
            files = list(files.items())

        for filename, byte_data in files:
            if isinstance(byte_data, str):
                byte_data = byte_data.encode()
            
            # Use the mimetypes module to guess the MIME type
            mime, _ = mimetypes.guess_type(filename.split(".")[-1])
            mimetype = 'application/octet-stream' if mime is None else mime
                
            assert byte_data and isinstance(byte_data, bytes), f'need to give non empty bytes object as byte_data but got {type(byte_data)=} with {byte_data=}'
            assert filename and isinstance(filename, str), f'need to give non empty str object as filename but got {type(filename)=} with {filename=}'

            tuples.append((filename, io.BytesIO(byte_data), mimetype))

        return self.api.post(route, files={'files': tuples}, ret_raw=True).json()
            


    def upload_doc(self, doc, doc_name='', force_overwrite=False, page_title='', script_id=None, validate=True, crop_result=True):
        """Uploads the document data to the server
            The json body is constructed as:
            
            upload = {
                "doc_name": doc_name,
                "doc": self.dump(),
                "force_overwrite": force_overwrite,
                "page_title": page_title
            }

        Args:
            doc (pydocmaker.Doc): The document to upload, either a pydocmaker.Doc object, or a list.
            doc_name (str, optional): The name of the uploaded document. Defaults to ''.
            force_overwrite (bool, optional): Whether to overwrite an existing document. Defaults to False.
            page_title (str, optional): The title of the uploaded document (if applicable). Defaults to ''.
            requests_kwargs: (dict, optional) with kwargs for requests.post(). Defaults to None.
            validate (bool, optional): Whether or not to validate the result for success and raise an assertion error if not successful. Defaults to True.
            validate (bool, optional): Whether or not to crop the script from the returned results to be more concide. Defaults to True.

        Returns:
            dict: The JSON response from the server after uploading the document.

        Raises:
            requests.exceptions.RequestException: If the upload request fails.
        """

        if script_id is None:
            script_id = self.script_id

        route = f'/action/script/{script_id}/upload/doc' if script_id else '/doc/upload'
        

        if hasattr(doc, 'dump'): # if its a 
            doc = doc.dump()

        assert isinstance(doc_name, str), f'doc_name needs to be a string but was {type(doc_name)=} {doc_name=}'
        assert isinstance(page_title, str), f'page_title needs to be a string but was {type(page_title)=} {page_title=}'
        assert isinstance(force_overwrite, (bool, int)), f'force_overwrite needs to be a bool or int but was {type(force_overwrite)=} {force_overwrite=}'
        assert isinstance(doc, list), f'doc needs to be a list (or needs to be able to do "doc.dump() -> list") but was {type(doc)=} {doc=}'

        # invalid_types = [k for k in doc if not isinstance(k, (dict, str, list))]
        
        upload = {
            "doc_name": doc_name,
            "doc": doc,
            "force_overwrite": force_overwrite,
            "page_title": page_title
        }
        result = self.api.post(route, json=upload, ret_raw=True).json()

        if validate:
            assert result.get('ok'), f'result object did not indicate success by ok=True {result=}'

        if crop_result:
            result.pop('script', None)

        return result

    def user_info(self, msg, color='', script_id=None, request_id=None, script_uid=None, device_id=None, doc=None):
        """Logs a message for the user to the server. (This will show up in the fser feedback screen)

        Args:
            msg (str or pydocmaker.Doc): The message to log. If a pydocmaker.Doc is provided, the doc will be converted to HTML.
            color (str, optional): The color to use for the message. Defaults to ''.
            script_id (str, optional): The ID of the script. If not provided, defaults to self.script_id.
            request_id (str, optional): The ID of the request. If not provided, a new ID will be generated.
            script_uid (str, optional): The name of the script. Defaults to ''.
            doc (Document, optional): A pydocmaker.Doc document to add to the post. If provided, the doc will be converted to HTML.

        Returns:
            dict: The JSON response from the API.
        """

        request_type = 'info'
        
        if script_id is None:
            script_id = self.script_id
        
        if not device_id:
            device_id = self.device_id

        if not script_uid:
            script_uid = self.script_uid

        if not request_id:
            request_id = get_uid(self, script_id)

        
        html = ''
        if not isinstance(msg, str) and hasattr(msg, 'to_html'):
            assert not doc, 'can not give doc and a doc as message!'
            html = msg.to_html()
            msg = 'HTML Document below...'
        if doc:
            html = doc.to_html()
        
        
        route = f'/user_feedback/create'
        data = {
            'message': msg,
            'request_type': request_type,
            'id': request_id,
            'script_id': script_id,
            'script_uid': script_uid,
            'device_id': device_id,
        }

        if color or html:
            data["kwargs"] = {}
            
        if color:
            data["kwargs"]["color"] = color
        if html:
            data["kwargs"]["html"] = html

        log.info(f'Sending User Info with {request_id=} {request_type=} and {script_uid=}|{script_id=}. Message = {limit_len(msg, 200)}')
        res = self.api.post(route, json=data, ret_raw=True).json()
        return res
    

    def user_get_feedback(self, msg, request_type='confirm', script_id=None, script_uid=None, request_id=None, device_id=None, t_poll_sec=2.0, verb=0, ret_all=False, doc=None, use_polling=False):
        """
        Gets user feedback through the API.

        This function retrieves user feedback for a given message and request type. It 
        makes a POST request to the `/user_feedback/create` endpoint to initiate the 
        feedback process and then polls the `/user_feedback/check` endpoint to 
        check for user response.

        Args:
            msg (str or pydocmaker.Doc): The message to show the user for feedback. If a pydocmaker.Doc is provided, the doc will be converted to HTML.
            request_type (str, optional): The type of feedback request. Must be one of 
                'confirm', 'file', 'files', 'picture', 'pictures', 'text', or 'number'. 
                Defaults to 'confirm'.
            script_id (str, optional): The ID of the script requesting the feedback (if not given the objects given script_id will be used). 
            request_id (str, optional): A unique identifier for the feedback request. 
                If not provided, a new one will be generated.
            t_poll_sec (float, optional): The time (in seconds) to wait between polling 
                attempts for user feedback. Defaults to 2.0.
            verb (int, optional): The verbosity level for logging polling attempts. If 
                positive, a message will be logged every `verb` polls. Defaults to 0 
                (no logging).
            ret_all (bool, optional): set to True or 1 to return the raw response dict
                instead of a casted type.
            doc (Document, optional): A pydocmaker.Doc document to add to the post. If provided, the doc will be converted to HTML.

        Returns:
            Union[bool, str, int, float, dict]: The user feedback response, which can be a boolean,
            string, integer, float, or dictionary, depending on the request type. If `ret_all` is True,
            the raw response dictionary is returned instead.

        Raises:
            AssertionError: If the provided `request_type` is not a valid option.
        """

        if script_id is None:
            script_id = self.script_id

        if not request_id:
            request_id = get_uid(self, script_id)

        if device_id is None:
            device_id = self.device_id

        if script_uid is None:
            script_uid = self.script_uid

        allowed = 'confirm file files picture pictures text int float'.split()

        assert request_type in allowed, f'{request_type=} is not in {allowed=}'

        html = ''
        if not isinstance(msg, str) and hasattr(msg, 'to_html'):
            assert not doc, 'can not give doc and a doc as message!'
            html = msg.to_html()

        if doc:
            html = doc.to_html()
        
        route = f'/user_feedback/create'
        data = {
            'message': msg,
            'request_type': request_type,
            'id': request_id,
            'script_id': script_id,
            'script_uid': script_uid,
            'device_id': device_id,
        }

        if html:
            data["kwargs"] = {"html": html}

        log.info(f'Requesting User Feedback with {request_id=} {request_type=} and {script_uid=}|{script_id=}. Message = {limit_len(msg, 200)}')
        res = self.api.post(route, json=data, ret_raw=True).json()
        if use_polling:

            # HACK: hacky :-( should implement something fancy, but non blocking... for now leave like this
            route = f'/user_feedback/check'

            i = 0
            while 1:
                time.sleep(t_poll_sec)
                res = self.api.get(route, params={'id':request_id}, ret_raw=True).json()
                i += 1
                if verb and i % verb == 0:
                    log.info(f'get_user_feedback for id="{request_id}" still polling...')
                if res:
                    break
            r = res.get('request', {})
            a = res.get('answer', {})
            assert r, 'no data in response object'
            assert a, 'no answer in response object'
            assert r['id'] == a['id'], f"request id and answer id are different! This should not be the case! {r['id']=} {a['id']=}"
        else:
            global rapi
            if rapi is None:
                rapi = RedisApi()
            generator = rapi.listen_pubsub(rapi.subscribe_user_feedback_reply(), decode_type='json')
            a = next((a for a in generator if r['id'] == a['id']))

        request_type = r.get('request_type')

        success = a.get('success')
        assert success, f'user feedback gave error or was aborted! message: "{a["message"]}"'

        if request_type == 'confirm':
            ret = success
        elif request_type == 'text':
            ret = a.get('message')
        elif request_type == 'int':
            ret = int(a.get('message'))
        elif request_type == 'float':
            ret = float(a.get('message'))
        else:
            raise KeyError(f'{request_type=} is an unknown input. Allowed are {allowed=}')
        
        return res if ret_all else ret
    



if __name__ == '__main__': 

    import pydocmaker as pyd
    doc = pyd.DocBuilder()
    doc.add_md('asnjfabfliabfl')
     
    api = ServerApi('http://134.104.78.41:7990')
    res = api.upload_doc(doc, 'Example_Testrun_1', script_id=16)

    print(res)
    
    # self = 12
    # print(f'{iso_now()}_{id(self)}_{get_sys_id()}_{get_primary_ip()}')