import pytest

from bwrapper.type_hints_attrs import (
    _Attr,
    TypeHintsAttrs,
    _TypeHintsBoundAttrs
)


def test_internals():
    storage = {}

    class Container:
        class X:
            a: int
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
    assert Container.x.a.default is None
    assert Container.x.a.type_hint is int
    assert Container.x.a.name == "a"

    cont = Container()
    assert isinstance(cont.x, _TypeHintsBoundAttrs)
    assert cont.x.a is None

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
