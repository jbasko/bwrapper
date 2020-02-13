"""
A few dummy functions that bwrapper.jobsy can be tested with (if you have an SQS queue).

    python -m bwrapper.jobsy --enqueue examples.jobs.say_hello

Here's a way to test timing out:

    python -m bwrapper.jobsy --enqueue examples.jobs.wait --kwargs seconds:20 --timeout 5

Failure:

    python -m bwrapper.jobsy --enqueue examples.jobs.fail

"""
import time

from bwrapper.sns import SnsMessage
from bwrapper.sqs import GenericSqsMessage


def say_hello(name: str = "world"):
    print(f"Hello, {name}")


def wait(seconds: int = 10):
    print(f"Will wait for {seconds} seconds")
    time.sleep(seconds)
    print(f"Finished waiting, done now")


def fail():
    raise RuntimeError("I was asked to fail and so I do")


def accept_all_handler(message: GenericSqsMessage, **kwargs):
    """
    A function that handles all unrecognised messages (passed through as instances
    of GenericSqsMessage).
    Message handlers won't be functional as message._queue is not passed to the sub-process.
    """
    body = message.body
    attributes = message.extract_attributes()

    if isinstance(body, dict) and body.get("Type") == "Notification":
        print("Got keys: ", ", ".join(body))

        notification = SnsMessage.from_sns_dict(body)
        print(f"Recognised SNS notification: {notification}")
        print(f"\tTopic: {notification.topic_arn}")
        print(f"\tSubject: {notification.subject}")
        print(f"\tAttributes:")
        for k, v in notification.extract_attributes().items():
            print(f"\t\t{k}: {v}")
        print(f"\tBody:")
        if notification.message_structure == "json":
            for k, v in notification.extract_body().items():
                print(f"\t\t{k}: {v}")
        else:
            print(f"\t\t({type(body)}) {body}")
        print(f"Finished\n")
    else:
        print(f"Starting to work on message {message.receipt_handle[:10]}...")
        print(f"\tAttributes:")
        for k, v in attributes.items():
            print(f"\t\t{k}: {v}")
        print(f"\tBody:")
        if isinstance(body, dict):
            for k, v in body.items():
                print(f"\t\t{k}: {v}")
        else:
            print(f"\t\t{body}")
        print(f"Finished\n")
