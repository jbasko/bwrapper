import boto3
from botocore.config import Config


class Boto:
    """
    Namespace for all boto3 clients.
    """

    class ClientOrResource:
        def __init__(
            self,
            service_name=None,
            region_name=None,
            requires_region: bool = None,
            config=None,
            type="client",
        ):
            self.service_name = service_name
            self.instance = None
            self.region_name = region_name
            self.requires_region = requires_region
            self.config = config
            self.type = type

        def __set_name__(self, owner, name):
            if self.service_name is None:
                self.service_name = name

        def __get__(self, instance, owner):
            if self.instance is None:
                extras = {}
                if self.region_name:
                    extras["region_name"] = self.region_name
                elif self.requires_region:
                    extras["region_name"] = boto3.session.Session().region_name or "eu-west-1"
                if self.config:
                    extras["config"] = self.config
                self.instance = getattr(boto3, self.type)(self.service_name, **extras)
            return self.instance

    sqs = ClientOrResource(requires_region=True)
    sfn = ClientOrResource(service_name="stepfunctions", requires_region=True)
    sfn_long_poll = ClientOrResource(service_name="stepfunctions", requires_region=True, config=Config(read_timeout=65))
    dynamodb_resource = ClientOrResource(type="resource", service_name="dynamodb", requires_region=True)
    dynamodb_client = ClientOrResource(type="client", service_name="dynamodb", requires_region=True)
    lambda_client = ClientOrResource(type="client", service_name="lambda", requires_region=True)


class BotoMixin:
    @property
    def sqs(self):
        return Boto.sqs

    @property
    def sfn(self):
        return Boto.sfn

    @property
    def sfn_long_poll(self):
        return Boto.sfn_long_poll

    @property
    def dynamodb_resource(self):
        return Boto.dynamodb_resource

    @property
    def dynamodb_client(self):
        return Boto.dynamodb_client

    @property
    def lambda_client(self):
        return Boto.lambda_client
