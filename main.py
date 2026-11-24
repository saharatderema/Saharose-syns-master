#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - หน้าต่างหลักของโปรแกรม SAHARose Sync Master (ระบบลิงค์ข้อมูลอัตโนมัติ)
รองรับการซิงค์แบบ Manual, Auto-Schedule และการแจ้งเตือนทาง Telegram / LINE
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import copy
import json
import os
import re
import sys
import subprocess
import threading
import time
from datetime import datetime

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

try:
    import schedule
except ImportError:
    schedule = None

try:
    import winreg
except ImportError:
    winreg = None

from mysql.connector import Error

from sync_engine import (
    load_config, save_config, check_vpn_port, get_jhcis_connection,
    get_hostatom_connection, test_hostatom_connection, extract_person_from_jhcis,
    upsert_person_to_hostatom, sync_hospital, sync_hospitals, get_jhcis_tables,
    get_jhcis_table_columns, preview_person_sql, validate_read_only_select,
    get_hospital_port, get_district_db_config,
    test_district_connection, test_district_sync_hostatom_connection,
    get_sql_mappings, save_sql_mapping,
    run_sync_task, sync_jhcis_to_district,
    log_info, log_error, resource_path
)
from notifier import send_notification
from district_sync_ui import DistrictSyncWindow

# Import UI Theme System
from ui_theme import (
    init_theme, setup_default_fonts, ctk_widgets as ttk,
    ContentStack, FONTS,
    SidebarNavigation, ToastManager, Colors, Spacing, Icons,
    create_card, create_section, create_card_section,
    create_primary_button, create_secondary_button, create_ghost_button,
    create_danger_button, create_success_button, create_warning_button,
    create_small_button, create_large_button,
    create_heading_label, create_title_label, create_muted_label, create_caption_label,
    create_status_label, create_treeview, create_progressbar,
    add_tooltip, center_window
)

CONFIG_FILE = "config.json"
PERSON_MAPPING_FIELDS = (
    "pcucodeperson",
    "pid",
    "cid",
    "prename",
    "fname",
    "lname",
    "sex",
    "birth",
    "typelive",
    "dischargetype",
    "d_update",
)
STARTUP_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REGISTRY_VALUE = "SAHARose Sync Master"
DATABASE_STATUS_REFRESH_INTERVAL_MS = 60 * 1000


def _windows_startup_command():
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable])

    script_path = os.path.abspath(__file__)
    interpreter = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(interpreter):
        interpreter = sys.executable
    startup_code = "import os,runpy;os.chdir({!r});runpy.run_path({!r},run_name='__main__')".format(
        os.path.dirname(script_path), script_path
    )
    return subprocess.list2cmdline([interpreter, "-c", startup_code])


def _set_windows_startup(enabled):
    if winreg is None:
        raise OSError("การตั้งค่าเริ่มต้นพร้อม Windows ใช้ได้เฉพาะบน Windows")

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        STARTUP_REGISTRY_KEY,
        0,
        winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                STARTUP_REGISTRY_VALUE,
                0,
                winreg.REG_SZ,
                _windows_startup_command()
            )
        else:
            try:
                winreg.DeleteValue(key, STARTUP_REGISTRY_VALUE)
            except FileNotFoundError:
                pass

class JHCISPersonSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SAHARose Sync Master (ระบบลิงค์ข้อมูลอัตโนมัติ)")
        minimum_width = min(960, max(320, self.root.winfo_screenwidth() - 40))
        minimum_height = min(620, max(240, self.root.winfo_screenheight() - 60))
        self.root.minsize(minimum_width, minimum_height)
        center_window(self.root, 1280, 820)

        # Initialize UI Theme System
        self.theme = init_theme(root)

        self.config_path = resource_path(CONFIG_FILE)
        self.config = self._load_config_safe()
        self.config.setdefault("district_sync_schedule", {
            "enabled": False, "sync_times": ["12:00", "17:00"], "notify_on_auto": True
        })
        self.district_sync_window = None
        self.start_with_windows = bool(self.config.get("start_with_windows", True))
        self.startup_error = None
        if winreg is not None:
            try:
                _set_windows_startup(self.start_with_windows)
            except OSError as e:
                self.startup_error = str(e)
        self.start_with_windows_var = tk.BooleanVar(value=self.start_with_windows)
        self.schedule_thread = None
        self.schedule_running = False
        self.sync_lock = threading.Lock()
        self.auto_sync_job_id = None
        self.vpn_indicator_states = {}
        self.vpn_blink_phase = False
        self.vpn_blink_job = None
        self.vpn_check_running = False
        self.database_status_check_job_id = None
        self.database_status_check_running = False

        self._setup_styles()
        self._setup_ui()
        self._load_hospitals_to_tree()
        self.vpn_blink_job = self.root.after(500, self._blink_vpn_indicators)
        self.root.after(500, self._check_all_vpn)
        self._update_auto_status_label()

        if self.config.get("schedule", {}).get("enabled", False) and schedule:
            self._start_scheduler()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        if self.config.get("district_sync_schedule", {}).get("enabled", False):
            self.root.after(500, self._open_district_sync)
        if self.startup_error:
            self.root.after_idle(lambda error=self.startup_error: messagebox.showerror(
                "ตั้งค่าเริ่มพร้อม Windows ไม่สำเร็จ", error
            ))

    def _load_config_safe(self):
        cfg = load_config()
        if not cfg:
            cfg = {
                "hostatom_db": {
                    "host": "", "port": 3306, "database": "", "user": "", "password": "", "batch_size": 500
                },
                "jhcis_default": {
                    "port": 3333, "database": "jhcisdb", "user": "root", "password": ""
                },
                "schedule": {
                    "enabled": False, "sync_times": ["12:00", "16:30"],
                    "target_mode": "selected", "notify_on_auto": True
                },
                "person_mapping": {field: field for field in PERSON_MAPPING_FIELDS},
                "start_with_windows": True,
                "notification": {
                    "telegram_enabled": False, "telegram_bot_token": "", "telegram_chat_id": "",
                    "line_enabled": False, "line_channel_token": "", "line_user_id": ""
                },
                "hospitals": []
            }
        return cfg

    def _setup_styles(self):
        """App-specific custom styles - base styles are handled by ui_theme"""
        style = ttk.Style()
        # App-specific treeview style for hospital list
        style.configure("Hospital.Treeview", rowheight=34, font=FONTS["BODY"])
        style.configure("Hospital.Treeview.Heading", font=FONTS["H3"])
        
        # Custom status indicator styles for VPN status
        style.configure("VPN.Online.TLabel", foreground=Colors.STATUS_ONLINE, font=FONTS["BODY"])
        style.configure("VPN.Offline.TLabel", foreground=Colors.STATUS_OFFLINE, font=FONTS["BODY"])
        style.configure("VPN.Warning.TLabel", foreground=Colors.STATUS_WARNING, font=FONTS["BODY"])
        style.configure("VPN.Syncing.TLabel", foreground=Colors.STATUS_SYNCING, font=FONTS["BODY"])

    def _setup_ui(self):
        app_shell = ttk.Frame(self.root, style="App.TFrame")
        app_shell.pack(fill=tk.BOTH, expand=True, padx=Spacing.SM, pady=Spacing.SM)
        app_shell.rowconfigure(0, weight=1)
        app_shell.columnconfigure(1, weight=1)

        self.content_notebook = ContentStack(
            app_shell, style="Content.TFrame"
        )
        self.content_notebook.grid(row=0, column=1, sticky=tk.NSEW)

        hospitals_tab = ttk.Frame(self.content_notebook)
        mapping_tab = ttk.Frame(self.content_notebook)
        control_tab = ttk.Frame(self.content_notebook)
        settings_tab = ttk.Frame(self.content_notebook)
        developer_tab = ttk.Frame(self.content_notebook)
        self.settings_tab = settings_tab
        pages = (
            (hospitals_tab, "ภาพรวม"),
            (mapping_tab, "Mapping"),
            (control_tab, "ควบคุมการทำงาน"),
            (settings_tab, "การตั้งค่า"),
            (developer_tab, "ผู้พัฒนา"),
        )
        for page, title in pages:
            self.content_notebook.add(page, text=title)
        SidebarNavigation(
            app_shell,
            self.content_notebook,
            (
                ("🏠", "ภาพรวม", hospitals_tab),
                ("🔗", "Mapping", mapping_tab),
                ("🔄", "ควบคุมการทำงาน", control_tab),
                ("⚙️", "การตั้งค่า", settings_tab),
                ("ℹ️", "ผู้พัฒนา", developer_tab),
            ),
        ).grid(row=0, column=0, sticky=tk.NS, padx=(0, Spacing.SM))
        self._setup_developer_tab(developer_tab)

        settings_content = ttk.ScrollableFrame(
            settings_tab,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=Colors.GRAY_300,
            scrollbar_button_hover_color=Colors.GRAY_400,
        )
        settings_content.pack(fill=tk.BOTH, expand=True)
        settings_view = settings_content
        self.settings_canvas = settings_content

        # === แถบด้านบน: การตั้งค่าและเครื่องมือ ===
        top_frame = ttk.LabelFrame(
            settings_content, text="⚙️ การตั้งค่าและเครื่องมือ", padding=10
        )
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        btn_row1 = ttk.Frame(top_frame)
        btn_row1.pack(fill=tk.X, pady=2)

        ttk.Button(btn_row1, text="🏥 จัดการรายชื่อ รพ.สต.",
                   command=self._open_hospital_manager).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row1, text="🔔 ตั้งค่าแจ้งเตือน",
                   command=self._open_notification_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btn_row1,
            text="🏢 District Dynamic Sync",
            command=self._open_district_sync
        ).pack(side=tk.LEFT, padx=5)

        district_frame = ttk.LabelFrame(
            top_frame, text="ตั้งค่าฐานข้อมูลอำเภอ (MySQL)", padding=5
        )
        district_frame.pack(fill=tk.X, pady=5)
        district_fields_frame = ttk.Frame(district_frame)
        district_fields_frame.pack(fill=tk.X)
        for column in range(2):
            district_fields_frame.columnconfigure(column, weight=1)

        district_db = self.config.get("district_db", {})
        self.entry_district_host = self._add_database_setting(
            district_fields_frame, "Host:", district_db.get("host", ""), 18,
            row=0, column=0
        )
        self.entry_district_port = self._add_database_setting(
            district_fields_frame, "Port:", district_db.get("port", ""), 7,
            row=0, column=1
        )
        self.entry_district_db = self._add_database_setting(
            district_fields_frame, "Database:", district_db.get("database", ""), 15,
            row=1, column=0
        )
        self.entry_district_user = self._add_database_setting(
            district_fields_frame, "User:", district_db.get("user", ""), 12,
            row=1, column=1
        )
        self.entry_district_pass = self._add_database_setting(
            district_fields_frame, "Password:", district_db.get("password", ""), 12,
            show="*", row=2, column=0
        )
        district_actions = ttk.Frame(district_fields_frame)
        district_actions.grid(row=2, column=1, sticky=tk.SE, padx=Spacing.XS, pady=Spacing.XS)
        self.btn_test_district_db = ttk.Button(
            district_actions, text="ทดสอบเชื่อมต่อ",
            command=self._test_district_database
        )
        self.btn_test_district_db.pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(
            district_actions, text="บันทึกตั้งค่า",
            command=self._save_district_db_settings
        ).pack(side=tk.LEFT, padx=(3, 0))
        self.district_db_status_var = tk.StringVar(value="")
        ttk.Label(
            district_frame, textvariable=self.district_db_status_var, anchor=tk.W
        ).pack(fill=tk.X, padx=6, pady=(3, 0))

        hostatom_frame = ttk.LabelFrame(
            top_frame, text="ตั้งค่าฐานข้อมูล Cloud DB (HostAtom)", padding=5
        )
        hostatom_frame.pack(fill=tk.X, pady=5)
        hostatom_fields_frame = ttk.Frame(hostatom_frame)
        hostatom_fields_frame.pack(fill=tk.X)
        for column in range(2):
            hostatom_fields_frame.columnconfigure(column, weight=1)

        hostatom_db = self.config.get("hostatom_db", {})
        self.entry_hostatom_host = self._add_database_setting(
            hostatom_fields_frame, "Host:", hostatom_db.get("host", ""), 18,
            row=0, column=0
        )
        self.entry_hostatom_port = self._add_database_setting(
            hostatom_fields_frame, "Port:", hostatom_db.get("port", 3306), 7,
            row=0, column=1
        )
        self.entry_hostatom_db = self._add_database_setting(
            hostatom_fields_frame, "Database:", hostatom_db.get("database", ""), 15,
            row=1, column=0
        )
        self.entry_hostatom_user = self._add_database_setting(
            hostatom_fields_frame, "User:", hostatom_db.get("user", ""), 12,
            row=1, column=1
        )
        self.entry_hostatom_pass = self._add_database_setting(
            hostatom_fields_frame, "Password:", hostatom_db.get("password", ""), 12,
            show="*", row=2, column=0
        )
        self.entry_hostatom_batch_size = self._add_database_setting(
            hostatom_fields_frame, "Batch Size:", hostatom_db.get("batch_size", 500), 6,
            row=2, column=1
        )
        hostatom_actions = ttk.Frame(hostatom_fields_frame)
        hostatom_actions.grid(row=3, column=0, columnspan=2, sticky=tk.E, padx=Spacing.XS)
        self.btn_test_hostatom_db = ttk.Button(
            hostatom_actions, text="ทดสอบเชื่อมต่อ",
            command=self._test_hostatom_database
        )
        self.btn_test_hostatom_db.pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(
            hostatom_actions, text="บันทึกตั้งค่า",
            command=self._save_hostatom_db_settings
        ).pack(side=tk.LEFT, padx=(3, 0))
        self.hostatom_db_status_var = tk.StringVar(value="")
        ttk.Label(
            hostatom_frame, textvariable=self.hostatom_db_status_var, anchor=tk.W
        ).pack(fill=tk.X, padx=6, pady=(3, 0))

        # === แถบควบคุมการทำงาน ===
        ctrl_frame = create_card_section(control_tab, title=f"{Icons.PIPELINE} ควบคุมการทำงาน", padding=Spacing.MD)
        ctrl_frame.pack(fill=tk.X, padx=Spacing.MD, pady=Spacing.MD)

        btn_row2 = ttk.Frame(ctrl_frame)
        btn_row2.pack(fill=tk.X, pady=Spacing.XS)

        self.btn_check_vpn = create_secondary_button(btn_row2, text=f"{Icons.VPN} ตรวจสอบ VPN",
                                                     command=self._check_all_vpn)
        self.btn_check_vpn.pack(side=tk.LEFT, padx=Spacing.SM)

        self.btn_sync_manual = create_primary_button(btn_row2, text=f"{Icons.SYNC} ซิงค์ Person → Cloud DB",
                                                     command=self._manual_sync)
        self.btn_sync_manual.pack(side=tk.LEFT, padx=Spacing.SM)

        create_ghost_button(btn_row2, text=f"{Icons.SCHEDULE} ตั้งค่า Auto-Schedule",
                           command=self._open_auto_schedule).pack(side=tk.LEFT, padx=Spacing.SM)

        flow_buttons_frame = ttk.Frame(ctrl_frame)
        flow_buttons_frame.pack(fill=tk.X, pady=(Spacing.SM, Spacing.XS))
        self.btn_jhcis_to_district = create_secondary_button(
            flow_buttons_frame,
            text=f"{Icons.DOWNLOAD} JHCIS (ลูกข่าย) → ฐานอำเภอ",
            command=self._start_jhcis_to_district
        )
        self.btn_jhcis_to_district.pack(side=tk.LEFT, padx=Spacing.SM)
        self.btn_district_to_cloud = create_primary_button(
            flow_buttons_frame,
            text=f"{Icons.UPLOAD} ฐานอำเภอ → Cloud DB",
            command=self._start_district_to_cloud
        )
        self.btn_district_to_cloud.pack(side=tk.LEFT, padx=Spacing.SM)

        # สถานะ Auto-Schedule
        self.lbl_auto_status = create_muted_label(ctrl_frame, text="สถานะ Auto: ยังไม่เปิดใช้งาน")
        self.lbl_auto_status.pack(anchor=tk.W, pady=Spacing.XS)
        self.chk_start_with_windows = ttk.Checkbutton(
            ctrl_frame,
            text="เปิดโปรแกรมพร้อม Windows (ผู้ใช้ปัจจุบัน)",
            variable=self.start_with_windows_var,
            command=self._toggle_windows_startup
        )
        self.chk_start_with_windows.pack(anchor=tk.W, pady=Spacing.XS)
        if winreg is None:
            self.chk_start_with_windows.state(["disabled"])

        flow_frame = create_card_section(hospitals_tab, title=f"{Icons.CHART} สถานะการไหลข้อมูล", padding=Spacing.MD)
        flow_frame.pack(fill=tk.X, padx=Spacing.MD, pady=(0, Spacing.MD))
        flow_frame.columnconfigure(0, weight=1)
        flow_frame.columnconfigure(1, weight=1)
        self.data_flow_status_vars = {
            "jhcis_to_district": tk.StringVar(value="ยังไม่มีการดึงข้อมูล"),
            "district_to_cloud": tk.StringVar(value="ยังไม่มีการส่งข้อมูล"),
        }
        self.data_flow_progress_bars = {}
        for column, stage, title in (
            (0, "jhcis_to_district", f"{Icons.DOWNLOAD} JHCIS ลูกข่าย → ฐานอำเภอ"),
            (1, "district_to_cloud", f"{Icons.UPLOAD} ฐานอำเภอ → Cloud DB"),
        ):
            stage_frame = create_card_section(flow_frame, title=title, padding=Spacing.SM)
            stage_frame.grid(
                row=0, column=column, sticky=tk.EW, padx=Spacing.SM, pady=Spacing.XS
            )
            create_muted_label(stage_frame,
                textvariable=self.data_flow_status_vars[stage]
            ).pack(fill=tk.X)
            progress_bar = create_progressbar(stage_frame, mode="indeterminate", maximum=100)
            progress_bar.pack(fill=tk.X, pady=(Spacing.XXS, 0))
            self.data_flow_progress_bars[stage] = progress_bar

        # === ตารางแสดงผล ===
        tree_frame = create_card_section(hospitals_tab, title=f"{Icons.LIST} รายชื่อ รพ.สต. และสถานะการซิงค์", padding=Spacing.MD)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=Spacing.MD, pady=Spacing.MD)

        columns = ("select", "code", "name", "ip", "vpn", "sync")
        self.tree = create_treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("select", text=f"{Icons.CHECK} เลือก", command=lambda: self._toggle_all_selection())
        self.tree.heading("code", text=f"{Icons.HOSPITAL} รหัส")
        self.tree.heading("name", text=f"{Icons.PATIENT} ชื่อสถานพยาบาล")
        self.tree.heading("ip", text=f"{Icons.VPN} Radmin IP")
        self.tree.heading("vpn", text=f"{Icons.NETWORK} สถานะ VPN")
        self.tree.heading("sync", text=f"{Icons.SYNC} ผลการซิงค์ล่าสุด")

        self.tree.column("select", width=60, anchor="center")
        self.tree.column("code", width=70, anchor="center")
        self.tree.column("name", width=250, anchor="w")
        self.tree.column("ip", width=140, anchor="center")
        self.tree.column("vpn", width=140, anchor="center")
        self.tree.column("sync", width=200, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._on_tree_scroll)
        self.vsb = vsb
        self.tree.configure(yscrollcommand=self._on_tree_yscroll)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind("<Button-1>", self._on_tree_click)
        self._setup_sql_mapping_tab(mapping_tab)
        self.content_notebook.bind(
            "<<NotebookTabChanged>>", self._on_main_notebook_tab_changed, add="+"
        )

        # แถบสถานะด้านล่าง
        self.status_var = tk.StringVar(value="พร้อมทำงาน")
        self.toast_var = tk.StringVar(value="")
        status_bar = ttk.Frame(self.root, style="Statusbar.TFrame")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=Spacing.SM, pady=(0, Spacing.SM))
        ttk.Label(
            status_bar, textvariable=self.status_var,
            style="Statusbar.TLabel", anchor=tk.W, padding=Spacing.SM
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        toast_label = ttk.Label(
            status_bar, textvariable=self.toast_var, style="Toast.TLabel",
            anchor=tk.E, padding=(Spacing.SM, Spacing.XXS)
        )
        toast_label.pack(side=tk.RIGHT, padx=Spacing.XS)
        self.toast_manager = ToastManager(self.root, self.toast_var, toast_label)
        self._bind_settings_scroll(settings_view)

    def _bind_settings_scroll(self, widget):
        widget.bind("<MouseWheel>", self._on_settings_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_settings_scroll(child)

    def _on_settings_mousewheel(self, event):
        if self.content_notebook.select() != str(self.settings_tab):
            return
        units = int(-event.delta / 120)
        if units == 0:
            units = -1 if event.delta > 0 else 1
        self.settings_canvas.yview_scroll(units, "units")
        return "break"

    def _setup_developer_tab(self, tab):
        frame = create_card_section(tab, title=f"{Icons.INFO} ข้อมูลผู้พัฒนา", padding=Spacing.XXL)
        frame.pack(expand=True, padx=Spacing.XXXL, pady=Spacing.XXXL)
        create_muted_label(frame, "พัฒนาโดย").pack(pady=(0, Spacing.SM))
        create_title_label(frame, "นายสหรัต เดเระมะ").pack(pady=Spacing.XS)
        create_muted_label(frame, "ตำแหน่งนักวิชาการคอมพิวเตอร์ชำนาญการ").pack(pady=Spacing.XS)
        create_muted_label(frame, "สสอ.เทพา").pack(pady=(Spacing.XS, Spacing.MD))

    def _add_database_setting(
        self, parent, label, value, width, show="", row=0, column=0
    ):
        field = ttk.Frame(parent)
        field.grid(
            row=row, column=column, sticky=tk.EW,
            padx=Spacing.XS, pady=Spacing.XS
        )
        create_muted_label(field, text=label).pack(
            anchor=tk.W, pady=(0, Spacing.XXS)
        )
        entry = ttk.Entry(field, width=width, show=show)
        entry.insert(0, str(value))
        entry.pack(fill=tk.X, expand=True, ipady=Spacing.XXS)
        return entry

    def _refresh_database_settings_fields(self):
        fields = (
            ("entry_district_host", "district_db", "host", ""),
            ("entry_district_port", "district_db", "port", ""),
            ("entry_district_db", "district_db", "database", ""),
            ("entry_district_user", "district_db", "user", ""),
            ("entry_district_pass", "district_db", "password", ""),
            ("entry_hostatom_host", "hostatom_db", "host", ""),
            ("entry_hostatom_port", "hostatom_db", "port", 3306),
            ("entry_hostatom_db", "hostatom_db", "database", ""),
            ("entry_hostatom_user", "hostatom_db", "user", ""),
            ("entry_hostatom_pass", "hostatom_db", "password", ""),
            ("entry_hostatom_batch_size", "hostatom_db", "batch_size", 500),
        )
        for attribute, section, key, default in fields:
            entry = getattr(self, attribute)
            entry.delete(0, tk.END)
            entry.insert(0, str(self.config.get(section, {}).get(key, default)))

    def _setup_sql_mapping_tab(self, tab):
        self.mapping_tab = tab
        self.sql_mapping_rows = []
        self.sql_mapping_loaded = False
        self.sql_mapping_loading = False
        self.sql_mapping_request_id = 0

        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=tk.X, padx=Spacing.MD, pady=(Spacing.MD, Spacing.SM))
        create_muted_label(
            toolbar,
            text="รายการ Mapping จากตาราง sql_mapping ในฐานข้อมูลอำเภอ"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.sql_mapping_status_var = tk.StringVar(value="ยังไม่ได้โหลดรายการ Mapping")
        create_muted_label(toolbar, textvariable=self.sql_mapping_status_var).pack(
            side=tk.LEFT, padx=Spacing.MD
        )
        self.btn_refresh_sql_mappings = create_small_button(
            toolbar, text=f"{Icons.REFRESH} รีเฟรช", variant="Primary",
            command=self._refresh_sql_mappings
        )
        self.btn_refresh_sql_mappings.pack(side=tk.RIGHT, padx=Spacing.SM)
        self.btn_add_sql_mapping = create_small_button(
            toolbar, text=f"{Icons.ADD} เพิ่ม Mapping", variant="Secondary",
            command=self._add_sql_mapping
        )
        self.btn_add_sql_mapping.pack(side=tk.RIGHT, padx=Spacing.SM)
        self.btn_edit_sql_mapping = create_small_button(
            toolbar, text=f"{Icons.EDIT} แก้ไข Mapping", variant="Ghost",
            command=self._edit_sql_mapping
        )
        self.btn_edit_sql_mapping.pack(side=tk.RIGHT, padx=Spacing.SM)
        self.btn_edit_sql_mapping.configure(state=tk.DISABLED)

        table_frame = create_card_section(tab, title=f"{Icons.TABLE} ข้อมูล Mapping", padding=Spacing.MD)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=Spacing.MD, pady=(0, Spacing.MD))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        columns = (
            "task_code", "task_name", "source", "staging",
            "procedure", "active", "sort_order", "updated_at"
        )
        self.sql_mapping_tree = create_treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        for column, title, width in (
            ("task_code", "รหัสงาน", 100),
            ("task_name", "ชื่อข้อมูล", 180),
            ("source", "ตารางต้นทางอำเภอ", 150),
            ("staging", "ตารางพัก Cloud DB", 150),
            ("procedure", "Stored Procedure", 170),
            ("active", "สถานะ", 85),
            ("sort_order", "ลำดับ", 65),
            ("updated_at", "แก้ไขล่าสุด", 145),
        ):
            self.sql_mapping_tree.heading(column, text=title)
            self.sql_mapping_tree.column(
                column, width=width, minwidth=60,
                anchor=tk.CENTER if column in ("sort_order", "active") else tk.W
            )
        y_scroll = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.sql_mapping_tree.yview
        )
        x_scroll = ttk.Scrollbar(
            table_frame, orient=tk.HORIZONTAL, command=self.sql_mapping_tree.xview
        )
        self.sql_mapping_tree.configure(
            yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set
        )
        self.sql_mapping_tree.grid(row=0, column=0, sticky=tk.NSEW)
        y_scroll.grid(row=0, column=1, sticky=tk.NS)
        x_scroll.grid(row=1, column=0, sticky=tk.EW)
        self.sql_mapping_tree.bind(
            "<<TreeviewSelect>>", self._on_sql_mapping_selection
        )
        self.sql_mapping_tree.bind("<Double-1>", self._on_sql_mapping_double_click)

    def _refresh_sql_mappings(self):
        if self.sql_mapping_loading:
            return
        district_config = dict(self.config.get("district_db", {}))
        self.sql_mapping_request_id += 1
        request_id = self.sql_mapping_request_id
        self.sql_mapping_loading = True
        self.btn_refresh_sql_mappings.configure(state=tk.DISABLED)
        self.sql_mapping_status_var.set("กำลังโหลด sql_mapping...")

        def _load():
            try:
                rows = get_sql_mappings(district_config)
                error = None
            except Exception as caught_error:
                rows = None
                error = caught_error
            try:
                self.root.after(
                    0, self._finish_sql_mapping_refresh, request_id, rows, error
                )
            except tk.TclError:
                pass

        threading.Thread(target=_load, daemon=True).start()

    def _finish_sql_mapping_refresh(self, request_id, rows, error, focus_id=None):
        if request_id != self.sql_mapping_request_id:
            return
        self.sql_mapping_loading = False
        self.btn_refresh_sql_mappings.configure(state=tk.NORMAL)
        if error is not None:
            self.sql_mapping_loaded = False
            self.sql_mapping_status_var.set(f"โหลด Mapping ไม่สำเร็จ: {error}")
            log_error(f"โหลด sql_mapping ไม่สำเร็จ: {error}")
            return
        self._render_sql_mappings(rows, focus_id)

    def _render_sql_mappings(self, rows, focus_id=None):
        self.sql_mapping_rows = list(rows)
        self.sql_mapping_loaded = True
        for item in self.sql_mapping_tree.get_children():
            self.sql_mapping_tree.delete(item)
        selected_item = None
        for row in self.sql_mapping_rows:
            mapping_id = str(row["id"])
            self.sql_mapping_tree.insert(
                "",
                tk.END,
                iid=mapping_id,
                values=(
                    row.get("task_code", ""),
                    row.get("task_name", ""),
                    row.get("local_source_table", ""),
                    row.get("host_staging_table", ""),
                    row.get("host_procedure_name", ""),
                    "ใช้งาน" if bool(row.get("is_active")) else "ปิดใช้งาน",
                    row.get("sort_order", 0),
                    row.get("updated_at", ""),
                ),
                tags=("inactive",) if not bool(row.get("is_active")) else (),
            )
            if focus_id is not None and mapping_id == str(focus_id):
                selected_item = mapping_id
        self.sql_mapping_tree.tag_configure("inactive", foreground="#888888")
        if selected_item is not None:
            self.sql_mapping_tree.selection_set(selected_item)
            self.sql_mapping_tree.focus(selected_item)
            self.sql_mapping_tree.see(selected_item)
        else:
            self._on_sql_mapping_selection()
        self.sql_mapping_status_var.set(f"โหลด Mapping แล้ว {len(rows)} รายการ")

    def _on_sql_mapping_selection(self, event=None):
        state = (
            tk.NORMAL if self.sql_mapping_tree.selection() else tk.DISABLED
        )
        self.btn_edit_sql_mapping.configure(state=state)

    def _on_sql_mapping_double_click(self, event):
        if self.sql_mapping_tree.identify_region(event.x, event.y) == "cell":
            self._edit_sql_mapping()

    def _add_sql_mapping(self):
        self._open_sql_mapping_editor()

    def _edit_sql_mapping(self):
        selection = self.sql_mapping_tree.selection()
        if not selection:
            messagebox.showwarning(
                "เลือก Mapping", "กรุณาเลือกรายการ Mapping ที่ต้องการแก้ไข",
                parent=self.root
            )
            return
        mapping_id = int(selection[0])
        mapping = next(
            (
                row for row in self.sql_mapping_rows
                if int(row.get("id", -1)) == mapping_id
            ),
            None,
        )
        if mapping is None:
            messagebox.showerror(
                "ไม่พบ Mapping", "โหลดรายการใหม่ก่อนแก้ไข Mapping นี้",
                parent=self.root
            )
            return
        self._open_sql_mapping_editor(mapping)

    def _open_sql_mapping_editor(self, mapping=None):
        original = dict(mapping or {})
        win = ctk.CTkToplevel(self.root)
        win.title("เพิ่ม Mapping" if mapping is None else "แก้ไข Mapping")
        win.geometry("900x650")
        win.minsize(760, 560)
        win.transient(self.root)
        win.grab_set()

        form = create_section(win, padding=Spacing.MD)
        form.pack(fill=tk.BOTH, expand=True)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        entry_defs = (
            ("task_code", f"{Icons.MAPPING} รหัสงาน", 0, 0, ""),
            ("task_name", f"{Icons.LIST} ชื่อข้อมูล", 0, 2, ""),
            ("local_source_table", f"{Icons.DATABASE} ตารางต้นทางอำเภอ", 1, 0, "org_person"),
            ("host_staging_table", f"{Icons.CLOUD} ตารางพัก Cloud DB", 1, 2, "store_person"),
            ("host_procedure_name", f"{Icons.CONFIG} Stored Procedure", 2, 0, "sp_merge_person"),
            ("sort_order", f"{Icons.INFO} ลำดับ", 2, 2, "0"),
        )
        entries = {}
        for key, label, row, column, default in entry_defs:
            create_muted_label(form, text=label).grid(
                row=row, column=column, sticky=tk.W, padx=Spacing.SM, pady=Spacing.SM
            )
            entry = ttk.Entry(form)
            value = original.get(key, default)
            entry.insert(0, "" if value is None else str(value))
            entry.grid(
                row=row, column=column + 1, sticky=tk.EW,
                padx=Spacing.SM, pady=Spacing.SM, ipady=Spacing.XXS
            )
            entries[key] = entry

        active_var = tk.BooleanVar(
            value=bool(original.get("is_active", True))
        )
        ttk.Checkbutton(form, text=f"{Icons.CHECK} เปิดใช้งาน Mapping", variable=active_var).grid(
            row=2, column=4, sticky=tk.W, padx=Spacing.SM, pady=Spacing.SM
        )
        create_muted_label(
            form,
            text="SQL SELECT จาก JHCIS (jhcis_extract_sql; ตั้งชื่อคอลัมน์ให้ตรงกับ district_table)"
        ).grid(row=3, column=0, columnspan=5, sticky=tk.W, padx=Spacing.SM, pady=(Spacing.MD, Spacing.XS))
        sql_frame = ttk.Frame(form)
        sql_frame.grid(row=4, column=0, columnspan=5, sticky=tk.NSEW, padx=Spacing.SM)
        form.rowconfigure(4, weight=1)
        sql_frame.rowconfigure(0, weight=1)
        sql_frame.columnconfigure(0, weight=1)
        sql_text = ttk.Text(sql_frame, wrap=tk.NONE, font=FONTS["MONO"])
        sql_y_scroll = ttk.Scrollbar(
            sql_frame, orient=tk.VERTICAL, command=sql_text.yview
        )
        sql_x_scroll = ttk.Scrollbar(
            sql_frame, orient=tk.HORIZONTAL, command=sql_text.xview
        )
        sql_text.configure(
            yscrollcommand=sql_y_scroll.set, xscrollcommand=sql_x_scroll.set
        )
        sql_text.insert("1.0", original.get("jhcis_extract_sql") or "")
        sql_text.edit_modified(False)
        sql_text.grid(row=0, column=0, sticky=tk.NSEW)
        sql_y_scroll.grid(row=0, column=1, sticky=tk.NS)
        sql_x_scroll.grid(row=1, column=0, sticky=tk.EW)

        status_var = tk.StringVar(value="")
        tested_sql = {"value": None}
        create_muted_label(form, textvariable=status_var, anchor=tk.W).grid(
            row=5, column=0, columnspan=5, sticky=tk.EW, padx=Spacing.SM, pady=Spacing.SM
        )
        buttons = ttk.Frame(form)
        buttons.grid(row=6, column=0, columnspan=5, sticky=tk.EW, pady=(Spacing.MD, 0))

        def clear_test_status(event):
            event.widget.edit_modified(False)
            if (
                tested_sql["value"] is not None
                and sql_text.get("1.0", "end-1c") != tested_sql["value"]
            ):
                tested_sql["value"] = None
                status_var.set("")

        sql_text.bind("<<Modified>>", clear_test_status)

        def copy_mapping_sql():
            sql = sql_text.get("1.0", "end-1c")
            if not sql.strip():
                status_var.set("ไม่มีคำสั่ง SQL ให้คัดลอก")
                messagebox.showwarning(
                    "SQL ว่าง", "กรุณากรอกคำสั่ง SQL ก่อนคัดลอก", parent=win
                )
                return
            try:
                win.clipboard_clear()
                win.clipboard_append(sql)
            except tk.TclError as error:
                status_var.set(f"คัดลอก SQL ไม่สำเร็จ: {error}")
                log_error(f"คัดลอก SQL Mapping ไม่สำเร็จ: {error}")
                messagebox.showerror(
                    "คัดลอกไม่สำเร็จ", str(error), parent=win
                )
                return
            status_var.set("คัดลอก SQL Mapping ไปยังคลิปบอร์ดแล้ว")

        def finish_mapping_test(hospital, query, error):
            if not win.winfo_exists():
                return
            test_button.configure(state=tk.NORMAL)
            sql_text.configure(state=tk.NORMAL)
            tested_sql["value"] = query
            if error is not None:
                status_var.set("Status: ERROR - SQL รันไม่ผ่านบน JHCIS")
                log_error(
                    f"ทดสอบ SQL Mapping {original.get('task_code', '')} "
                    f"บน JHCIS ({hospital.get('code', '')}) ไม่สำเร็จ: {error}"
                )
                return
            status_var.set(
                f"Status: OK - รันผ่านบน JHCIS "
                f"({hospital.get('name', hospital.get('code', ''))})"
            )

        def test_mapping_sql():
            query = sql_text.get("1.0", "end-1c")
            if not query.strip():
                tested_sql["value"] = query
                status_var.set("Status: ERROR - ไม่มีคำสั่ง SQL")
                return
            try:
                validate_read_only_select(query)
            except ValueError as error:
                tested_sql["value"] = query
                status_var.set("Status: ERROR - SQL ไม่ถูกต้อง")
                log_error(
                    f"ทดสอบ SQL Mapping {original.get('task_code', '')} "
                    f"ไม่ผ่านการตรวจสอบ: {error}"
                )
                return

            hospital = self.mapping_hospital or self._get_mapping_hospital()
            if hospital is None:
                tested_sql["value"] = query
                status_var.set("Status: ERROR - ไม่มี รพ.สต. สำหรับทดสอบ")
                return
            hospital = dict(hospital)
            jhcis_default = dict(self.config.get("jhcis_default", {}))
            test_button.configure(state=tk.DISABLED)
            sql_text.configure(state=tk.DISABLED)
            status_var.set("กำลังทดสอบ SQL บน JHCIS...")

            def _test():
                try:
                    preview_person_sql(
                        hospital, jhcis_default, query, max_rows=1
                    )
                    error = None
                except Exception as caught_error:
                    error = caught_error
                try:
                    self.root.after(
                        0, finish_mapping_test, hospital, query, error
                    )
                except tk.TclError:
                    pass

            try:
                threading.Thread(target=_test, daemon=True).start()
            except RuntimeError as error:
                test_button.configure(state=tk.NORMAL)
                sql_text.configure(state=tk.NORMAL)
                tested_sql["value"] = query
                status_var.set("Status: ERROR - เริ่มการทดสอบไม่สำเร็จ")
                log_error(f"เริ่มทดสอบ SQL Mapping ไม่สำเร็จ: {error}")

        test_button = create_secondary_button(
            buttons, text=f"{Icons.PLAY} ทดสอบ Mapping", command=test_mapping_sql
        )
        test_button.pack(side=tk.LEFT, padx=Spacing.SM)
        create_ghost_button(
            buttons, text=f"{Icons.COPY} Copy Mapping", command=copy_mapping_sql
        ).pack(side=tk.LEFT, padx=Spacing.SM)
        save_button = create_primary_button(
            buttons, text=f"{Icons.SAVE} บันทึก Mapping"
        )
        save_button.pack(side=tk.LEFT, padx=Spacing.SM)
        create_ghost_button(
            buttons, text=f"{Icons.CLOSE} ยกเลิก", command=win.destroy
        ).pack(side=tk.RIGHT, padx=Spacing.SM)

        def save_mapping():
            try:
                task_code = entries["task_code"].get().strip().upper()
                task_name = entries["task_name"].get().strip()
                sort_order = int(entries["sort_order"].get().strip() or 0)
                if not task_code or not task_name:
                    raise ValueError("กรุณากรอกรหัสงานและชื่อข้อมูล")
                for row in self.sql_mapping_rows:
                    if (
                        str(row.get("task_code", "")).strip().upper() == task_code
                        and int(row.get("id", -1)) != int(original.get("id", -1))
                    ):
                        raise ValueError(f"รหัสงาน {task_code} มีอยู่แล้ว")
            except ValueError as error:
                messagebox.showerror("ข้อมูลไม่ถูกต้อง", str(error), parent=win)
                return

            updated_mapping = {
                "id": original.get("id"),
                "task_code": task_code,
                "task_name": task_name,
                "jhcis_extract_sql": sql_text.get("1.0", "end-1c").strip() or None,
                "local_source_table": entries["local_source_table"].get().strip(),
                "host_staging_table": entries["host_staging_table"].get().strip(),
                "host_procedure_name": entries["host_procedure_name"].get().strip(),
                "is_active": active_var.get(),
                "sort_order": sort_order,
            }
            district_config = dict(self.config.get("district_db", {}))
            save_button.configure(state=tk.DISABLED)
            status_var.set("กำลังบันทึก Mapping...")

            def _save():
                try:
                    save_sql_mapping(district_config, updated_mapping)
                    saved = True
                except Exception as caught_error:
                    rows = None
                    error = caught_error
                    saved = False
                    log_error(f"บันทึก SQL Mapping {task_code} ไม่สำเร็จ: {error}")
                if saved:
                    try:
                        rows = get_sql_mappings(district_config)
                        error = None
                    except Exception as caught_error:
                        rows = None
                        error = caught_error
                        log_error(
                            f"บันทึก SQL Mapping {task_code} แล้ว "
                            f"แต่โหลดรายการกลับมาไม่สำเร็จ: {error}"
                        )
                try:
                    self.root.after(
                        0, self._finish_sql_mapping_save, win, save_button,
                        status_var, saved, rows, error, task_code
                    )
                except tk.TclError:
                    pass

            threading.Thread(target=_save, daemon=True).start()

        save_button.configure(command=save_mapping)
        win.bind("<Control-s>", lambda event: save_mapping())

    def _finish_sql_mapping_save(
        self, win, save_button, status_var, saved, rows, error, task_code
    ):
        if not win.winfo_exists():
            return
        save_button.configure(state=tk.NORMAL)
        if not saved:
            status_var.set(f"บันทึกไม่สำเร็จ: {error}")
            messagebox.showerror(
                "บันทึก Mapping ไม่สำเร็จ", str(error), parent=win
            )
            return
        if error is not None:
            self.sql_mapping_loaded = False
            status_var.set(f"บันทึกแล้ว แต่โหลดรายการกลับมาไม่สำเร็จ: {error}")
            win.destroy()
            messagebox.showwarning(
                "บันทึกแล้ว", f"บันทึก Mapping แล้ว แต่โหลดรายการกลับมาไม่สำเร็จ:\n{error}",
                parent=self.root
            )
            return
        saved_row = next(
            (
                row for row in rows
                if str(row.get("task_code", "")).strip().upper() == task_code
            ),
            None,
        )
        if saved_row is None:
            self.sql_mapping_loaded = False
            status_var.set("บันทึกแล้ว แต่ไม่พบ Mapping ในรายการที่โหลดกลับมา")
            win.destroy()
            messagebox.showwarning(
                "ตรวจสอบรายการ", "บันทึกแล้ว แต่ไม่พบ Mapping ในรายการที่โหลดกลับมา",
                parent=self.root
            )
            return
        self._render_sql_mappings(rows, saved_row.get("id") if saved_row else None)
        win.destroy()
        self.toast_manager.show(f"บันทึก Mapping {task_code} แล้ว", "success")

    def _setup_mapping_tab(self, tab):
        self.mapping_tab = tab
        self.mapping_hospital = None
        self.mapping_tables_loaded = False
        self.mapping_table_request_id = 0
        self.mapping_column_request_id = 0

        ttk.Label(
            tab,
            text="เลือกตารางและคอลัมน์จาก JHCIS แล้วแก้ไข SQL ในช่องที่ 3 เพื่อทดสอบผลลัพธ์"
        ).pack(anchor=tk.W, padx=8, pady=(8, 2))
        ttk.Label(
            tab,
            text="Run แบบอ่านอย่างเดียว แสดงผลไม่เกิน 100 แถว ใช้ รพ.สต. ที่เลือกไว้ลำดับแรก "
            "(ถ้าไม่ได้เลือกจะใช้รายการแรก)"
        ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        content = ttk.Frame(tab)
        self.mapping_content = content
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        table_frame = ttk.LabelFrame(content, text="1. ตารางทั้งหมดใน JHCIS", padding=6)
        columns_frame = ttk.LabelFrame(content, text="2. คอลัมน์ของตารางที่เลือก", padding=6)
        sql_frame = ttk.LabelFrame(content, text="3. SQL สำหรับดึงข้อมูล", padding=6)
        results_frame = ttk.LabelFrame(content, text="4. ผลลัพธ์เมื่อ Run SQL", padding=6)
        content.rowconfigure(0, weight=1)
        for column_index, pane in enumerate(
            (table_frame, columns_frame, sql_frame, results_frame)
        ):
            content.columnconfigure(
                column_index, weight=1, uniform="mapping_panes"
            )
            pane.grid(row=0, column=column_index, sticky=tk.NSEW, padx=2)

        table_frame.rowconfigure(1, weight=1)
        table_frame.columnconfigure(0, weight=1)
        table_toolbar = ttk.Frame(table_frame)
        table_toolbar.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))
        self.jhcis_table_status = create_muted_label(table_toolbar, text="ยังไม่ได้โหลดตาราง")
        self.jhcis_table_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_refresh_jhcis_tables = create_small_button(
            table_toolbar, text=f"{Icons.REFRESH} รีเฟรช", variant="Primary",
            command=self._refresh_jhcis_tables
        )
        self.btn_refresh_jhcis_tables.pack(side=tk.RIGHT)
        self.jhcis_tables = create_treeview(
            table_frame, columns=("table_name",), show="headings", selectmode="browse"
        )
        self.jhcis_tables.heading("table_name", text=f"{Icons.TABLE} ชื่อตาราง")
        self.jhcis_tables.column("table_name", width=200, anchor=tk.W)
        table_scroll = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.jhcis_tables.yview
        )
        table_x_scroll = ttk.Scrollbar(
            table_frame, orient=tk.HORIZONTAL, command=self.jhcis_tables.xview
        )
        self.jhcis_tables.configure(
            yscrollcommand=table_scroll.set, xscrollcommand=table_x_scroll.set
        )
        self.jhcis_tables.grid(row=1, column=0, sticky=tk.NSEW)
        table_scroll.grid(row=1, column=1, sticky=tk.NS)
        table_x_scroll.grid(row=2, column=0, sticky=tk.EW)
        self.jhcis_tables.bind("<<TreeviewSelect>>", self._on_jhcis_table_selected)

        columns_frame.rowconfigure(1, weight=1)
        columns_frame.columnconfigure(0, weight=1)
        self.jhcis_columns_status = create_muted_label(columns_frame, text="เลือกตารางเพื่อดูคอลัมน์")
        self.jhcis_columns_status.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))
        self.jhcis_table_columns = create_treeview(
            columns_frame, columns=("column_name", "data_type"),
            show="headings", selectmode="browse"
        )
        self.jhcis_table_columns.heading("column_name", text=f"{Icons.COLUMN} คอลัมน์")
        self.jhcis_table_columns.heading("data_type", text=f"{Icons.INFO} ชนิดข้อมูล")
        self.jhcis_table_columns.column("column_name", width=140, anchor=tk.W)
        self.jhcis_table_columns.column("data_type", width=120, anchor=tk.W)
        columns_scroll = ttk.Scrollbar(
            columns_frame, orient=tk.VERTICAL, command=self.jhcis_table_columns.yview
        )
        columns_x_scroll = ttk.Scrollbar(
            columns_frame, orient=tk.HORIZONTAL, command=self.jhcis_table_columns.xview
        )
        self.jhcis_table_columns.configure(
            yscrollcommand=columns_scroll.set, xscrollcommand=columns_x_scroll.set
        )
        self.jhcis_table_columns.grid(row=1, column=0, sticky=tk.NSEW)
        columns_scroll.grid(row=1, column=1, sticky=tk.NS)
        columns_x_scroll.grid(row=2, column=0, sticky=tk.EW)

        sql_frame.rowconfigure(0, weight=1)
        sql_frame.columnconfigure(0, weight=1)
        self.person_mapping_sql = ttk.Text(
            sql_frame, wrap=tk.NONE, font=FONTS["MONO_CAPTION"]
        )
        sql_y_scroll = ttk.Scrollbar(sql_frame, orient=tk.VERTICAL, command=self.person_mapping_sql.yview)
        sql_x_scroll = ttk.Scrollbar(sql_frame, orient=tk.HORIZONTAL, command=self.person_mapping_sql.xview)
        self.person_mapping_sql.configure(
            yscrollcommand=sql_y_scroll.set,
            xscrollcommand=sql_x_scroll.set
        )
        self.person_mapping_sql.grid(row=0, column=0, sticky=tk.NSEW)
        sql_y_scroll.grid(row=0, column=1, sticky=tk.NS)
        sql_x_scroll.grid(row=1, column=0, sticky=tk.EW)

        saved_mapping = self.config.get("person_mapping", {})
        if not isinstance(saved_mapping, dict):
            saved_mapping = {}
        default_mapping = {
            field: str(saved_mapping.get(field, field))
            for field in PERSON_MAPPING_FIELDS
        }
        saved_sql = self.config.get("person_sql")
        if not isinstance(saved_sql, str) or not saved_sql.strip():
            saved_sql = self._generate_person_mapping_sql(default_mapping)
        self.person_mapping_sql.insert("1.0", saved_sql)
        self.person_mapping_sql.edit_modified(False)
        self.person_mapping_sql.bind("<<Modified>>", self._on_person_sql_modified)

        results_frame.rowconfigure(1, weight=1)
        results_frame.columnconfigure(0, weight=1)
        self.person_sql_results_status = ttk.Label(
            results_frame, text="ผลลัพธ์จะแสดงหลังจากกด Run SQL"
        )
        self.person_sql_results_status.grid(
            row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4)
        )
        self.person_sql_results = ttk.Treeview(
            results_frame, columns=(), show="headings"
        )
        results_y_scroll = ttk.Scrollbar(
            results_frame, orient=tk.VERTICAL, command=self.person_sql_results.yview
        )
        results_x_scroll = ttk.Scrollbar(
            results_frame, orient=tk.HORIZONTAL, command=self.person_sql_results.xview
        )
        self.person_sql_results.configure(
            yscrollcommand=results_y_scroll.set, xscrollcommand=results_x_scroll.set
        )
        self.person_sql_results.grid(row=1, column=0, sticky=tk.NSEW)
        results_y_scroll.grid(row=1, column=1, sticky=tk.NS)
        results_x_scroll.grid(row=2, column=0, sticky=tk.EW)

        actions = ttk.Frame(tab)
        actions.pack(fill=tk.X, padx=8, pady=(4, 8))
        self.person_mapping_status = ttk.Label(actions, anchor=tk.W)
        self.person_mapping_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_save_person_mapping = ttk.Button(actions, text="บันทึก Mapping", command=self._save_person_mapping)
        self.btn_save_person_mapping.pack(side=tk.RIGHT, padx=3)
        self.btn_run_person_sql = ttk.Button(
            actions, text="▶ Run SQL", command=self._run_person_mapping_sql
        )
        self.btn_run_person_sql.pack(side=tk.RIGHT, padx=3)
        self.btn_copy_person_mapping_sql = ttk.Button(
            actions, text="คัดลอก SQL", command=self._copy_person_mapping_sql
        )
        self.btn_copy_person_mapping_sql.pack(side=tk.RIGHT, padx=3)
        ttk.Button(
            actions, text="คืนค่า SQL เริ่มต้น", command=self._reset_person_mapping
        ).pack(side=tk.RIGHT, padx=3)
        self.person_mapping_status.config(text="เลือกตารางจากช่องที่ 1 เพื่อโหลดคอลัมน์")

    def _on_main_notebook_tab_changed(self, event=None):
        selected_tab = self.content_notebook.select()
        if selected_tab == str(self.mapping_tab):
            if not self.sql_mapping_loaded:
                self._refresh_sql_mappings()
        if selected_tab == str(self.settings_tab):
            self._refresh_database_settings_fields()
            self._check_database_connections_automatically()
            self._schedule_database_status_refresh()
        else:
            self._cancel_database_status_refresh()

    def _get_mapping_hospital(self):
        hospitals = self.config.get("hospitals", [])
        if not hospitals:
            return None
        selected_hospitals = [
            hospital for hospital in hospitals if hospital.get("selected", False)
        ]
        return (selected_hospitals or hospitals)[0]

    def _refresh_jhcis_tables(self):
        hospital = self._get_mapping_hospital()
        if hospital is None:
            self.mapping_tables_loaded = False
            self.mapping_hospital = None
            self.mapping_table_request_id += 1
            self.mapping_column_request_id += 1
            self.btn_refresh_jhcis_tables.configure(state=tk.NORMAL)
            for item in self.jhcis_tables.get_children():
                self.jhcis_tables.delete(item)
            for item in self.jhcis_table_columns.get_children():
                self.jhcis_table_columns.delete(item)
            self.jhcis_table_status.config(text="ยังไม่มีรายชื่อ รพ.สต.")
            self.jhcis_columns_status.config(text="ไม่พบ รพ.สต. สำหรับเชื่อมต่อ")
            return

        hospital = dict(hospital)
        self.mapping_hospital = dict(hospital)
        jhcis_default = dict(self.config.get("jhcis_default", {}))
        self.mapping_table_request_id += 1
        request_id = self.mapping_table_request_id
        self.mapping_column_request_id += 1
        self.mapping_tables_loaded = False
        self.btn_refresh_jhcis_tables.configure(state=tk.DISABLED)
        for item in self.jhcis_tables.get_children():
            self.jhcis_tables.delete(item)
        for item in self.jhcis_table_columns.get_children():
            self.jhcis_table_columns.delete(item)
        self.jhcis_columns_status.config(text="เลือกตารางเพื่อดูคอลัมน์")
        self.jhcis_table_status.config(
            text=f"กำลังโหลดจาก {hospital.get('name', hospital.get('ip', ''))}..."
        )

        def _load():
            try:
                tables = get_jhcis_tables(hospital, jhcis_default)
                error = None
            except Exception as caught_error:
                tables = None
                error = caught_error
            try:
                self.root.after(
                    0, self._finish_jhcis_tables, request_id, hospital, tables, error
                )
            except tk.TclError:
                pass

        threading.Thread(target=_load, daemon=True).start()

    def _finish_jhcis_tables(self, request_id, hospital, tables, error):
        if request_id != self.mapping_table_request_id:
            return
        self.btn_refresh_jhcis_tables.configure(state=tk.NORMAL)
        for item in self.jhcis_tables.get_children():
            self.jhcis_tables.delete(item)
        for item in self.jhcis_table_columns.get_children():
            self.jhcis_table_columns.delete(item)

        if error is not None:
            self.mapping_tables_loaded = False
            self.jhcis_table_status.config(text=f"โหลดตารางไม่สำเร็จ: {error}")
            self.jhcis_columns_status.config(text="ไม่สามารถโหลดคอลัมน์ได้")
            log_error(f"[Mapping] โหลดตาราง JHCIS ไม่สำเร็จ: {error}")
            return

        for table_name in tables:
            self.jhcis_tables.insert("", tk.END, values=(table_name,))
        self.mapping_tables_loaded = True
        self.mapping_hospital = dict(hospital)
        hospital_name = hospital.get("name", hospital.get("ip", ""))
        self.jhcis_table_status.config(
            text=f"{len(tables)} ตาราง | {hospital_name}"
        )
        self.jhcis_columns_status.config(text="เลือกตารางเพื่อดูคอลัมน์")

    def _on_jhcis_table_selected(self, event=None):
        selection = self.jhcis_tables.selection()
        if not selection:
            return
        table_name = self.jhcis_tables.item(selection[0], "values")[0]
        hospital = dict(self.mapping_hospital or self._get_mapping_hospital() or {})
        if not hospital:
            self.jhcis_columns_status.config(text="ไม่พบ รพ.สต. สำหรับเชื่อมต่อ")
            return

        jhcis_default = dict(self.config.get("jhcis_default", {}))
        self.mapping_column_request_id += 1
        request_id = self.mapping_column_request_id
        self.jhcis_columns_status.config(text=f"กำลังโหลดคอลัมน์ของ {table_name}...")
        for item in self.jhcis_table_columns.get_children():
            self.jhcis_table_columns.delete(item)

        def _load():
            try:
                columns = get_jhcis_table_columns(
                    hospital, jhcis_default, table_name
                )
                error = None
            except Exception as caught_error:
                columns = None
                error = caught_error
            try:
                self.root.after(
                    0, self._finish_jhcis_table_columns,
                    request_id, table_name, columns, error
                )
            except tk.TclError:
                pass

        threading.Thread(target=_load, daemon=True).start()

    def _finish_jhcis_table_columns(self, request_id, table_name, columns, error):
        if request_id != self.mapping_column_request_id:
            return
        selection = self.jhcis_tables.selection()
        if not selection or self.jhcis_tables.item(selection[0], "values")[0] != table_name:
            return
        if error is not None:
            self.jhcis_columns_status.config(text=f"โหลดคอลัมน์ไม่สำเร็จ: {error}")
            log_error(f"[Mapping] โหลดคอลัมน์ {table_name} ไม่สำเร็จ: {error}")
            return

        for column_name, data_type in columns:
            self.jhcis_table_columns.insert(
                "", tk.END, values=(column_name, data_type)
            )
        self.jhcis_columns_status.config(
            text=f"{len(columns)} คอลัมน์ใน {table_name}"
        )

    def _generate_person_mapping_sql(self, mapping):
        select_fields = []
        for field in PERSON_MAPPING_FIELDS:
            source = mapping.get(field, "").strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", source):
                raise ValueError(f"ชื่อคอลัมน์ต้นทางของ {field} ไม่ถูกต้อง")
            select_fields.append(f"    `{source}` AS `{field}`")

        return (
            "SELECT\n"
            + ",\n".join(select_fields)
            + "\nFROM `person`\n"
            + "ORDER BY `d_update`, `pcucodeperson`, `pid`;"
        )

    def _get_person_mapping_sql(self):
        return self.person_mapping_sql.get("1.0", "end-1c").strip()

    def _clear_person_sql_results(self, status="ผลลัพธ์จะแสดงหลังจากกด Run SQL"):
        for item in self.person_sql_results.get_children():
            self.person_sql_results.delete(item)
        self.person_sql_results.configure(columns=())
        self.person_sql_results_status.config(text=status)

    def _on_person_sql_modified(self, event=None):
        if not self.person_mapping_sql.edit_modified():
            return
        self.person_mapping_sql.edit_modified(False)
        self._clear_person_sql_results("SQL ถูกแก้ไข: กด Run SQL เพื่อดูผลลัพธ์ใหม่")
        self.person_mapping_status.config(
            text="SQL มีการแก้ไข: กด Run SQL เพื่อดูผลลัพธ์ใหม่"
        )

    def _reset_person_mapping(self):
        saved_mapping = self.config.get("person_mapping", {})
        if not isinstance(saved_mapping, dict):
            saved_mapping = {}
        mapping = {
            field: str(saved_mapping.get(field, field))
            for field in PERSON_MAPPING_FIELDS
        }
        sql = self._generate_person_mapping_sql(mapping)
        self.person_mapping_sql.delete("1.0", tk.END)
        self.person_mapping_sql.insert("1.0", sql)
        self.person_mapping_sql.edit_modified(False)
        self._clear_person_sql_results()
        self.person_mapping_status.config(text="คืนค่า SQL เริ่มต้นแล้ว")

    def _copy_person_mapping_sql(self):
        sql = self._get_person_mapping_sql()
        if not sql:
            messagebox.showwarning("SQL ว่าง", "กรุณากรอก SQL ก่อนคัดลอก", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(sql)
        self.person_mapping_status.config(text="คัดลอก SQL แล้ว")

    def _save_person_mapping(self):
        try:
            sql = self._get_person_mapping_sql()
            validate_read_only_select(sql)
        except ValueError as e:
            messagebox.showerror("SQL ไม่ถูกต้อง", str(e), parent=self.root)
            return

        had_previous_sql = "person_sql" in self.config
        previous_sql = self.config.get("person_sql")
        self.config["person_sql"] = sql
        if not save_config(self.config):
            if had_previous_sql:
                self.config["person_sql"] = previous_sql
            else:
                self.config.pop("person_sql", None)
            messagebox.showerror(
                "บันทึกไม่สำเร็จ", "ไม่สามารถบันทึก SQL Mapping ลง config.json ได้",
                parent=self.root
            )
            return
        messagebox.showinfo(
            "บันทึกสำเร็จ",
            "บันทึก SQL Mapping แล้ว\nSQL นี้ใช้สำหรับทดสอบในแท็บ Mapping เท่านั้น "
            "ยังไม่เปลี่ยนขั้นตอน Manual หรือ Auto-Sync",
            parent=self.root
        )

    def _run_person_mapping_sql(self):
        query = self._get_person_mapping_sql()
        try:
            validate_read_only_select(query)
        except ValueError as error:
            messagebox.showerror("SQL ไม่ถูกต้อง", str(error), parent=self.root)
            return

        hospital = self.mapping_hospital or self._get_mapping_hospital()
        if hospital is None:
            messagebox.showwarning("ไม่มี รพ.สต.", "กรุณาเพิ่มรายชื่อ รพ.สต. ก่อน Run SQL", parent=self.root)
            return
        hospital = dict(hospital)
        jhcis_default = dict(self.config.get("jhcis_default", {}))

        self.btn_run_person_sql.configure(state=tk.DISABLED)
        self.person_mapping_sql.configure(state=tk.DISABLED)
        self._clear_person_sql_results("กำลังรัน SQL...")
        self.person_mapping_status.config(
            text=f"กำลัง Run SQL ที่ {hospital.get('name', hospital.get('ip', ''))}..."
        )

        def _run():
            try:
                result = preview_person_sql(hospital, jhcis_default, query, max_rows=100)
                error = None
            except Exception as caught_error:
                result = None
                error = caught_error

            try:
                self.root.after(
                    0, self._finish_person_sql_preview, hospital, result, error
                )
            except tk.TclError:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _finish_person_sql_preview(self, hospital, result, error):
        self.person_mapping_sql.configure(state=tk.NORMAL)
        self.btn_run_person_sql.configure(state=tk.NORMAL)
        if error is not None:
            self.person_mapping_status.config(text=f"Run SQL ไม่สำเร็จ: {error}")
            self.person_sql_results_status.config(text=f"Run SQL ไม่สำเร็จ: {error}")
            log_error(f"[Mapping SQL] {hospital.get('code', '')} - {error}")
            messagebox.showerror("Run SQL ไม่สำเร็จ", str(error), parent=self.root)
            return

        columns, rows, truncated = result
        result_columns = tuple(f"result_{index}" for index in range(len(columns)))
        self.person_sql_results.configure(columns=result_columns)
        for column_id, column_name in zip(result_columns, columns):
            self.person_sql_results.heading(column_id, text=str(column_name))
            self.person_sql_results.column(
                column_id, width=150, minwidth=80, anchor=tk.W
            )
        for row in rows:
            self.person_sql_results.insert(
                "", tk.END,
                values=tuple("" if value is None else str(value) for value in row)
            )
        suffix = " (แสดงไม่เกิน 100 แถว)" if truncated else ""
        hospital_name = hospital.get("name", hospital.get("ip", ""))
        self.person_sql_results_status.config(
            text=f"{len(columns)} ฟิลด์ | {len(rows)} แถว | {hospital_name}{suffix}"
        )
        self.person_mapping_status.config(
            text=f"Run สำเร็จ: {len(columns)} ฟิลด์, {len(rows)} แถว{suffix}"
        )

    # =====================================================================
    # โหลดและแสดงข้อมูลในตาราง
    # =====================================================================
    def _load_hospitals_to_tree(self):
        self.vpn_indicator_states.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for h in self.config.get("hospitals", []):
            selected = "✓" if h.get("selected", False) else "✗"
            self.tree.insert("", tk.END, values=(
                selected, h.get("code", ""), h.get("name", ""),
                h.get("ip", ""), "⏳ รอตรวจสอบ", "-"
            ), tags=(h.get("code", ""),))

    def _update_tree_status(self, code, vpn_status, sync_status):
        for item in self.tree.get_children():
            if self.tree.item(item, "tags")[0] == code:
                vals = list(self.tree.item(item, "values"))
                if "🟢" in vpn_status:
                    self.vpn_indicator_states[item] = "online"
                    vals[4] = self._vpn_status_text("online")
                elif "🔴" in vpn_status:
                    self.vpn_indicator_states[item] = "offline"
                    vals[4] = self._vpn_status_text("offline")
                elif "ตรวจสอบไม่ได้" in vpn_status:
                    self.vpn_indicator_states[item] = "unknown"
                    vals[4] = self._vpn_status_text("unknown")
                else:
                    self.vpn_indicator_states.pop(item, None)
                    vals[4] = vpn_status
                vals[5] = sync_status
                self.tree.item(item, values=vals)
                break

    def _vpn_status_text(self, state):
        if state == "online":
            return f"{'🟢' if self.vpn_blink_phase else '⚪'} ออนไลน์"
        if state == "offline":
            return "🔴 ออฟไลน์"
        return "⚪ ตรวจสอบไม่ได้"

    def _on_tree_yscroll(self, first, last):
        self.vsb.set(first, last)

    def _on_tree_scroll(self, *args):
        self.tree.yview(*args)

    def _blink_vpn_indicators(self):
        self.vpn_blink_phase = not self.vpn_blink_phase
        for item, state in self.vpn_indicator_states.items():
            if state == "online" and self.tree.exists(item):
                values = list(self.tree.item(item, "values"))
                values[4] = self._vpn_status_text(state)
                self.tree.item(item, values=values)
        self.vpn_blink_job = self.root.after(500, self._blink_vpn_indicators)

    def _toggle_all_selection(self):
        all_selected = all(h.get("selected", False) for h in self.config.get("hospitals", []))
        new_val = not all_selected
        updated_config = copy.deepcopy(self.config)
        for h in updated_config.get("hospitals", []):
            h["selected"] = new_val
        if not save_config(updated_config):
            messagebox.showerror(
                "บันทึกไม่สำเร็จ",
                "ไม่สามารถบันทึกสถานะการเลือก รพ.สต. ลง config.json ได้",
                parent=self.root
            )
            return
        self.config.clear()
        self.config.update(updated_config)
        self._load_hospitals_to_tree()

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":
                item = self.tree.identify_row(event.y)
                if item:
                    code = self.tree.item(item, "tags")[0]
                    updated_config = copy.deepcopy(self.config)
                    for h in updated_config.get("hospitals", []):
                        if h.get("code") == code:
                            h["selected"] = not h.get("selected", False)
                            break
                    if not save_config(updated_config):
                        messagebox.showerror(
                            "บันทึกไม่สำเร็จ",
                            "ไม่สามารถบันทึกสถานะการเลือก รพ.สต. ลง config.json ได้",
                            parent=self.root
                        )
                        return
                    self.config.clear()
                    self.config.update(updated_config)
                    self._load_hospitals_to_tree()

    def _update_auto_status_label(self):
        sched = self.config.get("schedule", {})
        if sched.get("enabled", False):
            times = ", ".join(sched.get("sync_times", []))
            mode_txt = "เฉพาะที่ติ๊กเลือก" if sched.get("target_mode") == "selected" else "ทั้งหมดที่ออนไลน์"
            self.lbl_auto_status.config(
                text=f"สถานะ Auto: เปิดใช้งาน | เวลา: {times} | โหมด: {mode_txt}"
            )
        else:
            self.lbl_auto_status.config(text="สถานะ Auto: ยังไม่เปิดใช้งาน")

    def _toggle_windows_startup(self):
        enabled = self.start_with_windows_var.get()
        previous = self.start_with_windows
        try:
            _set_windows_startup(enabled)
        except OSError as e:
            self.start_with_windows_var.set(previous)
            messagebox.showerror("ตั้งค่าเริ่มพร้อม Windows ไม่สำเร็จ", str(e))
            return

        self.config["start_with_windows"] = enabled
        if not save_config(self.config):
            self.config["start_with_windows"] = previous
            self.start_with_windows_var.set(previous)
            try:
                _set_windows_startup(previous)
            except OSError as e:
                log_error(f"ไม่สามารถคืนค่าสถานะ Windows Startup ได้: {e}")
                messagebox.showerror(
                    "บันทึกการตั้งค่าไม่สำเร็จ",
                    f"บันทึก config.json ไม่สำเร็จ และคืนค่าสถานะ Startup ไม่ได้:\n{e}"
                )
                return
            messagebox.showerror("บันทึกการตั้งค่าไม่สำเร็จ", "ไม่สามารถบันทึก config.json ได้")
            return

        self.start_with_windows = enabled

    # =====================================================================
    # หน้าต่างจัดการ รพ.สต.
    # =====================================================================
    def _open_hospital_manager(self):
        win = ctk.CTkToplevel(self.root)
        win.title("จัดการรายชื่อ รพ.สต.")
        win.geometry("900x700")
        win.transient(self.root)
        win.grab_set()

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        cols = ("code", "name", "ip", "port", "selected")
        tree = ttk.Treeview(frm, columns=cols, show="headings", selectmode="browse")
        tree.heading("code", text="รหัส")
        tree.heading("name", text="ชื่อสถานพยาบาล")
        tree.heading("ip", text="Radmin IP")
        tree.heading("port", text="Port")
        tree.heading("selected", text="เลือก")
        tree.column("code", width=70, anchor="center")
        tree.column("name", width=220, anchor="w")
        tree.column("ip", width=120, anchor="center")
        tree.column("port", width=70, anchor="center")
        tree.column("selected", width=60, anchor="center")

        def refresh_tree():
            for item in tree.get_children():
                tree.delete(item)
            for h in self.config.get("hospitals", []):
                tree.insert("", tk.END, values=(
                    h.get("code", ""), h.get("name", ""), h.get("ip", ""),
                    h.get("port", 3333),
                    "✓" if h.get("selected", False) else "✗"
                ))

        refresh_tree()
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        form = ttk.LabelFrame(win, text="เพิ่ม / แก้ไข รพ.สต.", padding=10)
        form.pack(fill=tk.X, padx=10, pady=5)
        form.columnconfigure(0, weight=1)

        hospital_frame = ttk.LabelFrame(form, text="ข้อมูล รพ.สต.", padding=6)
        hospital_frame.grid(row=0, column=0, sticky=tk.EW, padx=3, pady=3)
        for column in (1, 3):
            hospital_frame.columnconfigure(column, weight=1)

        ttk.Label(hospital_frame, text="รหัส:").grid(
            row=0, column=0, sticky=tk.W, padx=4, pady=3
        )
        ent_code = ttk.Entry(hospital_frame, width=10)
        ent_code.grid(row=0, column=1, padx=4, pady=3, sticky=tk.EW, ipady=Spacing.XXS)

        ttk.Label(hospital_frame, text="ชื่อสถานพยาบาล:").grid(
            row=0, column=2, sticky=tk.W, padx=4, pady=3
        )
        ent_name = ttk.Entry(hospital_frame, width=36)
        ent_name.grid(row=0, column=3, padx=4, pady=3, sticky=tk.EW, ipady=Spacing.XXS)

        ttk.Label(hospital_frame, text="IP (VPN):").grid(
            row=1, column=0, sticky=tk.W, padx=4, pady=3
        )
        ent_ip = ttk.Entry(hospital_frame, width=20)
        ent_ip.grid(row=1, column=1, padx=4, pady=3, sticky=tk.EW, ipady=Spacing.XXS)

        ttk.Label(hospital_frame, text="Port JHCIS:").grid(
            row=1, column=2, sticky=tk.W, padx=4, pady=3
        )
        ent_port = ttk.Entry(hospital_frame, width=8)
        ent_port.insert(0, "3333")
        ent_port.grid(row=1, column=3, padx=4, pady=3, sticky=tk.W, ipady=Spacing.XXS)

        jhcis_default = self.config.get("jhcis_default", {})
        database_frame = ttk.LabelFrame(
            form, text="การเชื่อมต่อฐานข้อมูล JHCIS", padding=6
        )
        database_frame.grid(row=1, column=0, sticky=tk.EW, padx=3, pady=3)
        for column in (1, 3):
            database_frame.columnconfigure(column, weight=1)

        ttk.Label(database_frame, text="ชื่อฐานข้อมูล:").grid(
            row=0, column=0, sticky=tk.W, padx=4, pady=3
        )
        ent_database = ttk.Entry(database_frame, width=24)
        ent_database.insert(0, str(jhcis_default.get("database", "jhcisdb")))
        ent_database.grid(row=0, column=1, padx=4, pady=3, sticky=tk.EW, ipady=Spacing.XXS)

        ttk.Label(database_frame, text="User:").grid(
            row=0, column=2, sticky=tk.W, padx=4, pady=3
        )
        ent_user = ttk.Entry(database_frame, width=20)
        ent_user.insert(0, str(jhcis_default.get("user", "")))
        ent_user.grid(row=0, column=3, padx=4, pady=3, sticky=tk.EW, ipady=Spacing.XXS)

        ttk.Label(database_frame, text="Password:").grid(
            row=1, column=0, sticky=tk.W, padx=4, pady=3
        )
        ent_password = ttk.Entry(database_frame, width=24, show="*")
        ent_password.insert(0, str(jhcis_default.get("password", "")))
        ent_password.grid(row=1, column=1, padx=4, pady=3, sticky=tk.EW, ipady=Spacing.XXS)

        var_sel = tk.BooleanVar(value=True)
        chk_sel = ttk.Checkbutton(
            form, text="เลือก รพ.สต. นี้สำหรับการซิงค์", variable=var_sel
        )
        chk_sel.grid(row=2, column=0, sticky=tk.W, padx=5, pady=4)

        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=3, column=0, sticky=tk.EW, pady=8)

        # ตัวแปรเก็บรหัสที่กำลังแก้ไขอยู่ (ใช้แทน ent_code.cget("data_edit") ที่ใช้ไม่ได้กับ ttk.Entry)
        editing_code = {"value": ""}

        def save_hospital():
            code = ent_code.get().strip()
            name = ent_name.get().strip()
            ip = ent_ip.get().strip()
            database = ent_database.get().strip()
            user = ent_user.get().strip()
            password = ent_password.get()
            try:
                port = int(ent_port.get().strip() or 3333)
            except ValueError:
                messagebox.showwarning("Port ไม่ถูกต้อง", "กรุณากรอก Port เป็นตัวเลข")
                return
            if not 1 <= port <= 65535:
                messagebox.showwarning(
                    "Port ไม่ถูกต้อง", "Port ต้องอยู่ระหว่าง 1 ถึง 65535"
                )
                return
            if not code or not name or not ip or not database or not user:
                messagebox.showwarning(
                    "ข้อมูลไม่ครบ",
                    "กรุณากรอกรหัส ชื่อ IP ชื่อฐานข้อมูล และ User ให้ครบถ้วน"
                )
                return
            edit_code = editing_code["value"]
            hospitals = self.config.setdefault("hospitals", [])
            for h in hospitals:
                hospital_code = str(h.get("code", "")).strip()
                if hospital_code == code and hospital_code != edit_code:
                    messagebox.showwarning("คำเตือน", f"รหัส {code} มีอยู่ในระบบแล้ว")
                    return
            hospital = {
                "code": code, "name": name, "ip": ip, "database": database,
                "port": port, "user": user, "password": password,
                "selected": var_sel.get()
            }
            edit_index = None
            if edit_code:
                for i, h in enumerate(hospitals):
                    if str(h.get("code", "")).strip() == edit_code:
                        edit_index = i
                        break
                if edit_index is None:
                    messagebox.showerror("บันทึกไม่สำเร็จ", f"ไม่พบ รพ.สต. รหัส {edit_code} ที่กำลังแก้ไข")
                    return
                previous_hospital = hospitals[edit_index]
                updated_hospital = dict(previous_hospital)
                updated_hospital.update(hospital)
                hospitals[edit_index] = updated_hospital
            else:
                previous_hospital = None
                hospitals.append(hospital)
            if not save_config(self.config):
                if edit_index is None:
                    hospitals.pop()
                else:
                    hospitals[edit_index] = previous_hospital
                messagebox.showerror("บันทึกไม่สำเร็จ", "ไม่สามารถบันทึก config.json ได้ กรุณาตรวจสอบสิทธิ์การเขียนไฟล์")
                return
            editing_code["value"] = ""
            refresh_tree()
            self._load_hospitals_to_tree()
            ent_code.delete(0, tk.END)
            ent_name.delete(0, tk.END)
            ent_ip.delete(0, tk.END)
            ent_port.delete(0, tk.END)
            ent_port.insert(0, "3333")
            ent_database.delete(0, tk.END)
            ent_database.insert(
                0, str(self.config.get("jhcis_default", {}).get("database", "jhcisdb"))
            )
            ent_user.delete(0, tk.END)
            ent_user.insert(0, str(self.config.get("jhcis_default", {}).get("user", "")))
            ent_password.delete(0, tk.END)
            ent_password.insert(
                0, str(self.config.get("jhcis_default", {}).get("password", ""))
            )
            var_sel.set(True)

        def delete_hospital():
            item = tree.focus()
            if not item:
                messagebox.showwarning("คำเตือน", "กรุณาเลือกรายการที่ต้องการลบ")
                return
            code = tree.item(item, "values")[0]
            if messagebox.askyesno("ยืนยัน", f"ลบ รพ.สต. รหัส {code} หรือไม่?"):
                updated_config = copy.deepcopy(self.config)
                updated_config["hospitals"] = [
                    hospital for hospital in updated_config.get("hospitals", [])
                    if hospital.get("code") != code
                ]
                if not save_config(updated_config):
                    messagebox.showerror(
                        "บันทึกไม่สำเร็จ",
                        "ไม่สามารถบันทึกการลบ รพ.สต. ลง config.json ได้",
                        parent=win
                    )
                    return
                self.config.clear()
                self.config.update(updated_config)
                refresh_tree()
                self._load_hospitals_to_tree()

        def populate_hospital_form(hospital, editing=False):
            ent_code.delete(0, tk.END)
            ent_code.insert(0, hospital.get("code", ""))
            ent_name.delete(0, tk.END)
            ent_name.insert(0, hospital.get("name", ""))
            ent_ip.delete(0, tk.END)
            ent_ip.insert(0, hospital.get("ip", ""))
            ent_port.delete(0, tk.END)
            ent_port.insert(0, str(hospital.get("port", 3333)))
            jhcis_default = self.config.get("jhcis_default", {})
            ent_database.delete(0, tk.END)
            ent_database.insert(
                0,
                str(hospital.get("database") or jhcis_default.get("database", "jhcisdb"))
            )
            ent_user.delete(0, tk.END)
            ent_user.insert(
                0, str(hospital.get("user") or jhcis_default.get("user", ""))
            )
            ent_password.delete(0, tk.END)
            password = hospital.get(
                "password", jhcis_default.get("password", "")
            )
            ent_password.insert(0, str(password or ""))
            var_sel.set(bool(hospital.get("selected", False)))
            editing_code["value"] = (
                str(hospital.get("code", "")) if editing else ""
            )

        def on_hospital_selected(event=None, editing=False):
            selection = tree.selection()
            if not selection:
                return
            values = tree.item(selection[0], "values")
            code = str(values[0]).strip()
            hospital = next(
                (
                    hospital for hospital in self.config.get("hospitals", [])
                    if str(hospital.get("code", "")).strip() == code
                ),
                None
            )
            if hospital is None:
                log_error(f"ไม่พบข้อมูล รพ.สต. รหัส {code} ที่เลือกในหน้าต่างจัดการ")
                return
            populate_hospital_form(hospital, editing=editing)

        def edit_hospital():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("คำเตือน", "กรุณาเลือกรายการที่ต้องการแก้ไข")
                return
            on_hospital_selected(editing=True)

        def test_hospital_db():
            """ทดสอบการเชื่อมต่อฐานข้อมูลลูกข่าย (JHCIS) ของ รพ.สต. ที่เลือก"""
            item = tree.focus()
            if not item:
                messagebox.showwarning("คำเตือน", "กรุณาเลือกรายการ รพ.สต. ที่ต้องการทดสอบการเชื่อมต่อ")
                return
            vals = tree.item(item, "values")
            code = vals[0]
            name = vals[1]
            ip = vals[2]
            try:
                port = get_hospital_port({"port": vals[3]})
            except ValueError:
                messagebox.showerror(
                    "Port ไม่ถูกต้อง", "แก้ไข Port ของ รพ.สต. นี้ให้เป็นตัวเลขก่อนทดสอบ"
                )
                return

            hospital = next(
                (
                    dict(hospital) for hospital in self.config.get("hospitals", [])
                    if str(hospital.get("code", "")).strip() == str(code).strip()
                ),
                None
            )
            if hospital is None:
                messagebox.showerror(
                    "ทดสอบการเชื่อมต่อ",
                    f"ไม่พบการตั้งค่าของ รพ.สต. รหัส {code}",
                    parent=win
                )
                return
            hospital.update({"ip": ip, "port": port, "code": code, "name": name})
            jd = self.config.get("jhcis_default", {})

            def _test():
                try:
                    # ขั้นที่ 1: เช็กพอร์ต VPN
                    vpn_ok = check_vpn_port(ip, port, timeout=3)
                    if not vpn_ok:
                        self.root.after(0, lambda: messagebox.showerror(
                            "ทดสอบการเชื่อมต่อฐานข้อมูลลูกข่าย",
                            f"รพ.สต. {name} (รหัส: {code})\nIP: {ip}:{port}\n\n"
                            f"❌ ไม่สามารถเชื่อมต่อพอร์ต VPN ({port}) ได้\n"
                            f"กรุณาตรวจสอบว่า Radmin VPN เชื่อมต่ออยู่และ IP ถูกต้อง"
                        ))
                        return

                    # ขั้นที่ 2: ลองเชื่อมต่อฐานข้อมูล MySQL
                    conn = get_jhcis_connection(hospital, jd)
                    conn.close()

                    self.root.after(0, lambda: messagebox.showinfo(
                        "ทดสอบการเชื่อมต่อฐานข้อมูลลูกข่าย",
                        f"รพ.สต. {name} (รหัส: {code})\nIP: {ip}:{port}\n\n"
                        f"✅ เชื่อมต่อฐานข้อมูลลูกข่ายสำเร็จแล้ว"
                    ))
                    log_info(f"[Test DB] รพ.สต. {code} {name} ({ip}:{port}) - เชื่อมต่อสำเร็จ")

                except Error as e:
                    self.root.after(0, lambda: messagebox.showerror(
                        "ทดสอบการเชื่อมต่อฐานข้อมูลลูกข่าย",
                        f"รพ.สต. {name} (รหัส: {code})\nIP: {ip}:{port}\n\n"
                        f"⚠️ เชื่อมต่อพอร์ต VPN ได้ แต่เชื่อมต่อฐานข้อมูลไม่สำเร็จ:\n{str(e)}"
                    ))
                    log_error(f"[Test DB] รพ.สต. {code} {name} ({ip}:{port}) - Database Error: {str(e)}")
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror(
                        "ทดสอบการเชื่อมต่อฐานข้อมูลลูกข่าย",
                        f"รพ.สต. {name} (รหัส: {code})\nIP: {ip}:{port}\n\n"
                        f"❌ เกิดข้อผิดพลาด:\n{str(e)}"
                    ))
                    log_error(f"[Test DB] รพ.สต. {code} {name} ({ip}:{port}) - Exception: {str(e)}")

            threading.Thread(target=_test, daemon=True).start()

        tree.bind("<<TreeviewSelect>>", on_hospital_selected)
        create_primary_button(btn_frame, text=f"{Icons.SAVE} บันทึก", command=save_hospital).pack(side=tk.LEFT, padx=Spacing.SM)
        create_secondary_button(btn_frame, text=f"{Icons.EDIT} แก้ไข", command=edit_hospital).pack(side=tk.LEFT, padx=Spacing.SM)
        create_danger_button(btn_frame, text=f"{Icons.DELETE} ลบ", command=delete_hospital).pack(side=tk.LEFT, padx=Spacing.SM)
        create_secondary_button(btn_frame, text=f"{Icons.VPN} ทดสอบเชื่อมต่อ DB", command=test_hospital_db).pack(side=tk.LEFT, padx=Spacing.SM)
        create_ghost_button(btn_frame, text=f"{Icons.CLOSE} ปิด", command=win.destroy).pack(side=tk.RIGHT, padx=Spacing.SM)

        win.wait_window(win)

    def _open_district_sync(self):
        if self.district_sync_window is not None and self.district_sync_window.exists():
            self.district_sync_window.show()
            return
        self.district_sync_window = DistrictSyncWindow(self)

    def _collect_hostatom_db_settings(self):
        hostatom_db = {
            "host": self.entry_hostatom_host.get().strip(),
            "database": self.entry_hostatom_db.get().strip(),
            "user": self.entry_hostatom_user.get().strip(),
            "password": self.entry_hostatom_pass.get().strip(),
        }
        try:
            hostatom_db["port"] = int(self.entry_hostatom_port.get().strip() or 3306)
            hostatom_db["batch_size"] = int(
                self.entry_hostatom_batch_size.get().strip() or 500
            )
        except ValueError as error:
            raise ValueError("Port และ Batch Size ต้องเป็นตัวเลข") from error
        if not 1 <= hostatom_db["port"] <= 65535:
            raise ValueError("Port ต้องอยู่ระหว่าง 1 ถึง 65535")
        if hostatom_db["batch_size"] <= 0:
            raise ValueError("Batch Size ต้องมากกว่า 0")
        if not hostatom_db["host"] or not hostatom_db["database"] or not hostatom_db["user"]:
            raise ValueError("กรุณากรอก Host, Database และ User ให้ครบ")
        return hostatom_db

    def _save_hostatom_db_settings(self):
        try:
            hostatom_db = self._collect_hostatom_db_settings()
        except ValueError as error:
            messagebox.showerror("ค่าตั้งค่าไม่ถูกต้อง", str(error), parent=self.root)
            return

        updated_config = dict(self.config)
        updated_config["hostatom_db"] = hostatom_db
        if not save_config(updated_config):
            messagebox.showerror(
                "บันทึกไม่สำเร็จ",
                "ไม่สามารถบันทึกการตั้งค่า HostAtom ลง config.json ได้",
                parent=self.root
            )
            return

        self.config.clear()
        self.config.update(updated_config)
        self.hostatom_db_status_var.set("บันทึกการตั้งค่า HostAtom แล้ว")
        self._check_database_connections_automatically()
        self.toast_manager.show("บันทึกการตั้งค่า HostAtom แล้ว", "success")

    def _test_hostatom_database(self):
        try:
            hostatom_db = self._collect_hostatom_db_settings()
        except ValueError as error:
            messagebox.showerror("ค่าตั้งค่าไม่ถูกต้อง", str(error), parent=self.root)
            return

        self.btn_test_hostatom_db.configure(state=tk.DISABLED)
        self.hostatom_db_status_var.set("กำลังทดสอบการเชื่อมต่อ...")

        def _test():
            try:
                success, result_message = test_hostatom_connection(hostatom_db)
            except Exception as error:
                success, result_message = False, str(error)
            try:
                self.root.after(
                    0, self._finish_hostatom_db_test, success, result_message
                )
            except tk.TclError:
                pass

        threading.Thread(target=_test, daemon=True).start()

    def _finish_hostatom_db_test(self, success, result_message):
        self.btn_test_hostatom_db.configure(state=tk.NORMAL)
        self.hostatom_db_status_var.set(
            "เชื่อมต่อ Cloud DB สำเร็จ" if success
            else "ทดสอบการเชื่อมต่อไม่สำเร็จ"
        )
        if success:
            self.toast_manager.show("เชื่อมต่อ Cloud DB สำเร็จ", "success")
        else:
            log_error(f"[HostAtom DB Test] {result_message}")
            messagebox.showerror(
                "ทดสอบ Cloud DB ไม่สำเร็จ", result_message, parent=self.root
            )

    # =====================================================================
    # หน้าตั้งค่าแจ้งเตือน (Telegram / LINE)
    # =====================================================================
    def _open_notification_settings(self):
        win = ctk.CTkToplevel(self.root)
        win.title("ตั้งค่าแจ้งเตือน")
        win.geometry("500x420")
        win.transient(self.root)
        win.grab_set()

        frm = ttk.Frame(win, padding=15)
        frm.pack(fill=tk.BOTH, expand=True)

        notif = self.config.get("notification", {})

        ttk.Label(frm, text="Telegram Bot", font=FONTS["H3"]).pack(anchor=tk.W, pady=(10, 0))
        var_tg = tk.BooleanVar(value=notif.get("telegram_enabled", False))
        ttk.Checkbutton(frm, text="เปิดใช้งาน Telegram", variable=var_tg).pack(anchor=tk.W)

        ttk.Label(frm, text="Bot Token:").pack(anchor=tk.W, pady=(5, 0))
        ent_tg_token = ttk.Entry(frm, width=50)
        ent_tg_token.insert(0, notif.get("telegram_bot_token", ""))
        ent_tg_token.pack(fill=tk.X, pady=2, ipady=Spacing.XXS)

        ttk.Label(frm, text="Chat ID:").pack(anchor=tk.W, pady=(5, 0))
        ent_tg_chat = ttk.Entry(frm, width=30)
        ent_tg_chat.insert(0, notif.get("telegram_chat_id", ""))
        ent_tg_chat.pack(fill=tk.X, pady=2, ipady=Spacing.XXS)

        ttk.Separator(frm, orient="horizontal").pack(fill=tk.X, pady=10)

        ttk.Label(frm, text="LINE Messaging API", font=FONTS["H3"]).pack(anchor=tk.W, pady=(10, 0))
        var_line = tk.BooleanVar(value=notif.get("line_enabled", False))
        ttk.Checkbutton(frm, text="เปิดใช้งาน LINE", variable=var_line).pack(anchor=tk.W)

        ttk.Label(frm, text="Channel Token:").pack(anchor=tk.W, pady=(5, 0))
        ent_line_tok = ttk.Entry(frm, width=50)
        ent_line_tok.insert(0, notif.get("line_channel_token", ""))
        ent_line_tok.pack(fill=tk.X, pady=2, ipady=Spacing.XXS)

        ttk.Label(frm, text="User ID:").pack(anchor=tk.W, pady=(5, 0))
        ent_line_user = ttk.Entry(frm, width=30)
        ent_line_user.insert(0, notif.get("line_user_id", ""))
        ent_line_user.pack(fill=tk.X, pady=2, ipady=Spacing.XXS)

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill=tk.X, pady=20)

        def save_notif():
            updated_config = copy.deepcopy(self.config)
            updated_config["notification"] = {
                "telegram_enabled": var_tg.get(),
                "telegram_bot_token": ent_tg_token.get().strip(),
                "telegram_chat_id": ent_tg_chat.get().strip(),
                "line_enabled": var_line.get(),
                "line_channel_token": ent_line_tok.get().strip(),
                "line_user_id": ent_line_user.get().strip()
            }
            if not save_config(updated_config):
                messagebox.showerror(
                    "บันทึกไม่สำเร็จ",
                    "ไม่สามารถบันทึกการตั้งค่าการแจ้งเตือนลง config.json ได้",
                    parent=win
                )
                return
            self.config.clear()
            self.config.update(updated_config)
            self.toast_manager.show("บันทึกการตั้งค่าการแจ้งเตือนแล้ว", "success")
            win.destroy()

        def test_notif():
            msg = "🔔 ทดสอบการแจ้งเตือนจาก SAHARose Sync Master\nระบบทำงานปกติดีครับ"
            results = []
            if var_tg.get() and ent_tg_token.get().strip() and ent_tg_chat.get().strip():
                from notifier import send_telegram_message
                ok, m = send_telegram_message(ent_tg_token.get().strip(), ent_tg_chat.get().strip(), msg)
                results.append(f"Telegram: {'สำเร็จ' if ok else 'ล้มเหลว'} ({m})")
            if var_line.get() and ent_line_tok.get().strip() and ent_line_user.get().strip():
                from notifier import send_line_message
                ok, m = send_line_message(ent_line_tok.get().strip(), ent_line_user.get().strip(), msg)
                results.append(f"LINE: {'สำเร็จ' if ok else 'ล้มเหลว'} ({m})")
            if results:
                messagebox.showinfo("ผลการทดสอบ", "\n".join(results))
            else:
                messagebox.showwarning("คำเตือน", "กรุณาเปิดใช้งานและกรอกข้อมูลอย่างน้อย 1 ช่องทาง")

        create_secondary_button(btn_frame, text=f"{Icons.BELL} ทดสอบส่งข้อความ", command=test_notif).pack(side=tk.LEFT, padx=Spacing.SM)
        create_primary_button(btn_frame, text=f"{Icons.SAVE} บันทึก", command=save_notif).pack(side=tk.LEFT, padx=Spacing.SM)
        create_ghost_button(btn_frame, text=f"{Icons.CLOSE} ยกเลิก", command=win.destroy).pack(side=tk.RIGHT, padx=Spacing.SM)

        win.wait_window(win)

    # =====================================================================
    # ตั้งค่าฐานข้อมูลอำเภอ
    # =====================================================================
    def _get_saved_district_db_settings(self):
        entered_settings = self._collect_district_db_settings()
        saved_settings = get_district_db_config(load_config())
        saved_settings = {
            "host": str(saved_settings.get("host", "")).strip(),
            "port": int(saved_settings["port"]),
            "database": str(saved_settings.get("database", "")).strip(),
            "user": str(saved_settings.get("user", "")).strip(),
            "password": str(saved_settings.get("password", "")).strip(),
        }
        if entered_settings != saved_settings:
            raise ValueError(
                "ค่าบนหน้าจอยังไม่ตรงกับ district_db ใน config.json "
                "กรุณาบันทึกการตั้งค่าก่อนทดสอบเชื่อมต่อ"
            )
        return saved_settings

    def _collect_district_db_settings(self):
        district_db = {
            "host": self.entry_district_host.get().strip(),
            "database": self.entry_district_db.get().strip(),
            "user": self.entry_district_user.get().strip(),
            "password": self.entry_district_pass.get().strip(),
        }
        try:
            district_db["port"] = int(self.entry_district_port.get().strip())
        except ValueError as error:
            raise ValueError("Port ต้องเป็นตัวเลข") from error
        if not 1 <= district_db["port"] <= 65535:
            raise ValueError("Port ต้องอยู่ระหว่าง 1 ถึง 65535")
        if not district_db["host"] or not district_db["database"] or not district_db["user"]:
            raise ValueError("กรุณากรอก Host, Database และ User ให้ครบ")
        return district_db

    def _save_district_db_settings(self):
        try:
            district_db = self._collect_district_db_settings()
        except ValueError as error:
            messagebox.showerror("ค่าตั้งค่าไม่ถูกต้อง", str(error), parent=self.root)
            return

        updated_config = dict(self.config)
        updated_config["district_db"] = district_db
        if not save_config(updated_config):
            messagebox.showerror(
                "บันทึกไม่สำเร็จ",
                "ไม่สามารถบันทึกการตั้งค่าฐานข้อมูลอำเภอลง config.json ได้",
                parent=self.root
            )
            return

        self.config.clear()
        self.config.update(updated_config)
        self.district_db_status_var.set("บันทึกการตั้งค่าฐานข้อมูลอำเภอแล้ว")
        self._check_database_connections_automatically()
        self.toast_manager.show("บันทึกการตั้งค่าฐานข้อมูลอำเภอแล้ว", "success")

    def _test_district_database(self):
        try:
            district_db = self._get_saved_district_db_settings()
        except (TypeError, ValueError) as error:
            messagebox.showerror("ค่าตั้งค่าไม่ถูกต้อง", str(error), parent=self.root)
            return

        self.btn_test_district_db.configure(state=tk.DISABLED)
        self.district_db_status_var.set("กำลังทดสอบการเชื่อมต่อ...")

        def _test():
            success, result_message = test_district_connection(district_db)
            try:
                self.root.after(
                    0, self._finish_district_db_test, success, result_message
                )
            except tk.TclError:
                pass

        threading.Thread(target=_test, daemon=True).start()

    def _finish_district_db_test(self, success, result_message):
        self.btn_test_district_db.configure(state=tk.NORMAL)
        self.district_db_status_var.set(
            "เชื่อมต่อฐานข้อมูลอำเภอสำเร็จ" if success
            else "ทดสอบการเชื่อมต่อไม่สำเร็จ"
        )
        if success:
            self.toast_manager.show("เชื่อมต่อฐานข้อมูลอำเภอสำเร็จ", "success")
        else:
            log_error(f"[District DB Test] {result_message}")
            messagebox.showerror(
                "ทดสอบฐานข้อมูลอำเภอไม่สำเร็จ",
                result_message,
                parent=self.root
            )

    def _check_database_connections_automatically(self):
        if self.database_status_check_running:
            return

        checks = []
        for label, variable, collect_settings, test_connection in (
            (
                "ฐานข้อมูลอำเภอ",
                self.district_db_status_var,
                self._get_saved_district_db_settings,
                test_district_connection,
            ),
            (
                "Cloud DB",
                self.hostatom_db_status_var,
                self._collect_hostatom_db_settings,
                test_district_sync_hostatom_connection,
            ),
        ):
            try:
                settings = collect_settings()
                settings_error = None
            except ValueError as error:
                settings = None
                settings_error = str(error)
            checks.append((label, variable, settings, settings_error, test_connection))

        self.database_status_check_running = True
        self.btn_test_district_db.configure(state=tk.DISABLED)
        self.btn_test_hostatom_db.configure(state=tk.DISABLED)
        for _, variable, _, _, _ in checks:
            variable.set("กำลังตรวจสอบการเชื่อมต่อ...")

        def _check():
            results = []
            for label, _, settings, settings_error, test_connection in checks:
                if settings_error is not None:
                    results.append((False, settings_error, True))
                    log_error(f"[{label} Auto Check] {settings_error}")
                    continue
                try:
                    success, result_message = test_connection(settings)
                except Exception as error:
                    success, result_message = False, str(error)
                if not success:
                    log_error(f"[{label} Auto Check] {result_message}")
                results.append((success, result_message, False))
            try:
                self.root.after(0, self._finish_automatic_database_check, results)
            except tk.TclError:
                pass

        try:
            threading.Thread(target=_check, daemon=True).start()
        except RuntimeError as error:
            self.database_status_check_running = False
            self.btn_test_district_db.configure(state=tk.NORMAL)
            self.btn_test_hostatom_db.configure(state=tk.NORMAL)
            message = f"เริ่มตรวจสอบการเชื่อมต่อไม่สำเร็จ: {error}"
            self.district_db_status_var.set(message)
            self.hostatom_db_status_var.set(message)
            log_error(f"[Database Auto Check] {error}")

    def _finish_automatic_database_check(self, results):
        self.database_status_check_running = False
        self.btn_test_district_db.configure(state=tk.NORMAL)
        self.btn_test_hostatom_db.configure(state=tk.NORMAL)
        checked_at = datetime.now().strftime("%H:%M:%S")
        status_vars = (self.district_db_status_var, self.hostatom_db_status_var)
        for variable, (success, _, invalid_settings) in zip(status_vars, results):
            if success:
                status = f"🟢 เชื่อมต่อสำเร็จ · ตรวจล่าสุด {checked_at}"
            elif invalid_settings:
                status = f"⚠️ กรุณาตรวจสอบการตั้งค่า · ตรวจล่าสุด {checked_at}"
            else:
                status = f"🔴 เชื่อมต่อไม่สำเร็จ · ตรวจล่าสุด {checked_at}"
            variable.set(status)

    def _schedule_database_status_refresh(self):
        self._cancel_database_status_refresh()
        self.database_status_check_job_id = self.root.after(
            DATABASE_STATUS_REFRESH_INTERVAL_MS,
            self._run_scheduled_database_status_refresh
        )

    def _run_scheduled_database_status_refresh(self):
        self.database_status_check_job_id = None
        if self.content_notebook.select() != str(self.settings_tab):
            return
        self._check_database_connections_automatically()
        self._schedule_database_status_refresh()

    def _cancel_database_status_refresh(self):
        if self.database_status_check_job_id is None:
            return
        try:
            self.root.after_cancel(self.database_status_check_job_id)
        except tk.TclError:
            pass
        self.database_status_check_job_id = None

    # =====================================================================
    # ตรวจสอบสถานะ VPN ทั้งหมด
    # =====================================================================
    def _check_all_vpn(self):
        if self.vpn_check_running:
            return
        hospitals = [
            (h.get("code", ""), h.get("ip", ""), h.get("port", 3333))
            for h in self.config.get("hospitals", [])
        ]
        self.vpn_check_running = True
        self.btn_check_vpn.config(state=tk.DISABLED)
        self.status_var.set("กำลังตรวจสอบสถานะ VPN...")

        def _check():
            for code, ip, port_value in hospitals:
                try:
                    port = get_hospital_port({"port": port_value})
                    ok = check_vpn_port(ip, port, timeout=2)
                    status = "🟢 ออนไลน์" if ok else "🔴 ออฟไลน์"
                except (TypeError, ValueError, OSError) as error:
                    log_error(
                        f"[{code}] ตรวจสอบ VPN {ip}:{port_value} ไม่สำเร็จ: {error}"
                    )
                    status = "⚠️ ตรวจสอบไม่ได้"
                try:
                    self.root.after(
                        0,
                        lambda c=code, s=status: self._update_tree_status(c, s, "-")
                    )
                except tk.TclError:
                    return
            try:
                self.root.after(0, lambda: self._check_vpn_finished())
            except tk.TclError:
                pass

        threading.Thread(target=_check, daemon=True).start()

    def _check_vpn_finished(self):
        self.vpn_check_running = False
        self.btn_check_vpn.config(state=tk.NORMAL)
        self.status_var.set("ตรวจสอบ VPN เรียบร้อยแล้ว")

    # =====================================================================
    # เปิดหน้าตั้งค่า Auto-Schedule
    # =====================================================================
    def _open_auto_schedule(self):
        win = ctk.CTkToplevel(self.root)
        win.title("ตั้งค่า Auto-Schedule")
        win.geometry("500x450")
        win.transient(self.root)
        win.grab_set()

        frm = ttk.Frame(win, padding=15)
        frm.pack(fill=tk.BOTH, expand=True)

        sched = self.config.get("schedule", {})

        var_enabled = tk.BooleanVar(value=sched.get("enabled", False))
        ttk.Checkbutton(frm, text="เปิดใช้งานการซิงค์อัตโนมัติ (Auto-Sync)", variable=var_enabled).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(frm, text="ช่วงเวลาซิงค์ (HH:MM) - เพิ่มได้หลายรอบ:").pack(anchor=tk.W)

        list_times = ttk.Listbox(frm, height=6, width=20, font=FONTS["BODY"])
        list_times.pack(fill=tk.X, pady=2)
        for t in sched.get("sync_times", ["12:00", "16:30"]):
            list_times.insert(tk.END, t)

        time_btn_frame = ttk.Frame(frm)
        time_btn_frame.pack(fill=tk.X, pady=5)

        ent_new_time = ttk.Entry(time_btn_frame, width=10)
        ent_new_time.pack(side=tk.LEFT, padx=2, ipady=Spacing.XXS)

        def add_time():
            t = ent_new_time.get().strip()
            if not t:
                return
            try:
                datetime.strptime(t, "%H:%M")
            except ValueError:
                messagebox.showwarning("คำเตือน", "รูปเวลาต้องเป็น HH:MM เช่น 12:00")
                return
            list_times.insert(tk.END, t)
            ent_new_time.delete(0, tk.END)

        def remove_time():
            sel = list_times.curselection()
            if sel:
                list_times.delete(sel[0])

        ttk.Button(time_btn_frame, text="เพิ่ม", command=add_time).pack(side=tk.LEFT, padx=2)
        ttk.Button(time_btn_frame, text="ลบ", command=remove_time).pack(side=tk.LEFT, padx=2)

        ttk.Label(frm, text="ขอบเขตการทำงาน:").pack(anchor=tk.W, pady=(10, 0))
        var_mode = tk.StringVar(value=sched.get("target_mode", "selected"))
        ttk.Radiobutton(frm, text="ดึงเฉพาะ รพ.สต. ที่ติ๊กเลือกไว้", variable=var_mode, value="selected").pack(anchor=tk.W)
        ttk.Radiobutton(frm, text="ดึงทุก รพ.สต. ที่ออนไลน์", variable=var_mode, value="all_online").pack(anchor=tk.W)

        var_notify = tk.BooleanVar(value=sched.get("notify_on_auto", True))
        ttk.Checkbutton(frm, text="ส่งแจ้งเตือนเข้า Telegram/LINE เมื่อซิงค์อัตโนมัติเสร็จ", variable=var_notify).pack(anchor=tk.W, pady=(10, 0))

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill=tk.X, pady=20)

        def save_schedule():
            times = list_times.get(0, tk.END)
            if not times:
                messagebox.showwarning("คำเตือน", "กรุณากำหนดเวลาซิงค์อย่างน้อย 1 รอบ")
                return
            for t in times:
                try:
                    datetime.strptime(t, "%H:%M")
                except ValueError:
                    messagebox.showwarning("คำเตือน", f"รูปเวลาไม่ถูกต้อง: {t}")
                    return

            updated_config = copy.deepcopy(self.config)
            updated_config["schedule"] = {
                "enabled": var_enabled.get(),
                "sync_times": list(times),
                "target_mode": var_mode.get(),
                "notify_on_auto": var_notify.get()
            }
            if not save_config(updated_config):
                messagebox.showerror(
                    "บันทึกไม่สำเร็จ",
                    "ไม่สามารถบันทึกตารางเวลาอัตโนมัติลง config.json ได้",
                    parent=win
                )
                return
            self.config.clear()
            self.config.update(updated_config)
            self._update_auto_status_label()

            if var_enabled.get() and schedule:
                self._restart_scheduler()
            elif not var_enabled.get():
                self._stop_scheduler()

            self.toast_manager.show("บันทึกตารางเวลาอัตโนมัติแล้ว", "success")
            win.destroy()

        ttk.Button(btn_frame, text="บันทึกตารางเวลา", command=save_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="ยกเลิก", command=win.destroy).pack(side=tk.RIGHT, padx=5)

        win.wait_window(win)

    # =====================================================================
    # ระบบ Auto-Schedule Background Thread
    # =====================================================================
    def _start_scheduler(self):
        if self.schedule_running:
            return
        self.schedule_running = True
        self.schedule_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.schedule_thread.start()
        log_info("เริ่มต้น Auto-Scheduler แล้ว")

    def _stop_scheduler(self):
        self.schedule_running = False
        log_info("หยุด Auto-Scheduler แล้ว")

    def _restart_scheduler(self):
        self._stop_scheduler()
        time.sleep(0.5)
        self._start_scheduler()

    def _scheduler_loop(self):
        schedule.clear()
        sched = self.config.get("schedule", {})
        for t in sched.get("sync_times", []):
            schedule.every().day.at(t).do(self._auto_sync_job)
        log_info(f"ตั้งเวลาซิงค์อัตโนมัติแล้ว: {', '.join(sched.get('sync_times', []))}")
        while self.schedule_running:
            schedule.run_pending()
            time.sleep(1)

    def _auto_sync_job(self):
        if not self.sync_lock.acquire(blocking=False):
            log_info("[Auto] มีการซิงค์อยู่แล้ว ข้ามรอบนี้")
            return
        try:
            threading.Thread(target=self._do_auto_sync, daemon=True).start()
        except RuntimeError as error:
            self.sync_lock.release()
            log_error(f"[Auto] เริ่มเธรดซิงค์ไม่สำเร็จ: {error}")
            try:
                self.root.after(
                    0, self.status_var.set, "เริ่มซิงค์อัตโนมัติไม่สำเร็จ"
                )
            except tk.TclError:
                pass

    def _set_sync_action_buttons(self, state):
        for button_name in (
            "btn_sync_manual", "btn_jhcis_to_district", "btn_district_to_cloud"
        ):
            button = getattr(self, button_name, None)
            if button is not None:
                button.configure(state=state)

    def _set_data_flow_status(self, stage, text, running=False):
        self.data_flow_status_vars[stage].set(text)
        progress_bar = self.data_flow_progress_bars[stage]
        if running:
            progress_bar.start(10)
        else:
            progress_bar.stop()

    def _queue_data_flow_status(self, stage, text):
        try:
            self.root.after(0, self.data_flow_status_vars[stage].set, text)
        except tk.TclError:
            pass

    def _queue_hospital_flow_status(self, code, text):
        try:
            self.root.after(0, self._set_hospital_flow_status, code, text)
        except tk.TclError:
            pass

    def _set_hospital_flow_status(self, code, text):
        for item in self.tree.get_children():
            tags = self.tree.item(item, "tags")
            if tags and tags[0] == code:
                values = list(self.tree.item(item, "values"))
                values[5] = text
                self.tree.item(item, values=values)
                return

    def _start_data_flow(self, stage, operation, initial_status):
        if not self.sync_lock.acquire(blocking=False):
            messagebox.showwarning(
                "กำลังทำงาน",
                "มีการซิงค์ข้อมูลอื่นทำงานอยู่ กรุณารอให้เสร็จก่อน",
                parent=self.root
            )
            return

        self._set_sync_action_buttons(tk.DISABLED)
        self._set_data_flow_status(stage, initial_status, running=True)
        self.status_var.set(initial_status)

        def _worker():
            try:
                success, summary, details = operation()
            except Exception as error:
                success = False
                summary = f"ล้มเหลว: {error}"
                details = [str(error)]
                log_error(f"[Data Flow:{stage}] {error}")
            finally:
                self.sync_lock.release()
            try:
                self.root.after(
                    0, self._finish_data_flow, stage, success, summary, details
                )
            except tk.TclError:
                pass

        try:
            threading.Thread(target=_worker, daemon=True).start()
        except RuntimeError as error:
            self.sync_lock.release()
            self._set_data_flow_status(stage, f"เริ่มงานไม่สำเร็จ: {error}")
            self._set_sync_action_buttons(tk.NORMAL)
            log_error(f"[Data Flow:{stage}] เริ่ม thread ไม่สำเร็จ: {error}")

    def _finish_data_flow(self, stage, success, summary, details):
        self._set_data_flow_status(stage, summary)
        self._set_sync_action_buttons(tk.NORMAL)
        self.status_var.set(summary)
        detail_lines = details[:15]
        if len(details) > len(detail_lines):
            detail_lines.append(f"... และอีก {len(details) - len(detail_lines)} รายการ")
        message = summary
        if detail_lines:
            message += "\n\n" + "\n".join(detail_lines)
        if success:
            messagebox.showinfo("ผลการไหลข้อมูล", message, parent=self.root)
        else:
            messagebox.showwarning("ผลการไหลข้อมูล", message, parent=self.root)

    def _start_jhcis_to_district(self):
        self._start_data_flow(
            "jhcis_to_district",
            self._perform_jhcis_to_district,
            "กำลังเริ่มดึงข้อมูล JHCIS เข้า ฐานอำเภอ..."
        )

    def _perform_jhcis_to_district(self):
        config = load_config()
        district_db = get_district_db_config(config)
        jhcis_default = dict(config.get("jhcis_default", {}))
        hostatom_db = dict(config.get("hostatom_db", {}))
        hospitals = [
            dict(hospital)
            for hospital in config.get("hospitals", [])
            if hospital.get("selected", False)
        ]
        if not hospitals:
            raise ValueError("กรุณาเลือก รพ.สต. ลูกข่ายอย่างน้อย 1 แห่ง")

        mappings = [
            row for row in get_sql_mappings(district_db)
            if bool(row.get("is_active"))
        ]
        if not mappings:
            raise ValueError("ไม่พบ Mapping ที่เปิดใช้งานใน sql_mapping")

        batch_size = int(hostatom_db.get("batch_size", 500))
        if batch_size <= 0:
            raise ValueError("Batch Size ต้องมากกว่า 0")

        valid_mappings = []
        details = []
        for mapping in mappings:
            try:
                validate_read_only_select(mapping.get("jhcis_extract_sql"))
            except ValueError as error:
                details.append(
                    f"{mapping.get('task_code', '')}: ไม่สามารถดึงข้อมูลได้ - {error}"
                )
                continue
            valid_mappings.append(mapping)
        if not valid_mappings:
            return (
                False,
                "ไม่มี Mapping ที่มี jhcis_extract_sql สำหรับดึงข้อมูล",
                details
            )

        total_jobs = len(valid_mappings) * len(hospitals)
        completed_jobs = 0
        success_jobs = 0
        total_rows = 0
        invalid_mapping_count = len(details)
        for mapping in valid_mappings:
            task_code = str(mapping.get("task_code", "")).strip()
            for hospital in hospitals:
                hospital_name = hospital.get("name", hospital.get("code", ""))
                self._queue_data_flow_status(
                    "jhcis_to_district",
                    f"กำลังดึง {task_code} จาก {hospital_name} "
                    f"({completed_jobs + 1}/{total_jobs})"
                )

                def report_progress(message, current, total):
                    self._queue_data_flow_status("jhcis_to_district", message)

                try:
                    result = sync_jhcis_to_district(
                        mapping,
                        hospital,
                        jhcis_default,
                        district_db,
                        batch_size=batch_size,
                        progress_callback=report_progress
                    )
                    success_jobs += 1
                    total_rows += result["count"]
                    status = (
                        f"JHCIS→อำเภอ {task_code}: สำเร็จ "
                        f"{result['count']} แถว"
                    )
                except Exception as error:
                    status = f"JHCIS→อำเภอ {task_code}: ล้มเหลว - {error}"
                    details.append(
                        f"{hospital_name} / {task_code}: {error}"
                    )
                    log_error(
                        f"[Data Flow] {hospital_name} / {task_code}: {error}"
                    )
                self._queue_hospital_flow_status(
                    str(hospital.get("code", "")), status
                )
                completed_jobs += 1

        summary = (
            f"JHCIS → ฐานอำเภอ: สำเร็จ {success_jobs}/{total_jobs} งาน, "
            f"รวม {total_rows} แถว"
        )
        if invalid_mapping_count:
            summary += f", Mapping ไม่พร้อม {invalid_mapping_count} รายการ"
        return (
            success_jobs == total_jobs and invalid_mapping_count == 0,
            summary,
            details
        )

    def _start_district_to_cloud(self):
        self._start_data_flow(
            "district_to_cloud",
            self._perform_district_to_cloud,
            "กำลังส่งข้อมูลจากฐานอำเภอไป Cloud DB..."
        )

    def _perform_district_to_cloud(self):
        saved_config = load_config()
        district_db = get_district_db_config(saved_config)
        config = {
            "district_db": district_db,
            "hostatom_db": dict(saved_config.get("hostatom_db", {})),
        }
        mappings = [
            row for row in get_sql_mappings(district_db)
            if bool(row.get("is_active"))
        ]
        if not mappings:
            raise ValueError("ไม่พบ Mapping ที่เปิดใช้งานใน sql_mapping")

        details = []
        success_jobs = 0
        total_rows = 0
        for index, mapping in enumerate(mappings, start=1):
            task_code = str(mapping.get("task_code", "")).strip()
            self._queue_data_flow_status(
                "district_to_cloud",
                f"กำลังส่ง {task_code} จากฐานอำเภอไป Cloud DB "
                f"({index}/{len(mappings)})"
            )

            def report_progress(message, current, total):
                self._queue_data_flow_status("district_to_cloud", message)

            try:
                result = run_sync_task(
                    mapping, config=config, progress_callback=report_progress
                )
                success_jobs += 1
                total_rows += result.get("count", 0)
                details.append(f"{task_code}: {result.get('message', 'สำเร็จ')}")
            except Exception as error:
                details.append(f"{task_code}: ล้มเหลว - {error}")
                log_error(f"[Data Flow] ฐานอำเภอ → Cloud DB / {task_code}: {error}")

        summary = (
            f"ฐานอำเภอ → Cloud DB: สำเร็จ {success_jobs}/{len(mappings)} งาน, "
            f"รวม {total_rows} แถว"
        )
        return success_jobs == len(mappings), summary, details

    def _do_auto_sync(self):
        try:
            self.root.after(0, lambda: self.status_var.set("กำลังซิงค์อัตโนมัติ..."))
            log_info("[Auto] เริ่มซิงค์อัตโนมัติ")

            jd = self.config.get("jhcis_default", {})
            hd = self.config.get("hostatom_db", {})
            hospitals = self.config.get("hospitals", [])
            selected_only = self.config.get("schedule", {}).get("target_mode", "selected") == "selected"
            batch_size = hd.get("batch_size", 500)
            if not hospitals:
                raise ValueError("ยังไม่มีรายชื่อ รพ.สต. ในระบบ")
            if selected_only and not any(
                hospital.get("selected", False) for hospital in hospitals
            ):
                raise ValueError("ไม่มี รพ.สต. ที่เลือกไว้สำหรับซิงค์อัตโนมัติ")

            results = sync_hospitals(hospitals, jd, hd, batch_size=batch_size, selected_only=selected_only)

            total_success = sum(1 for r in results if r["success"])
            total_count = sum(r["count"] for r in results if r["success"])

            for r in results:
                code = r["hospital"].get("code", "")
                vpn = "🟢 ออนไลน์" if r["success"] else "🔴 ออฟไลน์"
                self.root.after(0, lambda c=code, s=vpn, m=r["message"]: self._update_tree_status(c, s, m))

            msg_lines = [
                "📊 สรุปผลการซิงค์อัตโนมัติ",
                f"เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"จำนวน รพ.สต.: {len(results)} แห่ง",
                f"สำเร็จ: {total_success} แห่ง",
                f"จำนวนรายการที่อัปเดต: {total_count} รายการ",
            ]
            summary = "\n".join(msg_lines)
            log_info(f"[Auto] {summary}")

            self.root.after(0, lambda: self.status_var.set(f"ซิงค์อัตโนมัติเสร็จ: สำเร็จ {total_success}/{len(results)} แห่ง"))
            send_notification(self.config, summary, is_auto=True)

        except Exception as e:
            err = f"[Auto] เกิดข้อผิดพลาด: {str(e)}"
            log_error(err)
            self.root.after(0, lambda: self.status_var.set("ซิงค์อัตโนมัติล้มเหลว"))
        finally:
            self.sync_lock.release()

    # =====================================================================
    # Manual Sync
    # =====================================================================
    def _manual_sync(self):
        hospitals = self.config.get("hospitals", [])
        if not hospitals:
            messagebox.showwarning("คำเตือน", "ยังไม่มีรายชื่อ รพ.สต. ในระบบ")
            return
        if not any(hospital.get("selected", False) for hospital in hospitals):
            messagebox.showwarning(
                "ยังไม่ได้เลือก รพ.สต.",
                "กรุณาเลือก รพ.สต. อย่างน้อย 1 แห่งก่อนเริ่มซิงค์"
            )
            return
        if not self.sync_lock.acquire(blocking=False):
            messagebox.showwarning("คำเตือน", "มีการทำงานอยู่ในระบบ กรุณารอสักครู่")
            return

        self._set_sync_action_buttons(tk.DISABLED)
        self.status_var.set("กำลังดึงข้อมูลและส่งขึ้น HostAtom...")

        def _sync():
            try:
                jd = self.config.get("jhcis_default", {})
                hd = self.config.get("hostatom_db", {})
                hospitals = self.config.get("hospitals", [])
                batch_size = hd.get("batch_size", 500)

                if not hospitals:
                    self.root.after(0, lambda: messagebox.showwarning("คำเตือน", "ยังไม่มีรายชื่อ รพ.สต. ในระบบ"))
                    return

                results = sync_hospitals(hospitals, jd, hd, batch_size=batch_size, selected_only=True)

                total_success = sum(1 for r in results if r["success"])
                total_count = sum(r["count"] for r in results if r["success"])
                total_hospitals = len(results)

                for r in results:
                    code = r["hospital"].get("code", "")
                    vpn = "🟢 ออนไลน์" if r["success"] else "🔴 ออฟไลน์"
                    self.root.after(0, lambda c=code, s=vpn, m=r["message"]: self._update_tree_status(c, s, m))

                self.root.after(0, lambda: self._manual_sync_finished(total_success, total_hospitals, total_count, results))

                notif_cfg = self.config.get("notification", {})
                msg_lines = [
                    "📊 สรุปผลการซิงค์แบบ Manual",
                    f"เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"จำนวน รพ.สต.: {total_hospitals} แห่ง",
                    f"สำเร็จ: {total_success} แห่ง",
                    f"จำนวนรายการที่อัปเดต: {total_count} รายการ",
                ]
                send_notification(self.config, "\n".join(msg_lines), is_auto=False)

            except Exception as e:
                err = f"เกิดข้อผิดพลาดในการซิงค์: {str(e)}"
                log_error(err)
                self.root.after(0, lambda: messagebox.showerror("ผิดพลาด", err))
                self.root.after(0, lambda: self.status_var.set("ซิงค์ล้มเหลว"))
            finally:
                self.root.after(
                    0, lambda: self._set_sync_action_buttons(tk.NORMAL)
                )
                self.sync_lock.release()

        try:
            threading.Thread(target=_sync, daemon=True).start()
        except RuntimeError as error:
            self.sync_lock.release()
            self._set_sync_action_buttons(tk.NORMAL)
            self.status_var.set("เริ่มซิงค์ Manual ไม่สำเร็จ")
            log_error(f"เริ่มเธรด Manual Sync ไม่สำเร็จ: {error}")
            messagebox.showerror(
                "เริ่มซิงค์ไม่สำเร็จ", str(error), parent=self.root
            )

    def _manual_sync_finished(self, total_success, total_hospitals, total_count, results):
        self.status_var.set(f"ซิงค์ Manual เสร็จ: สำเร็จ {total_success}/{total_hospitals} แห่ง")
        detail_lines = [f"• {r['hospital'].get('name', '')} ({r['hospital'].get('code', '')}): {r['message']}" for r in results]
        detail = "\n".join(detail_lines)
        msg = (f"ซิงค์ข้อมูล Person เรียบร้อยแล้ว\n\n"
               f"จำนวน รพ.สต.: {total_hospitals} แห่ง\n"
               f"สำเร็จ: {total_success} แห่ง\n"
               f"จำนวนรายการที่อัปเดต: {total_count} รายการ\n\n"
               f"รายละเอียด:\n{detail}")
        messagebox.showinfo("ผลการซิงค์ (Manual)", msg)

    # =====================================================================
    # ปิดโปรแกรม
    # =====================================================================
    def _on_closing(self):
        if self.sync_lock.locked():
            messagebox.showwarning(
                "กำลังซิงค์",
                "มีงานซิงค์กำลังทำงานอยู่ กรุณารอให้เสร็จก่อนปิดโปรแกรม"
            )
            return
        if self.district_sync_window is not None:
            self.district_sync_window.shutdown()
        self._stop_scheduler()
        self._cancel_database_status_refresh()
        for job in (self.vpn_blink_job,):
            if job is not None:
                self.root.after_cancel(job)
        self.root.destroy()


def main():
    root = ctk.CTk()
    setup_default_fonts(root)
    app = JHCISPersonSyncApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()