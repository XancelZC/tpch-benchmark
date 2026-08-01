"""数据库连接器：统一超时与完整结果集计时语义。"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any


@dataclass
class QueryResult:
    elapsed_ms: float
    row_count: int
    result_hash: str | None = None
    scalar_value: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


def _normalize_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        normalized = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP).normalize()
        return format(normalized, "f")
    if isinstance(value, float):
        if value == 0:
            return "0"
        normalized = Decimal(str(value)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        ).normalize()
        return format(normalized, "f")
    if isinstance(value, str):
        return value.rstrip()
    return str(value)


def normalize_rows(rows: Iterable[Iterable[Any]]) -> list[list[str]]:
    """规范化不同数据库驱动返回的值，便于跨库结果校验。"""
    return [[_normalize_value(value) for value in row] for row in rows]


def result_digest(rows: Iterable[Iterable[Any]]) -> str:
    """生成与行顺序无关的结果集 SHA-256 摘要。"""
    encoded_rows = [
        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        for row in normalize_rows(rows)
    ]
    payload = "\n".join(sorted(encoded_rows)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class DatabaseConnector(ABC):
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self._conn = None

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def execute(self, sql: str, timeout: int = 300) -> QueryResult: ...

    @abstractmethod
    def load_csv(self, table: str, csv_path: str) -> bool: ...

    @abstractmethod
    def analyze(self, table: str | None = None) -> None: ...

    @abstractmethod
    def create_tables(self, ddl_path: str) -> None: ...

    def execute_params(self, params: list[str]) -> None:
        for sql in params:
            result = self.execute(sql)
            if not result.success:
                raise RuntimeError(f"Database parameter failed: {sql}: {result.error}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_args):
        self.close()


class PostgresConnector(DatabaseConnector):
    """供 PostgreSQL、YMatrix 和 Greenplum 复用的 PG 协议连接器。"""

    def connect(self) -> None:
        import psycopg2

        self._conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
        )
        self._conn.set_session(autocommit=True)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, timeout: int = 300) -> QueryResult:
        import psycopg2.errors

        cur = self._conn.cursor()
        try:
            cur.execute("SET statement_timeout = %s", (timeout * 1000,))
            start = time.perf_counter()
            cur.execute(sql)
            rows = cur.fetchall() if cur.description else []
            elapsed_ms = (time.perf_counter() - start) * 1000
            return QueryResult(
                elapsed_ms=round(elapsed_ms, 2),
                row_count=len(rows) if cur.description else max(cur.rowcount, 0),
                result_hash=result_digest(rows) if cur.description else None,
                scalar_value=_normalize_value(rows[0][0]) if rows and len(rows[0]) == 1 else None,
            )
        except psycopg2.errors.QueryCanceled:
            self._conn.rollback()
            return QueryResult(timeout * 1000, 0, error="timeout")
        except Exception as exc:
            self._conn.rollback()
            return QueryResult(0, 0, error=str(exc)[:500])
        finally:
            cur.close()

    def load_csv(self, table: str, csv_path: str) -> bool:
        cur = self._conn.cursor()
        try:
            with open(csv_path, encoding="utf-8") as source:
                cur.copy_expert(
                    f"COPY {table} FROM STDIN WITH (FORMAT csv, DELIMITER '|')", source
                )
            return True
        except Exception:
            self._conn.rollback()
            return False
        finally:
            cur.close()

    def analyze(self, table: str | None = None) -> None:
        result = self.execute(f"ANALYZE {table}" if table else "ANALYZE")
        if not result.success:
            raise RuntimeError(result.error)

    def create_tables(self, ddl_path: str) -> None:
        result = self.execute(Path(ddl_path).read_text(encoding="utf-8"))
        if not result.success:
            raise RuntimeError(result.error)


class MySQLConnector(DatabaseConnector):
    def connect(self) -> None:
        import mysql.connector

        self._conn = mysql.connector.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            autocommit=True,
            allow_local_infile=True,
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _ensure_connection(self) -> None:
        try:
            self._conn.ping(reconnect=True, attempts=3, delay=1)
        except Exception:
            self.close()
            self.connect()

    def _kill_query(self, connection_id: int, timed_out: threading.Event) -> None:
        """使用独立控制连接取消当前查询，覆盖服务端超时不生效的语句。"""
        import mysql.connector

        control = None
        timed_out.set()
        try:
            control = mysql.connector.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                autocommit=True,
            )
            cursor = control.cursor()
            cursor.execute(f"KILL QUERY {int(connection_id)}")
            cursor.close()
        except Exception:
            # KILL 未成功时不能把正常查询误判为超时。
            timed_out.clear()
            return
        finally:
            if control is not None:
                control.close()

    def execute(self, sql: str, timeout: int = 300) -> QueryResult:
        import mysql.connector.errors

        self._ensure_connection()
        cur = self._conn.cursor()
        timed_out = threading.Event()
        timer = threading.Timer(
            max(timeout - 0.05, 0.001),
            self._kill_query,
            args=(int(self._conn.connection_id), timed_out),
        )
        timer.daemon = True
        try:
            cur.execute(f"SET SESSION max_execution_time = {int(timeout * 1000)}")
            timer.start()
            start = time.perf_counter()
            cur.execute(sql)
            rows = cur.fetchall() if cur.description else []
            elapsed_ms = (time.perf_counter() - start) * 1000
            if timed_out.is_set():
                return QueryResult(timeout * 1000, 0, error="timeout")
            return QueryResult(
                elapsed_ms=round(elapsed_ms, 2),
                row_count=len(rows) if cur.description else max(cur.rowcount, 0),
                result_hash=result_digest(rows) if cur.description else None,
                scalar_value=_normalize_value(rows[0][0]) if rows and len(rows[0]) == 1 else None,
            )
        except mysql.connector.errors.DatabaseError as exc:
            self._conn.rollback()
            if timed_out.is_set() or getattr(exc, "errno", None) in {1317, 3024}:
                return QueryResult(timeout * 1000, 0, error="timeout")
            return QueryResult(0, 0, error=str(exc)[:500])
        except Exception as exc:
            self._conn.rollback()
            return QueryResult(0, 0, error=str(exc)[:500])
        finally:
            timer.cancel()
            # 定时器若已触发，必须等待控制连接完成，防止迟到的 KILL 误杀下一条查询。
            if timer.is_alive():
                timer.join(timeout=5)
            cur.close()

    def load_csv(self, table: str, csv_path: str) -> bool:
        self._ensure_connection()
        cur = self._conn.cursor()
        try:
            path = Path(csv_path).resolve().as_posix().replace("'", "''")
            cur.execute(
                f"LOAD DATA LOCAL INFILE '{path}' INTO TABLE {table} "
                "FIELDS TERMINATED BY '|' LINES TERMINATED BY '\\n'"
            )
            return True
        except Exception:
            self._conn.rollback()
            return False
        finally:
            cur.close()

    def analyze(self, table: str | None = None) -> None:
        if not table:
            raise ValueError("MySQL analyze requires an explicit table")
        result = self.execute(f"ANALYZE TABLE {table}")
        if not result.success:
            raise RuntimeError(result.error)

    def create_tables(self, ddl_path: str) -> None:
        ddl = Path(ddl_path).read_text(encoding="utf-8")
        for statement in ddl.split(";"):
            if statement.strip():
                result = self.execute(statement)
                if not result.success:
                    raise RuntimeError(result.error)


_CONNECTOR_REGISTRY = {
    "postgresql": PostgresConnector,
    "mysql": MySQLConnector,
    "ymatrix": PostgresConnector,
    "greenplum": PostgresConnector,
}


def create_connector(
    db_type: str, host: str, port: int, database: str, user: str, password: str
) -> DatabaseConnector:
    try:
        connector_class = _CONNECTOR_REGISTRY[db_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported database type: {db_type}") from exc
    return connector_class(host, port, database, user, password)
