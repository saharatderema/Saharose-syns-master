#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAHARose Sync Master - UI Design System
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Dict, Any, Tuple
import customtkinter as ctk

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")


class Colors:
    PRIMARY = "#2563EB"
    PRIMARY_HOVER = "#1D4ED8"
    PRIMARY_LIGHT = "#DBEAFE"
    PRIMARY_STRONG = "#1E40AF"
    SECONDARY = "#667085"
    SECONDARY_HOVER = "#475467"
    SECONDARY_LIGHT = "#F2F4F7"
    SUCCESS = "#15803D"
    SUCCESS_LIGHT = "#D1FAE5"
    SUCCESS_STRONG = "#065F46"
    WARNING = "#B54708"
    WARNING_LIGHT = "#FEF0C7"
    WARNING_STRONG = "#7A2E0E"
    DANGER = "#DC3545"
    DANGER_HOVER = "#BB2D3B"
    DANGER_LIGHT = "#FEE4E2"
    DANGER_STRONG = "#7A271A"
    INFO = "#1570EF"
    INFO_LIGHT = "#EAF2FF"
    INFO_STRONG = "#1849A9"
    WHITE = "#FFFFFF"
    GRAY_50 = "#F8FAFC"
    GRAY_100 = "#F2F4F7"
    GRAY_200 = "#EAECF0"
    GRAY_300 = "#D0D5DD"
    GRAY_400 = "#98A2B3"
    GRAY_500 = "#667085"
    GRAY_600 = "#475467"
    GRAY_700 = "#344054"
    GRAY_800 = "#1D2939"
    GRAY_900 = "#101828"
    GRAY_950 = "#0C111D"
    BG_PRIMARY = "#F4F7FA"
    BG_SECONDARY = WHITE
    BG_TERTIARY = GRAY_100
    BG_INVERSE = GRAY_900
    BORDER_LIGHT = GRAY_200
    BORDER_MEDIUM = GRAY_300
    BORDER_STRONG = GRAY_400
    TEXT_PRIMARY = GRAY_900
    TEXT_SECONDARY = GRAY_600
    TEXT_MUTED = GRAY_500
    TEXT_INVERSE = WHITE
    TEXT_LINK = PRIMARY

    # Status Colors
    STATUS_ONLINE = SUCCESS
    STATUS_OFFLINE = DANGER
    STATUS_WARNING = WARNING
    STATUS_PENDING = INFO
    STATUS_SYNCING = PRIMARY
    STATUS_IDLE = GRAY_400


class Typography:
    FONT_FAMILY_SANS = "Leelawadee UI"
    FONT_FAMILY_MONO = "Consolas"
    FONT_FAMILY_THAI = FONT_FAMILY_SANS
    FONT_FAMILY_BASE = FONT_FAMILY_SANS
    FONT_FAMILY_MONO_BASE = FONT_FAMILY_MONO
    SIZE_XS = 11
    SIZE_SM = 11
    SIZE_BASE = 13
    SIZE_LG = 14
    SIZE_XL = 14
    SIZE_2XL = 16
    SIZE_3XL = 22
    SIZE_4XL = 26
    WEIGHT_NORMAL = "normal"
    WEIGHT_MEDIUM = "bold"
    WEIGHT_BOLD = "bold"

    @classmethod
    def configure(cls, root: tk.Tk):
        setup_default_fonts(root)

    @classmethod
    def get_font(
        cls, size: int, weight: str = WEIGHT_NORMAL, family: str = None
    ) -> ctk.CTkFont:
        fam = family or cls.FONT_FAMILY_BASE
        return ctk.CTkFont(family=fam, size=size, weight=weight)

    CAPTION = (FONT_FAMILY_BASE, SIZE_XS, WEIGHT_NORMAL)
    LABEL = (FONT_FAMILY_BASE, SIZE_SM, WEIGHT_MEDIUM)
    BODY = (FONT_FAMILY_BASE, SIZE_BASE, WEIGHT_NORMAL)
    BODY_BOLD = (FONT_FAMILY_BASE, SIZE_BASE, WEIGHT_BOLD)
    BODY_LG = (FONT_FAMILY_BASE, SIZE_LG, WEIGHT_NORMAL)
    SUBHEADING = (FONT_FAMILY_BASE, SIZE_XL, WEIGHT_MEDIUM)
    HEADING = (FONT_FAMILY_BASE, SIZE_2XL, WEIGHT_BOLD)
    TITLE = (FONT_FAMILY_BASE, SIZE_3XL, WEIGHT_BOLD)
    HERO = (FONT_FAMILY_BASE, SIZE_4XL, WEIGHT_BOLD)
    MONO_SM = (FONT_FAMILY_MONO_BASE, SIZE_SM, WEIGHT_NORMAL)
    MONO_BASE = (FONT_FAMILY_MONO_BASE, SIZE_BASE, WEIGHT_NORMAL)
    MONO_LG = (FONT_FAMILY_MONO_BASE, SIZE_LG, WEIGHT_NORMAL)


FONT_SPECS = {
    "H1": (22, "bold"),
    "H2": (16, "bold"),
    "H3": (14, "bold"),
    "BODY": (13, "normal"),
    "CAPTION": (11, "normal"),
    "BUTTON": (13, "bold"),
}
FONTS: Dict[str, ctk.CTkFont] = {}


class Spacing:
    BASE = 8
    NONE = 0
    XXXS = 4
    XXS = 8
    XS = 8
    SM = 16
    MD = 24
    LG = 32
    XL = 40
    XXL = 48
    XXXL = 64
    XXXXL = 80
    PAGE_PADDING = 24
    SECTION_GAP = 24
    CARD_PADDING = 24
    BUTTON_GAP = 16
    FORM_GAP = 16
    CONTENT_MAX_WIDTH = 1200  # Max content width for readability


