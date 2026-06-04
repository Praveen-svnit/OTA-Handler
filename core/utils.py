import re
import json


def norm_id(v):
    s = str(v if v is not None else '').strip()
    return re.sub(r'\.0+$', '', s)


def parse_pms_rate(val):
    val = str(val or '')
    p = val.split('-')
    return {
        'propId':   norm_id(p[0]) if len(p) > 0 else '',
        'roomType': norm_id(p[1]) if len(p) > 1 else '',
        'rateCode': norm_id(p[2]) if len(p) > 2 else '',
        'suffix':   '-'.join(p[3:]) if len(p) > 3 else '',
        'raw':      val,
    }


def parse_pms_room(val):
    val = str(val or '')
    p = val.split('-')
    return {
        'propId':   norm_id(p[0]) if len(p) > 0 else '',
        'roomType': norm_id(p[1]) if len(p) > 1 else '',
        'raw':      val,
    }


def parse_obp(val):
    if val is None or str(val).strip() in ('', 'nan', 'None'):
        return {}
    try:
        obj = json.loads(str(val))
        return {str(k): v for k, v in obj.items()} if isinstance(obj, dict) else {}
    except Exception:
        return {}


def auto_detect(columns, *hint_groups):
    """Return the first column whose name contains all keywords in any hint group."""
    cols_lower = [(c, c.lower()) for c in columns]
    for hints in hint_groups:
        hints_l = [h.lower() for h in hints]
        for col, col_l in cols_lower:
            if all(h in col_l for h in hints_l):
                return col
    return None
