"""Generate validated SQL scripts for SQL Mapping data flows."""

import re


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
SUPPORTED_COLUMN_TYPES = (
    "VARCHAR(20)",
    "VARCHAR(50)",
    "VARCHAR(100)",
    "VARCHAR(255)",
    "CHAR(1)",
    "TINYINT(1)",
    "INT",
    "BIGINT",
    "DECIMAL(10,2)",
    "DATE",
    "DATETIME",
    "TEXT",
)


def _validated_identifier(value, label):
    value = str(value or "").strip()
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(
            f"{label} ต้องเป็น identifier ภาษาอังกฤษ ตัวเลข หรือ _ "
            "และต้องขึ้นต้นด้วยตัวอักษรหรือ _"
        )
    return value


def _quote_identifier(value):
    return f"`{value}`"


def suggested_column_type(mysql_type_name, column_size=None):
    type_name = str(mysql_type_name or "").upper()
    if type_name in {"DATE", "NEWDATE"}:
        return "DATE"
    if type_name in {"DATETIME", "TIMESTAMP"}:
        return "DATETIME"
    if type_name in {"TINY", "SHORT", "LONG", "INT24"}:
        return "INT"
    if type_name == "LONGLONG":
        return "BIGINT"
    if type_name in {"DECIMAL", "NEWDECIMAL"}:
        return "DECIMAL(10,2)"
    if type_name in {"FLOAT", "DOUBLE"}:
        return "DECIMAL(10,2)"
    if type_name in {
        "TINY_BLOB", "MEDIUM_BLOB", "LONG_BLOB", "BLOB"
    }:
        return "TEXT"
    if type_name in {"STRING", "VARCHAR", "VAR_STRING"}:
        try:
            size = int(column_size)
        except (TypeError, ValueError):
            size = 100
        if size <= 1:
            return "CHAR(1)"
        if size <= 20:
            return "VARCHAR(20)"
        if size <= 50:
            return "VARCHAR(50)"
        if size <= 100:
            return "VARCHAR(100)"
        return "VARCHAR(255)"
    return "VARCHAR(100)"


