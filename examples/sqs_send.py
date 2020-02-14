import argparse
import os

from bwrapper.sqs import SqsMessage, SqsQueue


def main():
    parser = argparse.ArgumentParser(description="Send an SQS message of specified type")
    parser.add_argument("--attributes", help="Comma and column separated content e.g. message:hello,name:world")
    parser.add_argument("--body")
    parser.add_argument("--queue-url", default=os.environ.get("SQS_QUEUE_URL"))
    args = parser.parse_args()

    queue = SqsQueue(url=args.queue_url)

    attributes = {}
    if args.attributes:
        attributes = dict(x.split(":") for x in args.attributes.split(","))
    message = SqsMessage(attributes=attributes, body=args.body)
    queue.send_message(message)
    print(f"Sent message: {message}")


if __name__ == "__main__":
    main()
