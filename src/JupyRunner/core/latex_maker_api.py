


import warnings
import requests
import socket
import enum
import json
import os
import shlex


import requests, json, base64

url = None
has_api_connection = None

def test_has_api_connection():
    global url, has_api_connection
    r = requests.get(url) # ping
    has_api_connection = r.status_code == 200
        

def setup(config=None):
    global url
    url = os.environ.get('LATEXMAKE_URL', 'http://134.104.78.41:1434/api/v1').rstrip('/')
    test_has_api_connection()

def start(config):
    pass


def compile_report(doc, template_id=None, template_params=None, docname='auto', input_format='pydocmaker', attachments_dc=None, raise_for_unknown_params=False, latex_compiler='pdflatex', ignore_error=True):

    if not attachments_dc:
        attachments_dc = {}

    fun = lambda v: base64.b64encode(v) if isinstance(v, bytes) else base64.b64encode(v.encode('utf-8'))

    attachments_dc = {k:fun(v) for k, v in attachments_dc.items()}

    if not isinstance(doc, list) and hasattr(doc, 'dump'):
        doc = doc.dump()
        
    kwargs = dict(
        doc_in = doc, 
        input_format=input_format, 
        template_id=template_id, 
        attachments_dc = attachments_dc, # b64 encoded files if applicable
        template_params = template_params,
        docname = docname, # sets the document name automatically based on "my_params"
        raise_for_unknown_params = raise_for_unknown_params, 
        latex_compiler = latex_compiler,
        ignore_error = ignore_error, 
    )


    r = requests.post(url + f'/report/compile', json=kwargs)
    r.raise_for_status()

    # {'success': 1, 'ret_format': oformat, 'file_uid': file_uid, 'link': lnk, 'is_b64': is_b64, "data": data}
    dc = r.json()
    
    if not dc.get('success', ''):
        err = dc.get('error', dc.get('err', dc.get('errors', '')))
        warnings.warn(f'Compilation did not succeed! error message: {err=}')

    b64 = dc.pop('data', '')
    document_as_bytes = base64.b64decode(b64)

    return dc, document_as_bytes


def get_available_templates():
    return requests.get(url + '/template/get_available').json()

def get_template_params(template_id):
    return requests.get(url + f'/template/{template_id}/params').json()

def get_example():
    return requests.get(url + f'/doc/example').json()

if __name__ == '__main__':
    

    setup()

    template = 'inaf'
    my_doc = get_example()

    my_params = {
        'project': "INAF MeerKAT Band5b Receiver",
        'title': "My Example Document",
        'DocNo': "MK-B5bRx-0000-123-ABC",
        'Revision': "A",
        'Status': "Draft",  # or "Released" or any other status
        'Date': "",  # or any date
        "Author": "Automatically Generated",
        "ApprovedBy": "Peter Pan \\par (Lost Child)",
        "ReleasedBy": "Capitain Hook \\par (Pirate)",
        'confidential': True,  # or True if the document is confidential
        'projectLogo': "\\parbox[b]{3.2cm}{\\vspace{.2cm}\\includegraphics[width=3cm,angle=0]{INAF-Logo.png}\\vspace{-1ex}}",
        "purpose": "",
        "scope": "",
        "acronyms": {
            "SOW": "Statement Of Work",
            "FTE": "Full Time Equivalent",
            "WP": "Work-Package",
            "LNA": "Low Noise Amplifier",
            "WBS": "Work Breakdown Structure",
            "INAF": "National Institute for Astrophysics",
            "RSF": "Receiver Support Frame",
            "PFS": "Passive Feed System",
            "RFS": "Radio-Frequency warm Section",
            "RXC": "Receiver Controller"
        },
        "references": {
            "sow": "INAF Tender document: MeerKAT Band 5b Receivers Technical Specification, V0.1, Relesaed 2024-02-29",
            "Management-Plan": "MPIfR Management Plan (MK-B5bRx-1110-001-PLA)",
            "techDescription": "System design description (MK-B5bRx-2310-001-DSN)",
            "WBS": "WBS (MK-B5bRx-1120-00-001-DRW)",
            "PBS": "PBS (MK-B5bRx-1120-00-002-PBS)",
            "WPD1000": "Workpackage Description (MK-B5bRx-1000-001-WBS)",
            "WPD2000": "Workpackage Description (MK-B5bRx-2000-001-WBS)",
            "WPD3000": "Workpackage Description (MK-B5bRx-3000-001-WBS)",
            "WPD4000": "Workpackage Description (MK-B5bRx-4000-001-WBS)",
            "WPD5000": "Workpackage Description (MK-B5bRx-5000-001-WBS)",
            "PFSDesign": "PFS design description (MK-B5bRx-2420-001-DSN)",
            "SystemDesign": "Receiver system design description (MK-B5bRx-2400-001-DSN)",
        }
    }

    dc, data_bytes = compile_report(my_doc, template, my_params)

    print(dc)
    print(len(data_bytes))

    print(dc.get('file_name', '')[:-4])