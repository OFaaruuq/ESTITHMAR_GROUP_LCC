"""Unit tests for estithmar.validators (no database)."""
from estithmar.validators import validate_phone


def test_phone_empty_optional():
    assert validate_phone(None) == (None, None)
    assert validate_phone("") == (None, None)
    assert validate_phone("   ") == (None, None)


def test_phone_rejects_letters():
    _, err = validate_phone("Hundm,ans")
    assert err and "letters" in err.lower()


def test_phone_accepts_international():
    n, err = validate_phone("+252 63 1234567")
    assert err is None
    assert n == "+252631234567"


def test_phone_accepts_digits_only():
    n, err = validate_phone("0631234567")
    assert err is None
    assert n == "0631234567"


def test_phone_rejects_too_short():
    _, err = validate_phone("123456")
    assert err and "7" in err


def test_phone_rejects_too_long():
    _, err = validate_phone("1" * 16)
    assert err and "15" in err
