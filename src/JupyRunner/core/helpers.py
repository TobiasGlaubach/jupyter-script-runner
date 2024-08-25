import re
import dateutil.parser, datetime, time, logging, sys

log = logging.getLogger()
level = logging.INFO
fmt = "[ %(levelname)s - %(asctime)s - %(name)s - %(filename)s:%(lineno)s] %(message)s"
frmatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S%z')
log.setLevel(level)
streamHandler = logging.StreamHandler(sys.stdout)

def tomorrow_iso(remove_ms = True):
    return make_zulustr(get_utcnow() + datetime.timedelta(hours=24), remove_ms=remove_ms)

def now_iso(remove_ms = True):
    return make_zulustr(get_utcnow(), remove_ms=remove_ms)

def iso_now(remove_ms = True):
    return now_iso(remove_ms)

def get_utcnow():
    return datetime.datetime.utcnow()#.replace(tzinfo=datetime.timezone.utc)

def limit_len(k, n_max =10, LR='L'):
    if k is None:
        return str(None)
    if LR == 'L':
        return k if len(k) < n_max else k[:n_max]+'...'
    else:
        return k if len(k) < n_max else '...' + k[-n_max:]
    

def make_zulustr(dtobj, remove_ms = True):
    utc = dtobj#.replace(tzinfo=datetime.timezone.utc)
    if remove_ms:
        utc = utc.replace(microsecond=0)
    return utc.isoformat().replace('+00:00','') + 'Z'

def mk_dtz(dtobj=None, remove_ms = True):
    if dtobj is None:
        dtobj = get_utcnow()
    return make_zulustr(dtobj, remove_ms).replace('T',' ').replace('Z',' ')

def match_zulutime(s):
    if s is None: return None

    s = s.strip()
    if '.' in s and re.match(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{1,6}Z', s) is not None:
        return s
    elif 'T' in s and re.match(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', s) is not None:
        return s
    elif re.match(r'[0-9]{4}-[0-9]{2}-[0-9]{2}Z', s) is not None:
        return s
    else:
        return None


def parse_zulutime(s):
    try:
        if re.match(r'[0-9]{4}-[0-9]{2}-[0-9]{2}Z', s) is not None:
            s = s[:-1] + 'T00:00:00Z'
        return dateutil.parser.isoparse(s) #.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None

def __get_starttime(row):
    if 'time_started_iso' in row and parse_zulutime(row['time_started_iso']):
        return parse_zulutime(row['time_started_iso'])
    elif parse_zulutime(row['start_condition']):
        return parse_zulutime(row['start_condition'])
    
def __get_endtime(row):
    if 'time_finished_iso' in row and match_zulutime(row['time_finished_iso']):
        return parse_zulutime(row['time_finished_iso'])
    elif 'end_condition' in row and parse_zulutime(row['end_condition']):
        return parse_zulutime(row['end_condition'])
    else:
        return parse_zulutime(row['start_condition']) + datetime.timedelta(minutes=30)


def split_flat_dict_into_nested(flat_dict):
  """
  Splits a flat dictionary with dotted keys into a nested dictionary.

  Args:
    flat_dict: The flat dictionary to split.

  Returns:
    The nested dictionary.
  """

  nested_dict = {}
  for key, value in flat_dict.items():
    keys = key.split('.')
    current_dict = nested_dict
    for k in keys[:-1]:
      if k not in current_dict:
        current_dict[k] = {}
      current_dict = current_dict[k]
    current_dict[keys[-1]] = value
  return nested_dict