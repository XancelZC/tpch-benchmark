import hashlib

from src.db_connector import QueryResult, normalize_rows, result_digest


def test_normalize_rows_makes_database_numeric_types_comparable():
    rows = [(1, 1.0, "x "), (2, None, "y")]
    assert normalize_rows(rows) == [["1", "1", "x"], ["2", "NULL", "y"]]


def test_normalize_rows_uses_six_decimal_places_for_cross_database_averages():
    from decimal import Decimal

    pg_value = Decimal("25.537587116854997")
    mysql_value = Decimal("25.537587")
    assert normalize_rows([(pg_value,)]) == normalize_rows([(mysql_value,)])


def test_result_digest_is_stable_for_same_rows():
    first = result_digest([(1, "a"), (2, "b")])
    second = result_digest([(1, "a"), (2, "b")])
    assert first == second
    assert len(first) == hashlib.sha256().digest_size * 2


def test_query_result_exposes_hash_and_row_count():
    result = QueryResult(elapsed_ms=1.0, row_count=2, result_hash="abc", scalar_value="2")
    assert result.success
    assert result.result_hash == "abc"
    assert result.scalar_value == "2"
