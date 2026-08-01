from pathlib import Path


def test_all_twenty_two_queries_exist_and_are_nonempty():
    query_dir = Path("queries")
    paths = sorted(query_dir.glob("q*.sql"))
    assert len(paths) == 22
    assert all(path.read_text(encoding="utf-8").strip() for path in paths)


def test_q15_has_no_shared_view_side_effect():
    sql = Path("queries/q15.sql").read_text(encoding="utf-8").lower()
    assert "create view" not in sql
    assert "drop view" not in sql
    assert sql.lstrip().startswith("with revenue0 as")


def test_q19_uses_standard_reg_air_ship_mode():
    sql = Path("queries/q19.sql").read_text(encoding="utf-8")
    assert "REG AIR" in sql
    assert "AIR REG" not in sql
