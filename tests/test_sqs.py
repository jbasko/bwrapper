import json
from typing import Dict, List

import pytest

from bwrapper.sqs import GenericSqsMessage, SqsMessage


def test_all():
    class JobMessage(SqsMessage):
        class MessageAttributes:
            job_id: str

        class MessageBody:
            uuid: str
            request: Dict

    class JobStatusMessage(SqsMessage):
        class MessageAttributes:
            job_id: str

        class MessageBody:
            uuid: str
            update: Dict

    assert JobMessage.MessageBody.schema == {
        "uuid": str,
        "request": Dict,
    }

    assert JobStatusMessage.MessageBody.schema == {
        "uuid": str,
        "update": Dict,
    }

    job = JobMessage({
        "MessageAttributes": {
            "job_id": {
                "DataType": "string",
                "StringValue": "123-456",
            },
        },
        "Body": json.dumps({
            "uuid": "1234-1234-1234-1234",
            "request": {
                "version": "JobRequest-1.0",
                "command": "bwrapper.providers.test.succeed",
            },
        }),
    })

    assert job.MessageAttributes.job_id == "123-456"
    assert job.MessageBody.uuid == "1234-1234-1234-1234"
    assert job.MessageBody.request["version"] == "JobRequest-1.0"
    assert job.MessageBody.request["command"] == "bwrapper.providers.test.succeed"

    sqs_dict = job.to_sqs_dict()
    assert sqs_dict["MessageAttributes"] == {
        "sqs_message_type": {
            "DataType": "String",
            "StringValue": "JobMessage",
        },
        "job_id": {
            "DataType": "String",
            "StringValue": "123-456",
        },
    }
    assert json.loads(sqs_dict["MessageBody"]) == {
        "uuid": "1234-1234-1234-1234",
        "request": {
            "version": "JobRequest-1.0",
            "command": "bwrapper.providers.test.succeed",
        },
    }

    # Make sure can write too
    job.MessageAttributes.job_id = "987-654"
    job.MessageBody.uuid = "8888-8888-8888-8888"
    job.MessageBody.request["command_params"] = {"period": "today"}

    assert job.MessageAttributes.job_id == "987-654"
    assert job.MessageBody.uuid == "8888-8888-8888-8888"

    sqs_dict = job.to_sqs_dict()
    assert sqs_dict["MessageAttributes"] == {
        "sqs_message_type": {
            "DataType": "String",
            "StringValue": "JobMessage",
        },
        "job_id": {
            "DataType": "String",
            "StringValue": "987-654",
        },
    }
    assert json.loads(sqs_dict["MessageBody"]) == {
        "uuid": "8888-8888-8888-8888",
        "request": {
            "version": "JobRequest-1.0",
            "command": "bwrapper.providers.test.succeed",
            "command_params": {
                "period": "today",
            },
        },
    }

    job2 = JobMessage()
    job2.MessageBody.uuid = "5555-5555"
    assert job2.MessageBody.uuid == "5555-5555"


def test_message_body_and_message_attributes_definitions_are_optional():
    class Message1(SqsMessage):
        pass

    class Message2(SqsMessage):
        class MessageBody:
            pass

    class Message3(SqsMessage):
        class MessageAttributes:
            pass

    Message1()
    Message2()
    Message3()


def test_message_attributes_from_dict():
    class Tx(SqsMessage):
        class MessageAttributes:
            currency: str
            amount: int

    tx: Tx = Tx(attributes={"currency": "GBP", "amount": 123})
    assert tx.MessageAttributes.currency == "GBP"
    assert tx.MessageAttributes.amount == 123


def test_message_body_from_dict():
    class Log(SqsMessage):
        class MessageBody:
            account: Dict
            transactions: List

    log: Log = Log(body={"account": {"name": "First"}, "transactions": [{"amount": 11}, {"amount": 20}]})
    assert log.MessageBody.account["name"] == "First"
    assert log.MessageBody.transactions[1]["amount"] == 20


def test_serialised_message_attributes_include_message_type():
    class Greeting(SqsMessage):
        class MessageAttributes:
            message: str

    greeting = Greeting(attributes={"message": "hello"})
    assert greeting.MessageAttributes.message == "hello"
    assert greeting.MessageAttributes.sqs_message_type == "Greeting"


def test_sqs_message_type_is_always_set():
    assert GenericSqsMessage().MessageAttributes.sqs_message_type == "GenericSqsMessage"
    assert GenericSqsMessage().to_sqs_dict()["MessageAttributes"]["sqs_message_type"] == {
        "DataType": "String",
        "StringValue": "GenericSqsMessage",
    }


def test_generic_sqs_message_accepts_anything():
    message = GenericSqsMessage(attributes={"a": 12, "b": "23"}, body={"c": 34, "d": "45"})
    assert message.MessageAttributes.a == 12
    assert message.MessageAttributes.b == "23"
    assert message.MessageBody.c == 34
    assert message.MessageBody.d == "45"


def test_unknown_fields_dont_raise_exception():
    class Message(SqsMessage):
        class MessageAttributes:
            message: str

    raw = {
        "MessageId": "9ac265aa-c50d-4846-a980-8b98e451627f",
        "ReceiptHandle": "blablabla",
        "MD5OfBody": "blablabla", "Body": "{}",
        "MD5OfMessageAttributes": "blablabla",
        "MessageAttributes": {
            "message": {"StringValue": "Hello", "DataType": "String"},
            "name": {"StringValue": "world", "DataType": "String"}
        }
    }

    message = Message(raw_sqs_message=raw)
    assert message.MessageAttributes.message == "Hello"
    assert not hasattr(message.MessageAttributes, "name")
    assert message.raw["MessageAttributes"]["name"] == {"StringValue": "world", "DataType": "String"}

    with pytest.raises(AttributeError):
        message.MessageAttributes.name = "Haha"

    dct = message.to_sqs_dict()
    assert dct["MessageAttributes"] == {
        "sqs_message_type": {"StringValue": "Message", "DataType": "String"},
        "message": {"StringValue": "Hello", "DataType": "String"},
    }


def test_unknown_fields_passed_as_attributes_or_body_raises_exception():
    # See also test_unknown_fields_dont_raise_exception

    class Message(SqsMessage):
        class MessageBody:
            subject: str

        class MessageAttributes:
            message: str

    with pytest.raises(AttributeError):
        Message(attributes={"title": "This is the title"})

    with pytest.raises(AttributeError):
        Message(body={"body": "This is the body"})


def test_int_and_bool_message_attributes():
    class Message(SqsMessage):
        class MessageAttributes:
            timeout: int
            validate: bool

    message = Message(attributes={"timeout": "123", "validate": 0})
    assert message.MessageAttributes.timeout == 123
    assert message.MessageAttributes.validate is False

    raw = {
        "MessageId": "9ac265aa-c50d-4846-a980-8b98e451627f",
        "ReceiptHandle": "blablabla",
        "MD5OfBody": "blablabla", "Body": "{}",
        "MD5OfMessageAttributes": "blablabla",
        "MessageAttributes": {
            "timeout": {"StringValue": "123", "DataType": "String"},
            "validate": {"StringValue": "True", "DataType": "String"},
        }
    }
    message = Message(raw_sqs_message=raw)
    assert message.MessageAttributes.timeout == 123
    assert message.MessageAttributes.validate is True
