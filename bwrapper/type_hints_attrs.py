from typing import Any, Type, get_type_hints


class _Attr:
    def __init__(self, *, name, type_hint, default=None):
        self.name = name
        self.type_hint = type_hint
        self.default = default

    def parse(self, value):
        if value is None or value == "None":
            return None

        if self.type_hint in (int, float, str):
            return self.type_hint(value)

        if self.type_hint is bool:
            if isinstance(value, bool):
                return value
            if value in ("True", "true", "yes", "y", "1"):
                return True
            elif value in ("False", "false", "no", "n", "0"):
                return False
            raise ValueError(value)

        return value


class TypeHintsAttrs:
    @classmethod
    def init_for(cls, *, target_cls: Type, name: str, definition: Type, **kwargs):
        """
        Correctly initialise the TypeHintsAttrs descriptor on the target class.

        This is needed because setting just the attribute to the descriptor isn't enough
        when called in __init_subclass__ which is where it would be usually called.
        """
        setattr(target_cls, name, cls(definition=definition, **kwargs))
        getattr(target_cls, name).__set_name__(target_cls, name)

    def __init__(self, definition: Type, *, name: str = None):
        self._owner = None
        self._name = name
        self._attr_name = None
        self._definition = definition
        self._type_hints = get_type_hints(definition)
        self._attrs = {
            k: _Attr(name=k, type_hint=t, default=getattr(self._definition, k, None))
            for k, t in self._type_hints.items()
        }

    def __set_name__(self, owner, name):
        self._owner = owner
        self._attr_name = name
        if self._name is None:
            self._name = name

    @property
    def _instance_attr_name(self):
        return f"_attrs:{self._attr_name}"

    def __get__(self, instance, owner):
        if instance is None:
            return self

        if not hasattr(instance, self._instance_attr_name):
            setattr(instance, self._instance_attr_name, _TypeHintsBoundAttrs(parent=self, instance=instance))
        return getattr(instance, self._instance_attr_name)

    def _has_attribute(self, name):
        return name in self._attrs

    def __getattr__(self, name):
        """
        This is called when class attribute is requested
        """
        if self._has_attribute(name):
            return self._attrs[name]
        else:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return super().__setattr__(name, value)
        # Do not allow overwriting anything
        raise AttributeError(name)

    def _update(self, **kwargs):
        """
        Update attributes in bulk.
        This is implemented only for bound attributes.
        """
        raise NotImplementedError()


class _TypeHintsBoundAttrs:
    def __init__(self, parent: TypeHintsAttrs, instance: Any):
        self._parent = parent
        self._instance = instance
        self._values = {}

        if not self._parent._attr_name:
            raise RuntimeError(
                f"{parent} is not fully initialised, it is missing _attr_name; "
                f"If you are initialising {TypeHintsAttrs.__name__} from __init_subclass__ you "
                f"need to do it with {TypeHintsAttrs.__name__}.{TypeHintsAttrs.init_for.__name__}(...)"
            )

    def __getattr__(self, name):
        if self._parent._has_attribute(name):
            if name not in self._values:
                return getattr(self._parent, name).default
            return self._values[name]
        return self._raise_informative_attribute_error(name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return super().__setattr__(name, value)
        if self._parent._has_attribute(name):
            self._values[name] = getattr(self._parent, name).parse(value)
            return
        return self._raise_informative_attribute_error(name)

    def _update(self, **kwargs):
        for k, v in kwargs.items():
            try:
                setattr(self, k, v)
            except AttributeError as e:
                return self._raise_informative_attribute_error(k, e)

    def _raise_informative_attribute_error(self, name, exception: Exception = None):
        message = f"{self._instance.__class__.__name__}.{self._parent._attr_name} does not have attribute {name!r}"
        if exception:
            raise AttributeError(message) from exception
        else:
            raise AttributeError(message)
