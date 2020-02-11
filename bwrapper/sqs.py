import abc
import json
import logging
from typing import Dict, Generator, Type, get_type_hints
from uuid import uuid4

from bwrapper.boto import BotoMixin
from bwrapper.log import LogMixin

log = logging.getLogger(__name__)


class SqsMessage(abc.ABC):
    _message_attributes_types: Dict[Type, str] = {
        str: "StringValue",
        int: "StringValue",
        float: "StringValue",
        bytes: "BinaryValue",
    }

    # Do not allow setting any attribute or body value to something
    # whose type isn't in this list. Derived classes are no good
    # because the values need to be JSON-serialisable.
    _exact_valid_value_types = (
        str,
        dict,
        list,
        int,
        bool,
        float,
    )

    @classmethod
    def _validate_value_type(cls, name, value):
        if value is None:
            return

        value_type = type(value)
        if value_type not in SqsMessage._exact_valid_value_types:
            raise TypeError((name, type(value), value))

        if isinstance(value, dict):
            for k, v in value.items():
                SqsMessage._validate_value_type(f"{name}[{k!r}]", v)

        elif isinstance(value, list):
            for i, v in enumerate(value):
                SqsMessage._validate_value_type(f"{name}[{i}]", v)

    class _BoundMessageBody:
        def __init__(self, schema, instance):
            self._schema = schema
            self._instance: SqsMessage = instance

        def __getattr__(self, name):
            if name not in self._schema:
                raise AttributeError(name)
            return self._instance._parsed_body.get(name)

        def __setattr__(self, name, value):
            if name.startswith("_"):
                return super().__setattr__(name, value)
            if name not in self._schema:
                raise AttributeError(name)
            SqsMessage._validate_value_type(name, value)
            self._instance._parsed_body[name] = value

        def __repr__(self):
            return f"<{self.__class__.__name__} {self._instance._parsed_body}>"

    class _BoundMessageAttributes:
        def __init__(self, schema, instance):
            self._schema = schema
            self._instance: SqsMessage = instance

        def __getattr__(self, name):
            if name not in self._schema:
                raise AttributeError(name)
            return self._instance._parsed_attributes.get(name)

        def __setattr__(self, name, value):
            if name.startswith("_"):
                return super().__setattr__(name, value)
            if name not in self._schema:
                raise AttributeError(name)
            SqsMessage._validate_value_type(name, value)
            self._instance._parsed_attributes[name] = value

        def __repr__(self):
            return f"<{self.__class__.__name__} {self._instance._parsed_attributes}>"

    class _MessageBody:
        def __init__(self, schema_type: Type):
            self.schema = get_type_hints(schema_type)

        def __get__(self, instance, owner):
            if instance is None:
                return self
            if not hasattr(instance, "_body"):
                setattr(instance, "_body", SqsMessage._BoundMessageBody(schema=self.schema, instance=instance))
            return getattr(instance, "_body")

    class _MessageAttributes:
        def __init__(self, schema_type: Type):
            self.schema = get_type_hints(schema_type)

        def __get__(self, instance, owner):
            if instance is None:
                return self.schema
            if not hasattr(instance, "_attributes"):
                setattr(
                    instance, "_attributes",
                    SqsMessage._BoundMessageAttributes(schema=self.schema, instance=instance),
                )
            return getattr(instance, "_attributes")

    class _UnspecifiedMessageBody:
        pass

    class _UnspecifiedMessageAttributes:
        pass

    def __init_subclass__(cls, **kwargs):
        cls.MessageBody = SqsMessage._MessageBody(
            getattr(cls, "MessageBody", SqsMessage._UnspecifiedMessageBody),
        )
        cls.MessageAttributes = SqsMessage._MessageAttributes(
            getattr(cls, "MessageAttributes", SqsMessage._UnspecifiedMessageAttributes),
        )

    def __init__(
        self,
        raw_sqs_message=None,
        receipt_handle: str = None,
        queue: "SqsQueue" = None,
        attributes: Dict = None,
        body: Dict = None
    ):
        self.receipt_handle = receipt_handle
        self._raw = raw_sqs_message
        self._raw_body = None
        self._raw_attributes = {}
        if self._raw:
            self._raw_body = self._raw["Body"]
            self._raw_attributes = self._raw.get("MessageAttributes", None) or {}
        self._parsed_body_obj = None
        self._parsed_attributes_obj = None

        # Only set for received messages
        self._queue: "SqsQueue" = queue

        if attributes:
            for k, v in attributes.items():
                setattr(self.MessageAttributes, k, v)

        if body:
            for k, v in body.items():
                setattr(self.MessageBody, k, v)

    @property
    def _parsed_body(self) -> Dict:
        if self._parsed_body_obj is None:
            if self._raw_body:
                self._parsed_body_obj = json.loads(self._raw_body)
            else:
                self._parsed_body_obj = {}
        return self._parsed_body_obj

    @property
    def _parsed_attributes(self) -> Dict:
        if self._parsed_attributes_obj is None:
            parsed = {}
            for k, v in self.MessageAttributes._schema.items():
                if v not in self._message_attributes_types:
                    raise RuntimeError(
                        f"Unsupported type in MessageAttributes schema of {self.__class__}: ({k!r}, {v})",
                    )
                if k in self._raw_attributes:
                    parsed[k] = self._raw_attributes[k][self._message_attributes_types[v]]
            self._parsed_attributes_obj = parsed
        return self._parsed_attributes_obj

    def to_sqs_dict(self) -> Dict:
        """
        Generate message in the SQS format.
        Note that the output of this is not acceptable by __init__ because boto
        expects "MessageBody" when sending a message and provides "Body" when receiving a message.
        """

        attributes = {}
        for k, v in self.MessageAttributes._schema.items():
            if k not in self._parsed_attributes:
                continue
            if v not in self._message_attributes_types:
                raise RuntimeError(
                    f"Unsupported type in MessageAttributes schema of {self.__class__}: ({k!r}, {v})",
                )
            attributes[k] = {}
            if v is str:
                attributes[k]["DataType"] = "String"
            elif v is bytes:
                attributes[k]["DataType"] = "Binary"
            else:
                assert False
            attributes[k][self._message_attributes_types[v]] = self._parsed_attributes[k]

        return {
            "MessageAttributes": attributes,
            "MessageBody": json.dumps(self._parsed_body, sort_keys=True),
        }

    def delete(self):
        self._queue.delete_message(self.receipt_handle)

    @property
    def raw(self) -> Dict:
        return self._raw

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.to_sqs_dict()}>"


class GenericSqsMessage(SqsMessage):

    class MessageAttributes:
        pass

    class MessageBody:
        pass


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
        message_cls: Type[SqsMessage] = GenericSqsMessage,
        delete=False,
        max_num_messages=10,
    ) -> Generator[SqsMessage, None, None]:
        """
        Receive multiple messages and yield them as instances of the specified
        SqsMessage sub-class.
        Yields nothing if no messages were seen.
        """
        self.log.info(f"Polling {self.url}")
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
            message = message_cls(raw_message, receipt_handle=raw_message["ReceiptHandle"], queue=self)
            if delete:
                message.delete()
            yield message

    def delete_message(self, receipt_handle: str):
        self.sqs.delete_message(
            QueueUrl=self.url,
            ReceiptHandle=receipt_handle,
        )