def setup_default_fonts(root: tk.Tk) -> str:
    try:
        installed_fonts = {
            family.casefold(): family for family in tkfont.families(root)
        }
    except tk.TclError:
        installed_fonts = {}

    default_family = tkfont.nametofont(
        "TkDefaultFont", root=root
    ).actual("family")
    family = next(
        (
            installed_fonts[name.casefold()]
            for name in ("Sarabun", "Prompt", "Leelawadee UI", "Tahoma", "Segoe UI")
            if name.casefold() in installed_fonts
        ),
        installed_fonts.get("segoe ui", default_family),
    )
    default_mono = tkfont.nametofont(
        "TkFixedFont", root=root
    ).actual("family")
    mono_family = next(
        (
            installed_fonts[name.casefold()]
            for name in ("Cascadia Mono", "Consolas", "Courier New")
            if name.casefold() in installed_fonts
        ),
        default_mono,
    )

    FONTS.clear()
    FONTS.update({
        name: ctk.CTkFont(family=family, size=size, weight=weight)
        for name, (size, weight) in FONT_SPECS.items()
    })
    FONTS.update({
        "BODY_LG": ctk.CTkFont(family=family, size=14, weight="normal"),
        "HERO": ctk.CTkFont(family=family, size=26, weight="bold"),
        "MONO": ctk.CTkFont(family=mono_family, size=13, weight="normal"),
        "MONO_CAPTION": ctk.CTkFont(family=mono_family, size=11, weight="normal"),
    })

    Typography.FONT_FAMILY_SANS = family
    Typography.FONT_FAMILY_THAI = family
    Typography.FONT_FAMILY_BASE = family
    Typography.FONT_FAMILY_MONO = mono_family
    Typography.FONT_FAMILY_MONO_BASE = mono_family
    Typography.SIZE_XS = 11
    Typography.SIZE_SM = 11
    Typography.SIZE_BASE = 13
    Typography.SIZE_LG = 14
    Typography.SIZE_XL = 14
    Typography.SIZE_2XL = 16
    Typography.SIZE_3XL = 22
    Typography.SIZE_4XL = 26
    Typography.CAPTION = FONTS["CAPTION"]
    Typography.LABEL = FONTS["BUTTON"]
    Typography.BODY = FONTS["BODY"]
    Typography.BODY_BOLD = FONTS["BUTTON"]
    Typography.BODY_LG = FONTS["BODY_LG"]
    Typography.SUBHEADING = FONTS["H3"]
    Typography.HEADING = FONTS["H2"]
    Typography.TITLE = FONTS["H1"]
    Typography.HERO = FONTS["HERO"]
    Typography.MONO_SM = FONTS["MONO_CAPTION"]
    Typography.MONO_BASE = FONTS["MONO"]
    Typography.MONO_LG = FONTS["MONO"]

    root.option_add("*Font", FONTS["BODY"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TButton", font=FONTS["BUTTON"])
    style.configure("TLabel", font=FONTS["BODY"])
    style.configure("TEntry", font=FONTS["BODY"], padding=(8, 8))
    style.configure("Treeview", font=FONTS["BODY"], rowheight=34)
    style.configure("Treeview.Heading", font=FONTS["H3"])
    return family


class Icons:
    HOME = "🏠"
    SETTINGS = "⚙️"
    DATABASE = "🗄️"
    SERVER = "🖥️"
    CLOUD = "☁️"
    NETWORK = "🌐"
    VPN = "🔒"
    PLAY = "▶️"
    PAUSE = "⏸️"
    STOP = "⏹️"
    REFRESH = "🔄"
    SYNC = "🔄"
    DOWNLOAD = "⬇️"
    UPLOAD = "⬆️"
    SEARCH = "🔍"
    FILTER = "🔎"
    ADD = "➕"
    EDIT = "✏️"
    DELETE = "🗑️"
    COPY = "📋"
    EXPORT = "📤"
    IMPORT = "📥"
    PRINT = "🖨️"
    SAVE = "💾"
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"
    PENDING = "⏳"
    LOADING = "⏳"
    ONLINE = "🟢"
    OFFLINE = "🔴"
    CHECK = "✓"
    CROSS = "✗"
    TABLE = "📊"
    CHART = "📈"
    LIST = "📋"
    ROW = "📄"
    COLUMN = "📑"
    MAPPING = "🔗"
    PIPELINE = "🔧"
    CLOCK = "🕐"
    CALENDAR = "📅"
    SCHEDULE = "⏰"
    TIMER = "⏱️"
    CHEVRON_RIGHT = "▶"
    CHEVRON_DOWN = "▼"
    CHEVRON_LEFT = "◀"
    CHEVRON_UP = "▲"
    DOTS = "⋯"
    MORE = "⋮"
    CLOSE = "✕"
    MINIMIZE = "—"
    MAXIMIZE = "□"
    EXPAND = "⤢"
    COLLAPSE = "⤡"
    HOSPITAL = "🏥"
    CLINIC = "🏥"
    PATIENT = "👤"
    DOCTOR = "👨‍⚕️"
    MEDICAL = "🩺"
    PRESCRIPTION = "💊"
    LAB = "🧪"
    VACCINE = "💉"
    BELL = "🔔"
    BELL_OFF = "🔕"
    TELEGRAM = "📱"
    LINE = "💬"
    EMAIL = "📧"
    FOLDER = "📁"
    FILE = "📄"
    SQL = "💾"
    LOG = "📝"
    CONFIG = "🔧"



class ThemeManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.style = ttk.Style(root)
        self._current_theme = "light"
        self._custom_styles = {}
        self._setup_base_theme()

    def _setup_base_theme(self):
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        Typography.configure(self.root)
        self.root.option_add("*Font", FONTS["BODY"])
        self.style.configure("Treeview", font=FONTS["BODY"], rowheight=34,
                             background=Colors.WHITE, fieldbackground=Colors.WHITE,
                             foreground=Colors.TEXT_PRIMARY, borderwidth=0)
        self.style.configure("Compact.Treeview", font=FONTS["BODY"], rowheight=34,
                             background=Colors.WHITE, fieldbackground=Colors.WHITE,
                             foreground=Colors.TEXT_PRIMARY, borderwidth=0)
        self.style.configure("Treeview.Heading", font=FONTS["H3"],
                             background=Colors.GRAY_50, foreground=Colors.TEXT_PRIMARY,
                             relief="flat", padding=(8, 8))
        self.style.configure("Compact.Treeview.Heading", font=FONTS["BUTTON"],
                             background=Colors.GRAY_50, foreground=Colors.TEXT_PRIMARY,
                             relief="flat", padding=(8, 8))
        self.style.map("Treeview", background=[("selected", Colors.PRIMARY_LIGHT)],
                       foreground=[("selected", Colors.PRIMARY_STRONG)])
        self.style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        self.style.configure("Vertical.TScrollbar", width=12,
                             background=Colors.GRAY_200, troughcolor=Colors.BG_PRIMARY)
        self.style.configure("TNotebook", background=Colors.BG_PRIMARY, borderwidth=0)
        self.style.configure("TNotebook.Tab", font=FONTS["BODY"], padding=(16, 10))

    def get_style(self, style_name: str) -> Dict[str, Any]:
        return self._custom_styles.get(style_name, {})
    
    def register_style(self, name: str, **kwargs):
        self.style.configure(name, **kwargs)
        self._custom_styles[name] = kwargs
    
    def apply_to_widget(self, widget: tk.Widget, style_name: str):
        widget.configure(style=style_name)
    
    def set_theme(self, theme: str):
        self._current_theme = theme
    
    @property
    def current_theme(self) -> str:
        return self._current_theme


_BUTTON_STYLES = {
    "Primary.TButton": (Colors.PRIMARY, Colors.WHITE, Colors.PRIMARY_HOVER, 0),
    "Small.Primary.TButton": (Colors.PRIMARY, Colors.WHITE, Colors.PRIMARY_HOVER, 0),
    "Large.Primary.TButton": (Colors.PRIMARY, Colors.WHITE, Colors.PRIMARY_HOVER, 0),
    "Secondary.TButton": (Colors.GRAY_100, Colors.TEXT_PRIMARY, Colors.GRAY_200, 1),
    "Small.Secondary.TButton": (Colors.GRAY_100, Colors.TEXT_PRIMARY, Colors.GRAY_200, 1),
    "Ghost.TButton": ("transparent", Colors.PRIMARY, Colors.PRIMARY_LIGHT, 0),
    "Small.TButton": ("transparent", Colors.TEXT_PRIMARY, Colors.GRAY_100, 0),
    "Danger.TButton": (Colors.DANGER, Colors.WHITE, Colors.DANGER_HOVER, 0),
    "Small.Danger.TButton": (Colors.DANGER, Colors.WHITE, Colors.DANGER_HOVER, 0),
    "Success.TButton": (Colors.SUCCESS, Colors.WHITE, Colors.SUCCESS_STRONG, 0),
    "Warning.TButton": (Colors.WARNING, Colors.WHITE, Colors.WARNING_STRONG, 0),
    "Sidebar.TButton": ("transparent", Colors.TEXT_SECONDARY, Colors.GRAY_100, 0),
    "SidebarSelected.TButton": (Colors.PRIMARY_LIGHT, Colors.PRIMARY_STRONG, Colors.PRIMARY_LIGHT, 0),
}

_LABEL_STYLES = {
    "Heading.TLabel": (Colors.TEXT_PRIMARY, "H3"),
    "Title.TLabel": (Colors.TEXT_PRIMARY, "H1"),
    "Hero.TLabel": (Colors.TEXT_PRIMARY, "HERO"),
    "Muted.TLabel": (Colors.TEXT_MUTED, "BODY"),
    "Caption.TLabel": (Colors.TEXT_MUTED, "CAPTION"),
    "Success.TLabel": (Colors.SUCCESS, "BODY"),
    "Warning.TLabel": (Colors.WARNING, "BODY"),
    "Danger.TLabel": (Colors.DANGER, "BODY"),
    "Info.TLabel": (Colors.INFO, "BODY"),
    "SidebarHeader.TLabel": (Colors.PRIMARY, "H2"),
    "SidebarCaption.TLabel": (Colors.TEXT_MUTED, "CAPTION"),
    "Statusbar.TLabel": (Colors.TEXT_SECONDARY, "CAPTION"),
    "Toast.TLabel": (Colors.TEXT_SECONDARY, "BODY"),
    "Toast.Success.TLabel": (Colors.SUCCESS_STRONG, "BODY"),
    "Toast.Warning.TLabel": (Colors.WARNING_STRONG, "BODY"),
    "Toast.Error.TLabel": (Colors.DANGER_STRONG, "BODY"),
    "Toast.Info.TLabel": (Colors.PRIMARY_STRONG, "BODY"),
}

_FRAME_STYLES = {
    "App.TFrame": (Colors.BG_PRIMARY, 0, 0),
    "Content.TFrame": (Colors.BG_PRIMARY, 0, 0),
    "Sidebar.TFrame": (Colors.BG_SECONDARY, 0, 0),
    "Statusbar.TFrame": (Colors.BG_SECONDARY, 0, 0),
    "Card.TFrame": (Colors.BG_SECONDARY, 12, 1),
    "Card.TLabelframe": (Colors.BG_SECONDARY, 12, 1),
    "Elevated.TFrame": (Colors.BG_SECONDARY, 12, 0),
    "Section.TLabelframe": (Colors.BG_PRIMARY, 0, 0),
}


def _frame_options(style_name=None):
    fg_color, radius, border_width = _FRAME_STYLES.get(
        style_name, ("transparent", 0, 0)
    )
    return {
        "fg_color": fg_color,
        "corner_radius": radius,
        "border_width": border_width,
        "border_color": Colors.BORDER_LIGHT,
    }


def _pixel_width(character_count, font):
    if not isinstance(character_count, (int, float)):
        return character_count
    try:
        return max(1, font.measure("0" * int(character_count)))
    except (AttributeError, tk.TclError):
        return max(1, int(character_count * 8))


class CTkFrameCompat(ctk.CTkFrame):
    def __init__(self, master=None, **kwargs):
        style_name = kwargs.pop("style", None)
        kwargs.pop("padding", None)
        kwargs.pop("relief", None)
        kwargs.pop("borderwidth", None)
        kwargs.pop("background", None)
        options = _frame_options(style_name)
        options.update(kwargs)
        super().__init__(master, **options)

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs.update(cnf)
        style_name = kwargs.pop("style", None)
        if style_name:
            kwargs.update(_frame_options(style_name))
        kwargs.pop("padding", None)
        kwargs.pop("relief", None)
        kwargs.pop("borderwidth", None)
        if "background" in kwargs:
            kwargs["fg_color"] = kwargs.pop("background")
        return super().configure(**kwargs)

    config = configure


class _CTkLabelFrameBody(ctk.CTkFrame):
    def __init__(self, master, text, **kwargs):
        style_name = kwargs.pop("style", "Card.TLabelframe")
        padding = kwargs.pop("padding", 12)
        kwargs.pop("relief", None)
        kwargs.pop("borderwidth", None)
        kwargs.pop("background", None)
        outer_options = _frame_options(style_name)
        outer_options.update(kwargs)
        self._outer = ctk.CTkFrame(master, **outer_options)
        super().__init__(self._outer, fg_color="transparent", corner_radius=0)

        if isinstance(padding, (tuple, list)):
            body_padx = padding[0]
            body_pady = padding[1] if len(padding) > 1 else padding[0]
        else:
            body_padx = body_pady = padding

        self._outer.grid_columnconfigure(0, weight=1)
        self._outer.grid_rowconfigure(1, weight=1)
        self._title_label = ctk.CTkLabel(
            self._outer,
            text=text,
            font=FONTS["H3"],
            text_color=Colors.TEXT_PRIMARY,
            anchor="w",
        )
        self._title_label.grid(
            row=0, column=0, sticky="ew", padx=12, pady=(12, 4)
        )
        ctk.CTkFrame.grid(
            self, row=1, column=0, sticky="nsew",
            padx=body_padx, pady=(0, body_pady),
        )

    def pack(self, **kwargs):
        return self._outer.pack(**kwargs)

    def grid(self, **kwargs):
        return self._outer.grid(**kwargs)

    def place(self, **kwargs):
        return self._outer.place(**kwargs)

    def pack_forget(self):
        self._outer.pack_forget()

    def grid_remove(self):
        self._outer.grid_remove()

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs.update(cnf)
        style_name = kwargs.pop("style", None)
        text = kwargs.pop("text", None)
        if style_name:
            self._outer.configure(**_frame_options(style_name))
        if text is not None:
            self._title_label.configure(text=text)
        return super().configure(**kwargs)

    config = configure

    def cget(self, key):
        if key == "text":
            return self._title_label.cget("text")
        return super().cget(key)


class CTkLabelFrameCompat:
    def __new__(cls, master=None, text="", **kwargs):
        return _CTkLabelFrameBody(master, text, **kwargs)


class CTkLabelCompat(ctk.CTkLabel):
    def __init__(self, master=None, **kwargs):
        style_name = kwargs.pop("style", None)
        textvariable = kwargs.pop("textvariable", None)
        kwargs.pop("padding", None)
        style_color, font_role = _LABEL_STYLES.get(
            style_name, (Colors.TEXT_PRIMARY, "BODY")
        )
        kwargs["text_color"] = kwargs.pop("foreground", style_color)
        kwargs["fg_color"] = kwargs.pop("background", "transparent")
        kwargs.setdefault("font", FONTS[font_role])
        if "width" in kwargs:
            kwargs["width"] = _pixel_width(kwargs["width"], kwargs["font"])
        if textvariable is not None:
            kwargs["text"] = textvariable.get()
        super().__init__(master, **kwargs)
        if textvariable is not None:
            textvariable.trace_add(
                "write", lambda *_: self.configure(text=textvariable.get())
            )

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs.update(cnf)
        style_name = kwargs.pop("style", None)
        if style_name in _LABEL_STYLES:
            color, font_role = _LABEL_STYLES[style_name]
            kwargs.setdefault("text_color", color)
            kwargs.setdefault("font", FONTS[font_role])
        if "foreground" in kwargs:
            kwargs["text_color"] = kwargs.pop("foreground")
        if "background" in kwargs:
            kwargs["fg_color"] = kwargs.pop("background")
        kwargs.pop("padding", None)
        return super().configure(**kwargs)

    config = configure


class CTkButtonCompat(ctk.CTkButton):
    def __init__(self, master=None, **kwargs):
        style_name = kwargs.pop("style", None)
        kwargs.pop("padding", None)
        kwargs.pop("default", None)
        kwargs.pop("takefocus", None)
        fg_color, text_color, hover_color, border_width = _BUTTON_STYLES.get(
            style_name,
            (Colors.GRAY_100, Colors.TEXT_PRIMARY, Colors.GRAY_200, 1),
        )
        kwargs.setdefault("fg_color", fg_color)
        kwargs.setdefault("text_color", text_color)
        kwargs.setdefault("hover_color", hover_color)
        kwargs.setdefault("border_color", Colors.BORDER_MEDIUM)
        kwargs.setdefault("border_width", border_width)
        kwargs.setdefault("font", FONTS["BUTTON"])
        kwargs.setdefault("height", 36)
        kwargs.setdefault("corner_radius", 8)
        if "width" in kwargs:
            kwargs["width"] = _pixel_width(kwargs["width"], kwargs["font"])
        super().__init__(master, **kwargs)

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs.update(cnf)
        style_name = kwargs.pop("style", None)
        if style_name:
            fg_color, text_color, hover_color, border_width = _BUTTON_STYLES.get(
                style_name,
                (Colors.GRAY_100, Colors.TEXT_PRIMARY, Colors.GRAY_200, 1),
            )
            kwargs.update(
                fg_color=fg_color,
                text_color=text_color,
                hover_color=hover_color,
                border_color=Colors.BORDER_MEDIUM,
                border_width=border_width,
            )
        kwargs.pop("padding", None)
        kwargs.pop("default", None)
        kwargs.pop("takefocus", None)
        return super().configure(**kwargs)

    config = configure


class CTkEntryCompat(ctk.CTkEntry):
    def __init__(self, master=None, **kwargs):
        kwargs.pop("style", None)
        kwargs.pop("padding", None)
        kwargs.pop("ipady", None)
        kwargs.setdefault("font", FONTS["BODY"])
        kwargs.setdefault("height", 36)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_color", Colors.BORDER_MEDIUM)
        if "width" in kwargs:
            kwargs["width"] = _pixel_width(kwargs["width"], kwargs["font"])
        super().__init__(master, **kwargs)


class CTkComboBoxCompat(ctk.CTkComboBox):
    def __init__(self, master=None, **kwargs):
        kwargs.pop("style", None)
        kwargs.pop("padding", None)
        kwargs.setdefault("font", FONTS["BODY"])
        kwargs.setdefault("height", 36)
        kwargs.setdefault("corner_radius", 8)
        if "width" in kwargs:
            kwargs["width"] = _pixel_width(kwargs["width"], kwargs["font"])
        super().__init__(master, **kwargs)

    def current(self, index=None):
        values = list(self.cget("values"))
        if index is None:
            try:
                return values.index(self.get())
            except ValueError:
                return -1
        if values:
            self.set(values[index])


class CTkCheckbuttonCompat(ctk.CTkCheckBox):
    def __init__(self, master=None, **kwargs):
        kwargs.pop("style", None)
        kwargs.pop("padding", None)
        kwargs.setdefault("font", FONTS["BODY"])
        super().__init__(master, **kwargs)

    def state(self, states=None):
        if states is None:
            return ("disabled",) if self.cget("state") == "disabled" else ()
        disabled = "disabled" in states
        self.configure(state="disabled" if disabled else "normal")
        return self.state()


class CTkRadiobuttonCompat(ctk.CTkRadioButton):
    def __init__(self, master=None, **kwargs):
        kwargs.pop("style", None)
        kwargs.pop("padding", None)
        kwargs.setdefault("font", FONTS["BODY"])
        super().__init__(master, **kwargs)


class CTkSeparatorCompat(ctk.CTkFrame):
    def __init__(self, master=None, orient=tk.HORIZONTAL, **kwargs):
        kwargs.pop("style", None)
        if orient == tk.VERTICAL:
            kwargs.setdefault("width", 2)
            kwargs.setdefault("height", 0)
        else:
            kwargs.setdefault("height", 2)
            kwargs.setdefault("width", 0)
        kwargs.setdefault("fg_color", Colors.BORDER_LIGHT)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)


class CTkScrollbarCompat(ctk.CTkScrollbar):
    def __init__(self, master=None, orient=tk.VERTICAL, **kwargs):
        orientation = kwargs.pop("orientation", orient)
        super().__init__(master, orientation=orientation, **kwargs)


class CTkScrollableFrameCompat(ctk.CTkScrollableFrame):
    def yview_scroll(self, units, what):
        self._parent_canvas.yview_scroll(units, what)


class CTkTextboxCompat(ctk.CTkTextbox):
    def __init__(self, master=None, **kwargs):
        height = kwargs.get("height", 200)
        if isinstance(height, (int, float)) and 0 < height < 100:
            kwargs["height"] = int(height * 24)
        width = kwargs.get("width")
        if isinstance(width, (int, float)) and 0 < width < 100:
            kwargs["width"] = _pixel_width(width, kwargs.get("font", FONTS["BODY"]))
        kwargs.setdefault("fg_color", Colors.WHITE)
        kwargs.setdefault("border_color", Colors.BORDER_MEDIUM)
        kwargs.setdefault("corner_radius", 8)
        super().__init__(master, **kwargs)

    def edit_modified(self, value=None):
        if value is None:
            return self._textbox.edit_modified()
        return self._textbox.edit_modified(value)


class CTkListboxCompat(ctk.CTkScrollableFrame):
    def __init__(self, master=None, height=6, width=20, font=None, **kwargs):
        self._items = []
        self._selected_index = None
        self._item_font = font or FONTS["BODY"]
        pixel_height = int(height * 32) if height < 100 else int(height)
        pixel_width = _pixel_width(width, self._item_font) if width < 100 else int(width)
        kwargs.setdefault("width", pixel_width)
        kwargs.setdefault("height", pixel_height)
        kwargs.setdefault("fg_color", Colors.WHITE)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", Colors.BORDER_MEDIUM)
        super().__init__(master, **kwargs)

    def insert(self, index, *elements):
        position = len(self._items) if index in (tk.END, "end") else int(index)
        for offset, element in enumerate(elements):
            self._items.insert(position + offset, str(element))
        self._render_items()

    def delete(self, first, last=None):
        start = len(self._items) - 1 if first in (tk.END, "end") else int(first)
        end = start if last is None else (
            len(self._items) - 1 if last in (tk.END, "end") else int(last)
        )
        del self._items[start:end + 1]
        self._selected_index = None
        self._render_items()

    def get(self, first, last=None):
        start = len(self._items) - 1 if first in (tk.END, "end") else int(first)
        if last is None:
            return self._items[start]
        end = len(self._items) if last in (tk.END, "end") else int(last) + 1
        return tuple(self._items[start:end])

    def curselection(self):
        if self._selected_index is None:
            return ()
        return (self._selected_index,)

    def _render_items(self):
        for child in self.winfo_children():
            child.destroy()
        for index, value in enumerate(self._items):
            selected = index == self._selected_index
            ctk.CTkButton(
                self,
                text=value,
                anchor="w",
                font=self._item_font,
                height=32,
                corner_radius=6,
                border_spacing=8,
                fg_color=Colors.PRIMARY_LIGHT if selected else "transparent",
                text_color=Colors.PRIMARY_STRONG if selected else Colors.TEXT_PRIMARY,
                hover_color=Colors.GRAY_100,
                command=lambda selected_index=index: self._select(selected_index),
            ).pack(fill="x", padx=4, pady=1)

    def _select(self, index):
        self._selected_index = index
        self._render_items()


class CTkProgressBarCompat(ctk.CTkProgressBar):
    def __init__(self, master=None, **kwargs):
        kwargs.pop("style", None)
        self._maximum = kwargs.pop("maximum", 1.0)
        variable = kwargs.pop("variable", None)
        value = kwargs.pop("value", None)
        kwargs.setdefault("height", 8)
        kwargs.setdefault("progress_color", Colors.PRIMARY)
        kwargs.setdefault("fg_color", Colors.GRAY_200)
        super().__init__(master, **kwargs)
        self._progress_variable = variable
        if variable is not None:
            variable.trace_add("write", self._sync_variable)
            self._sync_variable()
        elif value is not None:
            self.set(float(value) / self._maximum)

    def _sync_variable(self, *_):
        if self._progress_variable is not None:
            self.set(float(self._progress_variable.get()) / self._maximum)

    def start(self, interval=50):
        super().start()

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs.update(cnf)
        if "maximum" in kwargs:
            self._maximum = kwargs.pop("maximum")
        value = kwargs.pop("value", None)
        result = super().configure(**kwargs)
        if value is not None:
            self.set(float(value) / self._maximum)
        return result

    config = configure


class _CTkWidgets:
    def __init__(self):
        self.Frame = CTkFrameCompat
        self.LabelFrame = CTkLabelFrameCompat
        self.Label = CTkLabelCompat
        self.Button = CTkButtonCompat
        self.Entry = CTkEntryCompat
        self.Combobox = CTkComboBoxCompat
        self.Checkbutton = CTkCheckbuttonCompat
        self.Radiobutton = CTkRadiobuttonCompat
        self.Separator = CTkSeparatorCompat
        self.Scrollbar = CTkScrollbarCompat
        self.ScrollableFrame = CTkScrollableFrameCompat
        self.Listbox = CTkListboxCompat
        self.Text = CTkTextboxCompat
        self.Progressbar = CTkProgressBarCompat
        self.Style = ttk.Style
        self.Treeview = ttk.Treeview
        self.Notebook = ttk.Notebook


ctk_widgets = _CTkWidgets()
ttk = ctk_widgets


class ContentStack(ctk.CTkFrame):
    """Responsive single-page container with a Notebook-compatible select API."""

    def __init__(self, master, **kwargs):
        kwargs.pop("style", None)
        kwargs.pop("padding", None)
        kwargs.setdefault("fg_color", Colors.BG_PRIMARY)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)
        self._pages = []
        self._current_page = None
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def add(self, page: tk.Widget, text: str = ""):
        self._pages.append((page, text))
        page.grid(row=0, column=0, sticky=tk.NSEW)
        if self._current_page is None:
            self._current_page = page
        else:
            page.grid_remove()

    def select(self, page=None):
        if page is None:
            return str(self._current_page) if self._current_page is not None else ""
        target = next(
            (
                widget for widget, _ in self._pages
                if widget == page or str(widget) == str(page)
            ),
            None,
        )
        if target is None:
            raise ValueError("ไม่พบหน้าที่ต้องการแสดง")
        if target != self._current_page:
            if self._current_page is not None:
                self._current_page.grid_remove()
            target.grid()
            self._current_page = target
        self.event_generate("<<NotebookTabChanged>>", when="tail")
        return str(self._current_page)


