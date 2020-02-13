import argparse
import logging

from bwrapper.boto import BotoMixin
from bwrapper.log import LogMixin
from bwrapper.sns import SnsMessage


class Notsy(BotoMixin, LogMixin):
    """
    A simple SNS notification publisher.
    """

    def __init__(self):
        super().__init__()

    def publish(self, notification: SnsMessage):
        self.sns.publish(**notification.to_sns_dict())
        self.log.info(f"Published notification {notification}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--topic-arn")
    parser.add_argument("--subject")
    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] [%(name)s] (%(funcName)s) %(message)s",
    )
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.INFO)

    notifier = Notsy()
    notifier.publish(SnsMessage(
        subject=args.subject,
        topic_arn=args.topic_arn,
    ))


if __name__ == "__main__":
    main()
