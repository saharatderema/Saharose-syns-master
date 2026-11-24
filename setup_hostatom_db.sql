CREATE TABLE IF NOT EXISTS store_person (
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
    batch_id VARCHAR(50) NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (hospcode, pid),
    KEY ix_store_person_batch (batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS real_person (
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
    last_synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (hospcode, pid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_merge_person$$
CREATE PROCEDURE sp_merge_person()
BEGIN
    INSERT INTO real_person (
        hospcode,
        pid,
        cid,
        prename,
        fname,
        lname,
        sex,
        birth,
        typelive,
        dischargetype,
        d_update,
        last_synced_at
    )
    SELECT
        hospcode,
        pid,
        cid,
        prename,
        fname,
        lname,
        sex,
        birth,
        typelive,
        dischargetype,
        d_update,
        CURRENT_TIMESTAMP
    FROM store_person
    ON DUPLICATE KEY UPDATE
        cid = VALUES(cid),
        prename = VALUES(prename),
        fname = VALUES(fname),
        lname = VALUES(lname),
        sex = VALUES(sex),
        birth = VALUES(birth),
        typelive = VALUES(typelive),
        dischargetype = VALUES(dischargetype),
        d_update = VALUES(d_update),
        last_synced_at = CURRENT_TIMESTAMP;

    DELETE FROM store_person;
END$$

DELIMITER ;
