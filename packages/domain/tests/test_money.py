"""Money 値オブジェクトの単体テスト。

Web 取得文字列のパース・加減算・表示書式という公開された振る舞いを検証する。
"""

import pytest

from domain.asset import Money


class TestParse:
    def test_yen_symbol_with_grouping(self) -> None:
        assert Money.parse("¥1,234,567") == Money(1234567)

    def test_trailing_yen_kanji_with_minus(self) -> None:
        assert Money.parse("-80,000円") == Money(-80000)

    def test_accounting_white_triangle_is_negative(self) -> None:
        assert Money.parse("△80,000") == Money(-80000)

    def test_accounting_black_triangle_is_negative(self) -> None:
        assert Money.parse("▲80,000") == Money(-80000)

    def test_zero(self) -> None:
        assert Money.parse("¥0") == Money(0)

    def test_unparseable_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            Money.parse("N/A")

    def test_empty_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            Money.parse("")


class TestArithmetic:
    def test_add(self) -> None:
        assert Money(1000) + Money(500) == Money(1500)

    def test_sub(self) -> None:
        assert Money(1000) - Money(1500) == Money(-500)


class TestSign:
    def test_is_positive(self) -> None:
        assert Money(1).is_positive
        assert not Money(0).is_positive
        assert not Money(-1).is_positive

    def test_is_negative(self) -> None:
        assert Money(-1).is_negative
        assert not Money(0).is_negative
        assert not Money(1).is_negative


class TestFormat:
    def test_format_positive(self) -> None:
        assert Money(1234567).format() == "¥1,234,567"

    def test_format_negative(self) -> None:
        assert Money(-80000).format() == "-¥80,000"

    def test_format_zero(self) -> None:
        assert Money(0).format() == "¥0"

    def test_signed_positive_has_plus(self) -> None:
        assert Money(1234567).signed() == "+¥1,234,567"

    def test_signed_negative(self) -> None:
        assert Money(-80000).signed() == "-¥80,000"

    def test_signed_zero_has_no_sign(self) -> None:
        assert Money(0).signed() == "¥0"
