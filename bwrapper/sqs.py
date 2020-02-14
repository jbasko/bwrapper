import copy
import json
import logging
from typing import Any, Dict, Generator, Union

from bwrapper.boto import BotoMixin
from bwrapper.log import LogMixin

log = logging.getLogger(__name__)


class SqsMessage:
    def __init__(
        self,
        *,
        queue: "SqsQueue" = None,
        queue_url: str = None,
        body: Union[str, Dict] = None,
        delay_seconds: int = None,
        attributes: Dict = None,
        system_attributes: Dict = None,
        deduplication_id: str = None,
        group_id: str = None,
        receipt_handle: str = None,
    ):
        self._queue = queue
        self._queue_url = queue_url
        self.body = body
        self.delay_seconds = delay_seconds
        self.attributes = attributes
        self.system_attributes = system_attributes
        self.deduplication_id = deduplication_id
        self.group_id = group_id
        self.receipt_handle = receipt_handle

        self.raw: Dict = None

    @property
    def queue(self) -> "SqsQueue":
        if self._queue is None and self._queue_url:
            self._queue = SqsQueue(self._queue_url)
        return self._queue

    @property
    def queue_url(self) -> str:
        if self.queue:
            return self.queue.url

    @queue_url.setter
    def queue_url(self, value: str):
        if self.queue:
            self._queue = None
        self._queue_url = value

    def to_sqs_dict(self, **overrides) -> Dict:
        dct = {}

        attributes = overrides.pop("attributes", None) or self.attributes
        system_attributes = overrides.pop("system_attributes", None) or self.system_attributes

        dct["QueueUrl"] = self.queue_url
        dct["MessageBody"] = self.body
        if self.delay_seconds is not None:
            dct["DelaySeconds"] = self.delay_seconds
        if attributes:
            dct["MessageAttributes"] = {
                k: self._serialise_value(v)
                for k, v in attributes.items()
            }
        if system_attributes:
            dct["MessageSystemAttributes"] = {
                k: self._serialise_value(v)
                for k, v in system_attributes.items()
            }
        if self.deduplication_id:
            dct["MessageDeduplicationId"] = self.deduplication_id
        if self.group_id:
            dct["MessageGroupId"] = self.group_id

        dct.update(overrides)
        return dct

    def _serialise_value(self, value: Any) -> Dict:
        v_type = type(value)
        s_type = "Number" if v_type in (int, float) else "String"
        return {
            "DataType": s_type,
            "StringValue": str(value),  # None -> "None", True -> "True", etc.
        }

    @classmethod
    def from_sqs_dict(cls, dct: Dict, *, queue: "SqsQueue" = None) -> "SqsMessage":

        attributes = None
        raw_attributes = dct.get("MessageAttributes", None)
        if raw_attributes:
            attributes = {}
            for k, v_def in raw_attributes.items():
                attributes[k] = v_def["StringValue"]  # Don't do any type conversions, it's not our job

        raw_body = dct.get("Body")
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = raw_body

        instance = cls(
            queue=queue,
            body=body,
            attributes=attributes,
            receipt_handle=dct.get("ReceiptHandle"),
        )
        instance.raw = copy.deepcopy(dct)
        return instance

    def copy(self) -> "SqsMessage":
        assert self.raw
        return self.__class__.from_sqs_dict(self.raw)

    def hold(self, timeout: int):
        self.queue.hold_message(self, timeout=timeout)

    def delete(self):
        self.queue.delete_message(self)

    def release(self):
        self.queue.release_message(self)

    @property
    def is_sns_notification(self):
        return isinstance(self.body, dict) and self.body.get("Type") == "Notification"

    def extract_sns_notification(self):
        from bwrapper.sns import SnsNotification
        assert self.is_sns_notification
        return SnsNotification.from_sns_via_sqs_dict(self.body)


class SqsQueue(LogMixin, BotoMixin):

    def __init__(self, url):
        self.url = url

    @property
    def is_fifo(self):
        return self.url.endswith(".fifo")

    def send_message(self, message: SqsMessage):
        self.log.info(f"Sending {message} to {self.url}")
        try:
            self.sqs.send_message(**message.to_sqs_dict(QueueUrl=self.url))
        except Exception:
            self.log.error(f"Sending message {message} failed:")
            raise
        else:
            self.log.info("Message sent")

    def receive_message(self, delete=False) -> SqsMessage:
        """
        Returns None if no messages were seen.
        """
        for message in self.receive_messages(delete=delete, max_num_messages=1):
            return message

    def receive_messages(
        self,
        delete=False,
        max_num_messages=10,
    ) -> Generator[SqsMessage, None, None]:
        """
        Receive multiple messages and yield them as instances of SqsMessage class.
        """
        resp = self.sqs.receive_message(
            QueueUrl=self.url,
            MaxNumberOfMessages=max_num_messages,
            MessageAttributeNames=[
                "All",
            ],
            WaitTimeSeconds=20,
        )

        if "Messages" not in resp:
            self.log.info("No messages discovered")
            return

        for raw_message in resp["Messages"]:
            message = SqsMessage.from_sqs_dict(raw_message, queue=self)
            if delete:
                self.delete_message(message)
            yield message

    def delete_message(self, message: "SqsMessage"):
        self.sqs.delete_message(
            QueueUrl=self.url,
            ReceiptHandle=message.receipt_handle,
        )

    def change_visibility_timeout(self, *, message: "SqsMessage", timeout: int):
        self.sqs.change_message_visibility(
            QueueUrl=self.url,
            ReceiptHandle=message.receipt_handle,
            VisibilityTimeout=int(round(timeout)),
        )

    def release_message(self, message: "SqsMessage"):
        """
        Make the message immediately visible to other queue consumers.
        """
        self.change_visibility_timeout(message=message, timeout=0)

    def hold_message(self, message: "SqsMessage", *, timeout: int):
        """
        Request the message to not be released for another `timeout` seconds.
        This is just an alias for change_visibility_timeout()
        """
        self.change_visibility_timeout(message=message, timeout=timeout)
