#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_engine.py - โมดูลจัดการเชื่อมต่อฐานข้อมูล เช็กพอร์ต VPN และดึง-ส่งข้อมูลแบบ Batch Upsert
"""

import json
import hashlib
import logging
import os
import re
import socket
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import mysql.connector
from mysql.connector import Error

LOG_FILE = "sync.log"
CONFIG_FILE = "config.json"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)


def log_info(msg):
    logging.info(msg)
    if sys.stdout is not None:
        print(msg)


def log_error(msg):
    logging.error(msg)
    if sys.stderr is not None:
        print(msg, file=sys.stderr)


def resource_path(relative_path):
    """คืนค่าพาธจริงของไฟล์ทั้งรันเป็นสคริปต์หรือเป็น .exe ที่แตกด้วย PyInstaller"""
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


CONFIG_FILE = resource_path("config.json")


def load_config():
    """อ่านการตั้งค่าจาก config.json (UTF-8)"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log_error(f"ไม่สามารถอ่าน config.json ได้: {str(e)}")
        return {}


def save_config(config):
    """บันทึกการตั้งค่าลง config.json (UTF-8, ไม่ escape ภาษาไทย)"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        log_error(f"ไม่สามารถบันทึก config.json ได้: {str(e)}")
        return False


def check_vpn_port(ip, port=3333, timeout=2):
    """
    ตรวจสอบว่าพอร์ต VPN (Radmin) ของ รพ.สต. เปิดอยู่หรือไม่
    ใช้ socket.create_connection timeout=2 วินาที
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (socket.timeout, OSError, ConnectionRefusedError):
        return False


def get_hospital_port(hospital):
    """Return and validate the client MySQL port; default to the VPN port."""
    port_value = hospital.get("port", 3333)
    if port_value in (None, ""):
        port_value = 3333
    try:
        port = int(port_value)
    except (TypeError, ValueError) as error:
        raise ValueError("Port ของ รพ.สต. ต้องเป็นตัวเลข") from error
    if not 1 <= port <= 65535:
        raise ValueError("Port ของ รพ.สต. ต้องอยู่ระหว่าง 1 ถึง 65535")
    return port


def get_jhcis_connection(hospital, jhcis_default):
    """
    สร้างการเชื่อมต่อ MySQL ของ JHCIS ผ่าน Radmin VPN
    """
    user = hospital.get("user")
    if not user:
        user = jhcis_default.get("user", "root")
    password = hospital.get(
        "password", jhcis_default.get("password", "")
    )
    database = hospital.get("database") or jhcis_default.get("database", "jhcisdb")
    return mysql.connector.connect(
        host=hospital["ip"],
        port=get_hospital_port(hospital),
        database=database,
        user=user,
        password=password,
        connect_timeout=10,
        autocommit=True
    )


def get_hostatom_connection(hostatom_db):
    """
    สร้างการเชื่อมต่อ MySQL บน HostAtom (Web Hosting)
    กำหนด connect_timeout=15 เพื่อรองรับความหน่วงของอินเทอร์เน็ต
    """
    return mysql.connector.connect(
        host=hostatom_db["host"],
        port=hostatom_db.get("port", 3306),
        database=hostatom_db["database"],
        user=hostatom_db["user"],
        password=hostatom_db["password"],
        connect_timeout=15,
        autocommit=True
    )


def test_hostatom_connection(hostatom_db):
    """
    ทดสอบการเชื่อมต่อ HostAtom และตรวจสอบว่ามีตาราง central_person อยู่หรือไม่
    คืนค่า (สำเร็จไหม, ข้อความแจ้ง)
    """
    try:
        conn = get_hostatom_connection(hostatom_db)
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES LIKE 'central_person'")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result:
            return True, "การเชื่อมต่อสำเร็จ และพบตาราง central_person ในฐานข้อมูลแล้ว"
        else:
            return True, "การเชื่อมต่อสำเร็จ แต่ยังไม่พบตาราง central_person กรุณา Import table_setup_hostatom.sql ก่อน"
    except Error as e:
        return False, str(e)


