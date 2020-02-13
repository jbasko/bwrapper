import copy
import json
import logging
from typing import Any, Dict, Generator, Sequence, Type, Union
from uuid import uuid4

from bwrapper.boto import BotoMixin
from bwrapper.log import LogMixin
from bwrapper.type_hints_attrs import TypeHintsAttrs, _Attr

log = logging.getLogger(__name__)


class _SqsMessageBase:
    class MessageAttributes:
        pass

    class MessageBody:
        pass

    def __init_subclass__(cls, **kwargs):
        TypeHintsAttrs.init_for(target_cls=cls, name="MessageAttributes")
        TypeHintsAttrs.init_for(target_cls=cls, name="MessageBody")


class SqsMessage(_SqsMessageBase):
    """
    Base class for custom SQS messages.
    An SQS message class defines the accepted format of the message.

    Example:

        class Message(SqsMessage):
            class MessageAttributes:
                subject: str
            class MessageBody:
                body: str

    MessageAttributes can only be of primitive types.
    MessageBody can contain nested attributes (list, dict).

    """

    class MessageAttributes:
        sqs_message_type: str  # Internal attribute included in every message

    def __init__(
        self,
        *,
        receipt_handle: str = None,
        queue: "SqsQueue" = None,
        attributes: Dict = None,
        body: Dict = None,
    ):
        """
        By default, only attributes= and body= are validated against the schema.
        Raw SQS message is validated only as far as it concerns known fields.
        Unknown fields are set as given.
        """

        super().__init__()

        self.receipt_handle = receipt_handle

        self._raw: Dict = None

        # Only set for received messages
        self._queue: "SqsQueue" = queue

        if attributes:
            for k, v in attributes.items():
                setattr(self.MessageAttributes, k, v)

        if body:
            for k, v in body.items():
                setattr(self.MessageBody, k, v)

        if not self.MessageAttributes.sqs_message_type:
            self.MessageAttributes.sqs_message_type = self.__class__.__name__

    @classmethod
    def from_sqs_dict(cls, sqs_dict: Dict, queue: "SqsQueue" = None) -> "SqsMessage":
        instance = cls()
        instance.receipt_handle = sqs_dict.get("ReceiptHandle")
        instance._raw = copy.deepcopy(sqs_dict)
        if sqs_dict.get("MessageAttributes"):
            for k, v_dct in sqs_dict["MessageAttributes"].items():
                raw_value = v_dct.get("StringValue", v_dct.get("BinaryValue"))
                if k in instance.MessageAttributes:
                    attr = instance.MessageAttributes[k]
                    setattr(instance.MessageAttributes, attr.name, attr.parse(raw_value))
                elif instance.MessageAttributes._accepts_anything:
                    setattr(instance.MessageAttributes, k, raw_value)
        # For some stupid reason to send the message it is "MessageBody", yet in the received payload it is "Body".
        if sqs_dict.get("Body"):
            instance.MessageBody._update(**json.loads(sqs_dict["Body"]))
        instance._queue = queue
        return instance

    def to_sqs_dict(self) -> Dict:
        """
        Generate message in the SQS format.
        Note that the output of this is not acceptable by __init__ because boto
        expects "MessageBody" when sending a message and provides "Body" when receiving a message.
        """

        # accepts_anything setting is ignored here -- unknown items aren't serialised.

        attributes_dct = {}
        for attr_name in self.MessageAttributes:
            attr: _Attr = self.MessageAttributes[attr_name]
            value = getattr(self.MessageAttributes, attr.name)
            attributes_dct[attr.name] = self._serialise_attr(attr, value)

        body_dct = {}
        for attr_name in self.MessageBody:
            attr: _Attr = self.MessageBody[attr_name]
            value = getattr(self.MessageBody, attr.name)
            body_dct[attr.name] = value

        return {
            "MessageAttributes": attributes_dct,
            "MessageBody": json.dumps(body_dct, sort_keys=True),
        }

    def delete(self):
        self._queue.delete_message(receipt_handle=self.receipt_handle)

    def release(self):
        self._queue.release_message(receipt_handle=self.receipt_handle)

    def hold(self, timeout: int):
        self._queue.hold_message(receipt_handle=self.receipt_handle, timeout=timeout)

    @property
    def raw(self) -> Dict:
        return self._raw

    def extract_body(self) -> Dict:
        return self.MessageBody._extract_values()

    def extract_attributes(self) -> Dict:
        return self.MessageAttributes._extract_values()

    @classmethod
    def _parse_value(cls, value_type, value):
        if value is None or value == "None":
            return None
        if value_type in (int, float, str):
            return value_type(value)
        if value_type is bool:
            if isinstance(value, bool):
                return value
            if value in ("True", "true", "yes", "y", "1"):
                return True
            elif value in ("False", "false", "no", "n", "0"):
                return False
            return bool(value)
        return value

    def _serialise_attr(self, attr: _Attr, value: Any) -> Dict:
        s_type = "String"
        if attr.type is bytes:
            s_type = "Binary"
        elif not issubclass(attr.type, (int, float, str)):
            raise TypeError(
                f"Unsupported type for {attr}: {attr.type}"
            )

        if s_type == "Binary":
            return {
                "DataType": "Binary",
                "BinaryValue": value,
            }
        else:
            return {
                "DataType": "String",
                "StringValue": str(value),
            }

    def __repr__(self):
        return f"<{self.__class__.__name__} {str(self.receipt_handle)[:10]}...>"