class SidebarNavigation(ctk.CTkFrame):
    def __init__(self, master, content_stack: ContentStack, pages):
        super().__init__(
            master, fg_color=Colors.BG_SECONDARY, width=236,
            corner_radius=0,
        )
        self.content_stack = content_stack
        self.pages = list(pages)
        self.buttons = []
        self.grid_propagate(False)
        self.rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text="SAHARose",
            font=FONTS["H2"],
            text_color=Colors.PRIMARY,
        ).grid(row=0, column=0, sticky=tk.W, padx=8)
        ctk.CTkLabel(
            self,
            text="SYNC MASTER",
            font=FONTS["CAPTION"],
            text_color=Colors.TEXT_MUTED,
        ).grid(row=1, column=0, sticky=tk.W, padx=8, pady=(0, 20))

        menu = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        menu.grid(row=2, column=0, sticky=tk.NSEW)
        for icon, label, page in self.pages:
            button = ctk.CTkButton(
                menu,
                text=f"{icon}   {label}",
                font=FONTS["BUTTON"],
                anchor="w",
                height=40,
                corner_radius=8,
                fg_color="transparent",
                text_color=Colors.TEXT_SECONDARY,
                hover_color=Colors.GRAY_100,
                command=lambda selected=page: self.content_stack.select(selected),
            )
            button.pack(fill=tk.X, pady=3)
            self.buttons.append((button, page))

        ctk.CTkLabel(
            self,
            text="ระบบจัดการและซิงค์ข้อมูล",
            font=FONTS["CAPTION"],
            text_color=Colors.TEXT_MUTED,
            wraplength=200,
        ).grid(row=3, column=0, sticky=tk.SW, padx=8, pady=(16, 0))
        self.content_stack.bind(
            "<<NotebookTabChanged>>", self._sync_selected_state, add="+"
        )
        self._sync_selected_state()

    def _sync_selected_state(self, event=None):
        selected = self.content_stack.select()
        for button, page in self.buttons:
            button.configure(
                fg_color=Colors.PRIMARY_LIGHT if str(page) == selected else "transparent",
                text_color=Colors.PRIMARY_STRONG if str(page) == selected else Colors.TEXT_SECONDARY,
            )


