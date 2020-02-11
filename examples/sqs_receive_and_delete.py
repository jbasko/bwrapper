import os

from bwrapper.sqs import SqsMessage, SqsQueue


class Greeting(SqsMessage):
    class MessageAttributes:
        message: str
        name: str


def main():
    queue = SqsQueue(url=os.environ["SQS_QUEUE_URL"])
    for message in queue.receive_messages(message_cls=Greeting):
        print("MessageAttributes", message.MessageAttributes)
        print("MessageBody", message.MessageBody)
        print("raw:", message.raw)
        message.delete()


if __name__ == "__main__":
    main()
