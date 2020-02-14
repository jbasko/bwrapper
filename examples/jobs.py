"""
A few dummy functions that bwrapper.jobsy can be tested with (if you have an SQS queue).

    python -m bwrapper.jobsy --enqueue examples.jobs.say_hello

Here's a way to test timing out:

    python -m bwrapper.jobsy --enqueue examples.jobs.wait --kwargs seconds:20 --timeout 5

Failure:

    python -m bwrapper.jobsy --enqueue examples.jobs.fail

"""
import time

from bwrapper.sqs import SqsMessage


def say_hello(name: str = "world"):
    print(f"Hello, {name}")


def wait(seconds: int = 10):
    print(f"Will wait for {seconds} seconds")
    time.sleep(seconds)
    print(f"Finished waiting, done now")


def fail():
    raise RuntimeError("I was asked to fail and so I do")


def handle_job(message: SqsMessage, **kwargs):
    """
    A function that handles all unrecognised messages (passed through as instances
    of GenericSqsMessage).
    Message handlers won't be functional as message.queue is not passed to the sub-process.
    """

    print("::: H A N D L I N G :::")
    print(message.__dict__)

    if message.is_sns_notification:
        print("\tThis is a SNS notification")
        print("\t\t", message.extract_sns_notification().__dict__)
