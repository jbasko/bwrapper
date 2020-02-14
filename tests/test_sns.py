import json

from bwrapper.sns import SnsNotification


def test_sns_notification():
    notif = SnsNotification(
        subject="Ha",
        topic_arn="arn:topic",
        attributes={"x": "12", "y": 34},
        message={"default": "Do something!"},
    )
    assert notif.subject == "Ha"
    assert notif.topic_arn == "arn:topic"
    assert notif.attributes == {"x": "12", "y": 34}
    assert notif.message_structure == "json"
    assert notif.message == {"default": "Do something!"}

    assert notif.to_sns_dict() == {
        "TopicArn": "arn:topic",
        "Subject": "Ha",
        "MessageStructure": "json",
        "MessageAttributes": {
            "x": {
                "DataType": "String",
                "StringValue": "12",
            },
            "y": {
                "DataType": "Number",
                "StringValue": "34",
            },
        },
        "Message": json.dumps({"default": "Do something!"}, sort_keys=True),
    }


def test_from_sns_via_sqs_dict():
    notif = SnsNotification.from_sns_via_sqs_dict({
        "Type": "Notification",
        "MessageId": "42262d56-fe11-59ed-ad89-6b962104aeeb",
        "TopicArn": "arn:aws:sns:eu-west-1:1234:topic-name",
        "Subject": "This is the subject",
        "Message": "Sample message for Amazon SQS endpoints",
        "Timestamp": "2020-02-14T16:29:27.597Z",
        "SignatureVersion": "1",
        "Signature": "...",
        "SigningCertURL": "...",
        "UnsubscribeURL": "...",
        "MessageAttributes": {
            "x": {"Type": "Number", "Value": "12"},
            "y": {"Type": "String", "Value": "23"}
        },
    })
    assert isinstance(notif, SnsNotification)
    assert notif.subject == "This is the subject"
    assert notif.topic_arn == "arn:aws:sns:eu-west-1:1234:topic-name"
    assert notif.message == "Sample message for Amazon SQS endpoints"
    assert notif.attributes == {
        "x": "12",  # No type conversion, by design.
        "y": "23",
    }
