import json
from typing import Type

import pytest

from bwrapper.sns import SnsNotification


@pytest.fixture
def MyMessage() -> Type[SnsNotification]:
    class MyNotification(SnsNotification):
        class body:
            func: str

        class attributes:
            x: str
            y: int

    return MyNotification


def test_sns_message(MyMessage):
    msg = MyMessage(
        subject="Ha",
        topic_arn="arn:topic",
        attributes={"x": "12", "y": "34"},
        message_structure="json",
        body={"func": "do.something"},
    )
    assert msg.subject == "Ha"
    assert msg.topic_arn == "arn:topic"
    assert msg.attributes.x == "12"
    assert msg.attributes.y == 34

    assert msg.message_structure == "json"
    assert msg.message_attributes == {
        "x": {
            "DataType": "String",
            "StringValue": "12",
        },
        "y": {
            "DataType": "Number",
            "StringValue": "34",
        },
    }
    assert msg.message == json.dumps({"func": "do.something"}, sort_keys=True)


def test_from_raw_sns_dict(MyMessage):
    msg = MyMessage.from_sns_dict({
        "MessageStructure": "json",
        "Message": "{\"func\": \"do.something\"}",
        "TopicArn": "arn:topic",
        "Subject": "Ha",
        "MessageAttributes": {
            "x": {"DataType": "String", "StringValue": "12"},
            "y": {"DataType": "Number", "StringValue": "34"},
        },
    })

    assert msg.subject == "Ha"
    assert msg.topic_arn == "arn:topic"
    assert msg.body.func == "do.something"
    assert msg.attributes.x == "12"
    assert msg.attributes.y == 34


def test_plain_body():
    class PlainBodyNotification(SnsNotification):
        pass

    msg = PlainBodyNotification(message="Hello, world!")
    assert msg.message == "Hello, world!"

    with pytest.raises(AssertionError):
        msg.extract_body()
