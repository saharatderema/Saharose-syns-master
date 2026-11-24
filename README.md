# SAHARose Sync Master (ระบบลิงค์ข้อมูลอัตโนมัติ) - คู่มือการติดตั้งและใช้งาน

โปรแกรมสำหรับดึงข้อมูลจากตาราง `person` ในฐานข้อมูล MySQL (JHCIS) ของ รพ.สต. หลายแห่ง
ผ่านวง Radmin VPN และส่งข้อมูลผ่านอินเทอร์เน็ตไปยังฐานข้อมูล Remote MySQL บน Web Hosting (HostAtom)

---

## โครงสร้างไฟล์ในโปรเจกต์

| ไฟล์ / โฟลเดอร์ | รายละเอียด |
|---|---|
| `requirements.txt` | รายการไลบรารีที่ต้องติดตั้ง |
| `app_paths.py` | แยก path ของทรัพยากรที่ bundle กับไฟล์ config/log ที่เขียนได้ |
| `config.example.json` | ค่าเริ่มต้นที่ไม่มี credentials ใช้สร้าง config ภายนอกครั้งแรก |
| `config.json` | ไฟล์ตั้งค่าการเชื่อมต่อฐานข้อมูล, รพ.สต., การแจ้งเตือน และกำหนดเวลา |
| `sql/extract_person.sql` | คำสั่ง SQL สำหรับดึงข้อมูลจากตาราง person ของ JHCIS |
| `table_setup_hostatom.sql` | คำสั่ง SQL สำหรับสร้างตาราง central_person บน HostAtom |
| `sync_engine.py` | โมดูลจัดการเชื่อมต่อฐานข้อมูล, เช็ก VPN, ดึง-ส่งข้อมูลแบบ Batch Upsert |
| `district_sync_ui.py` | หน้าต่าง District Dynamic Sync ที่ต่อยอดจากโปรแกรมเดิม |
| `setup_district_db.sql` | สร้าง `sql_mapping` และ `org_person` บน MySQL อำเภอ |
| `setup_hostatom_db.sql` | สร้าง `store_person`, `real_person` และ `sp_merge_person` บน HostAtom |
| `notifier.py` | โมดูลส่งแจ้งเตือนผ่าน Telegram Bot API และ LINE Messaging API |
| `main.py` | หน้าต่างโปรแกรม GUI (Tkinter / ttk) |
| `build.bat` | สร้างแอปแบบ onedir ด้วย PyInstaller |
| `build_exe.bat` | คำสั่งรองรับชื่อสคริปต์ Build เดิม เรียก `build.bat` |
| `installer.iss` | Inno Setup script สำหรับสร้าง `Setup_SAHARoseSyncMaster.exe` |
| `sync.log` | ไฟล์บันทึกเหตุการณ์และข้อผิดพลาด (สร้างอัตโนมัติ) |

---

## ขั้นตอนที่ 1: ติดตั้งโปรแกรมและสภาพแวดล้อม

