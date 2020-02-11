import argparse
import os

from bwrapper.sqs import GenericSqsMessage, SqsMessage, SqsQueue


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

    parser = argparse.ArgumentParser(description="Receive and delete SQS messages of any or specified type")
    parser.add_argument(
        "--type",
        choices=[mt.__name__ for mt in message_types],
        help="Defaults to GenericSqsMessage which allows receiving all messages",
    )
    parser.add_argument("--queue-url", default=os.environ.get("SQS_QUEUE_URL"))
    args = parser.parse_args()

    if args.type:
        message_cls = next(mt for mt in message_types if mt.__name__ == args.type)
    else:
        message_cls = GenericSqsMessage

    queue = SqsQueue(url=args.queue_url)

    for message in queue.receive_messages(message_cls=message_cls):
        print("MessageAttributes", message.MessageAttributes)
        print("MessageBody", message.MessageBody)
        print("raw:", message.raw)
        message.delete()


if __name__ == "__main__":
    main()
