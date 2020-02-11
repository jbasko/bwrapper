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
    queue = SqsQueue(url=os.environ["SQS_QUEUE_URL"])

    message = Greeting(attributes={"message": "Hello", "name": "world"})
    queue.send_message(message)


if __name__ == "__main__":
    main()