def generate_mapping_scripts(mapping, columns):
    task_code = str(mapping.get("task_code", "")).strip()
    district_table = _validated_identifier(
        mapping.get("district_table", mapping.get("local_source_table")),
        "District Table",
    )
    staging_table = _validated_identifier(
        mapping.get("host_staging_table"), "Host Staging Table"
    )
    procedure_name = _validated_identifier(
        mapping.get("host_procedure_name"), "Host Procedure Name"
    )
    if not isinstance(columns, (list, tuple)) or not columns:
        raise ValueError("กรุณาดึงโครงสร้างคอลัมน์จาก SQL ก่อนสร้างสคริปต์")

    normalized_columns = []
    seen_names = set()
    for column in columns:
        name = _validated_identifier(column.get("name"), "ชื่อคอลัมน์")
        name_key = name.casefold()
        if name_key in {"batch_id", "uploaded_at", "last_synced_at"}:
            raise ValueError(
                f"ชื่อคอลัมน์ {name} สงวนไว้สำหรับข้อมูลประกอบของ Host DB"
            )
        if name_key in seen_names:
            raise ValueError(f"พบชื่อคอลัมน์ซ้ำ: {name}")
        seen_names.add(name_key)
        column_type = str(column.get("type", "")).upper()
        if column_type not in SUPPORTED_COLUMN_TYPES:
            raise ValueError(f"ไม่รองรับ Data Type ของ {name}: {column_type}")
        normalized_columns.append({
            "name": name,
            "type": column_type,
            "primary_key": bool(column.get("primary_key")),
        })

    primary_keys = [
        column for column in normalized_columns if column["primary_key"]
    ]
    if not primary_keys:
        raise ValueError("กรุณาเลือก Primary Key อย่างน้อย 1 คอลัมน์")
    if any(column["type"] == "TEXT" for column in primary_keys):
        raise ValueError("ไม่สามารถใช้ TEXT เป็น Primary Key ได้")

    primary_key_sql = ", ".join(
        _quote_identifier(column["name"]) for column in primary_keys
    )
    column_definitions = [
        f"    {_quote_identifier(column['name'])} {column['type']} "
        f"{'NOT NULL' if column['primary_key'] else 'NULL'}"
        for column in normalized_columns
    ]
    district_create = (
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(district_table)} (\n"
        + ",\n".join(column_definitions)
        + f",\n    PRIMARY KEY ({primary_key_sql})\n"
        + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
        "COLLATE=utf8mb4_unicode_ci"
    )

    if staging_table.casefold().startswith("store_"):
        suffix = staging_table[len("store_"):]
        if not suffix:
            raise ValueError("Host Staging Table ต้องมีชื่อหลัง store_")
        real_table = f"real_{suffix}"
    else:
        suffix = re.sub(r"[^A-Za-z0-9_]", "_", task_code.lower()).strip("_")
        real_table = f"real_{suffix or staging_table}"
    real_table = _validated_identifier(real_table, "Host Real Table")
    if real_table.casefold() == staging_table.casefold():
        raise ValueError(
            "ชื่อ Host Staging Table ชนกับตารางจริง ให้ใช้รูปแบบ store_<name>"
        )
    batch_index = _validated_identifier(
        f"ix_{staging_table}_batch"[:64], "Batch Index"
    )

    host_column_definitions = [
        f"    {_quote_identifier(column['name'])} {column['type']} "
        f"{'NOT NULL' if column['primary_key'] else 'NULL'}"
        for column in normalized_columns
    ]
    staging_create = (
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(staging_table)} (\n"
        + ",\n".join(host_column_definitions)
        + ",\n    `batch_id` VARCHAR(50) NOT NULL"
        + ",\n    `uploaded_at` TIMESTAMP NOT NULL "
        "DEFAULT CURRENT_TIMESTAMP"
        + f",\n    PRIMARY KEY ({primary_key_sql})"
        + f",\n    KEY {_quote_identifier(batch_index)} (`batch_id`)\n"
        + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
        "COLLATE=utf8mb4_unicode_ci"
    )
    real_create = (
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(real_table)} (\n"
        + ",\n".join(host_column_definitions)
        + f",\n    `last_synced_at` TIMESTAMP NOT NULL "
        "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        + f",\n    PRIMARY KEY ({primary_key_sql})\n"
        + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
        "COLLATE=utf8mb4_unicode_ci"
    )

    field_names = ",\n        ".join(
        _quote_identifier(column["name"]) for column in normalized_columns
    )
    select_values = ",\n        ".join(
        _quote_identifier(column["name"]) for column in normalized_columns
    )
    update_columns = [
        column for column in normalized_columns if not column["primary_key"]
    ]
    update_assignments = [
        f"        {_quote_identifier(column['name'])} = "
        f"VALUES({_quote_identifier(column['name'])})"
        for column in update_columns
    ]
    update_assignments.append("        `last_synced_at` = CURRENT_TIMESTAMP")
    procedure_create = (
        f"CREATE PROCEDURE {_quote_identifier(procedure_name)}()\n"
        "BEGIN\n"
        f"    INSERT INTO {_quote_identifier(real_table)} (\n"
        f"        {field_names},\n"
        "        `last_synced_at`\n"
        "    )\n"
        "    SELECT\n"
        f"        {select_values},\n"
        "        CURRENT_TIMESTAMP\n"
        f"    FROM {_quote_identifier(staging_table)}\n"
        "    ON DUPLICATE KEY UPDATE\n"
        + ",\n".join(update_assignments)
        + ";\n\n"
        f"    DELETE FROM {_quote_identifier(staging_table)};\n"
        "END"
    )
    procedure_drop = (
        f"DROP PROCEDURE IF EXISTS {_quote_identifier(procedure_name)}"
    )
    procedure_script = (
        f"{procedure_drop};\n"
        "DELIMITER $$\n"
        f"{procedure_create}$$\n"
        "DELIMITER ;"
    )

    return {
        "district_table": district_table,
        "host_staging_table": staging_table,
        "host_real_table": real_table,
        "host_procedure_name": procedure_name,
        "scripts": {
            "district": district_create + ";",
            "host_tables": staging_create + ";\n\n" + real_create + ";",
            "host_procedure": procedure_script,
        },
        "statements": {
            "district": (district_create,),
            "host_tables": (staging_create, real_create),
            "host_procedure": (procedure_drop, procedure_create),
        },
    }