### 1.1 ติดตั้ง Python
ดาวน์โหลดและติดตั้ง Python 3.10 ขึ้นไปจาก [python.org](https://www.python.org/)

### 1.2 สร้าง Virtual Environment และติดตั้งแพ็กเกจ
เปิด Command Prompt หรือ PowerShell ที่โฟลเดอร์โปรเจกต์ แล้วรันคำสั่ง:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

แพ็กเกจ `customtkinter` เป็นไลบรารี UI หลัก (ติดตั้งแยกได้ด้วย `pip install customtkinter`)
และจัดการ High DPI scaling อัตโนมัติบน Windows

หรือใช้ไฟล์ `build.bat` ซึ่งจะสร้าง venv และติดตั้งแพ็กเกจให้โดยอัตโนมัติ

## ขั้นตอนที่ 2: ตั้งค่าฝั่ง HostAtom (DirectAdmin + phpMyAdmin)

### 2.1 เปิด Remote MySQL Access บน DirectAdmin
1. เข้าสู่ระบบ DirectAdmin ของ HostAtom
2. ไปที่เมนู **Remote MySQL** (อยู่ในหมวด Extra Features หรือ Advanced)
3. เพิ่ม IP แอดเดรสของเครื่องที่จะใช้รันโปรแกรมนี้ (เช่น IP ของสำนักงานหรือ VPN Gateway)
   - หากไม่ทราบ IP ให้ใช้ `%` เพื่ออนุญาตทุก IP (ไม่แนะนำในระบบproduction)
4. บันทึกการตั้งค่า

### 2.2 สร้างฐานข้อมูลและผู้ใช้บน HostAtom
1. ใน DirectAdmin ไปที่ **MySQL Management**
2. สร้างฐานข้อมูลใหม่ (เช่น `jhcis_central`)
3. สร้างผู้ใช้ฐานข้อมูลและกำหนดรหัสผ่าน
4. เพิ่มผู้ใช้เข้าไปในฐานข้อมูลที่สร้าง และกำหนดสิทธิ์ทั้งหมด (All Privileges)

### 2.3 Import ตาราง central_person ผ่าน phpMyAdmin
1. เข้าสู่ระบบ **phpMyAdmin** บน HostAtom
2. เลือกฐานข้อมูลที่สร้างไว้
3. คลิกแท็บ **SQL** แต่วางคำสั่งจากไฟล์ `table_setup_hostatom.sql`:

```sql
CREATE TABLE IF NOT EXISTS central_person (
    pcucodeperson VARCHAR(20) NOT NULL,
    pid VARCHAR(20) NOT NULL,
    cid VARCHAR(20),
    prename VARCHAR(50),
    fname VARCHAR(100),
    lname VARCHAR(100),
    sex CHAR(1),
    birth DATE,
    typelive CHAR(1),
    dischargetype CHAR(1),
    d_update DATETIME,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (pcucodeperson, pid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

4. คลิก **Go** เพื่อรันคำสั่ง
5. ตรวจสอบว่ามีตาราง `central_person` ปรากฏในรายการตาราง

> ⚠️ หมายเหตุ: ไฟล์ `table_setup_hostatom.sql` ไม่มีคำสั่ง `CREATE DATABASE` ตามที่ระบุไว้ ให้สร้างฐานข้อมูลผ่าน DirectAdmin ก่อนเสมอ

## ขั้นตอนที่ 3: ตั้งค่า config.json

เปิดไฟล์ `config.json` ด้วยโปรแกรมแก้ไขข้อความ (เช่น Notepad, VS Code) และแก้ไขดังนี้:

```json
{
  "district_db": {
    "host": "127.0.0.1",
    "port": 3306,
    "database": "district_db",
    "user": "root",
    "password": ""
  },
  "hostatom_db": {
    "host": "your-domain.com",
    "port": 3306,
    "database": "ชื่อฐานข้อมูลบน HostAtom",
    "user": "ชื่อผู้ใช้ฐานข้อมูล",
    "password": "รหัสผ่านฐานข้อมูล",
    "batch_size": 500
  },
  "jhcis_default": {
    "port": 3333,
    "database": "jhcisdb",
    "user": "root",
    "password": ""
  },
  "schedule": {
    "enabled": false,
    "sync_times": ["12:00", "16:30"],
    "target_mode": "selected",
    "notify_on_auto": true
  },
  "district_sync_schedule": {
    "enabled": false,
    "sync_times": ["12:00", "17:00"],
    "notify_on_auto": true
  },
  "start_with_windows": true,
  "notification": {
    "telegram_enabled": false,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "line_enabled": false,
    "line_channel_token": "",
    "line_user_id": ""
  },
  "hospitals": [
    {
      "code": "11915",
      "name": "รพ.สต.ตัวอย่าง 1",
      "ip": "26.100.1.10",
      "port": 3333,
      "selected": true
    },
    {
      "code": "09491",
      "name": "รพ.สต.ตัวอย่าง 2",
      "ip": "26.100.2.20",
      "port": 3333,
      "selected": true
    }
  ]
}
```

## ขั้นตอนที่ 4: วิธีหา Telegram Bot Token และ Chat ID

### Telegram Bot
1. เปิด Telegram แล้วค้นหา **@BotFather**
2. ส่งคำสั่ง `/newbot` และทำตามขั้นตอนตั้งชื่อบอท
3. BotFather จะส่ง **Bot Token** ให้ (ตัวอย่าง: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
4. นำ Bot Token ไปใส่ใน `config.json` ฟิลด์ `telegram_bot_token`

### Telegram Chat ID
1. ส่งข้อความอะไรก็ได้ไปยังบอทที่สร้างขึ้น
2. เปิดลิงก์ในเบราว์เซอร์:
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
   (แทนที่ `<BOT_TOKEN>` ด้วยโทเคนที่ได้รับจาก BotFather)
3. ดูค่า `"chat":{"id":123456789}` ในข้อความตอบกลับ นั่นคือ **Chat ID**
4. นำ Chat ID ไปใส่ใน `config.json` ฟิลด์ `telegram_chat_id`

### LINE Messaging API
1. เข้าไปที่ [LINE Developers Console](https://developers.line.biz/console/)
2. สร้าง Provider และสร้างช่องทางประเภท **Messaging API**
3. คัดลอก **Channel access token (long-lived)** ไปใส่ใน `line_channel_token`
4. ใช้ฟีเจอร์ **Inspect** หรือ Webhook เพื่อหา **User ID** ของผู้ที่ต้องการรับข้อความ
5. นำ User ID ไปใส่ใน `line_user_id`

## ขั้นตอนที่ 5: วิธีรันโปรแกรม

### รันในโหมดพัฒนา (ผ่าน Python)
```powershell
.venv\Scripts\activate
python main.py
```

### รันในโหมด .exe (หลังจาก Build)
```powershell
.\dist\SAHARoseSyncMaster\SAHARoseSyncMaster.exe
```

หน้าต่างหลักใช้ CustomTkinter สำหรับ UI สไตล์ Modern และเลือกฟอนต์ภาษาไทยที่ติดตั้งอยู่ตามลำดับ
Sarabun, Prompt, Leelawadee UI, Tahoma และ Segoe UI (หากไม่มีจะใช้ฟอนต์ระบบสำรอง)
CustomTkinter จัดการ High DPI scaling โดยอัตโนมัติ โดยไม่ตั้ง DPI awareness ซ้ำผ่าน `ctypes`
หากต้องการรูปแบบ Sarabun โดยเฉพาะ ให้ติดตั้งฟอนต์ Sarabun ใน Windows ก่อนเปิดโปรแกรม
    {
      "code": "15107",
      "name": "รพ.สต.ตัวอย่าง 3",
      "ip": "26.100.3.30",
      "selected": true
    }
  ]
}
```

### คำอธิบายฟิลด์สำคัญ
- **hostatom_db.host**: โดเมนของ Web Hosting HostAtom (เช่น `your-domain.com` หรือ `server.hostatom.com`)
- **district_db.port** และ **hostatom_db.port**: ปกติใช้ `3306`; เป็นพอร์ตฐานข้อมูลอำเภอและ Cloud DB ตามลำดับ
- **hostatom_db.batch_size**: จำนวนแถวต่อการส่ง 1 ครั้ง (แนะนำ `500` เพื่อป้องกัน `max_allowed_packet` ของ Shared Hosting)
- **hospitals[].port**: พอร์ต MySQL ของ JHCIS เครื่องลูกข่ายผ่าน Radmin VPN; ค่าเริ่มต้น `3333` และกำหนดแยกแต่ละ รพ.สต. ได้
- **jhcis_default.port**: ค่าเก่าที่เก็บไว้เพื่อความเข้ากันได้; การเชื่อมต่อ รพ.สต. ใช้ `hospitals[].port` โดยตรง
- **district_db.host**: Host ของ MySQL อำเภอ (เช่น `127.0.0.1` หรือ IP/ชื่อเครื่องแม่ข่าย); ตั้งค่าได้จากแท็บ **การตั้งค่าเครื่องมือ**
- **hospitals[].ip**: IP ของ รพ.สต. ในวง Radmin VPN (รูปแบบ `26.x.x.x`)
- **hospitals[].selected**: `true` = เลือกไว้ในรายการเริ่มต้น, `false` = ไม่เลือก

## ขั้นตอนที่ 6: Build และสร้าง Windows Installer

### 6.1 Build โปรแกรม

ติดตั้ง Python 3.10 ขึ้นไป แล้วรัน `build.bat` โดยดับเบิลคลิกหรือจาก Command Prompt:

```powershell
build.bat
```

สคริปต์จะ:
1. สร้าง Virtual Environment หากยังไม่มี และติดตั้งแพ็กเกจจาก `requirements.txt`
2. รัน PyInstaller ด้วย `--onedir --windowed` และรวบรวม assets ของ CustomTkinter กับ MySQL Connector
3. Bundle เฉพาะ `config.example.json` ซึ่งไม่มี credentials; ไม่ฝัง `config.json` ของเครื่องผู้พัฒนา

หลัง Build ไฟล์โปรแกรมอยู่ที่:
```
dist\SAHARoseSyncMaster\SAHARoseSyncMaster.exe
```

### 6.2 สร้างตัวติดตั้ง

ติดตั้ง [Inno Setup 6](https://jrsoftware.org/isinfo.php), จากนั้นเปิด `installer.iss` ด้วย Inno Setup Compiler
แล้วกด **Compile** หรือรัน `ISCC.exe installer.iss` จากโฟลเดอร์โปรเจกต์ หลัง Build สำเร็จจะได้:

```
installer\Setup_SAHARoseSyncMaster.exe
```

ตัวติดตั้งเป็นแบบ per-user ไม่ต้องใช้สิทธิ์ Administrator และติดตั้งใต้
`%LOCALAPPDATA%\Programs\SAHARoseSyncMaster` เพื่อให้โปรแกรมเขียน `config.json` และ `sync.log` ได้
โดยไม่ต้องยกระดับสิทธิ์ พร้อมสร้าง Shortcut ใน Start Menu และ Desktop

ไฟล์ `config.json` อยู่ในโฟลเดอร์ติดตั้งและแก้ไขได้โดยตรง; ตัวติดตั้งใช้ `config.example.json`
สร้างไฟล์เริ่มต้นเฉพาะเมื่อยังไม่มี config และจะเก็บ config ไว้เมื่อถอนการติดตั้ง ส่วนการรัน EXE
จาก `dist` โดยตรงจะสร้าง config จากไฟล์ตัวอย่างที่ bundle ไว้ในการเปิดครั้งแรก

---

## ขั้นตอนที่ 7: วิธีการใช้งานโปรแกรม

### หน้าต่างหลัก (Main Window)

เมนูหลักอยู่ในแถบด้านซ้าย: **ภาพรวม**, **Mapping**, **ควบคุมการทำงาน**,
**การตั้งค่า** และ **ผู้พัฒนา**; เลือกเมนูเพื่อสลับพื้นที่ทำงานทางด้านขวา
หน้าต่างรองรับการย่อ-ขยายและ High DPI scaling อัตโนมัติของ CustomTkinter
หน้า **การตั้งค่า** มีแถบเลื่อนแนวตั้งและรองรับการเลื่อนด้วยล้อเมาส์เมื่อเนื้อหาเกินพื้นที่แสดงผล

#### แท็บการตั้งค่า
| ปุ่ม | รายละเอียด |
|---|---|
| **ตั้งค่าฐานข้อมูล Cloud DB (HostAtom)** | ตั้งค่า Host, Port, Database, User, Password, Batch Size ในแท็บการตั้งค่าเครื่องมือ พร้อมปุ่มทดสอบและบันทึก |
| **🏥 จัดการรายชื่อ รพ.สต.** | คลิกเลือกรายชื่อเพื่อโหลดค่าล่าสุดลงฟอร์ม แล้วเพิ่ม, แก้ไข หรือลบ รหัส, ชื่อ, IP, Port, ชื่อฐานข้อมูล, User และ Password JHCIS รายแห่ง; บันทึกลง `config.json` และรายการเดิมที่ไม่มีค่ารายแห่งยังใช้ค่า `jhcis_default` |
| **🔔 ตั้งค่าแจ้งเตือน** | ตั้งค่า Telegram Bot Token / Chat ID และ LINE Channel Token / User ID มีปุ่มทดสอบส่งข้อความ |
| **เปิดโปรแกรมพร้อม Windows** | เปิด/ปิดการเริ่มโปรแกรมอัตโนมัติสำหรับบัญชี Windows ปัจจุบัน |
| **ตั้งค่าฐานข้อมูลอำเภอ** | กำหนด Host, Port, Database, User และ Password (อนุญาตให้ว่าง) ลง `district_db` ใน `config.json`; การทดสอบและการซิงค์ใช้ค่าที่บันทึกไว้นี้ชุดเดียวกัน จึงต้องบันทึกก่อนทดสอบ |
| **ตั้งค่าฐานข้อมูล Cloud DB** | ตั้งค่า Host, Port, Database, User, Password และ Batch Size |

สถานะการเชื่อมต่อของฐานข้อมูลอำเภอและ Cloud DB จะแสดงอัตโนมัติเมื่อเปิดแท็บการตั้งค่า ตรวจซ้ำทุก 60 วินาทีขณะอยู่ในแท็บ และตรวจใหม่หลังบันทึกการตั้งค่า

#### แถบควบคุมการทำงาน
| ปุ่ม | รายละเอียด |
|---|---|
| **1. ตรวจสอบ VPN (พอร์ต รพ.สต.)** | ตรวจสอบพอร์ตที่ตั้งแยกไว้ของ รพ.สต. ทั้งหมดที่อยู่ในรายการ (ค่าเริ่มต้น `3333`) |
| **ดึง JHCIS (ลูกข่าย) → ฐานอำเภอ** | ดึงข้อมูลตาม `jhcis_extract_sql` ของ Mapping ที่เปิดใช้งาน จาก รพ.สต. ที่เลือก แล้ว Upsert เข้า `district_table` |
| **ดึงฐานอำเภอ → Cloud DB** | ส่งข้อมูลจาก `district_table` ของ Mapping ที่เปิดใช้งานเข้า staging และเรียก Stored Procedure บน Cloud DB |
| **ซิงค์ Person → Cloud DB (2 ขั้นตอน)** | ทำงานต่อเนื่องโดยดึงข้อมูลจาก JHCIS ของ รพ.สต. ที่เลือกเข้า `district_table` ก่อน แล้วจึงส่งข้อมูลจากฐานอำเภอเข้า Cloud DB; หากขั้นแรกมีข้อผิดพลาดจะข้ามขั้นที่สอง |
| **⏰ ตั้งค่า Auto-Schedule** | ตั้งเวลาซิงค์อัตโนมัติ, โหมดเปิด/ปิด, รอบเวลา, ขอบเขต, การแจ้งเตือน |

ใต้แถบควบคุมมีแผง **หน้าต่างประมวลผลแบบเรียลไทม์** แสดง log และขั้นตอนจากงานซิงค์
พร้อมสถานะกำลังทำงาน/พร้อมทำงาน; เลื่อนดูรายการล่าสุดได้ และกด **ล้างรายการ** เพื่อล้างเฉพาะหน้าจอ
โดยไฟล์ `sync.log` ยังคงเก็บประวัติเดิมไว้

#### ตารางแสดงผล (Treeview)
คอลัมน์: `เลือก | รหัส | ชื่อสถานพยาบาล | Radmin IP | สถานะ VPN | ผลการซิงค์ล่าสุด`

- คลิกที่คอลัมน์ "เลือก" เพื่อสลับ ✓ / ✗ สำหรับแต่ละแถว
- เมื่อเปิดโปรแกรม ระบบตรวจสอบ VPN ของ รพ.สต. ทั้งหมดอัตโนมัติ โดยใช้ Port ของแต่ละแห่งใน `hospitals[].port`; สามารถกดปุ่มตรวจสอบ VPN เพื่อตรวจซ้ำได้
- สถานะ VPN แสดงเป็นวงกลมสีเขียวกระพริบเมื่อออนไลน์ และสีแดงเมื่อออฟไลน์ โดยไม่ใช้ widget ลอยทับตาราง
- แผง **สถานะการไหลข้อมูล** แสดงความคืบหน้าล่าสุดของทั้ง `JHCIS → ฐานอำเภอ` และ `ฐานอำเภอ → Cloud DB`; คอลัมน์ผลซิงค์แสดงผลแยกตาม รพ.สต. สำหรับขั้นตอนแรก
- ผลการซิงค์ล่าสุดแสดงเช่น `✔ สำเร็จ: 500 รายการ` หรือ `❌ เชื่อมต่อไม่ได้`

แท็บ **ผู้พัฒนา** แสดงชื่อและตำแหน่งผู้พัฒนาโปรแกรม

#### แท็บ Mapping
- ใช้หน้าเดียวแบบ 2 คอลัมน์: เลือก Mapping ทางซ้าย และแก้ไขข้อมูล/SQL/สคริปต์ทางขวา; รายการจะโหลดใหม่ทุกครั้งที่เปิดแท็บ
- กด **เพิ่ม Mapping ใหม่** เพื่อเริ่มรายการ; เลือกแถวเพื่อโหลดข้อมูลเข้าฟอร์มอัตโนมัติ และกด **บันทึก Mapping** หรือ **ลบรายการ** ตามต้องการ
- ช่องชื่อ `District Table`, `Host Staging Table` และ `Host Procedure Name` จะเติมค่าเริ่มต้นตาม `Task Code` โดยผู้ใช้แก้ไขได้
- กด **ทดสอบ Mapping** เพื่อรัน SQL แบบอ่านอย่างเดียวบน JHCIS ของ รพ.สต. ที่เลือกไว้ (ถ้าไม่มีรายการที่เลือกจะใช้รายการแรก); แสดงเฉพาะสถานะ `Status: OK` หรือ `Status: ERROR` โดยไม่แสดงแถวข้อมูล
- กด **ดึงโครงสร้างคอลัมน์จาก SQL นี้** เพื่ออ่านเฉพาะ Metadata จาก JHCIS แล้วกำหนด Data Type และ Primary Key ก่อนสร้าง DDL
- กด **Generate SQL** เพื่อสร้างสคริปต์สำหรับ District Table, Host Store/Real Tables และ Host Procedure; สคริปต์ใช้ InnoDB/utf8mb4 และ Procedure จะลบข้อมูลใน staging หลัง merge
- แต่ละแท็บรองรับ **Copy**, **บันทึก .sql** และ **รันสร้างใน District DB/Cloud DB**; การ Execute ต้องยืนยันก่อน และไม่อนุญาตให้ทำระหว่างมีงานซิงค์
- การรัน DDL อาจ commit โดยอัตโนมัติและบางคำสั่งอาจสำเร็จก่อนคำสั่งถัดไปล้มเหลว ควรสำรองฐานข้อมูลและตรวจสอบสคริปต์ก่อนใช้งานจริง

### หน้าตั้งค่า Auto-Schedule (Toplevel)

| ตัวเลือก | รายละเอียด |
|---|---|
| เปิดใช้งาน Auto-Sync | เปิด/ปิดการทำงานอัตโนมัติ |
| ช่วงเวลาซิงค์ | เพิ่ม/ลบเวลาซิงค์ได้หลายรอบต่อวัน (รูปแบบ HH:MM) |
| ขอบเขต | `ดึงเฉพาะ รพ.สต. ที่ติ๊กเลือกไว้` หรือ `ดึงทุก รพ.สต. ที่ออนไลน์` |
| ส่งแจ้งเตือนอัตโนมัติ | เปิด/ปิดการส่งข้อความเข้า Telegram/LINE หลังซิงค์อัตโนมัติเสร็จ |
| บันทึกตารางเวลา | บันทึกลง config.json และเริ่มต้นตัวจับเวลาทันทีโดยไม่ต้องรีสตาร์ทโปรแกรม |

### ความแตกต่างระหว่าง Manual กับ Auto

| รายละเอียด | Manual | Auto-Schedule |
|---|---|---|
| Workflow | ✅ JHCIS → ฐานอำเภอ → Cloud DB ตาม Mapping | JHCIS → Cloud DB โดยตรง |
| แสดง messagebox | ✅ แสดงผลแยกตามทั้ง 2 ขั้นตอน | ❌ ไม่แสดง (ป้องกันโปรแกรมค้าง) |
| ส่งแจ้งเตือน | ✅ ส่ง (ถ้าเปิดใช้งาน) | ✅ ส่ง (ถ้า `notify_on_auto = true`) |
| อัปเดตตาราง | ✅ อัปเดต Real-time | ✅ อัปเดต Real-time |
| บันทึก sync.log | ✅ บันทึก | ✅ บันทึก |

---

## การแก้ไขปัญหาเบื้องต้น

| ปัญหา | สาเหตุที่เป็นไปได้ | วิธีแก้ไข |
|---|---|---|
| ไม่สามารถเชื่อมต่อ HostAtom | Remote MySQL Access ยังไม่เปิด / IP ไม่ถูกต้อง | ตั้งค่า Remote MySQL ใน DirectAdmin ให้อนุญาต IP ของเครื่อง |
| ตรวจสอบ VPN แล้วขึ้น ออฟไลน์ | Radmin VPN ไม่ได้เชื่อมต่อ / IP ผิด / พอร์ต 3333 ปิด | ตรวจสอบการเชื่อมต่อ Radmin VPN และ IP ของ รพ.สต. |
| MySQL server has gone away | ข้อมูลส่งครั้งละมากเกินไป / max_allowed_packet ต่ำ | ลดค่า `batch_size` ใน config.json เช่น เหลือ 200 หรือ 100 |
| ภาษาไทยในฐานข้อมูลเพี้ยน | Charset ของตารางไม่ใช่ utf8mb4 | ใช้ `table_setup_hostatom.sql` ที่กำหนด `utf8mb4_unicode_ci` แล้ว Import ใหม่ |
| โปรแกรมค้างเมื่อซิงค์ | มีการซิงค์อยู่แล้วหรือเครือข่ายช้ามาก | รอให้การซิงค์ปัจจุบันเสร็จสิ้น หรือเพิ่ม timeout ในโค้ด |

---

## หมายเหตุเพิ่มเติม

- ไฟล์ `sync.log` จะถูกสร้างในโฟลเดอร์เดียวกับ EXE ใช้สำหรับตรวจสอบประวัติการทำงานและข้อผิดพลาด
- การซิงค์แบบ Batch Upsert ใช้ `ON DUPLICATE KEY UPDATE` หากข้อมูลซ้ำจะอัปเดตแทนที่
- พื้นที่เก็บข้อมูลบน Shared Hosting อาจมีข้อจำกัด ให้เลือก `batch_size` ที่เหมาะสมกับแพ็กเกจ hosting ที่ใช้
- รุ่น Deploy ใช้รูปแบบ PyInstaller `onedir` (ไม่ต้องติดตั้ง Python บนเครื่องเป้าหมาย); แจกจ่ายผ่านตัวติดตั้ง `Setup_SAHARoseSyncMaster.exe`

---

## District Dynamic Data Sync (ส่วนขยายจากระบบเดิม)

ส่วนนี้เพิ่มหน้าต่าง **District Dynamic Sync** โดยไม่ลบ workflow เดิมที่ซิงค์ JHCIS ราย รพ.สต. เปิดได้จากปุ่ม **🏢 District Dynamic Sync** บนหน้าหลัก ทั้งสองระบบใช้ `hostatom_db` และ `notification` ร่วมกัน ส่วนการเชื่อมต่อ MySQL อำเภอและ Auto-Schedule ของ District แยกเก็บใน `district_db` และ `district_sync_schedule` เพื่อรักษาค่ากำหนดเดิม

### ติดตั้งฐานข้อมูล

1. บน MySQL อำเภอ รัน [setup_district_db.sql](./setup_district_db.sql) เพื่อสร้าง `district_db`, `sql_mapping`, `org_person` และ Mapping เริ่มต้น `PERSON`
2. ใน phpMyAdmin บน HostAtom เลือกฐานข้อมูลที่สร้างไว้ แล้ว Import [setup_hostatom_db.sql](./setup_hostatom_db.sql) (ไฟล์นี้ไม่มี `CREATE DATABASE`)
3. ผู้ใช้ HostAtom ที่แอปใช้ต้องมีสิทธิ์อ่าน/เขียน staging และ real tables, `DROP` สำหรับ `TRUNCATE`, และ `EXECUTE` สำหรับ Stored Procedure
4. ตั้งค่าอำเภอและ HostAtom ผ่านปุ่ม **ตั้งค่าฐานข้อมูล** ในหน้าต่าง District Sync

Mapping `PERSON` เริ่มต้นใช้ `district_table = org_person` และ `jhcis_extract_sql = NULL` เพราะ schema JHCIS อาจแตกต่างกันในแต่ละพื้นที่ ก่อนใช้ปุ่ม **ดึง JHCIS (ลูกข่าย) → ฐานอำเภอ** ให้ผู้ดูแลตรวจสอบและกำหนด SELECT ใน `jhcis_extract_sql` โดย alias ชื่อคอลัมน์ให้ตรงกับ `district_table` (เช่น `pcucodeperson AS hospcode`)

### Pipeline และการเพิ่มงาน

- ขั้นที่ 1 ใช้ `jhcis_extract_sql` อ่าน JHCIS ของ รพ.สต. ที่เลือก แล้ว Upsert คอลัมน์ที่ตรงกันเข้า `district_table` เป็นชุดย่อย; รองรับการจับคู่ `pcucodeperson` ไปยัง `hospcode`
- ขั้นที่ 2 อ่าน `district_table` แบบ dynamic และค้นพบคอลัมน์จาก `cursor.description`
- ส่งคอลัมน์ที่ตรงกับ staging table เป็น batches; `batch_id` สร้างโดยแอป และ `uploaded_at` ใช้ค่า default ของ Cloud DB
- ใช้ MySQL advisory lock ต่อ staging table, `TRUNCATE`, ส่ง batches พร้อม commit และเรียก Stored Procedure หลังส่งครบ
- `sp_merge_person` upsert ข้อมูลเข้า `real_person` และลบแถวจาก `store_person` หลัง merge

เมื่อต้องเพิ่มงานใหม่ ให้สร้าง JHCIS SELECT, ตารางในอำเภอ, staging table, real table และ Stored Procedure ที่เข้ากันก่อน จากนั้นเปิด **จัดการ SQL Mapping** เพื่อกำหนด `task_code`, `jhcis_extract_sql`, `district_table`, `host_staging_table`, `host_procedure_name`, `is_active` และ `sort_order` ชื่อ table/procedure รองรับ identifier ภาษาอังกฤษ ตัวเลข และ `_` เท่านั้น ส่วน SQL ใน `jhcis_extract_sql` ต้องเป็น SELECT ที่ตรวจสอบแล้ว

Auto-Schedule ของ District กำหนดหลายเวลาได้และแยกจาก Auto-Schedule เดิม หากเปิดไว้ หน้าต่าง District Sync จะเปิดพร้อมโปรแกรมเพื่อให้ตัว scheduler ทำงาน ส่วน Auto จะไม่แสดง Popup และแจ้งสรุปผ่าน Telegram/LINE ตามค่า `notify_on_auto`

---

**สร้างโดย:** Senior Python Developer & Data Engineer
**เวอร์ชัน:** 1.0
**วันที่:** พฤศจิกายน 2026
# Saharose-syns-master
# Saharose-syns-master
#   S a h a r o s e - s y n s - m a s t e r  
 #   S a h a r o s e - s y n s - m a s t e r  
 #   S a h a r o s e - s y n s - m a s t e r  
 