class ToastManager:
    def __init__(self, root: tk.Tk, variable: tk.StringVar, label: ctk.CTkLabel):
        self.root = root
        self.variable = variable
        self.label = label
        self._after_id = None
        self._generation = 0

    def show(self, message: str, tone: str = "info", duration_ms: int = 4000):
        styles = {
            "success": "Toast.Success.TLabel",
            "warning": "Toast.Warning.TLabel",
            "error": "Toast.Error.TLabel",
            "info": "Toast.Info.TLabel",
        }
        self._generation += 1
        generation = self._generation
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self.label.configure(style=styles.get(tone, styles["info"]))
        self.variable.set(message)
        self._after_id = self.root.after(
            duration_ms, self._clear, generation
        )

    def _clear(self, generation: int):
        if generation != self._generation:
            return
        self.variable.set("")
        self.label.configure(style="Toast.TLabel")
        self._after_id = None



def create_card(parent: tk.Widget, **kwargs) -> ttk.Frame:
    kwargs.pop("padding", None)
    kwargs.setdefault("fg_color", Colors.BG_SECONDARY)
    kwargs.setdefault("corner_radius", 12)
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", Colors.BORDER_LIGHT)
    return ctk.CTkFrame(parent, **kwargs)

def create_elevated_card(parent: tk.Widget, **kwargs) -> ttk.Frame:
    kwargs.pop("padding", None)
    kwargs.setdefault("fg_color", Colors.BG_SECONDARY)
    kwargs.setdefault("corner_radius", 12)
    return ctk.CTkFrame(parent, **kwargs)

