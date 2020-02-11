import json
from typing import Dict, List

from bwrapper.sqs import SqsMessage


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
