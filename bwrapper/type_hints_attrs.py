"""
If you are getting error:

    TypeError: __init__() takes 2 positional arguments but 4 were given

it means you're inheriting from something that is not a class. Note that the dummy attribute declaration classes
are replaced during class initialisation so they can no longer be inherited from:

    class X(Base):
        class attrs(Base.attrs):  <-- this is incorrect! The actual attrs of Base will be inherited automatically.
            pass

"""


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
            if isinstance(value, int):
                return bool(value)
            if value in ("True", "true", "yes", "y", "1"):
                return True
            elif value in ("False", "false", "no", "n", "0", "None"):
                return False
            raise ValueError(value)

        return value

    @property
    def type(self) -> Type:
        if isinstance(self.type_hint, type):
            return self.type_hint
        elif getattr(self.type_hint, "__origin__", None):
            return self.type_hint.__origin__
        return self.type_hint

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name!r}>"


class TypeHintsAttrs:
    @classmethod
    def init_for(cls, *, target_cls: Type, name: str, definition: Type = None, **kwargs):
        """
        Correctly initialise the TypeHintsAttrs descriptor on the target class.

        This is needed because setting just the attribute to the descriptor isn't enough
        when called in __init_subclass__ which is where it would be usually called.
        """

        if definition is None:
            # definition is a type (a class) which uses type hints to declare fields.
            # If target_cls inherits from another class then we should check if its base class(-es) don't
            # define fields for this attribute collection.
            # If they do, we must include their type hints in the type hints for this definition too.
            # We do that by constructing types on the fly that inherit.
            # TODO Perhaps it would have been better to merge actual type hints.

            own_definition = None
            if name in target_cls.__dict__:
                own_definition = target_cls.__dict__[name]

            parent_definitions = [
                getattr(b, name)._definition
                for b in target_cls.__bases__
                if isinstance(getattr(b, name, None), TypeHintsAttrs)
            ]

            if own_definition:
                if parent_definitions:
                    definition = type(name, (own_definition, *parent_definitions), {})
                else:
                    definition = own_definition
            else:
                if parent_definitions:
                    definition = type(name, (*parent_definitions,), {})
                else:
                    definition = type("Unspecified", (), {})

        else:
            # Make sure that the definition type does not extend from TypeHintsAttrs
            # which would be the case if someone tried to specify inheritance manually.
            pass

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

    @property
    def _accepts_anything(self):
        """
        True if this attribute collection allows setting any attributes (schema-less).
        """
        return getattr(self._definition, "accepts_anything", False)

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

    def __iter__(self):
        return iter(self._attrs)

    def __getitem__(self, name) -> _Attr:
        return self._attrs[name]

    def __len__(self):
        return len(self._attrs)


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

    @property
    def _accepts_anything(self):
        return self._parent._accepts_anything

    def _has_attribute(self, name):
        return self._parent._has_attribute(name)

    def __getattr__(self, name):
        if self._has_attribute(name):
            if name not in self._values:
                return getattr(self._parent, name).default
            return self._values[name]
        if self._accepts_anything and name in self._values:
            return self._values[name]
        return self._raise_informative_attribute_error(name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return super().__setattr__(name, value)
        if self._has_attribute(name):
            self._values[name] = getattr(self._parent, name).parse(value)
            return
        if self._accepts_anything:
            self._values[name] = value
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

    def __iter__(self):
        return iter(self._parent._attrs)

    def __getitem__(self, name) -> _Attr:
        return self._parent._attrs[name]

    def __len__(self):
        return len(self._parent._attrs)
