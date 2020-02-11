import logging


class LogMixin:
    log_name: str = None
    log_level: int = logging.INFO

    class _Log:
        attr_name = "_log"

        def __get__(self, instance, owner):
            if instance is None:
                return self
            if not hasattr(instance, self.attr_name):
                logger = logging.getLogger(getattr(instance, "log_name") or instance.__class__.__name__)
                setattr(instance, self.attr_name, logger)
            logger = getattr(instance, self.attr_name)

            if instance.log_level is not None and logger.level != instance.log_level:
                logger.setLevel(instance.log_level)

            return logger

    log: logging.Logger = _Log()
