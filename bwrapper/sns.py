import json
from typing import Dict

from bwrapper.type_hints_attrs import TypeHintsAttrs, _Attr


class _SnsMessageBase:
    class attributes:
        pass

    class body:
        pass

    def __init_subclass__(cls, **kwargs):
        TypeHintsAttrs.init_for(target_cls=cls, name="attributes")
        TypeHintsAttrs.init_for(target_cls=cls, name="body")


class SnsMessage(_SnsMessageBase):
    topic_arn: str = None
    subject: str = None
    message_structure: str = None

    def __init__(
        self,
        *,
        topic_arn: str = None,
        subject: str = None,
        attributes: Dict = None,
        body: Dict = None,
    ):
        super().__init__()

        self.topic_arn = topic_arn
        self.subject = subject

        if attributes:
            self.attributes._update(**attributes)

        if body:
            self.body._update(**body)

    @classmethod
    def _serialise_attr(cls, attr: _Attr, value):
        s_type = "Number" if attr.type in (int, float) and isinstance(value, (int, float)) else "String"
        if attr.type in (int, bool, float, str):  # None is serialised as "None"
            s_value = str(value)
        else:
            raise ValueError(f"Unsupported value type {attr.type}")
        return {
            "DataType": s_type,
            "StringValue": s_value,
        }

    @property
    def message_attributes(self) -> Dict:
        """
        The serialised form of message attributes
        """
        dct = {}
        for attr_name in self.attributes:
            attr: _Attr = self.attributes[attr_name]
            value = getattr(self.attributes, attr.name)
            dct[attr.name] = self._serialise_attr(attr, value)
        return dct

    @property
    def message(self) -> str:
        dct = {}
        for attr_name in self.body:
            attr: _Attr = self.body[attr_name]
            value = getattr(self.body, attr.name)
            dct[attr.name] = value
        return json.dumps(dct, sort_keys=True)

    def to_sns_dict(self) -> Dict:
        parts = [
            ("Message", self.message),
        ]
        if self.topic_arn:
            parts.append(("TopicArn", self.topic_arn))
        if self.subject:
            parts.append(("Subject", self.subject))
        if self.message_structure:
            parts.append(("MessageStructure", self.message_structure))
        if self.message_attributes:
            parts.append(("MessageAttributes", self.message_attributes))

        return dict(parts)

    @classmethod
    def from_sns_dict(cls, sns_dict: Dict) -> "SnsMessage":
        instance = cls()
        if "Subject" in sns_dict:
            instance.subject = sns_dict["Subject"]
        if "TopicArn" in sns_dict:
            instance.topic_arn = sns_dict["TopicArn"]
        if "Message" in sns_dict and sns_dict["Message"]:
            instance.body._update(**json.loads(sns_dict["Message"]))
        if "MessageAttributes" in sns_dict:
            for k, v_dct in sns_dict["MessageAttributes"].items():
                raw_value = v_dct.get("StringValue", v_dct.get("BinaryValue"))
                if k in instance.attributes:
                    attr = instance.attributes[k]
                    setattr(instance.attributes, attr.name, attr.parse(raw_value))
                elif instance.attributes._accepts_anything:
                    setattr(instance.attributes, k, raw_value)
        return instance
