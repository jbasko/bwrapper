import json
from typing import Dict

from bwrapper.type_hints_attrs import TypeHintsAttrs, _Attr


class _SnsNotificationBase:
    class Attributes:
        pass

    class Body:
        pass

    def __init_subclass__(cls, **kwargs):
        TypeHintsAttrs.init_for(target_cls=cls, name="Attributes")
        TypeHintsAttrs.init_for(target_cls=cls, name="Body")


class SnsNotification(_SnsNotificationBase):
    topic_arn: str
    subject: str
    message_structure: str

    def __init__(
        self,
        *,
        topic_arn: str = None,
        subject: str = None,
        message_structure: str = None,
        message: str = None,
        attributes: Dict = None,
        body: Dict = None,
    ):
        super().__init__()

        self.topic_arn = topic_arn
        self.subject = subject
        self.message_structure = message_structure

        self._str_message = message

        if attributes:
            self.Attributes._update(**attributes)

        if body:
            self.Body._update(**body)

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
        for attr_name in self.Attributes:
            attr: _Attr = self.Attributes[attr_name]
            value = getattr(self.Attributes, attr.name)
            dct[attr.name] = self._serialise_attr(attr, value)
        return dct

    @property
    def message(self) -> str:
        if self.message_structure == "json":
            dct = {}
            for attr_name in self.Body:
                attr: _Attr = self.Body[attr_name]
                value = getattr(self.Body, attr.name)
                dct[attr.name] = value
            return json.dumps(dct, sort_keys=True)
        else:
            return self._str_message

    def extract_body(self) -> Dict:
        assert self.message_structure == "json"
        return self.Body._extract_values()

    def extract_attributes(self) -> Dict:
        return self.Attributes._extract_values()

    def to_sns_dict(self) -> Dict:
        assert self.message
        parts = [
            ("Message", self.message),
        ]
        if self.message_structure:
            parts.append(("MessageStructure", self.message_structure))
        if self.topic_arn:
            parts.append(("TopicArn", self.topic_arn))
        if self.subject:
            parts.append(("Subject", self.subject))
        if self.message_attributes:
            parts.append(("MessageAttributes", self.message_attributes))

        return dict(parts)

    @classmethod
    def from_sns_dict(cls, sns_dict: Dict) -> "SnsNotification":
        instance = cls()
        if "Subject" in sns_dict:
            instance.subject = sns_dict["Subject"]
        if "TopicArn" in sns_dict:
            instance.topic_arn = sns_dict["TopicArn"]

        if "MessageStructure" in sns_dict:
            instance.message_structure = sns_dict["MessageStructure"]

        attributes_key = "MessageAttributes"
        if "MessageAttributes" not in sns_dict and "Attributes" in sns_dict:
            attributes_key = "Attributes"
        if attributes_key in sns_dict:
            for k, v_dct in sns_dict[attributes_key].items():
                raw_value = v_dct.get("StringValue", v_dct.get("BinaryValue"))
                if k in instance.Attributes:
                    attr = instance.Attributes[k]
                    setattr(instance.Attributes, attr.name, attr.parse(raw_value))
                elif instance.Attributes._accepts_anything:
                    setattr(instance.Attributes, k, raw_value)

        body_key = "Message"
        if "Message" not in sns_dict and "Body" in sns_dict:
            body_key = "Body"
        if body_key in sns_dict and sns_dict[body_key]:
            if sns_dict.get("MessageStructure") == "json":
                instance.Body._update(**json.loads(sns_dict[body_key]))
            else:
                instance._str_message = sns_dict[body_key]

        return instance
