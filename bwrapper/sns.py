import json
from typing import Any, Dict, Union


class SnsNotification:
    def __init__(
        self,
        *,
        message: Union[Dict, str],
        topic_arn: str = None,
        target_arn: str = None,
        phone_number: str = None,
        subject: str = None,
        attributes: Dict = None,
    ):
        self._message = None
        self.topic_arn = topic_arn
        self.target_arn = target_arn
        self.phone_number = phone_number
        self.subject = subject
        self.attributes = attributes

        self.message = message

    def to_sns_dict(self) -> Dict:
        """
        Convert to a dictionary whose contents can be passed as kwargs to
        boto3 sns client's publish method.
        """

        is_json = isinstance(self._message, dict)
        dct = {
            "Message": json.dumps(self._message, sort_keys=True) if is_json else self._message,
        }
        if is_json:
            dct["MessageStructure"] = "json"
        if self.attributes:
            dct["MessageAttributes"] = {
                k: self._serialise_value(v)
                for k, v in self.attributes.items()
            }
        if self.topic_arn:
            dct["TopicArn"] = self.topic_arn
        if self.target_arn:
            dct["TargetArn"] = self.target_arn
        if self.phone_number:
            dct["PhoneNumber"] = self.phone_number
        if self.subject:
            dct["Subject"] = self.subject
        return dct

    @classmethod
    def from_sns_via_sqs_dict(cls, dct) -> "SnsNotification":
        """
        Parse the dictionary that you get as MessageBody in SQS when forwarding
        an SNS notification to SQS.
        """
        attributes = None
        if "MessageAttributes" in dct:
            attributes = {}
            for k, v_def in dct["MessageAttributes"].items():
                attributes[k] = v_def["Value"]  # Don't do any type conversions, not our job
        return cls(
            topic_arn=dct.get("TopicArn"),
            subject=dct.get("Subject"),
            message=dct["Message"],
            attributes=attributes,
        )

    @property
    def message(self) -> Union[Dict, str]:
        return self._message

    @message.setter
    def message(self, value: Union[Dict, str]):
        if not isinstance(value, (str, Dict)):
            raise TypeError(type(value))
        self._message = value

    @property
    def message_structure(self):
        if isinstance(self._message, dict):
            return "json"
        return None

    def _serialise_value(self, value: Any):
        v_type = type(value)
        s_type = "Number" if v_type in (int, float) else "String"
        return {
            "DataType": s_type,
            "StringValue": str(value),  # None -> "None", True -> "True", etc.
        }
