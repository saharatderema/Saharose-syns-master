#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""District data-sync window embedded in the legacy application."""

import copy
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk
import schedule

import notifier
import sync_engine

# Import UI Theme System
from ui_theme import (
    init_theme, Colors, FONTS, Spacing, VSpacing, Icons, ctk_widgets as ttk,
    create_card, create_section, create_card_section,
    create_primary_button, create_secondary_button, create_ghost_button,
    create_danger_button, create_success_button, create_warning_button,
    create_small_button, create_large_button,
    create_heading_label, create_title_label, create_muted_label, create_caption_label,
    create_status_label, create_treeview, create_progressbar,
    add_tooltip, center_window
)


class DistrictSyncWindow:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.win = ctk.CTkToplevel(self.root)
        self.win.title(f"SAHARose Sync Master v{self.app.config.get('app_version', '1.0.0')} - District Dynamic Data Sync Manager")
        minimum_width = min(1000, max(320, self.win.winfo_screenwidth() - 40))
        minimum_height = min(650, max(240, self.win.winfo_screenheight() - 60))
        self.win.minsize(minimum_width, minimum_height)
        center_window(self.win, 1280, 820)
        self.win.transient(self.root)
        self.win.protocol("WM_DELETE_WINDOW", self.hide)

        self.mapping_rows = []
        self.selected_mapping_ids = set()
        self.latest_status = {}
        self.has_loaded_mappings = False
        self.sync_lock = app.sync_lock
        self.shutdown_requested = False
        self.scheduler_thread = None
        self.scheduler_stop = threading.Event()

        self._setup_ui()
        self._refresh_mappings()
        if self.config.get("district_sync_schedule", {}).get("enabled", False):
            try:
                self._restart_scheduler()
            except (ValueError, schedule.ScheduleValueError) as error:
                self._append_log(f"เปิด District Auto-Scheduler ไม่สำเร็จ: {error}")
                messagebox.showerror("ตั้งเวลาไม่ถูกต้อง", str(error), parent=self.win)

    @property
    def config(self):
        return self.app.config

    def exists(self):
        return bool(self.win.winfo_exists())

    def show(self):
        if self.exists():
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()

    def hide(self):
        if self.exists():
            self.win.withdraw()

    def is_syncing(self):
        return self.sync_lock.locked()

    def shutdown(self):
        self.shutdown_requested = True
        self.scheduler_stop.set()
        if self.exists():
            self.win.destroy()

    def _post(self, callback, *args):
        if self.shutdown_requested or not self.exists():
            return
        try:
            self.win.after(0, lambda: callback(*args))
        except tk.TclError:
            return

    def _setup_ui(self):
        # Use theme from main app
        self.theme = self.app.theme
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(2, weight=3)
        self.win.rowconfigure(4, weight=2)

        status = create_card_section(self.win, title=f"{Icons.DATABASE} สถานะการเชื่อมต่อ", padding=Spacing.MD)
        status.grid(row=0, column=0, sticky=tk.EW, padx=Spacing.MD, pady=(VSpacing.MD, VSpacing.SM))
        self.district_status_var = tk.StringVar(value="MySQL อำเภอ: ยังไม่ได้ทดสอบ")
        self.hostatom_status_var = tk.StringVar(value="Cloud DB Port 3306: ยังไม่ได้ทดสอบ")
        create_muted_label(status, textvariable=self.district_status_var).pack(side=tk.LEFT, padx=Spacing.SM)
        create_muted_label(status, textvariable=self.hostatom_status_var).pack(side=tk.LEFT, padx=Spacing.MD)
        create_ghost_button(status, text=f"{Icons.SETTINGS} ตั้งค่าฐานข้อมูล", command=self._open_db_settings).pack(side=tk.RIGHT, padx=Spacing.SM)
        self.btn_test_connections = create_primary_button(status, text=f"{Icons.VPN} ทดสอบเชื่อมต่อ", command=self._test_connections)
        self.btn_test_connections.pack(side=tk.RIGHT, padx=Spacing.SM)

        controls = create_card_section(self.win, title=f"{Icons.PIPELINE} ควบคุมการซิงค์", padding=Spacing.MD)
        controls.grid(row=1, column=0, sticky=tk.EW, padx=Spacing.MD, pady=VSpacing.SM)
        self.btn_manual_sync = create_primary_button(
            controls,
            text="🚀 เริ่มซิงค์ข้อมูลที่เลือก (Manual)",
            command=lambda: self._start_sync(is_auto=False)
        )
        self.btn_manual_sync.pack(side=tk.LEFT, padx=3)
        ttk.Button(controls, text="🔄 รีเฟรชรายการ Mapping", command=self._refresh_mappings).pack(side=tk.LEFT, padx=3)
        ttk.Button(controls, text="🛠️ จัดการ SQL Mapping", command=self._open_mapping_manager).pack(side=tk.LEFT, padx=3)
        create_ghost_button(controls, text=f"{Icons.SCHEDULE} ตั้งค่า Auto-Schedule", command=self._open_schedule_settings).pack(side=tk.LEFT, padx=Spacing.SM)
        create_ghost_button(controls, text=f"{Icons.BELL} ตั้งค่าแจ้งเตือน", command=self.app._open_notification_settings).pack(side=tk.LEFT, padx=Spacing.SM)
        self.schedule_status_var = tk.StringVar(value="Auto-Schedule: ปิด")
        create_muted_label(controls, textvariable=self.schedule_status_var).pack(side=tk.RIGHT, padx=Spacing.MD)

        table_frame = create_card_section(self.win, title=f"{Icons.TABLE} รายการซิงค์จาก sql_mapping", padding=Spacing.MD)
        table_frame.grid(row=2, column=0, sticky=tk.NSEW, padx=Spacing.MD, pady=VSpacing.SM)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        columns = (
            "select", "task_code", "task_name", "local_source_table",
            "host_staging_table", "host_procedure_name", "status"
        )
        self.mapping_tree = create_treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        headings = (
            ("select", f"{Icons.CHECK} เลือก", 55, "center"),
            ("task_code", f"{Icons.MAPPING} รหัสงาน", 100, "center"),
            ("task_name", f"{Icons.LIST} ชื่อข้อมูล", 210, "w"),
            ("local_source_table", f"{Icons.DATABASE} ตารางอำเภอ", 150, "center"),
            ("host_staging_table", f"{Icons.CLOUD} ตารางพัก Host", 160, "center"),
            ("host_procedure_name", f"{Icons.CONFIG} Procedure ตารางจริง", 190, "center"),
            ("status", f"{Icons.INFO} สถานะล่าสุด", 280, "w"),
        )
        for column, title, width, anchor in headings:
            if column == "select":
                self.mapping_tree.heading(column, text=title, command=self._toggle_all_selection)
            else:
                self.mapping_tree.heading(column, text=title)
            self.mapping_tree.column(column, width=width, anchor=anchor)
        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.mapping_tree.yview)
        self.mapping_tree.configure(yscrollcommand=y_scroll.set)
        self.mapping_tree.grid(row=0, column=0, sticky=tk.NSEW)
        y_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.mapping_tree.bind("<Button-1>", self._on_tree_click)
        self.mapping_tree.bind("<Double-1>", lambda event: self._open_mapping_manager())

        progress_frame = create_card_section(self.win, title=f"{Icons.CHART} Progress", padding=Spacing.MD)
        progress_frame.grid(row=3, column=0, sticky=tk.EW, padx=Spacing.MD, pady=VSpacing.SM)
        progress_frame.columnconfigure(0, weight=1)
        self.progress_value = tk.DoubleVar(value=0)
        self.progressbar = create_progressbar(
            progress_frame, variable=self.progress_value, maximum=100, mode="determinate"
        )
        self.progressbar.grid(row=0, column=0, sticky=tk.EW, padx=(0, Spacing.SM))
        self.progress_text_var = tk.StringVar(value="พร้อมทำงาน")
        create_muted_label(progress_frame, textvariable=self.progress_text_var, width=55).grid(
            row=0, column=1, sticky=tk.E
        )

        log_frame = create_card_section(self.win, title=f"{Icons.LOG} Progress & Live Log", padding=Spacing.MD)
        log_frame.grid(row=4, column=0, sticky=tk.NSEW, padx=Spacing.MD, pady=(VSpacing.SM, VSpacing.MD))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.live_log = ttk.Text(
            log_frame, height=10, wrap=tk.WORD, font=FONTS["MONO"], state=tk.DISABLED
        )
        self.live_log.grid(row=0, column=0, sticky=tk.NSEW)
        self._append_log("District Sync พร้อมทำงาน")

    def _append_log(self, message):
        if not self.exists():
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.live_log.configure(state=tk.NORMAL)
        self.live_log.insert(tk.END, f"{timestamp} {message}\n")
        self.live_log.see(tk.END)
        self.live_log.configure(state=tk.DISABLED)

    def _refresh_mappings(self):
        self.btn_manual_sync.configure(state=tk.DISABLED)
        self.progress_text_var.set("กำลังโหลดรายการ sql_mapping...")
        district_config = copy.deepcopy(self.config.get("district_db", {}))

        def worker():
            try:
                mappings = sync_engine.get_sql_mappings(district_config)
                self._post(self._finish_mapping_refresh, mappings, None)
            except Exception as error:
                sync_engine.log_error(f"โหลด sql_mapping ไม่สำเร็จ: {error}")
                self._post(self._finish_mapping_refresh, None, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_mapping_refresh(self, mappings, error):
        self.btn_manual_sync.configure(state=tk.NORMAL)
        if error:
            self.district_status_var.set("MySQL อำเภอ: โหลด sql_mapping ไม่สำเร็จ")
            self.progress_text_var.set("โหลด Mapping ไม่สำเร็จ")
            self._append_log(f"โหลด sql_mapping ไม่สำเร็จ: {error}")
            return

        previous_selection = self.selected_mapping_ids
        self.mapping_rows = mappings
        active_ids = {
            int(row["id"]) for row in mappings
            if bool(row.get("is_active", False))
        }
        if not self.has_loaded_mappings:
            self.selected_mapping_ids = active_ids
            self.has_loaded_mappings = True
        else:
            self.selected_mapping_ids = previous_selection & active_ids
        self.district_status_var.set("MySQL อำเภอ: โหลด Mapping สำเร็จ")
        self.progress_text_var.set(f"โหลด Mapping แล้ว {len(mappings)} งาน")
        self._render_mappings()
        self._append_log(f"โหลด sql_mapping สำเร็จ {len(mappings)} งาน")

    def _render_mappings(self):
        for item in self.mapping_tree.get_children():
            self.mapping_tree.delete(item)
        for row in self.mapping_rows:
            mapping_id = int(row["id"])
            active = bool(row.get("is_active", False))
            checked = active and mapping_id in self.selected_mapping_ids
            self.mapping_tree.insert(
                "",
                tk.END,
                iid=str(mapping_id),
                values=(
                    "✓" if checked else "✗",
                    row.get("task_code", ""),
                    row.get("task_name", ""),
                    row.get("local_source_table", ""),
                    row.get("host_staging_table", ""),
                    row.get("host_procedure_name", ""),
                    self.latest_status.get(mapping_id, "พร้อมซิงค์" if active else "ปิดใช้งาน"),
                ),
                tags=("inactive",) if not active else ()
            )
        self.mapping_tree.tag_configure("inactive", foreground="#888888")

    def _on_tree_click(self, event):
        if self.mapping_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.mapping_tree.identify_column(event.x) != "#1":
            return
        item = self.mapping_tree.identify_row(event.y)
        if not item:
            return
        mapping_id = int(item)
        row = next((candidate for candidate in self.mapping_rows if int(candidate["id"]) == mapping_id), None)
        if row is None or not bool(row.get("is_active", False)):
            return "break"
        if mapping_id in self.selected_mapping_ids:
            self.selected_mapping_ids.remove(mapping_id)
        else:
            self.selected_mapping_ids.add(mapping_id)
        self._render_mappings()
        return "break"

    def _toggle_all_selection(self):
        active_ids = {
            int(row["id"]) for row in self.mapping_rows
            if bool(row.get("is_active", False))
        }
        if active_ids and active_ids.issubset(self.selected_mapping_ids):
            self.selected_mapping_ids.difference_update(active_ids)
        else:
            self.selected_mapping_ids.update(active_ids)
        self._render_mappings()

    def _test_connections(self):
        self.btn_test_connections.configure(state=tk.DISABLED)
        try:
            config = sync_engine.load_config()
            district_config = sync_engine.get_district_db_config(config)
            hostatom_config = dict(config.get("hostatom_db", {}))
        except (TypeError, ValueError) as error:
            self.btn_test_connections.configure(state=tk.NORMAL)
            self.district_status_var.set("MySQL อำเภอ: ค่าตั้งค่าไม่ถูกต้อง")
            self.hostatom_status_var.set("Cloud DB: ค่าตั้งค่าไม่ถูกต้อง")
            self._append_log(f"อ่าน config.json สำหรับทดสอบการเชื่อมต่อไม่สำเร็จ: {error}")
            return

        def worker():
            district_result = sync_engine.test_district_connection(district_config)
            hostatom_result = sync_engine.test_district_sync_hostatom_connection(hostatom_config)
            self._post(self._finish_connection_test, district_result, hostatom_result)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_connection_test(self, district_result, hostatom_result):
        self.btn_test_connections.configure(state=tk.NORMAL)
        district_ok, district_message = district_result
        hostatom_ok, hostatom_message = hostatom_result
        self.district_status_var.set(
            f"MySQL อำเภอ: {'เชื่อมต่อสำเร็จ' if district_ok else 'เชื่อมต่อไม่สำเร็จ'}"
        )
        self.hostatom_status_var.set(
            f"Cloud DB Port 3306: {'เชื่อมต่อสำเร็จ' if hostatom_ok else 'เชื่อมต่อไม่สำเร็จ'}"
        )
        self._append_log(f"MySQL อำเภอ: {district_message}")
        self._append_log(f"HostAtom: {hostatom_message}")

    def _open_db_settings(self):
        win = ctk.CTkToplevel(self.win)
        win.title("ตั้งค่าฐานข้อมูล District Sync")
        win.geometry("520x520")
        win.transient(self.win)
        win.grab_set()
        notebook = ctk.CTkTabview(win, corner_radius=12)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        fields = {}

        for key, title in (
            ("district_db", "MySQL อำเภอ"),
            ("hostatom_db", "Cloud DB (HostAtom Remote MySQL)"),
        ):
            frame = notebook.add(title)
            current = self.config.get(key, {})
            field_values = (
                ("host", "Host", current.get("host", "")),
                (
                    "port",
                    "Port",
                    current.get("port", "" if key == "district_db" else 3306),
                ),
                ("database", "Database", current.get("database", "")),
                ("user", "User", current.get("user", "")),
                ("password", "Password", current.get("password", "")),
            )
            fields[key] = {}
            for row, (name, label, value) in enumerate(field_values):
                ttk.Label(frame, text=label).grid(row=row, column=0, sticky=tk.W, padx=4, pady=2)
                entry = ttk.Entry(frame, show="*" if name == "password" else "")
                entry.insert(0, str(value))
                entry.grid(
                    row=row, column=1, sticky=tk.EW, padx=4, pady=2,
                    ipady=Spacing.XXS
                )
                fields[key][name] = entry
            if key == "hostatom_db":
                ttk.Label(frame, text="Batch Size").grid(row=5, column=0, sticky=tk.W, padx=4, pady=2)
                batch_entry = ttk.Entry(frame)
                batch_entry.insert(0, str(current.get("batch_size", 500)))
                batch_entry.grid(
                    row=5, column=1, sticky=tk.EW, padx=4, pady=2,
                    ipady=Spacing.XXS
                )
                fields[key]["batch_size"] = batch_entry
            frame.columnconfigure(1, weight=1)

        def save_settings():
            try:
                district = {name: widget.get().strip() for name, widget in fields["district_db"].items()}
                hostatom = {name: widget.get().strip() for name, widget in fields["hostatom_db"].items()}
                district["port"] = int(district["port"])
                hostatom["port"] = int(hostatom["port"] or 3306)
                hostatom["batch_size"] = int(hostatom["batch_size"] or 500)
                if not 1 <= district["port"] <= 65535 or not 1 <= hostatom["port"] <= 65535:
                    raise ValueError("Port ต้องอยู่ระหว่าง 1 ถึง 65535")
                if hostatom["batch_size"] <= 0:
                    raise ValueError("Batch Size ต้องมากกว่า 0")
            except ValueError as error:
                messagebox.showerror("ค่าตั้งค่าไม่ถูกต้อง", str(error), parent=win)
                return

            updated = copy.deepcopy(self.config)
            updated["district_db"] = district
            updated["hostatom_db"] = hostatom
            if not sync_engine.save_config(updated):
                messagebox.showerror("บันทึกไม่สำเร็จ", "ไม่สามารถบันทึก config.json ได้", parent=win)
                return
            self.app.config.clear()
            self.app.config.update(updated)
            self.app._refresh_database_settings_fields()
            self.app.toast_manager.show("บันทึกการตั้งค่าฐานข้อมูลแล้ว", "success")
            win.destroy()
            self._refresh_mappings()

        buttons = ttk.Frame(win)
        buttons.pack(fill=tk.X, padx=Spacing.MD, pady=(0, VSpacing.MD))
        create_primary_button(buttons, text=f"{Icons.SAVE} บันทึก", command=save_settings).pack(side=tk.LEFT, padx=Spacing.SM)
        create_ghost_button(buttons, text=f"{Icons.CLOSE} ปิด", command=win.destroy).pack(side=tk.RIGHT, padx=Spacing.SM)
        win.wait_window(win)

    def _open_mapping_manager(self):
        win = ctk.CTkToplevel(self.win)
        win.title("จัดการ SQL Mapping")
        win.geometry("1080x760")
        win.transient(self.win)
        win.grab_set()

        list_frame = create_card_section(win, title=f"{Icons.TABLE} รายการ Mapping ใน sql_mapping", padding=Spacing.MD)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=Spacing.MD, pady=(VSpacing.MD, VSpacing.SM))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        columns = ("code", "name", "source", "staging", "procedure", "active")
        tree = create_treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        for column, title, width in (
            ("code", f"{Icons.MAPPING} รหัสงาน", 100),
            ("name", f"{Icons.LIST} ชื่อข้อมูล", 200),
            ("source", f"{Icons.DATABASE} ตารางอำเภอ", 150),
            ("staging", f"{Icons.CLOUD} ตารางพัก", 150),
            ("procedure", f"{Icons.CONFIG} Procedure", 180),
            ("active", f"{Icons.CHECK} ใช้งาน", 70),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=width)
        tree.grid(row=0, column=0, sticky=tk.NSEW)
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=list_scroll.set)
        list_scroll.grid(row=0, column=1, sticky=tk.NS)

        form = create_card_section(win, title=f"{Icons.EDIT} เพิ่ม / แก้ไข Mapping", padding=Spacing.MD)
        form.pack(fill=tk.BOTH, expand=True, padx=Spacing.MD, pady=VSpacing.SM)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        entry_defs = (
            ("task_code", f"{Icons.MAPPING} รหัสงาน", 0, 0),
            ("task_name", f"{Icons.LIST} ชื่อข้อมูล", 0, 2),
            ("local_source_table", f"{Icons.DATABASE} ตารางอำเภอ", 1, 0),
            ("host_staging_table", f"{Icons.CLOUD} ตารางพัก Host", 1, 2),
            ("host_procedure_name", f"{Icons.CONFIG} Procedure", 2, 0),
            ("sort_order", f"{Icons.INFO} ลำดับ", 2, 2),
        )
        entries = {}
        for key, label, row, column in entry_defs:
            create_muted_label(form, text=label).grid(row=row, column=column, sticky=tk.W, padx=Spacing.SM, pady=VSpacing.SM)
            entry = ttk.Entry(form)
            entry.grid(
                row=row, column=column + 1, sticky=tk.EW,
                padx=Spacing.SM, pady=VSpacing.SM, ipady=Spacing.XXS
            )
            entries[key] = entry
        active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text=f"{Icons.CHECK} เปิดใช้งาน", variable=active_var).grid(
            row=2, column=4, sticky=tk.W, padx=Spacing.SM, pady=VSpacing.SM
        )
        create_muted_label(
            form,
            text="SQL SELECT จาก JHCIS (jhcis_extract_sql; ตั้งชื่อคอลัมน์ให้ตรงกับ district_table)"
        ).grid(
            row=3, column=0, columnspan=5, sticky=tk.W, padx=Spacing.SM, pady=(VSpacing.MD, VSpacing.XS)
        )
        sql_text = ttk.Text(form, height=7, wrap=tk.NONE, font=FONTS["MONO"])
        sql_text.grid(row=4, column=0, columnspan=5, sticky=tk.NSEW, padx=Spacing.SM, pady=VSpacing.SM)
        sql_text.edit_modified(False)
        form.rowconfigure(4, weight=1)
        selected_id = {"value": None}
        status_var = tk.StringVar(value="")
        tested_sql = {"value": None}
        create_muted_label(form, textvariable=status_var, anchor=tk.W).grid(
            row=5, column=0, columnspan=5, sticky=tk.EW, padx=Spacing.SM, pady=VSpacing.SM
        )

        def clear_test_status(event):
            event.widget.edit_modified(False)
            if (
                tested_sql["value"] is not None
                and sql_text.get("1.0", "end-1c") != tested_sql["value"]
            ):
                tested_sql["value"] = None
                status_var.set("")

        sql_text.bind("<<Modified>>", clear_test_status)

        def clear_form():
            selected_id["value"] = None
            tested_sql["value"] = None
            status_var.set("")
            for widget in entries.values():
                widget.delete(0, tk.END)
            entries["local_source_table"].insert(0, "org_person")
            entries["host_staging_table"].insert(0, "store_person")
            entries["host_procedure_name"].insert(0, "sp_merge_person")
            entries["sort_order"].insert(0, "0")
            active_var.set(True)
            sql_text.delete("1.0", tk.END)
            sql_text.edit_modified(False)

        def load_selected(event=None):
            selected = tree.selection()
            if not selected:
                return
            mapping_id = int(selected[0])
            row = next((item for item in self.mapping_rows if int(item["id"]) == mapping_id), None)
            if row is None:
                return
            selected_id["value"] = mapping_id
            for key, widget in entries.items():
                widget.delete(0, tk.END)
                widget.insert(0, str(row.get(key, "")))
            active_var.set(bool(row.get("is_active", False)))
            sql_text.delete("1.0", tk.END)
            sql_text.insert("1.0", row.get("jhcis_extract_sql") or "")
            sql_text.edit_modified(False)
            tested_sql["value"] = None
            status_var.set("")

        def populate_tree(rows, focus_id=None):
            for item in tree.get_children():
                tree.delete(item)
            for row in rows:
                mapping_id = int(row["id"])
                tree.insert(
                    "",
                    tk.END,
                    iid=str(mapping_id),
                    values=(
                        row.get("task_code", ""),
                        row.get("task_name", ""),
                        row.get("local_source_table", ""),
                        row.get("host_staging_table", ""),
                        row.get("host_procedure_name", ""),
                        "ใช้งาน" if row.get("is_active") else "ปิด",
                    )
                )
            if focus_id is not None and str(focus_id) in tree.get_children():
                tree.selection_set(str(focus_id))
                tree.focus(str(focus_id))
                load_selected()

        def sync_main_rows(rows):
            self._finish_mapping_refresh(rows, None)
            populate_tree(rows)

        def save_mapping():
            try:
                mapping = {
                    "id": selected_id["value"],
                    "task_code": entries["task_code"].get().strip(),
                    "task_name": entries["task_name"].get().strip(),
                    "jhcis_extract_sql": sql_text.get("1.0", "end-1c").strip() or None,
                    "local_source_table": entries["local_source_table"].get().strip(),
                    "host_staging_table": entries["host_staging_table"].get().strip(),
                    "host_procedure_name": entries["host_procedure_name"].get().strip(),
                    "is_active": active_var.get(),
                    "sort_order": int(entries["sort_order"].get().strip() or 0),
                }
                if not mapping["task_code"] or not mapping["task_name"]:
                    raise ValueError("กรุณากรอกรหัสงานและชื่อข้อมูล")
            except ValueError as error:
                messagebox.showerror("ข้อมูลไม่ถูกต้อง", str(error), parent=win)
                return

            save_button.configure(state=tk.DISABLED)
            district_config = copy.deepcopy(self.config.get("district_db", {}))

            def on_save_complete(rows, error, task_code, mapping_id):
                if not win.winfo_exists():
                    return
                save_button.configure(state=tk.NORMAL)
                if error:
                    messagebox.showerror("บันทึก Mapping ไม่สำเร็จ", error, parent=win)
                    return
                sync_main_rows(rows)
                self.app.toast_manager.show(
                    f"บันทึก Mapping {task_code} แล้ว", "success"
                )
                populate_tree(rows, mapping_id)

            def worker():
                try:
                    sync_engine.save_sql_mapping(district_config, mapping)
                    rows = sync_engine.get_sql_mappings(district_config)
                    self._post(
                        on_save_complete, rows, None,
                        mapping["task_code"], mapping.get("id")
                    )
                except Exception as error:
                    sync_engine.log_error(f"บันทึก SQL Mapping ไม่สำเร็จ: {error}")
                    self._post(on_save_complete, None, str(error), mapping["task_code"], mapping.get("id"))

            threading.Thread(target=worker, daemon=True).start()

        def delete_mapping():
            mapping_id = selected_id["value"]
            if mapping_id is None:
                messagebox.showwarning("คำเตือน", "กรุณาเลือกรายการที่จะลบ", parent=win)
                return
            if not messagebox.askyesno("ยืนยัน", "ลบ Mapping ที่เลือกหรือไม่?", parent=win):
                return
            delete_button.configure(state=tk.DISABLED)
            district_config = copy.deepcopy(self.config.get("district_db", {}))

            def on_delete_complete(rows, error):
                if not win.winfo_exists():
                    return
                delete_button.configure(state=tk.NORMAL)
                if error:
                    messagebox.showerror("ลบ Mapping ไม่สำเร็จ", error, parent=win)
                    return
                selected_id["value"] = None
                clear_form()
                sync_main_rows(rows)
                populate_tree(rows)

            def worker():
                try:
                    sync_engine.delete_sql_mapping(district_config, mapping_id)
                    rows = sync_engine.get_sql_mappings(district_config)
                    self._post(on_delete_complete, rows, None)
                except Exception as error:
                    sync_engine.log_error(f"ลบ SQL Mapping ไม่สำเร็จ: {error}")
                    self._post(on_delete_complete, None, str(error))

            threading.Thread(target=worker, daemon=True).start()

        tree.bind("<<TreeviewSelect>>", load_selected)
        buttons = ttk.Frame(win)
        buttons.pack(fill=tk.X, padx=Spacing.MD, pady=(0, VSpacing.MD))
        create_ghost_button(
            buttons,
            text=f"{Icons.COPY} Copy Mapping",
            command=lambda: copy_mapping_sql()
        ).pack(side=tk.LEFT, padx=Spacing.SM)
        test_button = create_secondary_button(
            buttons,
            text=f"{Icons.PLAY} ทดสอบ Mapping",
            command=lambda: test_mapping_sql()
        )
        test_button.pack(side=tk.LEFT, padx=Spacing.SM)
        create_secondary_button(
            buttons, text=f"{Icons.ADD} รายการใหม่", command=clear_form
        ).pack(side=tk.LEFT, padx=Spacing.SM)
        save_button = create_primary_button(
            buttons, text=f"{Icons.SAVE} บันทึก Mapping", command=save_mapping
        )
        save_button.pack(side=tk.LEFT, padx=Spacing.SM)
        delete_button = create_danger_button(
            buttons, text=f"{Icons.DELETE} ลบ Mapping", command=delete_mapping
        )
        delete_button.pack(side=tk.LEFT, padx=Spacing.SM)
        create_ghost_button(
            buttons, text=f"{Icons.CLOSE} ปิด", command=win.destroy
        ).pack(side=tk.RIGHT, padx=Spacing.SM)

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
                sync_engine.log_error(f"คัดลอก SQL Mapping ไม่สำเร็จ: {error}")
                messagebox.showerror("คัดลอกไม่สำเร็จ", str(error), parent=win)
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
                sync_engine.log_error(
                    f"ทดสอบ SQL Mapping {entries['task_code'].get().strip()} "
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
                sync_engine.validate_read_only_select(query)
            except ValueError as error:
                tested_sql["value"] = query
                status_var.set("Status: ERROR - SQL ไม่ถูกต้อง")
                sync_engine.log_error(
                    f"ทดสอบ SQL Mapping {entries['task_code'].get().strip()} "
                    f"ไม่ผ่านการตรวจสอบ: {error}"
                )
                return

            hospitals = self.config.get("hospitals", [])
            hospital = next(
                (dict(item) for item in hospitals if item.get("selected", False)),
                None
            )
            if hospital is None and hospitals:
                hospital = dict(hospitals[0])
            if hospital is None:
                tested_sql["value"] = query
                status_var.set("Status: ERROR - ไม่มี รพ.สต. สำหรับทดสอบ")
                return

            jhcis_default = dict(self.config.get("jhcis_default", {}))
            test_button.configure(state=tk.DISABLED)
            sql_text.configure(state=tk.DISABLED)
            status_var.set("กำลังทดสอบ SQL บน JHCIS...")

            def worker():
                try:
                    sync_engine.preview_person_sql(
                        hospital, jhcis_default, query, max_rows=1
                    )
                    error = None
                except Exception as caught_error:
                    error = caught_error
                self._post(finish_mapping_test, hospital, query, error)

            try:
                threading.Thread(target=worker, daemon=True).start()
            except RuntimeError as error:
                test_button.configure(state=tk.NORMAL)
                sql_text.configure(state=tk.NORMAL)
                tested_sql["value"] = query
                status_var.set("Status: ERROR - เริ่มการทดสอบไม่สำเร็จ")
                sync_engine.log_error(f"เริ่มทดสอบ SQL Mapping ไม่สำเร็จ: {error}")

        populate_tree(self.mapping_rows)
        clear_form()
        win.wait_window(win)

    def _start_sync(self, is_auto):
        if self.sync_lock.locked():
            message = "มี District Sync ทำงานอยู่แล้ว"
            self._append_log(message)
            if not is_auto:
                messagebox.showwarning("กำลังซิงค์", message, parent=self.win)
            return

        if is_auto:
            tasks = [row for row in self.mapping_rows if bool(row.get("is_active", False))]
        else:
            tasks = [
                row for row in self.mapping_rows
                if int(row["id"]) in self.selected_mapping_ids and bool(row.get("is_active", False))
            ]
        if not tasks:
            message = "ไม่มีงาน Mapping ที่เลือกและเปิดใช้งาน"
            self._append_log(message)
            if not is_auto:
                messagebox.showwarning("ไม่มีรายการซิงค์", message, parent=self.win)
            return
        if not self.sync_lock.acquire(blocking=False):
            return

        self.btn_manual_sync.configure(state=tk.DISABLED)
        self.progress_value.set(0)
        self.progress_text_var.set("กำลังเริ่มซิงค์...")
        try:
            config_snapshot = sync_engine.load_config()
            config_snapshot["district_db"] = sync_engine.get_district_db_config(
                config_snapshot
            )
        except (TypeError, ValueError) as error:
            self.sync_lock.release()
            self.btn_manual_sync.configure(state=tk.NORMAL)
            self.progress_text_var.set("อ่านการตั้งค่า MySQL อำเภอไม่สำเร็จ")
            self._append_log(f"เริ่มซิงค์ไม่ได้: {error}")
            messagebox.showerror(
                "อ่านการตั้งค่าไม่สำเร็จ",
                "ไม่สามารถอ่านการตั้งค่า district_db จาก config.json ได้",
                parent=self.win
            )
            return
        config_snapshot = copy.deepcopy(config_snapshot)
        threading.Thread(
            target=self._sync_worker,
            args=(tasks, config_snapshot, is_auto),
            daemon=True
        ).start()

    def _sync_worker(self, tasks, config_snapshot, is_auto):
        results = []
        try:
            for task in tasks:
                mapping_id = int(task["id"])
                self._post(self._update_task_status, mapping_id, "กำลังซิงค์")
                self._post(self._append_log, f"เริ่มงาน {task['task_code']} - {task['task_name']}")
                try:
                    result = sync_engine.run_sync_task(
                        task,
                        config_snapshot,
                        progress_callback=lambda message, current, total: self._post(
                            self._update_progress, message, current, total
                        )
                    )
                except Exception as error:
                    result = {
                        "success": False,
                        "task_code": task.get("task_code", ""),
                        "count": 0,
                        "message": str(error),
                    }
                results.append(result)
                self._post(
                    self._update_task_status,
                    mapping_id,
                    f"{'สำเร็จ' if result['success'] else 'ผิดพลาด'}: {result['message']}"
                )

            summary = self._format_summary(results, is_auto)
            if is_auto:
                notification_config = copy.deepcopy(config_snapshot)
                notification_config["schedule"] = config_snapshot.get(
                    "district_sync_schedule", {}
                )
                notifier.send_notification(notification_config, summary, is_auto=True)
                notification_status = (
                    "ส่งสรุป Auto-Sync ตามช่องทางที่ตั้งค่าไว้แล้ว"
                    if notification_config["schedule"].get("notify_on_auto", False)
                    else "ข้ามการแจ้งเตือน Auto-Sync ตามการตั้งค่า"
                )
                self._post(self._append_log, notification_status)
        except Exception as error:
            sync_engine.log_error(f"District Sync ผิดพลาด: {error}")
            self._post(self._append_log, f"District Sync ผิดพลาด: {error}")
        finally:
            self.sync_lock.release()
            self._post(self._finish_sync, results, is_auto)

    def _format_summary(self, results, is_auto):
        success_count = sum(1 for result in results if result["success"])
        uploaded_count = sum(result["count"] for result in results if result["success"])
        mode = "อัตโนมัติ" if is_auto else "Manual"
        lines = [
            f"SAHARose Sync Master v{self.app.config.get('app_version', '1.0.0')} - สรุปผล District Sync {mode}",
            f"เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"งานทั้งหมด: {len(results)}",
            f"สำเร็จ: {success_count}",
            f"จำนวนแถวที่ส่ง: {uploaded_count}",
        ]
        lines.extend(
            f"{'สำเร็จ' if result['success'] else 'ผิดพลาด'} - {result['task_code']}: {result['message']}"
            for result in results
        )
        return "\n".join(lines)

    def _finish_sync(self, results, is_auto):
        self.btn_manual_sync.configure(state=tk.NORMAL)
        succeeded = sum(1 for result in results if result["success"])
        self.progress_text_var.set(f"เสร็จแล้ว: {succeeded}/{len(results)} งานสำเร็จ")
        summary = self._format_summary(results, is_auto)
        if is_auto:
            self._append_log(summary.replace("\n", " | "))
        else:
            messagebox.showinfo("ผลการซิงค์ Manual", summary, parent=self.win)

    def _update_task_status(self, mapping_id, status):
        self.latest_status[mapping_id] = status
        item = str(mapping_id)
        if self.mapping_tree.exists(item):
            values = list(self.mapping_tree.item(item, "values"))
            values[6] = status
            self.mapping_tree.item(item, values=values)

    def _update_progress(self, message, current, total):
        if total > 0:
            self.progressbar.configure(maximum=total)
            self.progress_value.set(min(current, total))
        else:
            self.progressbar.configure(maximum=100)
            self.progress_value.set(0)
        self.progress_text_var.set(message)
        self._append_log(message)

    def _open_schedule_settings(self):
        win = ctk.CTkToplevel(self.win)
        win.title("ตั้งค่า Auto-Schedule District Sync")
        win.geometry("420x430")
        win.transient(self.win)
        win.grab_set()
        current = self.config.get("district_sync_schedule", {})
        enabled_var = tk.BooleanVar(value=current.get("enabled", False))
        notify_var = tk.BooleanVar(value=current.get("notify_on_auto", True))
        ttk.Checkbutton(win, text="เปิดใช้งาน Auto-Sync", variable=enabled_var).pack(
            anchor=tk.W, padx=12, pady=(6, 2)
        )
        ttk.Label(win, text="เวลาซิงค์ (HH:MM)").pack(anchor=tk.W, padx=12)
        times_list = ttk.Listbox(win, height=8)
        times_list.pack(fill=tk.X, padx=12, pady=2)
        for sync_time in current.get("sync_times", ["12:00", "17:00"]):
            times_list.insert(tk.END, sync_time)
        time_input = ttk.Entry(win, width=12)
        time_input.pack(anchor=tk.W, padx=12, pady=1, ipady=Spacing.XXS)

        def add_time():
            value = time_input.get().strip()
            try:
                datetime.strptime(value, "%H:%M")
            except ValueError:
                messagebox.showwarning("เวลาไม่ถูกต้อง", "กรุณาระบุเวลาแบบ HH:MM", parent=win)
                return
            if value not in times_list.get(0, tk.END):
                times_list.insert(tk.END, value)
            time_input.delete(0, tk.END)

        def remove_time():
            selection = times_list.curselection()
            if selection:
                times_list.delete(selection[0])

        time_buttons = ttk.Frame(win)
        time_buttons.pack(fill=tk.X, padx=10, pady=1)
        ttk.Button(time_buttons, text="เพิ่มเวลา", command=add_time).pack(side=tk.LEFT, padx=3)
        ttk.Button(time_buttons, text="ลบเวลาที่เลือก", command=remove_time).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(
            win,
            text="แจ้งผลผ่าน Telegram / LINE เมื่อ Auto-Sync เสร็จ",
            variable=notify_var
        ).pack(anchor=tk.W, padx=12, pady=5)

        def save_schedule():
            times = list(times_list.get(0, tk.END))
            if not times:
                messagebox.showwarning("กำหนดเวลา", "กรุณาระบุเวลาอย่างน้อย 1 รอบ", parent=win)
                return
            try:
                for sync_time in times:
                    datetime.strptime(sync_time, "%H:%M")
            except ValueError:
                messagebox.showwarning("กำหนดเวลา", "เวลาต้องอยู่ในรูปแบบ HH:MM", parent=win)
                return
            updated = copy.deepcopy(self.config)
            updated["district_sync_schedule"] = {
                "enabled": enabled_var.get(),
                "sync_times": times,
                "notify_on_auto": notify_var.get(),
            }
            if not sync_engine.save_config(updated):
                messagebox.showerror("บันทึกไม่สำเร็จ", "ไม่สามารถบันทึก config.json ได้", parent=win)
                return
            self.app.config.clear()
            self.app.config.update(updated)
            try:
                self._restart_scheduler()
            except (ValueError, schedule.ScheduleValueError) as error:
                self._stop_scheduler()
                messagebox.showerror("ตั้งเวลาไม่สำเร็จ", str(error), parent=win)
                return
            win.destroy()

        buttons = ttk.Frame(win)
        buttons.pack(fill=tk.X, padx=Spacing.MD, pady=VSpacing.MD)
        create_primary_button(buttons, text=f"{Icons.SAVE} บันทึก", command=save_schedule).pack(side=tk.LEFT, padx=Spacing.SM)
        create_ghost_button(buttons, text=f"{Icons.CLOSE} ปิด", command=win.destroy).pack(side=tk.RIGHT, padx=Spacing.SM)
        win.wait_window(win)

    def _restart_scheduler(self):
        self._stop_scheduler()
        if self.scheduler_thread is not None and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=1)
        schedule_config = self.config.get("district_sync_schedule", {})
        if not schedule_config.get("enabled", False):
            self.schedule_status_var.set("Auto-Schedule: ปิด")
            return
        times = schedule_config.get("sync_times", [])
        if not times:
            raise ValueError("Auto-Schedule ต้องมีเวลาอย่างน้อย 1 รอบ")
        scheduler = schedule.Scheduler()
        for sync_time in times:
            datetime.strptime(sync_time, "%H:%M")
            scheduler.every().day.at(sync_time).do(self._auto_sync_due)
        self.scheduler_stop = threading.Event()
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            args=(scheduler, self.scheduler_stop),
            daemon=True
        )
        self.scheduler_thread.start()
        self.schedule_status_var.set(f"Auto-Schedule: เปิด | {', '.join(times)}")
        sync_engine.log_info(f"เริ่ม District Auto-Scheduler: {', '.join(times)}")

    def _scheduler_loop(self, scheduler, stop_event):
        while not stop_event.wait(1):
            scheduler.run_pending()

    def _auto_sync_due(self):
        self._post(self._start_sync, True)

    def _stop_scheduler(self):
        self.scheduler_stop.set()

    def _open_notification_settings(self):
        self.app._open_notification_settings()