def create_section(parent: tk.Widget, title: str = None, **kwargs) -> ttk.LabelFrame:
    if title:
        return CTkLabelFrameCompat(
            parent, text=title, style="Section.TLabelframe", **kwargs
        )
    return CTkFrameCompat(parent, style="Section.TLabelframe", **kwargs)

def create_card_section(parent: tk.Widget, title: str = None, **kwargs) -> ttk.LabelFrame:
    if title:
        return CTkLabelFrameCompat(
            parent, text=title, style="Card.TLabelframe", **kwargs
        )
    return CTkFrameCompat(parent, style="Card.TFrame", **kwargs)

def create_primary_button(parent: tk.Widget, text: str, command=None, **kwargs) -> ttk.Button:
    return CTkButtonCompat(parent, text=text, command=command, style="Primary.TButton", **kwargs)

def create_secondary_button(parent: tk.Widget, text: str, command=None, **kwargs) -> ttk.Button:
    return CTkButtonCompat(parent, text=text, command=command, style="Secondary.TButton", **kwargs)

def create_ghost_button(parent: tk.Widget, text: str, command=None, **kwargs) -> ttk.Button:
    return CTkButtonCompat(parent, text=text, command=command, style="Ghost.TButton", **kwargs)

def create_danger_button(parent: tk.Widget, text: str, command=None, **kwargs) -> ttk.Button:
    return CTkButtonCompat(parent, text=text, command=command, style="Danger.TButton", **kwargs)

