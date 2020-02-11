import datetime as dt
import decimal
import json


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, dt.datetime):
            return str(obj)
        if isinstance(obj, decimal.Decimal):
            obj_str = str(obj)
            if "." in obj_str:
                return float(obj)
            else:
                return int(obj)
        return json.JSONEncoder.default(self, obj)


def to_json(obj, **kwargs):
    kwargs.setdefault("cls", JsonEncoder)
    if obj is None:
        return None
    return json.dumps(obj, **kwargs)


def from_json(obj_str: str, **kwargs):
    if obj_str is None:
        return None
    return json.loads(obj_str, **kwargs)