def extract_person_from_jhcis(conn, last_sync=None):
    """
    ดึงข้อมูลจากตาราง person ของ JHCIS
    ฟิลด์: pcucodeperson, pid, cid, prename, fname, lname, sex, birth, typelive, dischargetype, d_update
    """
    cursor = conn.cursor(dictionary=True)
    sql = """
    SELECT 
        pcucodeperson,
        pid,
        cid,
        prename,
        fname,
        lname,
        sex,
        birth,
        typelive,
        dischargetype,
        d_update
    FROM person
    ORDER BY d_update, pcucodeperson, pid
    """
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def _fetch_jhcis_metadata(hospital, jhcis_default, query):
    connection = get_jhcis_connection(hospital, jhcis_default)
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        return cursor.fetchall()
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()


def get_jhcis_tables(hospital, jhcis_default):
    return [row[0] for row in _fetch_jhcis_metadata(
        hospital, jhcis_default, "SHOW TABLES"
    )]


def get_jhcis_table_columns(hospital, jhcis_default, table_name):
    if not isinstance(table_name, str) or not table_name:
        raise ValueError("กรุณาเลือกชื่อตาราง JHCIS")
    quoted_table = "`" + table_name.replace("`", "``") + "`"
    rows = _fetch_jhcis_metadata(
        hospital, jhcis_default, f"SHOW COLUMNS FROM {quoted_table}"
    )
    return [(row[0], row[1]) for row in rows]