def create_success_button(parent: tk.Widget, text: str, command=None, **kwargs) -> ttk.Button:
    return CTkButtonCompat(parent, text=text, command=command, style="Success.TButton", **kwargs)

def create_warning_button(parent: tk.Widget, text: str, command=None, **kwargs) -> ttk.Button:
    return CTkButtonCompat(parent, text=text, command=command, style="Warning.TButton", **kwargs)

def create_small_button(parent: tk.Widget, text: str, variant: str = "Secondary", command=None, **kwargs) -> ttk.Button:
    style_map = {"Primary": "Small.Primary.TButton", "Secondary": "Small.Secondary.TButton", "Danger": "Small.Danger.TButton", "Ghost": "Small.TButton"}
    return CTkButtonCompat(parent, text=text, command=command, style=style_map.get(variant, "Small.Secondary.TButton"), **kwargs)

def create_large_button(parent: tk.Widget, text: str, variant: str = "Primary", command=None, **kwargs) -> ttk.Button:
    style_map = {"Primary": "Large.Primary.TButton"}
    return CTkButtonCompat(parent, text=text, command=command, style=style_map.get(variant, "Large.Primary.TButton"), **kwargs)

def create_heading_label(parent: tk.Widget, text: str, **kwargs) -> ttk.Label:
    return CTkLabelCompat(parent, text=text, style="Heading.TLabel", **kwargs)

