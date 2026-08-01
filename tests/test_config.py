from pathlib import Path

import pytest

from src.config import Config


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def valid_databases() -> str:
    return """
databases:
  - name: A
    type: postgresql
  - name: B
    type: mysql
"""


def test_empty_yaml_has_clear_error(tmp_path):
    path = write_config(tmp_path, "")
    with pytest.raises(ValueError, match="empty"):
        Config.from_file(str(path))


def test_database_names_must_be_unique(tmp_path):
    path = write_config(
        tmp_path,
        """
databases:
  - name: duplicate
    type: postgresql
  - name: duplicate
    type: mysql
""",
    )
    with pytest.raises(ValueError, match="unique"):
        Config.from_file(str(path))


@pytest.mark.parametrize(
    ("field", "value"),
    [("test_rounds", 0), ("timeout_seconds", 0), ("concurrency", 0)],
)
def test_positive_benchmark_numbers_are_required(tmp_path, field, value):
    path = write_config(
        tmp_path,
        valid_databases() + f"\nbenchmark:\n  {field}: {value}\n",
    )
    with pytest.raises(ValueError, match=field):
        Config.from_file(str(path))


def test_unimplemented_concurrency_fails_fast(tmp_path):
    path = write_config(
        tmp_path,
        valid_databases() + "\nbenchmark:\n  concurrency: 2\n",
    )
    with pytest.raises(ValueError, match="concurrency=1"):
        Config.from_file(str(path))


def test_supported_database_type_is_validated(tmp_path):
    path = write_config(
        tmp_path,
        """
databases:
  - name: A
    type: postgresql
  - name: B
    type: unknown
""",
    )
    with pytest.raises(ValueError, match="Unsupported database type"):
        Config.from_file(str(path))


def test_optional_container_name_is_loaded(tmp_path):
    path = write_config(
        tmp_path,
        valid_databases() + "\nbenchmark:\n  concurrency: 1\n",
    )
    config = Config.from_file(str(path))
    assert config.databases[0].container is None


def test_password_environment_variable_is_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret-value")
    body = valid_databases().replace(
        "  - name: A\n    type: postgresql",
        "  - name: A\n    type: postgresql\n    password: \"${TEST_DB_PASSWORD}\"",
    )
    path = write_config(tmp_path, body + "\nbenchmark:\n  concurrency: 1\n")
    config = Config.from_file(str(path))
    assert config.databases[0].password == "secret-value"
