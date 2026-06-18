"""Credentials が表示時に各フィールドをマスクすることを保証する。

認証情報がログ・例外・f-string 経由で漏れないことを公開された表示経路で検証する。
"""

from datetime import date

from domain.collection import Credentials

_SECRETS = ("user01", "secret", "1990")


def _credentials() -> Credentials:
    return Credentials(user_id="user01", password="secret", birthdate=date(1990, 1, 1))


def test_repr_masks_all_fields() -> None:
    assert repr(_credentials()) == "Credentials(user_id=***, password=***, birthdate=***)"


def test_repr_leaks_no_secret() -> None:
    rendered = repr(_credentials())
    assert not any(secret in rendered for secret in _SECRETS)


def test_str_falls_back_to_masked_repr() -> None:
    rendered = str(_credentials())
    assert not any(secret in rendered for secret in _SECRETS)


def test_fstring_masks() -> None:
    rendered = f"{_credentials()}"
    assert not any(secret in rendered for secret in _SECRETS)


def test_values_remain_accessible() -> None:
    cred = _credentials()
    assert cred.user_id == "user01"
    assert cred.password == "secret"
    assert cred.birthdate == date(1990, 1, 1)
