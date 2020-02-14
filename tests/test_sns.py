import json
from typing import Type

import pytest

from bwrapper.sns import GenericSnsNotification, SnsNotification


def test_sns_notification_basics():
    assert not SnsNotification.Attributes._definition.accepts_anything
    assert SnsNotification.Body._definition.accepts_anything


@pytest.fixture
def MyNotification() -> Type[SnsNotification]:
    class MyNotification(SnsNotification):
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
        body={"default": "Do something!"},
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
    assert notif.message == json.dumps({"default": "Do something!"}, sort_keys=True)


def test_from_raw_sns_dict(MyNotification):
    notif = MyNotification.from_sns_dict({
        "MessageStructure": "json",
        "Message": "{\"default\": \"Do something!\"}",
        "TopicArn": "arn:topic",
        "Subject": "Ha",
        "MessageAttributes": {
            "x": {"DataType": "String", "StringValue": "12"},
            "y": {"DataType": "Number", "StringValue": "34"},
        },
    })

    assert notif.subject == "Ha"
    assert notif.topic_arn == "arn:topic"
    assert notif.Body.default == "Do something!"
    assert notif.Attributes.x == "12"
    assert notif.Attributes.y == 34


def test_plain_body():
    class PlainBodyNotification(SnsNotification):
        pass

    msg = PlainBodyNotification(message="Hello, world!")
    assert msg.message == "Hello, world!"

    with pytest.raises(AssertionError):
        msg.extract_body()


def test_generic_sns_notification():
    notif = GenericSnsNotification(
        topic_arn="arn:topic",
        subject="The Subject",
        attributes={},
        body={
            "default": {
                "id": 123,
            },
            "something_else": "pure string",
        },
    )
    assert notif.Body.default == json.dumps({"id": 123})
    assert notif.Body.something_else == "pure string"
    assert notif.message_structure == "json"

    assert notif.to_sns_dict() == {
        "Subject": "The Subject",
        "TopicArn": "arn:topic",
        "MessageStructure": "json",
        "Message": json.dumps({
            "default": json.dumps({"id": 123}),
            "something_else": "pure string",
        }, sort_keys=True),
    }
