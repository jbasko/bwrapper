import argparse
import os

from bwrapper.sqs import SqsQueue


def main():
    parser = argparse.ArgumentParser(description="Receive and delete SQS messages")
    parser.add_argument("--queue-url", default=os.environ.get("SQS_QUEUE_URL"))
    args = parser.parse_args()

    queue = SqsQueue(url=args.queue_url)

    for message in queue.receive_messages():

        print("message.attributes", message.attributes)
        print("message.body", message.body)
        queue.delete_message(message)


if __name__ == "__main__":
    main()