def create_title_label(parent: tk.Widget, text: str, **kwargs) -> ttk.Label:
    return CTkLabelCompat(parent, text=text, style="Title.TLabel", **kwargs)

def create_muted_label(parent: tk.Widget, text: str = None, textvariable=None, **kwargs) -> ttk.Label:
    return CTkLabelCompat(parent, text=text, textvariable=textvariable, style="Muted.TLabel", **kwargs)

def create_caption_label(parent: tk.Widget, text: str, **kwargs) -> ttk.Label:
    return CTkLabelCompat(parent, text=text, style="Caption.TLabel", **kwargs)

def create_status_label(parent: tk.Widget, text: str, status: str = "default", **kwargs) -> ttk.Label:
    style_map = {"success": "Success.TLabel", "warning": "Warning.TLabel", "danger": "Danger.TLabel", "error": "Danger.TLabel", "info": "Info.TLabel", "pending": "Info.TLabel", "online": "Success.TLabel", "offline": "Danger.TLabel"}
    return CTkLabelCompat(parent, text=text, style=style_map.get(status.lower(), "Muted.TLabel"), **kwargs)

def create_treeview(parent: tk.Widget, columns: list, show: str = "headings", compact: bool = False, **kwargs) -> ttk.Treeview:
    style = "Compact.Treeview" if compact else "Treeview"
    return ttk.Treeview(parent, columns=columns, show=show, style=style, **kwargs)

def create_progressbar(parent: tk.Widget, variant: str = "default", **kwargs) -> ctk.CTkProgressBar:
    progress_colors = {
        "success": Colors.SUCCESS,
        "warning": Colors.WARNING,
        "danger": Colors.DANGER,
        "info": Colors.INFO,
    }
    kwargs.setdefault("progress_color", progress_colors.get(variant, Colors.PRIMARY))
    kwargs.setdefault("fg_color", Colors.GRAY_200)
    return CTkProgressBarCompat(parent, **kwargs)

def add_tooltip(widget: tk.Widget, text: str):
    tooltip = None
    def show_tooltip(event):
        nonlocal tooltip
        if tooltip: return
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 5
        tooltip = ctk.CTkToplevel(widget)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{x}+{y}")
        lbl = ctk.CTkLabel(
            tooltip, text=text, fg_color=Colors.GRAY_900,
            text_color=Colors.WHITE, font=FONTS["CAPTION"],
            corner_radius=6,
        )
        lbl.pack()
    def hide_tooltip(event):
        nonlocal tooltip
        if tooltip: tooltip.destroy(); tooltip = None
    widget.bind("<Enter>", show_tooltip)
    widget.bind("<Leave>", hide_tooltip)

def center_window(window: tk.Tk, width: int = None, height: int = None):
    window.update_idletasks()
    if width is None: width = window.winfo_width()
    if height is None: height = window.winfo_height()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    width = min(width, max(320, screen_width - 40))
    height = min(height, max(240, screen_height - 60))
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")

def init_theme(root: tk.Tk) -> ThemeManager:
    return ThemeManager(root)


def enable_windows_high_dpi_awareness() -> bool:
    """Compatibility shim; CustomTkinter applies DPI scaling automatically."""
    return True