def validate_read_only_select(query):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("กรุณากรอก SQL สำหรับทดสอบ")

    index = 0
    while index < len(query):
        while index < len(query) and query[index].isspace():
            index += 1
        if query.startswith("/*", index):
            if query.startswith("/*!", index):
                raise ValueError("ไม่อนุญาต MySQL executable comments ใน SQL ทดสอบ")
            comment_end = query.find("*/", index + 2)
            if comment_end == -1:
                raise ValueError("SQL มี comment ที่ยังไม่ปิด")
            index = comment_end + 2
        elif query.startswith("#", index) or (
            query.startswith("--", index)
            and (index + 2 == len(query) or query[index + 2].isspace())
        ):
            line_end = query.find("\n", index)
            index = len(query) if line_end == -1 else line_end + 1
        else:
            break

    keyword = re.match(r"[A-Za-z]+", query[index:])
    if not keyword or keyword.group(0).upper() != "SELECT":
        raise ValueError("อนุญาตเฉพาะคำสั่ง SELECT สำหรับ Run SQL")
    quote = None
    line_comment = False
    block_comment = False
    statement_ended = False
    visible_sql = []
    index = 0
    while index < len(query):
        char = query[index]
        next_char = query[index + 1] if index + 1 < len(query) else ""

        if line_comment:
            visible_sql.append(" ")
            if char in "\r\n":
                line_comment = False
        elif block_comment:
            visible_sql.append(" ")
            if char == "*" and next_char == "/":
                block_comment = False
                index += 1
        elif quote:
            visible_sql.append(" ")
            if char == "\\":
                index += 1
            elif char == quote:
                if next_char == quote:
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"', "`"):
            if statement_ended and not char.isspace():
                raise ValueError("อนุญาต SQL ได้ครั้งละหนึ่งคำสั่ง")
            visible_sql.append(" ")
            quote = char
        elif query.startswith("/*!", index):
            raise ValueError("ไม่อนุญาต MySQL executable comments ใน SQL ทดสอบ")
        elif query.startswith("/*", index):
            visible_sql.append(" ")
            block_comment = True
            index += 1
        elif char == "#" or (
            char == "-"
            and next_char == "-"
            and (index + 2 == len(query) or query[index + 2].isspace())
        ):
            visible_sql.append(" ")
            line_comment = True
            if char == "-":
                index += 1
        elif char == ";":
            visible_sql.append(char)
            if statement_ended:
                raise ValueError("อนุญาต SQL ได้ครั้งละหนึ่งคำสั่ง")
            statement_ended = True
        elif statement_ended and not char.isspace():
            raise ValueError("อนุญาต SQL ได้ครั้งละหนึ่งคำสั่ง")
        else:
            visible_sql.append(char)
        index += 1

    if re.search(
        r"\bINTO\s+(?:OUTFILE|DUMPFILE)\b",
        "".join(visible_sql),
        re.IGNORECASE
    ):
        raise ValueError("ไม่อนุญาต SELECT INTO OUTFILE/DUMPFILE")


def preview_person_sql(hospital, jhcis_default, query, max_rows=100):
    validate_read_only_select(query)
    if not isinstance(max_rows, int) or max_rows < 1:
        raise ValueError("จำนวนแถวตัวอย่างต้องมากกว่า 0")

    connection = get_jhcis_connection(hospital, jhcis_default)
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("START TRANSACTION READ ONLY")
        cursor.execute(query)
        if cursor.description is None:
            raise ValueError("SQL ต้องคืนผลลัพธ์เป็นชุดข้อมูล")
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        while cursor.fetchmany(1000):
            pass
        return columns, rows[:max_rows], truncated
    finally:
        try:
            connection.rollback()
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                connection.close()


def upsert_person_to_hostatom(conn, rows, batch_size=500):
    """
    ส่งข้อมูลขึ้น HostAtom แบบ Batch Upsert (ON DUPLICATE KEY UPDATE)
    แยกเป็นก้อนย่อยตาม batch_size เพื่อป้องกัน max_allowed_packet และ gone away
    """
    if not rows:
        return 0

    total_inserted = 0
    sql = """
    INSERT INTO central_person 
    (pcucodeperson, pid, cid, prename, fname, lname, sex, birth, typelive, dischargetype, d_update, synced_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    ON DUPLICATE KEY UPDATE
    cid=VALUES(cid),
    prename=VALUES(prename),
    fname=VALUES(fname),
    lname=VALUES(lname),
    sex=VALUES(sex),
    birth=VALUES(birth),
    typelive=VALUES(typelive),
    dischargetype=VALUES(dischargetype),
    d_update=VALUES(d_update),
    synced_at=CURRENT_TIMESTAMP
    """
    cursor = conn.cursor()
    try:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values = [
                (
                    r.get("pcucodeperson"),
                    r.get("pid"),
                    r.get("cid"),
                    r.get("prename"),
                    r.get("fname"),
                    r.get("lname"),
                    r.get("sex"),
                    r.get("birth"),
                    r.get("typelive"),
                    r.get("dischargetype"),
                    r.get("d_update")
                )
                for r in batch
            ]
            cursor.executemany(sql, values)
            conn.commit()
            total_inserted += len(batch)
            log_info(f"Upsert batch {i // batch_size + 1}: {len(batch)} รายการ (รวม {total_inserted})")
    finally:
        cursor.close()
    return total_inserted


def sync_hospital(hospital, jhcis_default, hostatom_db, batch_size=500):
    """
    ซิงค์ข้อมูล person ของโรงพยาบาลแห่งเดียว
    ขั้นตอน: เช็ก VPN -> ดึงจาก JHCIS -> ส่งขึ้น HostAtom แบบ Upsert
    """
    result = {
        "hospital": hospital,
        "success": False,
        "count": 0,
        "message": ""
    }

    try:
        # ขั้นที่ 1: เช็กสถานะ VPN ด้วยพอร์ตที่ตั้งไว้ของ รพ.สต.
        hospital_port = get_hospital_port(hospital)
        if not check_vpn_port(hospital["ip"], hospital_port, timeout=2):
            result["message"] = f"❌ VPN ออฟไลน์ (Port {hospital_port} ไม่ตอบสนอง)"
            log_error(f"[{hospital['code']}] {hospital['name']} - {result['message']}")
            return result

        # ขั้นที่ 2: ดึงข้อมูลจาก JHCIS
        conn_jhcis = get_jhcis_connection(hospital, jhcis_default)
        rows = extract_person_from_jhcis(conn_jhcis)
        conn_jhcis.close()

        if not rows:
            result["success"] = True
            result["count"] = 0
            result["message"] = "✔ ไม่มีข้อมูลให้อัปเดต"
            log_info(f"[{hospital['code']}] {hospital['name']} - {result['message']}")
            return result

        # ขั้นที่ 3: ส่งขึ้น HostAtom แบบ Batch Upsert
        conn_hostatom = get_hostatom_connection(hostatom_db)
        count = upsert_person_to_hostatom(conn_hostatom, rows, batch_size)
        conn_hostatom.close()

        result["success"] = True
        result["count"] = count
        result["message"] = f"✔ สำเร็จ: {count} รายการ"
        log_info(f"[{hospital['code']}] {hospital['name']} - {result['message']}")
        return result

    except Error as e:
        result["message"] = f"❌ Database Error: {str(e)}"
        log_error(f"[{hospital['code']}] {hospital['name']} - {result['message']}")
        return result
    except Exception as e:
        result["message"] = f"❌ Error: {str(e)}"
        log_error(f"[{hospital['code']}] {hospital['name']} - {result['message']}")
        return result


def sync_hospitals(hospitals, jhcis_default, hostatom_db, batch_size=500,
                   selected_only=True, max_workers=5):
    """
    ซิงค์ข้อมูลหลายโรงพยาบาลพร้อมกันโดยใช้ ThreadPoolExecutor
    เพื่อไม่ให้หน้าต่าง GUI ค้าง (Not Responding)
    """
    if selected_only:
        target_hospitals = [h for h in hospitals if h.get("selected", False)]
    else:
        target_hospitals = list(hospitals)

    if not target_hospitals:
        return []

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_hospital = {
            executor.submit(sync_hospital, h, jhcis_default, hostatom_db, batch_size): h
            for h in target_hospitals
        }
        for future in as_completed(future_to_hospital):
            try:
                results.append(future.result())
            except Exception as e:
                h = future_to_hospital[future]
                results.append({
                    "hospital": h,
                    "success": False,
                    "count": 0,
                    "message": f"❌ Thread Error: {str(e)}"
                })
                log_error(f"[{h['code']}] {h['name']} - Thread Error: {str(e)}")

    return results


_DYNAMIC_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_dynamic_identifier(value, label):
    if not isinstance(value, str) or not _DYNAMIC_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} ต้องเป็น identifier ที่ขึ้นต้นด้วยตัวอักษรหรือ _ และมีเฉพาะ A-Z, 0-9, _")
    return value


def _quote_dynamic_identifier(value):
    return "`" + value.replace("`", "``") + "`"