class GenericSqsMessage(SqsMessage):
    """
    Special message class that can be used to represent message with any attributes and body content.
    """
    class MessageBody:
        accepts_anything = True

    class MessageAttributes:
        accepts_anything = True


class SqsQueue(LogMixin, BotoMixin):

    def __init__(self, url):
        self.url = url

    @property
    def is_fifo(self):
        return self.url.endswith(".fifo")

    def send_message(self, message: SqsMessage):
        self.log.info(f"Sending message to {self.url}")
        params = dict(
            QueueUrl=self.url,
            **message.to_sqs_dict(),
        )
        if self.is_fifo and "MessageGroupId" not in params:
            params["MessageGroupId"] = str(uuid4())
        try:
            self.sqs.send_message(**params)
        except Exception:
            self.log.error(f"Sending message {message} failed:")
            raise
        else:
            self.log.info("Message sent")

    def receive_message(self, message_cls: Type[SqsMessage], delete=False) -> SqsMessage:
        """
        Receive a single message and create an instance of the specified SqsMessage sub-class.
        Returns None if no messages were seen.
        """
        for message in self.receive_messages(message_cls, delete=delete, max_num_messages=1):
            return message

    def receive_messages(
        self,
        message_cls: Union[Type[SqsMessage], Sequence[Type[SqsMessage]]] = None,
        delete=False,
        max_num_messages=10,
        accept_all=False,
    ) -> Generator[SqsMessage, None, None]:
        """
        Receive multiple messages and yield them as instances of the specified
        SqsMessage subclass(-es).
        If the received message is of type not expected, the message will be immediately released
        by changing its visibility timeout to 0 so that other consumers can see it.
        Yields nothing if no messages were seen.
        """
        if message_cls:
            if isinstance(message_cls, type):
                message_classes = [message_cls]
            else:
                message_classes = message_cls
        else:
            message_classes = []
        message_types = {mc.__name__: mc for mc in message_classes}

        self.log.info(f"Polling {self.url} for message types [{', '.join(message_types)}], accept_all={accept_all}")
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
            receipt_handle = raw_message["ReceiptHandle"]

            if "MessageAttributes" in raw_message and "sqs_message_type" in raw_message["MessageAttributes"]:
                raw_message_type_name = raw_message["MessageAttributes"]["sqs_message_type"]["StringValue"]
                if message_types:
                    if raw_message_type_name not in message_types:
                        self.log.info(f"Releasing message of type {raw_message_type_name!r}")
                        self.release_message(receipt_handle=receipt_handle)
                        continue
                    else:
                        message_cls = message_types[raw_message_type_name]
                else:
                    self.log.debug(
                        f"Interpreting message of type {raw_message_type_name} as {GenericSqsMessage.__name__}"
                    )
                    message_cls = GenericSqsMessage
            elif message_types and not accept_all:
                self.log.info(f"Releasing message of unspecified type")
                self.release_message(receipt_handle=receipt_handle)
                continue
            else:
                self.log.debug(f"Interpreting message of unspecified type as {GenericSqsMessage.__name__}")
                message_cls = GenericSqsMessage

            message = message_cls.from_sqs_dict(
                raw_message,
                queue=self,
            )
            if delete:
                message.delete()
            yield message

    def delete_message(self, *, receipt_handle: str):
        self.sqs.delete_message(
            QueueUrl=self.url,
            ReceiptHandle=receipt_handle,
        )

    def change_visibility_timeout(self, *, receipt_handle: str, timeout: int):
        self.sqs.change_message_visibility(
            QueueUrl=self.url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=int(round(timeout)),
        )

    def release_message(self, *, receipt_handle: str):
        """
        Make the message immediately visible to other queue consumers.
        """
        self.change_visibility_timeout(receipt_handle=receipt_handle, timeout=0)

    def hold_message(self, *, receipt_handle: str, timeout: int):
        """
        Request the message to not be released for another `timeout` seconds.
        This is just an alias for change_visibility_timeout()
        """
        self.change_visibility_timeout(receipt_handle=receipt_handle, timeout=timeout)
