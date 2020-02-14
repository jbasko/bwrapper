import json

from bwrapper.sns import SnsNotification
from bwrapper.sqs import SqsMessage


def test_to_sqs_dict():
    msg = SqsMessage(
        body="This is actually required",
        attributes={
            "x": 12,
            "y": "34",
            "z": True,
        },
        system_attributes={
            "AWSTraceHeader": "xyz",
        },
    )
    assert msg.body == "This is actually required"
    assert msg.attributes == {
        "x": 12,
        "y": "34",
        "z": True,
    }
    assert msg.system_attributes == {
        "AWSTraceHeader": "xyz",
    }

    assert msg.to_sqs_dict() == {
        "QueueUrl": None,
        "MessageBody": "This is actually required",
        "MessageAttributes": {
            "x": {
                "DataType": "Number",
                "StringValue": "12",
            },
            "y": {
                "DataType": "String",
                "StringValue": "34",
            },
            "z": {
                "DataType": "String",
                "StringValue": "True",
            },
        },
        "MessageSystemAttributes": {
            "AWSTraceHeader": {
                "DataType": "String",
                "StringValue": "xyz",
            },
        },
    }


def test_from_sqs_dict():
    raw = {
        "MessageId": "message-id",
        "ReceiptHandle": "receipt-handle",
        "MD5OfBody": "937291ea09c5c6979c06e41eaa070fb1",
        "Body": "This is the plain text body",
        "MD5OfMessageAttributes": "29571d39c72f098303b31901d2bebec0",
        "MessageAttributes": {
            "x": {"StringValue": "5", "DataType": "String"},
            "y": {"StringValue": "45", "DataType": "Number"},
            "z": {"StringValue": "ha", "DataType": "String"}
        }
    }

    msg = SqsMessage.from_sqs_dict(raw)
    assert msg.receipt_handle == "receipt-handle"
    assert msg.body == "This is the plain text body"
    assert msg.attributes == {
        "x": "5",
        "y": "45",  # No type conversions, by design
        "z": "ha",
    }


def test_from_sqs_dict_with_json_body():
    body = {"a": 123, "b": 456}
    raw = {
        "MessageId": "message-id",
        "ReceiptHandle": "receipt-handle",
        "MD5OfBody": "937291ea09c5c6979c06e41eaa070fb1",
        "Body": json.dumps(body, sort_keys=True),
        "MD5OfMessageAttributes": "29571d39c72f098303b31901d2bebec0",
        "MessageAttributes": {
            "x": {"StringValue": "5", "DataType": "String"},
            "y": {"StringValue": "45", "DataType": "Number"},
            "z": {"StringValue": "ha", "DataType": "String"}
        }
    }

    msg = SqsMessage.from_sqs_dict(raw)
    assert msg.receipt_handle == "receipt-handle"
    assert msg.body == body
    assert msg.attributes == {
        "x": "5",
        "y": "45",  # No type conversions, by design
        "z": "ha",
    }


def test_forwarded_sns_notification():
    msg = SqsMessage(body={
        "Type": "Notification",
        "MessageId": "message-id",
        "TopicArn": "arn:aws:sns:eu-west-1:123:topic-name",
        "Subject": "Are you listening?",
        "Message": "Some message",
        "Timestamp": "2020-02-14T17:56:10.035Z",
        "SignatureVersion": "1",
        "Signature": "...",
        "SigningCertURL": "...",
        "UnsubscribeURL": "...",
    })

    assert msg.is_sns_notification
    notif = msg.extract_sns_notification()
    assert isinstance(notif, SnsNotification)
    assert notif.subject == "Are you listening?"
    assert notif.message == "Some message"
