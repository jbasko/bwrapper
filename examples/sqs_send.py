import argparse
import os

from bwrapper.sqs import SqsMessage, SqsQueue


class Greeting(SqsMessage):
    class MessageAttributes:
        message: str
        name: str


class Transaction(SqsMessage):
    class MessageAttributes:
        currency: str
        amount: int


def main():
    message_types = (Greeting, Transaction)

    parser = argparse.ArgumentParser(description="Send an SQS message of specified type")
    parser.add_argument("--type", choices=[mt.__name__ for mt in message_types], default=message_types[0].__name__)
    parser.add_argument("--attributes", help="Comma and column separated content e.g. message:hello,name:world")
    parser.add_argument("--body", help="Comma and column separated content e.g. message:hello,name:world")
    parser.add_argument("--queue-url", default=os.environ.get("SQS_QUEUE_URL"))
    args = parser.parse_args()

    queue = SqsQueue(url=args.queue_url)

    message_cls = next(mt for mt in message_types if mt.__name__ == args.type)
    attributes = {}
    body = {}

    if args.attributes:
        attributes = dict(x.split(":") for x in args.attributes.split(","))

    if args.body:
        body = dict(x.split(":") for x in args.body.split(","))

    message = message_cls(attributes=attributes, body=body)
    queue.send_message(message)
    print(f"Sent message: {message}")


if __name__ == "__main__":
    main()
