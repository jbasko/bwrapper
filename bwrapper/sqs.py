import abc
import json
import logging
from typing import Dict, Generator, List, Type, Union, get_type_hints
from uuid import uuid4

from bwrapper.boto import BotoMixin
from bwrapper.log import LogMixin

log = logging.getLogger(__name__)


class SqsMessage(abc.ABC):
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

    If a message class does not specify internal MessageBody or MessageAttributes classes,
    it means it accepts anything in that particular section.
    """

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

    class _BoundMessagePart:
        _internal_attrs = []
        _parsed_content_attr: str = None  # set in subclass

        def __init__(self, schema, instance):
            self._schema = schema
            self._instance: SqsMessage = instance

        def _has_attribute(self, name):
            if self._schema is None:
                return True
            return name in self._schema or name in self._internal_attrs

        def __getattr__(self, name):
            if not self._has_attribute(name):
                raise AttributeError(f"{self._instance.__class__.__name__!r} class does not have attribute {name!r}")
            return getattr(self._instance, self._parsed_content_attr).get(name)

        def __setattr__(self, name, value):
            if name.startswith("_"):
                return super().__setattr__(name, value)
            if not self._has_attribute(name):
                raise AttributeError(f"{self._instance.__class__.__name__} does not have attribute {name!r}")
            SqsMessage._validate_value_type(name, value)
            getattr(self._instance, self._parsed_content_attr)[name] = value

        def __repr__(self):
            return f"<{self.__class__.__name__} {getattr(self._instance, self._parsed_content_attr)}>"

    class _BoundMessageBody(_BoundMessagePart):
        _parsed_content_attr = "_parsed_body"

    class _BoundMessageAttributes(_BoundMessagePart):
        _internal_attrs = ("sqs_message_type",)
        _parsed_content_attr = "_parsed_attributes"

    class _MessageBody:
        def __init__(self, schema_type: Type = None):
            self.schema = None
            if schema_type:
                self.schema = get_type_hints(schema_type)

        def __get__(self, instance, owner):
            if instance is None:
                return self
            if not hasattr(instance, "_body"):
                setattr(instance, "_body", SqsMessage._BoundMessageBody(schema=self.schema, instance=instance))
            return getattr(instance, "_body")

    class _MessageAttributes:
        def __init__(self, schema_type: Type):
            self.schema = None
            if schema_type:
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

    def __init_subclass__(cls, **kwargs):
        cls.MessageBody = SqsMessage._MessageBody(getattr(cls, "MessageBody", None))
        cls.MessageAttributes = SqsMessage._MessageAttributes(getattr(cls, "MessageAttributes", None))

    def __init__(
        self,
        raw_sqs_message=None,
        receipt_handle: str = None,
        queue: "SqsQueue" = None,
        attributes: Dict = None,
        body: Dict = None,
        validate: bool = None,
    ):
        """
        By default, only attributes= and body= are validated against the schema.
        Raw SQS message is validated only as far as it concerns known fields.
        Unknown fields are set as given.
        """

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

        if not self._raw:
            setattr(self.MessageAttributes, "sqs_message_type", self.__class__.__name__)

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
            schema = self.MessageAttributes._schema
            if schema is None:
                for k, v_obj in self._raw_attributes.items():
                    if v_obj["DataType"] == "String":
                        parsed[k] = v_obj["StringValue"]
                    else:
                        parsed[k] = v_obj["BinaryValue"]
            else:
                for k, v in schema.items():
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

        attributes = {
            "sqs_message_type": {"DataType": "String", "StringValue": self.__class__.__name__},
        }
        if self.MessageAttributes._schema:
            schema_items = self.MessageAttributes._schema.items()
        else:
            schema_items = [(k, type(v)) for k, v in self._parsed_attributes.items()]

        for k, t in schema_items:
            if k not in self._parsed_attributes:
                continue
            if t not in self._message_attributes_types:
                raise RuntimeError(
                    f"Unsupported type in MessageAttributes schema of {self.__class__}: ({k!r}, {t})",
                )
            attributes[k] = {}
            if t is str:
                attributes[k]["DataType"] = "String"
            elif t is bytes:
                attributes[k]["DataType"] = "Binary"
            elif t in (int, float):
                attributes[k]["DataType"] = "String"
                attributes[k]["StringValue"] = str(self._parsed_attributes[k])
                continue

            attributes[k][self._message_attributes_types[t]] = self._parsed_attributes[k]

        return {
            "MessageAttributes": attributes,
            "MessageBody": json.dumps(self._parsed_body, sort_keys=True),
        }

    def delete(self):
        self._queue.delete_message(self.receipt_handle)

    def release(self):
        self._queue.release_message(self.receipt_handle)

    @property
    def raw(self) -> Dict:
        return self._raw

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.to_sqs_dict()}>"


class GenericSqsMessage(SqsMessage):
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
        message_cls: Union[Type[SqsMessage], List[Type[SqsMessage]]] = None,
        delete=False,
        max_num_messages=10,
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
            if "MessageAttributes" in raw_message and "sqs_message_type" in raw_message["MessageAttributes"]:
                raw_message_type_name = raw_message["MessageAttributes"]["sqs_message_type"]["StringValue"]
                if message_types:
                    if raw_message_type_name not in message_types:
                        self.log.info(f"Releasing message of type {raw_message_type_name!r}")
                        self.release_message(raw_message["ReceiptHandle"])
                        continue
                    else:
                        message_cls = message_types[raw_message_type_name]
                else:
                    message_cls = GenericSqsMessage
            else:
                if message_classes:
                    message_cls = message_classes[0]
                else:
                    message_cls = GenericSqsMessage

            message = message_cls(raw_message, receipt_handle=raw_message["ReceiptHandle"], queue=self)
            if delete:
                message.delete()
            yield message

    def delete_message(self, receipt_handle: str):
        self.sqs.delete_message(
            QueueUrl=self.url,
            ReceiptHandle=receipt_handle,
        )

    def release_message(self, receipt_handle: str):
        """
        Make the message immediately visible to other queue consumers.
        """
        self.sqs.change_message_visibility(
            QueueUrl=self.url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=0,
        )
