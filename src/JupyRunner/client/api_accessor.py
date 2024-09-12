
import io
import mimetypes
import time
import requests, datetime, enum, re, dateutil, logging, sys

from typing import Any, Dict, List, Union



if __name__ == '__main__':
    import os, inspect, sys
    current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) 
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    print(parent_dir)
    sys.path.insert(0, parent_dir)
    

from JupyRunner.core.helpers import log, make_zulustr, parse_zulutime, iso_now, get_primary_ip, get_sys_id
    


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
        data = self._json(data)
        log.debug(f'PUT: {url} {data=}')
        response = self.session.put(url, json=json, headers=headers)
        response.raise_for_status()  # Raise an exception for error responses

        if ret_raw: 
            return response
        resp = response.json()
        self.validate(data, resp)
        return resp


    def post(self, endpoint, json=None, headers=None, ret_raw=False):
        url = self._url(endpoint)
        json = self._json(json)
        log.debug(f'POST: {url} {json=}')
        response = self.session.post(url, json=json, headers=headers)
        response.raise_for_status()  # Raise an exception for error responses
        if ret_raw: 
            return response
        resp = response.json()
        self.validate(json, resp)
        return resp
        

    def patch(self, endpoint, json:Dict[str, Any]|None=None, headers=None, ret_raw=False):
        url = self._url(endpoint)
        json = self._json(json)
        log.debug(f'POST: {url} {json=}')
        response = requests.patch(url, json=json, headers=headers)
        response.raise_for_status()  # Raise an exception for error responses
        if ret_raw: 
            return response
        resp = response.json()
        self.validate(json, resp)
        return resp
    


class ServerApi(object):
    def __init__(self, base_url, none_on_404=False) -> None:
        self.api = BaseAPIClient(base_url, none_on_404)

    def ping(self):
        r = self.api.get(f'/ping', ret_raw=True)
        return r.text
    
    def get_device(self, device_id):
        assert device_id, 'device_id can not be None or empty!'
        return self.api.get(f'device/{device_id}')
    
    def get_script(self, script_id):
        assert script_id, 'script_id can not be None or empty!'
        return self.api.get(f'script/{script_id}')


    def get_script_full(self, script_id):
        assert script_id, 'script_id can not be None or empty!'
        return self.api.get(f'script_full/{script_id}')


    def upload_file(self, script_id, filename:str, byte_data:bytes, mimetype=None):
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

        route = f'/action/script/{script_id}/upload/files'

        if isinstance(byte_data, str):
            byte_data = byte_data.encode()
        
        if not mimetype:
            mime, _ = mimetypes.guess_type(filename.split(".")[-1])[0]
            mimetype = 'application/octet-stream' if mime is None else mime

        # Send the request with bytes as a file
        files = {'files': (filename, io.BytesIO(byte_data), mimetype)}

        return self.api.post(route, files=files)
            

    def upload_files(self, script_id, files:Dict[str, Union[str, bytes]]):
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

        route = f'/action/script/{script_id}/upload/files'

        tuples = []
        for filename, byte_data in files:
            if isinstance(byte_data, str):
                byte_data = byte_data.encode()
            
            # Use the mimetypes module to guess the MIME type
            mime, _ = mimetypes.guess_type(filename.split(".")[-1])[0]
            mimetype = 'application/octet-stream' if mime is None else mime
                
            assert isinstance(byte_data, bytes), 'can only upload bytes or strings to the server!'
            tuples.append((filename, io.BytesIO(byte_data), mimetype))

        return self.api.post(route, files={'files': tuples})
            


    def upload_doc(self, doc, report_name='', script_id=None):
        """Uploads a document to the server.

        Args:
            doc (DocBuilder): The document to upload.
            report_name (str, optional): The name of the uploaded document. Defaults to a timestamp-based name assigned by the backend.
            script_id (int, optional): The script where this data is associated with or None for a loose document. Defaults to None.

        Returns:
            dict: The JSON response from the server after uploading the document.
        """
        url = f'/action/script/{script_id}/upload/doc' if script_id else '/doc/upload'
        return doc.upload(url, report_name)


    def get_user_feedback(self, msg, request_type='okcancle', script_id=None, request_id=None, t_poll_sec=2.0, verb=0, ret_all=False):
        """
        Gets user feedback through the API.

        This function retrieves user feedback for a given message and request type. It 
        makes a POST request to the `/user_feedback/create` endpoint to initiate the 
        feedback process and then polls the `/user_feedback/check` endpoint to 
        check for user response.

        Args:
            msg (str): The message to show the user for feedback.
            request_type (str, optional): The type of feedback request. Must be one of 
                'okcancle', 'file', 'files', 'picture', 'pictures', 'text', or 'number'. 
                Defaults to 'okcancle'.
            script_id (str, optional): The ID of the script requesting the feedback.
            request_id (str, optional): A unique identifier for the feedback request. 
                If not provided, a new one will be generated.
            t_poll_sec (float, optional): The time (in seconds) to wait between polling 
                attempts for user feedback. Defaults to 2.0.
            verb (int, optional): The verbosity level for logging polling attempts. If 
                positive, a message will be logged every `verb` polls. Defaults to 0 
                (no logging).
            ret_all (bool, optional): set to True or 1 to return the raw response dict
                instead of a casted type.

        Returns:
            dict: The user feedback response as a dictionary, or None if the user has 
                not responded within the polling loop.

        Raises:
            AssertionError: If the provided `request_type` is not a valid option.
        """

        if not request_id:
            request_id = f'{iso_now()}_{id(self)}_{get_sys_id()}_{get_primary_ip()}'
        allowed = 'confirm file files picture pictures text int float'.split()

        assert request_type in allowed, f'{request_type=} is not in {allowed=}'

        route = f'/user_feedback/create'
        data = {
            'message': msg,
            'request_type': request_type,
            'id': request_id,
            'script_id': script_id,
        }

        res = self.api.post(route, json=data, ret_raw=True).json()


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

    api = ServerApi('http://localhost:8000')
    result = api.get_user_feedback('Feel free to give any response...', ret_all=True)
    print(result)
    # self = 12
    # print(f'{iso_now()}_{id(self)}_{get_sys_id()}_{get_primary_ip()}')