def get_district_db_config(config=None):
    source = load_config() if config is None else config
    if not isinstance(source, dict) or not source:
        raise ValueError("config.json ไม่มีการตั้งค่าที่ใช้งานได้")
    district_db = source.get("district_db", source)
    if not isinstance(district_db, dict):
        raise ValueError("ไม่พบการตั้งค่า district_db ใน config.json")
    required_keys = ("host", "port", "database", "user", "password")
    missing_keys = [key for key in required_keys if key not in district_db]
    if missing_keys:
        raise ValueError(
            "district_db ใน config.json ขาดค่า: " + ", ".join(missing_keys)
        )
    return dict(district_db)


def get_district_connection(district_db):
    district_db = get_district_db_config(district_db)
    host = str(district_db["host"]).strip()
    database = str(district_db["database"]).strip()
    user = str(district_db["user"]).strip()
    if not host or not database or not user:
        raise ValueError("กรุณาตั้งค่า Host, Database และ User ของ MySQL อำเภอ")
    port = int(district_db["port"])
    if not 1 <= port <= 65535:
        raise ValueError("Port ของ MySQL อำเภอต้องอยู่ระหว่าง 1 ถึง 65535")
    return mysql.connector.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=str(district_db["password"]),
        connect_timeout=5,
        autocommit=False
    )


def get_district_sync_hostatom_connection(hostatom_db):
    host = str(hostatom_db.get("host", "")).strip()
    database = str(hostatom_db.get("database", "")).strip()
    user = str(hostatom_db.get("user", "")).strip()
    if not host or not database or not user:
        raise ValueError("กรุณาตั้งค่า Host, Database และ User ของ HostAtom")
    port = int(hostatom_db.get("port", 3306))
    if not 1 <= port <= 65535:
        raise ValueError("Port ของ HostAtom ต้องอยู่ระหว่าง 1 ถึง 65535")
    return mysql.connector.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=str(hostatom_db.get("password", "")),
        connect_timeout=15,
        autocommit=False
    )


def test_district_connection(district_db):
    connection = None
    try:
        connection = get_district_connection(district_db)
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return True, "เชื่อมต่อ MySQL อำเภอสำเร็จ"
    except (Error, TypeError, ValueError) as error:
        return False, str(error)
    finally:
        if connection is not None:
            connection.close()


def test_district_sync_hostatom_connection(hostatom_db):
    connection = None
    try:
        connection = get_district_sync_hostatom_connection(hostatom_db)
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return True, "เชื่อมต่อ HostAtom Port 3306 สำเร็จ"
    except (Error, TypeError, ValueError) as error:
        return False, str(error)
    finally:
        if connection is not None:
            connection.close()


