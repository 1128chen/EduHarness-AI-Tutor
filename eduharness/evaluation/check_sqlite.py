from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def scalar(connection: sqlite3.Connection, sql: str) -> object:
    row = connection.execute(sql).fetchone()
    return row[0] if row else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        default=r"D:\agent_dev\MiniCode-Python\eduharness.db",
    )
    args = parser.parse_args()

    path = Path(args.database)
    if not path.exists():
        raise SystemExit(f"Database does not exist: {path}")

    connection = sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    tables = {
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        )
    }

    print(f"DATABASE={path}")
    print(f"TABLES={sorted(tables)}")
    print(f"INTEGRITY={scalar(connection, 'PRAGMA integrity_check')}")

    foreign_key_errors = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()
    print(f"FOREIGN_KEY_ERRORS={len(foreign_key_errors)}")

    for table in sorted(tables):
        if table.startswith("sqlite_"):
            continue
        count = scalar(
            connection,
            f'SELECT COUNT(*) FROM "{table}"',
        )
        print(f"COUNT {table}={count}")

    if {"mastery_states"}.issubset(tables):
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(mastery_states)"
            )
        }

        required = {"student_id", "knowledge_point_id"}
        if required.issubset(columns):
            duplicates = connection.execute(
                """
                SELECT
                    student_id,
                    knowledge_point_id,
                    COUNT(*) AS count_value
                FROM mastery_states
                GROUP BY student_id, knowledge_point_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            print(f"DUPLICATE_MASTERY={len(duplicates)}")

        if "mastery" in columns:
            out_of_range = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM mastery_states
                WHERE mastery < 0
                   OR mastery > 1
                   OR mastery IS NULL
                """
            )
            print(f"INVALID_MASTERY={out_of_range}")

        if "confidence" in columns:
            invalid_confidence = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM mastery_states
                WHERE confidence < 0
                   OR confidence > 1
                   OR confidence IS NULL
                """
            )
            print(f"INVALID_CONFIDENCE={invalid_confidence}")

    if {"messages"}.issubset(tables):
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(messages)"
            )
        }

        if {"turn_id", "sequence"}.issubset(columns):
            duplicate_sequences = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM (
                    SELECT turn_id, sequence
                    FROM messages
                    GROUP BY turn_id, sequence
                    HAVING COUNT(*) > 1
                )
                """
            )
            print(
                f"DUPLICATE_MESSAGE_SEQUENCES="
                f"{duplicate_sequences}"
            )

    connection.close()


if __name__ == "__main__":
    main()