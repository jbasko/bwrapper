import json
from typing import Type

import pytest

from bwrapper.sns import SnsNotification


@pytest.fixture
def MyNotification() -> Type[SnsNotification]:
    class MyNotification(SnsNotification):
        class Body:
            func: str

        class Attributes:
            x: str
            y: int

    return MyNotification


def test_sns_notification(MyNotification):
    notif = MyNotification(
        subject="Ha",
        topic_arn="arn:topic",
        attributes={"x": "12", "y": "34"},
        message_structure="json",
        body={"func": "do.something"},
    )
    assert notif.subject == "Ha"
    assert notif.topic_arn == "arn:topic"
    assert notif.Attributes.x == "12"
    assert notif.Attributes.y == 34

    assert notif.message_structure == "json"
    assert notif.message_attributes == {
        "x": {
            "DataType": "String",
            "StringValue": "12",
        },
        "y": {
            "DataType": "Number",
            "StringValue": "34",
        },
    }
    assert notif.message == json.dumps({"func": "do.something"}, sort_keys=True)


def test_from_raw_sns_dict(MyNotification):
    notif = MyNotification.from_sns_dict({
        "MessageStructure": "json",
        "Message": "{\"func\": \"do.something\"}",
        "TopicArn": "arn:topic",
        "Subject": "Ha",
        "MessageAttributes": {
            "x": {"DataType": "String", "StringValue": "12"},
            "y": {"DataType": "Number", "StringValue": "34"},
        },
    })

    assert notif.subject == "Ha"
    assert notif.topic_arn == "arn:topic"
    assert notif.Body.func == "do.something"
    assert notif.Attributes.x == "12"
    assert notif.Attributes.y == 34


def test_plain_body():
    class PlainBodyNotification(SnsNotification):
        pass

    msg = PlainBodyNotification(message="Hello, world!")
    assert msg.message == "Hello, world!"

    with pytest.raises(AssertionError):
        msg.extract_body()