def get_sql_mappings(district_db):
    connection = get_district_connection(district_db)
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, task_code, task_name, jhcis_extract_sql,
                   district_table AS local_source_table, host_staging_table,
                   host_procedure_name, is_active, sort_order, updated_at
            FROM sql_mapping
            ORDER BY sort_order, id
            """
        )
        return cursor.fetchall()
    finally:
        connection.close()


def save_sql_mapping(district_db, mapping):
    task_code = str(mapping.get("task_code", "")).strip().upper()
    task_name = str(mapping.get("task_name", "")).strip()
    if not task_code or not task_name:
        raise ValueError("กรุณากรอกรหัสงานและชื่อข้อมูล")
    local_source_table = _validate_dynamic_identifier(
        mapping.get("district_table", mapping.get("local_source_table")),
        "district_table"
    )
    host_staging_table = _validate_dynamic_identifier(
        mapping.get("host_staging_table"), "host_staging_table"
    )
    host_procedure_name = _validate_dynamic_identifier(
        mapping.get("host_procedure_name"), "host_procedure_name"
    )
    values = (
        task_code,
        task_name,
        str(
            mapping.get("jhcis_extract_sql", mapping.get("local_extract_sql")) or ""
        ).strip() or None,
        local_source_table,
        host_staging_table,
        host_procedure_name,
        1 if mapping.get("is_active", True) else 0,
        int(mapping.get("sort_order", 0)),
    )
    connection = get_district_connection(district_db)
    try:
        cursor = connection.cursor()
        if mapping.get("id"):
            cursor.execute(
                """
                UPDATE sql_mapping
                SET task_code=%s, task_name=%s, jhcis_extract_sql=%s,
                    district_table=%s, host_staging_table=%s,
                    host_procedure_name=%s, is_active=%s, sort_order=%s
                WHERE id=%s
                """,
                values + (int(mapping["id"]),)
            )
        else:
            cursor.execute(
                """
                INSERT INTO sql_mapping (
                    task_code, task_name, jhcis_extract_sql, district_table,
                    host_staging_table, host_procedure_name, is_active, sort_order
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    task_name=VALUES(task_name),
                    jhcis_extract_sql=VALUES(jhcis_extract_sql),
                    district_table=VALUES(district_table),
                    host_staging_table=VALUES(host_staging_table),
                    host_procedure_name=VALUES(host_procedure_name),
                    is_active=VALUES(is_active),
                    sort_order=VALUES(sort_order)
                """,
                values
            )
        connection.commit()
        return cursor.lastrowid
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_sql_mapping(district_db, mapping_id):
    connection = get_district_connection(district_db)
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM sql_mapping WHERE id=%s", (int(mapping_id),))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _dynamic_report(task_code, message, current, total, progress_callback):
    formatted = f"[{task_code}] {message}"
    log_info(formatted)
    if progress_callback is not None:
        progress_callback(formatted, current, total)


def _close_dynamic_resources(resources):
    for resource in reversed(resources):
        try:
            resource.close()
        except Error as error:
            log_error(f"ปิดทรัพยากรฐานข้อมูลไม่สำเร็จ: {error}")


def sync_jhcis_to_district(
    task_row, hospital, jhcis_default, district_db, batch_size=500,
    progress_callback=None
):
    district_db = get_district_db_config(district_db)
    task_code = str(task_row.get("task_code", "")).strip()
    if not task_code:
        raise ValueError("Mapping ไม่มี task_code")
    destination_table = _validate_dynamic_identifier(
        task_row.get("district_table", task_row.get("local_source_table")),
        "district_table"
    )
    query = str(task_row.get("jhcis_extract_sql") or "").strip()
    if not query:
        raise ValueError(f"Mapping {task_code} ยังไม่ได้กำหนด jhcis_extract_sql")
    validate_read_only_select(query)
    try:
        batch_size = int(batch_size)
    except (TypeError, ValueError) as error:
        raise ValueError("batch_size ต้องเป็นจำนวนเต็ม") from error
    if batch_size <= 0:
        raise ValueError("batch_size ต้องเป็นจำนวนเต็มมากกว่า 0")

    jhcis_connection = None
    jhcis_cursor = None
    district_connection = None
    district_cursor = None
    uploaded_rows = 0
    try:
        _dynamic_report(
            task_code,
            f"อ่าน SQL จาก JHCIS ({hospital.get('name', hospital.get('code', ''))})",
            0, 0, progress_callback
        )
        jhcis_connection = get_jhcis_connection(hospital, jhcis_default)
        jhcis_cursor = jhcis_connection.cursor(dictionary=True)
        jhcis_cursor.execute("START TRANSACTION READ ONLY")
        jhcis_cursor.execute(query)
        if not jhcis_cursor.description:
            raise RuntimeError("jhcis_extract_sql ต้องคืนผลลัพธ์เป็นชุดข้อมูล")

        source_columns = [column[0] for column in jhcis_cursor.description]
        for column in source_columns:
            _validate_dynamic_identifier(column, "คอลัมน์จาก jhcis_extract_sql")
        if len(set(column.lower() for column in source_columns)) != len(source_columns):
            raise RuntimeError("jhcis_extract_sql คืนชื่อคอลัมน์ซ้ำ")

        district_connection = get_district_connection(district_db)
        district_cursor = district_connection.cursor()
        district_cursor.execute(
            f"SELECT * FROM {_quote_dynamic_identifier(destination_table)} LIMIT 0"
        )
        if not district_cursor.description:
            raise RuntimeError(f"ไม่พบคอลัมน์ในตาราง {destination_table}")
        destination_columns = [column[0] for column in district_cursor.description]
        district_cursor.fetchall()
        destination_by_lower = {
            column.lower(): column for column in destination_columns
        }
        transfer_columns = []
        used_destination_columns = set()
        for source in source_columns:
            target_column = destination_by_lower.get(source.lower())
            if target_column is None and source.lower() == "pcucodeperson":
                target_column = destination_by_lower.get("hospcode")
            if target_column is None:
                continue
            if target_column.lower() in used_destination_columns:
                raise RuntimeError(
                    f"หลายคอลัมน์จาก JHCIS ถูกจับคู่ไปยัง {target_column}"
                )
            used_destination_columns.add(target_column.lower())
            transfer_columns.append((source, target_column))
        if not transfer_columns:
            raise RuntimeError(
                f"ไม่พบคอลัมน์ร่วมกันระหว่าง jhcis_extract_sql และ {destination_table}; "
                "ตั้งชื่อหรือ alias คอลัมน์ SQL ให้ตรงกับตารางอำเภอ"
            )

        insert_columns = [destination for _, destination in transfer_columns]
        insert_sql = (
            f"INSERT INTO {_quote_dynamic_identifier(destination_table)} "
            f"({', '.join(_quote_dynamic_identifier(column) for column in insert_columns)}) "
            f"VALUES ({', '.join(['%s'] * len(insert_columns))}) "
            f"ON DUPLICATE KEY UPDATE "
            + ", ".join(
                f"{_quote_dynamic_identifier(column)}=VALUES({_quote_dynamic_identifier(column)})"
                for column in insert_columns
            )
        )
        _dynamic_report(
            task_code,
            f"เริ่มบันทึกข้อมูลเข้า {destination_table}",
            0, 0, progress_callback
        )
        while True:
            batch = jhcis_cursor.fetchmany(batch_size)
            if not batch:
                break
            values = [
                tuple(row[source] for source, _ in transfer_columns)
                for row in batch
            ]
            district_cursor.executemany(insert_sql, values)
            district_connection.commit()
            uploaded_rows += len(batch)
            _dynamic_report(
                task_code,
                f"{hospital.get('code', '')}: บันทึก {uploaded_rows} แถวเข้า {destination_table}",
                uploaded_rows, 0, progress_callback
            )

        _dynamic_report(
            task_code,
            f"{hospital.get('code', '')}: ดึงเข้า {destination_table} สำเร็จ "
            f"({uploaded_rows} แถว)",
            uploaded_rows, uploaded_rows, progress_callback
        )
        return {
            "success": True,
            "task_code": task_code,
            "hospital": hospital,
            "destination_table": destination_table,
            "count": uploaded_rows,
            "message": f"สำเร็จ: {uploaded_rows} แถวเข้า {destination_table}",
        }
    except Exception as error:
        if district_connection is not None:
            try:
                district_connection.rollback()
            except Error as rollback_error:
                log_error(f"[{task_code}] rollback ฐานอำเภอไม่สำเร็จ: {rollback_error}")
        log_error(
            f"[{task_code}] JHCIS → ฐานอำเภอ "
            f"({hospital.get('code', '')}) ล้มเหลวหลังบันทึก {uploaded_rows} แถว: {error}"
        )
        raise
    finally:
        if jhcis_cursor is not None:
            try:
                jhcis_connection.rollback()
            except Error as rollback_error:
                log_error(f"[{task_code}] rollback JHCIS ไม่สำเร็จ: {rollback_error}")
        _close_dynamic_resources(
            [
                resource for resource in (
                    jhcis_connection, jhcis_cursor,
                    district_connection, district_cursor
                )
                if resource is not None
            ]
        )


def run_sync_task(task_row, config=None, progress_callback=None):
    config = config or load_config()
    district_db = get_district_db_config(config)
    hostatom_db = config.get("hostatom_db", {})
    try:
        batch_size = int(hostatom_db.get("batch_size", 500))
    except (TypeError, ValueError) as error:
        raise ValueError("batch_size ต้องเป็นจำนวนเต็ม") from error
    if batch_size <= 0:
        raise ValueError("batch_size ต้องมากกว่า 0")

    task_code = str(task_row.get("task_code", "")).strip()
    if not task_code:
        raise ValueError("Mapping ไม่มี task_code")
    source_table = _validate_dynamic_identifier(
        task_row.get("district_table", task_row.get("local_source_table")),
        "district_table"
    )
    staging_table = _validate_dynamic_identifier(
        task_row.get("host_staging_table"), "host_staging_table"
    )
    procedure_name = _validate_dynamic_identifier(
        task_row.get("host_procedure_name"), "host_procedure_name"
    )

    resources = []
    district_connection = None
    hostatom_connection = None
    host_lock_acquired = False
    host_lock_name = None
    uploaded_rows = 0
    total_rows = 0
    try:
        _dynamic_report(task_code, "Step 1: อ่านข้อมูลจากฐานอำเภอ", 0, 0, progress_callback)
        district_connection = get_district_connection(district_db)
        resources.append(district_connection)

        count_cursor = district_connection.cursor()
        resources.append(count_cursor)
        count_cursor.execute(f"SELECT COUNT(*) FROM {_quote_dynamic_identifier(source_table)}")
        total_rows = int(count_cursor.fetchone()[0])

        source_cursor = district_connection.cursor()
        resources.append(source_cursor)
        source_cursor.execute(f"SELECT * FROM {_quote_dynamic_identifier(source_table)}")
        if not source_cursor.description:
            raise RuntimeError(f"ไม่พบคอลัมน์ในตาราง {source_table}")
        source_columns = [column[0] for column in source_cursor.description]
        if len(set(source_columns)) != len(source_columns):
            raise RuntimeError(f"ตาราง {source_table} มีชื่อคอลัมน์ซ้ำ")
        _dynamic_report(
            task_code,
            f"Step 2: อ่าน {source_table} ({len(source_columns)} คอลัมน์, {total_rows} แถว)",
            0,
            total_rows,
            progress_callback
        )

        hostatom_connection = get_district_sync_hostatom_connection(hostatom_db)
        resources.append(hostatom_connection)
        host_cursor = hostatom_connection.cursor()
        resources.append(host_cursor)
        lock_key = f"{hostatom_db.get('database', '')}:{staging_table}".encode("utf-8")
        host_lock_name = "district_sync_" + hashlib.sha256(lock_key).hexdigest()[:32]
        host_cursor.execute("SELECT GET_LOCK(%s, %s)", (host_lock_name, 30))
        lock_result = host_cursor.fetchone()
        if not lock_result or lock_result[0] != 1:
            raise TimeoutError(f"ล็อก staging table {staging_table} ไม่สำเร็จภายใน 30 วินาที")
        host_lock_acquired = True
        _dynamic_report(task_code, f"Step 3: ล็อก {staging_table} สำเร็จ", 0, total_rows, progress_callback)
        host_cursor.execute(f"TRUNCATE TABLE {_quote_dynamic_identifier(staging_table)}")
        hostatom_connection.commit()

        host_cursor.execute(f"SELECT * FROM {_quote_dynamic_identifier(staging_table)} LIMIT 0")
        if not host_cursor.description:
            raise RuntimeError(f"ไม่พบคอลัมน์ใน staging table {staging_table}")
        staging_columns = [column[0] for column in host_cursor.description]
        host_cursor.fetchall()
        staging_by_lower = {column.lower(): column for column in staging_columns}
        transfer_columns = [
            (source_column, staging_by_lower[source_column.lower()])
            for source_column in source_columns
            if source_column.lower() in staging_by_lower
            and source_column.lower() not in ("batch_id", "uploaded_at")
        ]
        skipped_columns = [
            column for column in source_columns
            if column.lower() not in staging_by_lower
        ]
        if skipped_columns:
            _dynamic_report(
                task_code,
                f"Step 3: ข้ามคอลัมน์ที่ไม่มีใน staging: {', '.join(skipped_columns)}",
                0,
                total_rows,
                progress_callback
            )
        if not transfer_columns:
            raise RuntimeError("ไม่พบคอลัมน์ร่วมกันระหว่าง source table และ staging table")

        batch_id_column = staging_by_lower.get("batch_id")
        insert_columns = [target for _, target in transfer_columns]
        if batch_id_column:
            insert_columns.append(batch_id_column)
        insert_sql = (
            f"INSERT INTO {_quote_dynamic_identifier(staging_table)} "
            f"({', '.join(_quote_dynamic_identifier(column) for column in insert_columns)}) "
            f"VALUES ({', '.join(['%s'] * len(insert_columns))})"
        )
        source_indexes = {column: index for index, column in enumerate(source_columns)}
        batch_id = uuid.uuid4().hex
        _dynamic_report(task_code, f"Step 3: เริ่มส่งข้อมูลเข้า {staging_table}", 0, total_rows, progress_callback)

        while True:
            batch = source_cursor.fetchmany(batch_size)
            if not batch:
                break
            values = []
            for row in batch:
                row_values = tuple(
                    row[source_indexes[source_column]]
                    for source_column, _ in transfer_columns
                )
                if batch_id_column:
                    row_values += (batch_id,)
                values.append(row_values)
            host_cursor.executemany(insert_sql, values)
            hostatom_connection.commit()
            uploaded_rows += len(batch)
            _dynamic_report(
                task_code,
                f"Step 3: ส่งเข้า {staging_table} ({uploaded_rows}/{total_rows})",
                uploaded_rows,
                total_rows,
                progress_callback
            )

        _dynamic_report(
            task_code,
            f"Step 4: เรียก {procedure_name} เพื่อ merge ลง real table",
            uploaded_rows,
            total_rows,
            progress_callback
        )
        procedure_cursor = hostatom_connection.cursor()
        resources.append(procedure_cursor)
        procedure_cursor.callproc(procedure_name)
        for result_cursor in procedure_cursor.stored_results():
            result_cursor.fetchall()
            result_cursor.close()
        hostatom_connection.commit()
        result = {
            "success": True,
            "task_code": task_code,
            "count": uploaded_rows,
            "message": f"สำเร็จ: ส่ง {uploaded_rows} แถวและเรียก {procedure_name} แล้ว",
        }
        _dynamic_report(
            task_code,
            f"Step 4: merge สำเร็จ ({uploaded_rows} แถว)",
            uploaded_rows,
            total_rows,
            progress_callback
        )
        return result
    except Exception as error:
        if district_connection is not None:
            try:
                district_connection.rollback()
            except Error as rollback_error:
                log_error(f"[{task_code}] rollback MySQL อำเภอล้มเหลว: {rollback_error}")
        if hostatom_connection is not None:
            try:
                hostatom_connection.rollback()
            except Error as rollback_error:
                log_error(f"[{task_code}] rollback HostAtom ล้มเหลว: {rollback_error}")
        log_error(f"[{task_code}] Pipeline ล้มเหลว: {error}")
        raise
    finally:
        if host_lock_acquired and hostatom_connection is not None:
            release_cursor = None
            try:
                release_cursor = hostatom_connection.cursor()
                release_cursor.execute("SELECT RELEASE_LOCK(%s)", (host_lock_name,))
                release_cursor.fetchone()
            except Error as error:
                log_error(f"[{task_code}] ปลดล็อก staging table ไม่สำเร็จ: {error}")
            finally:
                if release_cursor is not None:
                    release_cursor.close()
        _close_dynamic_resources(resources)