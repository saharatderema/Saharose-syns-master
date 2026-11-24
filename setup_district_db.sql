CREATE DATABASE IF NOT EXISTS district_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
USE district_db;

CREATE TABLE IF NOT EXISTS sql_mapping (
    id INT NOT NULL AUTO_INCREMENT,
    task_code VARCHAR(50) NOT NULL,
    task_name VARCHAR(150) NOT NULL,
    jhcis_extract_sql LONGTEXT NULL,
    district_table VARCHAR(128) NOT NULL,
    host_staging_table VARCHAR(128) NOT NULL,
    host_procedure_name VARCHAR(128) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    sort_order INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_sql_mapping_task_code (task_code),
    KEY ix_sql_mapping_active_order (is_active, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS org_person (
    hospcode VARCHAR(20) NOT NULL,
    pid VARCHAR(20) NOT NULL,
    cid VARCHAR(20) NULL,
    prename VARCHAR(50) NULL,
    fname VARCHAR(100) NULL,
    lname VARCHAR(100) NULL,
    sex CHAR(1) NULL,
    birth DATE NULL,
    typelive CHAR(1) NULL,
    dischargetype CHAR(1) NULL,
    d_update DATETIME NULL,
    PRIMARY KEY (hospcode, pid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO sql_mapping (
    task_code,
    task_name,
    jhcis_extract_sql,
    district_table,
    host_staging_table,
    host_procedure_name,
    is_active,
    sort_order
) VALUES (
    'PERSON',
    'ข้อมูลบุคคล',
    NULL,
    'org_person',
    'store_person',
    'sp_merge_person',
    1,
    10
);