if __name__ == "__main__":
    root = ctk.CTk()
    setup_default_fonts(root)
    root.title("SAHARose UI Theme Demo")
    root.geometry("900x700")
    
    theme = init_theme(root)
    
    main_frame = ttk.Frame(root, padding=Spacing.LG)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    create_title_label(main_frame, "SAHARose Sync Master - UI Theme Demo").pack(anchor=tk.W, pady=(0, Spacing.XS))
    create_muted_label(main_frame, "Design System Components Showcase").pack(anchor=tk.W, pady=(0, Spacing.XXL))
    
    create_heading_label(main_frame, "Buttons").pack(anchor=tk.W, pady=(0, Spacing.SM))
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(fill=tk.X, pady=(0, Spacing.LG))
    
    create_primary_button(btn_frame, f"{Icons.PLAY} Primary").pack(side=tk.LEFT, padx=(0, Spacing.SM))
    create_secondary_button(btn_frame, f"{Icons.SETTINGS} Secondary").pack(side=tk.LEFT, padx=(0, Spacing.SM))
    create_ghost_button(btn_frame, f"{Icons.SEARCH} Ghost").pack(side=tk.LEFT, padx=(0, Spacing.SM))
    create_danger_button(btn_frame, f"{Icons.DELETE} Danger").pack(side=tk.LEFT, padx=(0, Spacing.SM))
    create_success_button(btn_frame, f"{Icons.SUCCESS} Success").pack(side=tk.LEFT, padx=(0, Spacing.SM))
    create_warning_button(btn_frame, f"{Icons.WARNING} Warning").pack(side=tk.LEFT, padx=(0, Spacing.SM))
    create_small_button(btn_frame, f"{Icons.EDIT} Small", variant="Primary").pack(side=tk.LEFT, padx=(0, Spacing.SM))
    create_small_button(btn_frame, f"{Icons.DELETE} Small Danger", variant="Danger").pack(side=tk.LEFT, padx=(0, Spacing.SM))
    
    create_heading_label(main_frame, "Cards").pack(anchor=tk.W, pady=(0, Spacing.SM))
    card_frame = ttk.Frame(main_frame)
    card_frame.pack(fill=tk.X, pady=(0, Spacing.LG))


    card1 = create_card(card_frame)
    card1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, Spacing.SM))
    ttk.Label(card1, text="Card Title", font=FONTS["H3"]).pack(anchor=tk.W, padx=Spacing.MD, pady=(Spacing.MD, Spacing.XS))
    ttk.Label(card1, text="Card content goes here with some description text.", style="Muted.TLabel").pack(anchor=tk.W, padx=Spacing.MD, pady=(0, Spacing.SM))
    create_primary_button(card1, f"{Icons.SAVE} Action").pack(anchor=tk.W, padx=Spacing.MD, pady=(0, Spacing.MD))
    
    card2 = create_card(card_frame)
    card2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(Spacing.SM, 0))
    ttk.Label(card2, text="Elevated Card", font=FONTS["H3"]).pack(anchor=tk.W, padx=Spacing.MD, pady=(Spacing.MD, Spacing.XS))
    ttk.Label(card2, text="Elevated card with more visual prominence.", style="Muted.TLabel").pack(anchor=tk.W, padx=Spacing.MD, pady=(0, Spacing.SM))
    create_secondary_button(card2, f"{Icons.SETTINGS} Configure").pack(anchor=tk.W, padx=Spacing.MD, pady=(0, Spacing.MD))
    
    create_heading_label(main_frame, "Status Labels").pack(anchor=tk.W, pady=(0, Spacing.SM))
    status_frame = ttk.Frame(main_frame)
    status_frame.pack(fill=tk.X, pady=(0, Spacing.LG))
    
    create_status_label(status_frame, f"{Icons.ONLINE} Online", "online").pack(side=tk.LEFT, padx=(0, Spacing.MD))
    create_status_label(status_frame, f"{Icons.OFFLINE} Offline", "offline").pack(side=tk.LEFT, padx=(0, Spacing.MD))
    create_status_label(status_frame, f"{Icons.WARNING} Warning", "warning").pack(side=tk.LEFT, padx=(0, Spacing.MD))
    create_status_label(status_frame, f"{Icons.ERROR} Error", "danger").pack(side=tk.LEFT, padx=(0, Spacing.MD))
    create_status_label(status_frame, f"{Icons.INFO} Info", "info").pack(side=tk.LEFT, padx=(0, Spacing.MD))
    create_status_label(status_frame, f"{Icons.PENDING} Pending", "pending").pack(side=tk.LEFT, padx=(0, Spacing.MD))
    
    create_heading_label(main_frame, "Progress Bars").pack(anchor=tk.W, pady=(0, Spacing.SM))
    prog_frame = ttk.Frame(main_frame)
    prog_frame.pack(fill=tk.X, pady=(0, Spacing.LG))
    
    pb1 = create_progressbar(prog_frame, variant="default", value=65, maximum=100)
    pb1.pack(fill=tk.X, pady=(0, Spacing.SM))
    ttk.Label(prog_frame, text="Default Progress: 65%", style="Caption.TLabel").pack(anchor=tk.W)


    pb2 = create_progressbar(prog_frame, variant="success", value=100, maximum=100)
    pb2.pack(fill=tk.X, pady=(Spacing.SM, Spacing.XS))
    ttk.Label(prog_frame, text="Success Progress: 100%", style="Caption.TLabel").pack(anchor=tk.W)
    
    pb3 = create_progressbar(prog_frame, variant="warning", value=75, maximum=100)
    pb3.pack(fill=tk.X, pady=(Spacing.SM, Spacing.XS))
    ttk.Label(prog_frame, text="Warning Progress: 75%", style="Caption.TLabel").pack(anchor=tk.W)
    
    pb4 = create_progressbar(prog_frame, variant="danger", value=30, maximum=100)
    pb4.pack(fill=tk.X, pady=(Spacing.SM, Spacing.XS))
    ttk.Label(prog_frame, text="Danger Progress: 30%", style="Caption.TLabel").pack(anchor=tk.W)
    
    create_heading_label(main_frame, "Form Inputs").pack(anchor=tk.W, pady=(0, Spacing.SM))
    input_frame = ttk.Frame(main_frame)
    input_frame.pack(fill=tk.X, pady=(0, Spacing.LG))
    
    ttk.Label(input_frame, text="Text Input:", style="Label.TLabel").grid(row=0, column=0, sticky=tk.W, pady=Spacing.XS)
    entry = ttk.Entry(input_frame, width=30)
    entry.grid(row=0, column=1, sticky=tk.EW, padx=(Spacing.SM, 0), pady=Spacing.XS, ipady=Spacing.XXS)
    entry.insert(0, "Sample input...")
    
    ttk.Label(input_frame, text="Combobox:", style="Label.TLabel").grid(row=1, column=0, sticky=tk.W, pady=Spacing.XS)
    combo = ttk.Combobox(input_frame, values=["Option 1", "Option 2", "Option 3"], width=28, state="readonly")
    combo.grid(row=1, column=1, sticky=tk.EW, padx=(Spacing.SM, 0), pady=Spacing.XS)
    combo.current(0)
    
    input_frame.columnconfigure(1, weight=1)
    
    create_heading_label(main_frame, "Data Table (Treeview)").pack(anchor=tk.W, pady=(0, Spacing.SM))
    tree_frame = ttk.Frame(main_frame)
    tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, Spacing.LG))
    
    tree = create_treeview(tree_frame, columns=("col1", "col2", "col3", "col4"), show="headings")
    tree.heading("col1", text=f"{Icons.HOSPITAL} Hospital")
    tree.heading("col2", text=f"{Icons.PATIENT} Patients")
    tree.heading("col3", text=f"{Icons.SYNC} Last Sync")
    tree.heading("col4", text=f"{Icons.INFO} Status")
    tree.column("col1", width=200)
    tree.column("col2", width=100, anchor=tk.CENTER)
    tree.column("col3", width=150, anchor=tk.CENTER)
    tree.column("col4", width=120, anchor=tk.CENTER)
    
    sample_data = [
        ("รพ.สต.ตูหยง", "1,234", "2026-11-23 10:30", "Online"),
        ("รพ.สต.สะกอม", "987", "2026-11-23 10:25", "Online"),
        ("รพ.สต.ทุ่งโดน", "2,156", "2026-11-23 09:45", "Warning"),
        ("รพ.สต.หนองไผ่", "543", "2026-11-22 16:30", "Offline"),
    ]
    for row in sample_data:
        tags = ()
        if row[3] == "Offline":
            tags = ("danger",)
        elif row[3] == "Warning":
            tags = ("warning",)
        tree.insert("", tk.END, values=row, tags=tags)
    
    tree.tag_configure("danger", foreground=Colors.DANGER)
    tree.tag_configure("warning", foreground=Colors.WARNING)
    
    y_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=y_scroll.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    
    center_window(root)
    root.mainloop()
