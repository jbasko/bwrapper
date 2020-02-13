from typing import Type

import pytest

from bwrapper.type_hints_attrs import (
    TypeHintsAttrs,
    _Attr,
    _TypeHintsBoundAttrs
)


def test_internals():
    storage = {}

    class Container:
        class X:
            a: int = 2
            b: str
            c: float

        storage["original_X"] = X

        x = TypeHintsAttrs(definition=X)

    assert isinstance(Container.x, TypeHintsAttrs)
    assert Container.x._name == "x"
    assert Container.x._attr_name == "x"
    assert Container.x._owner is Container
    assert Container.x._definition is storage["original_X"]
    assert set(Container.x._attrs.keys()) == {"a", "b", "c"}

    assert hasattr(Container.x, "a")
    assert hasattr(Container.x, "b")
    assert hasattr(Container.x, "c")
    assert not hasattr(Container.x, "d")

    assert isinstance(Container.x.a, _Attr)
    assert Container.x.a.default == 2
    assert Container.x.a.type_hint is int
    assert Container.x.a.name == "a"

    cont = Container()
    assert isinstance(cont.x, _TypeHintsBoundAttrs)
    assert cont.x.a == 2

    cont.x._parent._name == "x"
    cont.x._parent._attr_name == "x"

    cont.x.a = "55"
    assert "a" not in cont.x.__dict__
    assert cont.x.a == 55

    # Sanity check: no relation between instances

    cont2 = Container()
    cont3 = Container()

    cont2.x.a = 15
    cont3.x.a = 24

    assert cont2.x.a == 15
    assert cont3.x.a == 24


def test_subclass_approach():
    class Base:
        class x:
            pass

        def __init_subclass__(cls, **kwargs):
            TypeHintsAttrs.init_for(target_cls=cls, name="x", definition=getattr(cls, "x", Base.x))

    class Derived(Base):
        class x:
            a: int
            b: str

    d1 = Derived()
    d2 = Derived()

    d1.x.a = "55"
    assert d1.x.a == 55

    d2.x.a = "None"
    assert d2.x.a is None

    assert d1.x.a == 55

    d1.x._parent._name == "x"
    d1.x._parent._attr_name == "x"

    # Make sure we cannot set non-existent attributes
    with pytest.raises(AttributeError):
        d1.x.c = 23


def test_update_helper():
    class Base:
        def __init_subclass__(cls, **kwargs):
            TypeHintsAttrs.init_for(target_cls=cls, name="x", definition=cls.x)

    class C(Base):
        class x:
            p: int
            q: float
            r: bool

    c1 = C()
    c1.x._update(p="23", q="1.23", r="False")
    assert c1.x.p == 23
    assert c1.x.q == 1.23
    assert c1.x.r is False


@pytest.fixture
def X() -> Type:
    class Base:
        class attrs:
            pass

        def __init_subclass__(cls, **kwargs):
            TypeHintsAttrs.init_for(target_cls=cls, name="attrs")

        def __init__(self, **attrs):
            super().__init__()
            self.attrs._update(**attrs)

    class X(Base):
        class attrs:
            a: int
            b: str = "BBB"
            c: float

    return X


def test_init_for_without_definition(X):
    x = X(a="1", b="2")
    assert x.attrs.a == 1
    assert x.attrs.b == "2"
    assert x.attrs.c is None


def test_iterate_over_attrs(X):
    x = X()
    assert set(X.attrs) == {"a", "b", "c"}
    assert isinstance(X.attrs["a"], _Attr)

    assert set(x.attrs) == {"a", "b", "c"}
    assert isinstance(x.attrs["a"], _Attr)


def test_iterate_over_all_unknown_attrs():
    class B:
        class attrs:
            pass

        def __init_subclass__(cls, **kwargs):
            TypeHintsAttrs.init_for(target_cls=cls, name="attrs")

    class C(B):
        class attrs:
            accepts_anything = True

    c = C()
    assert set(c.attrs) == set()

    c.attrs.x = 123
    assert set(c.attrs) == {"x"}

    c.attrs.y = None
    assert set(c.attrs) == {"x", "y"}

    assert isinstance(c.attrs["x"], _Attr)
    assert c.attrs["x"].name == "x"
    assert c.attrs["y"].name == "y"


def test_inherited_attrs(X):
    class Y(X):
        class attrs:
            d: int = 10

    assert Y.attrs.b.default == "BBB"

    y = Y(a="1")
    assert y.attrs.a == 1
    assert y.attrs.b == "BBB"  # inherited default
    assert y.attrs.d == 10


def test_clear(X):
    x = X(a="12", b="34", c="56")
    assert x.attrs._extract_values() == {
        "a": 12,
        "b": "34",
        "c": 56.0,
    }

    # Back to defaults
    x.attrs._clear()
    assert x.attrs._extract_values() == {
        "a": None,
        "b": "BBB",
        "c": None,
    }
