import datetime
import os
import random
import threading
import tkinter as tk
from tkinter import colorchooser, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

import config
import displays
import paths
import platform_info
import startup_manager
import update_checker
import wallpaper_apply
import wallpaper_generator
import wallpaper_setter
from scheduler import DailyScheduler

# Configure CustomTkinter dark appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ==============================================================================
# DESIGN TOKENS: Material 3 Tonal Slate & Minimalist Studio System
# ==============================================================================
COLOR_CANVAS = "#1E2025"          # Main App Background (Warm Slate Charcoal)
COLOR_BARS = "#17191D"            # Top & Bottom Toolbars (Surface Lowest)
COLOR_PANEL = "#252830"           # Major Cards & Stages (Surface)
COLOR_PANEL_ALT = "#202227"       # Distinct Alternate Surface
COLOR_INPUT = "#2E323B"           # Controls, Inputs & Sub-Cards (Surface High)
COLOR_HOVER = "#393D48"           # Interactive Hover / Selected (Surface Highest)
COLOR_BORDER = "#3C404C"          # Structural 1px Divider (Outline Variant)
COLOR_BORDER_FOCUS = "#5A6070"    # Active / Focus Border (Outline)

# Typographic Inks
TEXT_PRIMARY = "#FFFFFF"          # High-emphasis Pure White
TEXT_SECONDARY = "#CCD1DC"        # Medium-emphasis Soft Slate
TEXT_MUTED = "#969BA7"            # Micro-labels & Captions Muted Slate
TEXT_INVERSE = "#17191D"          # Deep Ink for High-contrast White CTA

# Controls & Accent Tokens
ACCENT_PRIMARY = "#FFFFFF"        # Pure Crisp White CTA
ACCENT_PRIMARY_HOVER = "#E6E9EF"  # Subtle off-white hover
CONTROL_TRACK = "#353943"         # Inactive Switch / Slider Base Track
CONTROL_ACTIVE = "#E4E6EB"        # Active Switch Track
CONTROL_KNOB = "#1C1E23"          # Active Switch Knob

# Shared option maps: the segmented/dropdown builders and their change
# handlers both need them, so they live at module scope (single definition).
LAYOUT_MAP = {
    "Reference (10 Col)": "ref_10",
    "Balanced (20 Col)": "balanced_20",
    "Wide Matrix (25 Col)": "matrix_25",
    "Calendar (53 Col)": "calendar_53",
}
QUOTE_MODE_MAP = {
    "Curated Catalog": "preset",
    "Custom Quote": "custom",
    "Daily Random": "daily_random",
}


class YearProgressUI:
    def __init__(self, root, start_minimized=False):
        self.root = root
        self.start_minimized = start_minimized
        
        self.settings = config.load_settings()
        self.quotes_list = config.load_quotes()
        
        # Debounce timer for live preview updates
        self._preview_job = None
        self.preview_image_ref = None
        
        # Window configuration
        self.root.title("Year Progress • Studio Control Center")
        self.root.geometry("1240x820")
        self.root.minsize(1100, 740)
        self.root.configure(fg_color=COLOR_CANVAS)
        
        # Application Icon
        icon_path = os.path.join(paths.resource_dir(), "app_icon.png")
        if os.path.exists(icon_path):
            try:
                self.icon_photo = ImageTk.PhotoImage(file=icon_path)
                self.root.iconphoto(False, self.icon_photo)
            except Exception as e:
                print(f"Failed to set window icon: {e}")
                
        # Intercept close to minimize to system tray
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        
        # Build Studio Layout
        self._build_top_bar()
        self._build_studio_body()
        self._build_bottom_status_bar()
        
        # Initial live preview render
        self.schedule_preview_update(immediate=True)
        self._schedule_countdown_tick()
        
        # Bring window to foreground (unless starting minimized/hidden)
        if not self.start_minimized:
            self.root.lift()
            self.root.focus_force()

    # ==========================================================================
    # 1. TOP COMMAND BAR
    # ==========================================================================
    def _build_top_bar(self):
        top_bar = ctk.CTkFrame(
            self.root, fg_color=COLOR_BARS, height=68, corner_radius=0,
            border_width=1, border_color=COLOR_BORDER
        )
        top_bar.pack(fill="x", side="top")
        top_bar.pack_propagate(False)
        
        # Left Branding
        brand_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        brand_box.pack(side="left", padx=20, pady=10)
        
        lbl_title = ctk.CTkLabel(
            brand_box, text="YEAR PROGRESS",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        lbl_title.pack(side="left")
        
        # Year Badge
        curr_year = datetime.date.today().year
        year_pill = ctk.CTkFrame(
            brand_box, fg_color=COLOR_INPUT, corner_radius=4,
            border_width=1, border_color=COLOR_BORDER
        )
        year_pill.pack(side="left", padx=(12, 0))
        
        lbl_year = ctk.CTkLabel(
            year_pill, text=f"{curr_year} · STUDIO",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_SECONDARY
        )
        lbl_year.pack(padx=8, pady=2)
        
        # Center: Architectural Time Metrics
        today = datetime.date.today()
        day_of_year = today.timetuple().tm_yday
        is_leap = (curr_year % 4 == 0 and (curr_year % 100 != 0 or curr_year % 400 == 0))
        total_days = 366 if is_leap else 365
        days_left = total_days - day_of_year
        pct = (day_of_year / total_days) * 100.0
        
        metrics_capsule = ctk.CTkFrame(
            top_bar, fg_color=COLOR_PANEL, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        metrics_capsule.pack(side="left", expand=True, padx=20)
        
        def add_metric_item(parent, title, val, show_divider=True):
            box = ctk.CTkFrame(parent, fg_color="transparent")
            box.pack(side="left", padx=14, pady=5)
            
            v = ctk.CTkLabel(
                box, text=val,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=TEXT_PRIMARY
            )
            v.pack(anchor="center")
            
            t = ctk.CTkLabel(
                box, text=title,
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=TEXT_MUTED
            )
            t.pack(anchor="center")
            
            if show_divider:
                div = ctk.CTkFrame(parent, width=1, height=22, fg_color=COLOR_BORDER)
                div.pack(side="left")
                
        add_metric_item(metrics_capsule, "DAY OF YEAR", f"{day_of_year} / {total_days}")
        add_metric_item(metrics_capsule, "YEAR PASSED", f"{pct:.1f}%")
        add_metric_item(metrics_capsule, "DAYS REMAINING", f"{days_left}", show_divider=False)
        
        # Right Actions
        actions_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        actions_box.pack(side="right", padx=20, pady=10)
        
        btn_save = ctk.CTkButton(
            actions_box, text="Save Settings",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=COLOR_INPUT, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            text_color=TEXT_PRIMARY, corner_radius=6,
            height=34, width=105,
            command=self.save_settings
        )
        btn_save.pack(side="left", padx=4)
        
        btn_tray = ctk.CTkButton(
            actions_box, text="Minimize",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=COLOR_INPUT, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            text_color=TEXT_PRIMARY, corner_radius=6,
            height=34, width=80,
            command=self.minimize_to_tray
        )
        btn_tray.pack(side="left", padx=4)
        
        btn_apply = ctk.CTkButton(
            actions_box, text="Apply Wallpaper",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_PRIMARY_HOVER,
            text_color=TEXT_INVERSE, corner_radius=6,
            height=34, width=145,
            command=self.apply_wallpaper_now
        )
        btn_apply.pack(side="left", padx=(4, 0))

    # ==========================================================================
    # 2. STUDIO BODY: TWO-PANE ARCHITECTURE
    # ==========================================================================
    def _build_studio_body(self):
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=16)
        
        # ----------------------------------------------------------------------
        # LEFT PANE: Live Canvas Stage (~58% Width)
        # ----------------------------------------------------------------------
        canvas_stage = ctk.CTkFrame(
            body, fg_color=COLOR_PANEL, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        canvas_stage.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._build_canvas_stage(canvas_stage)
        
        # ----------------------------------------------------------------------
        # RIGHT PANE: Precision Inspector Panel (~42% Width)
        # ----------------------------------------------------------------------
        inspector_panel = ctk.CTkFrame(
            body, fg_color=COLOR_PANEL, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER, width=500
        )
        inspector_panel.pack(side="right", fill="both", expand=False)
        inspector_panel.pack_propagate(False)
        self._build_inspector_panel(inspector_panel)

    # ==========================================================================
    # A. CANVAS STAGE (HERO LIVE PREVIEW)
    # ==========================================================================
    def _build_canvas_stage(self, parent):
        # Stage Header
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 8))
        
        lbl_h = ctk.CTkLabel(
            head, text="LIVE WALLPAPER CANVASES",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_SECONDARY
        )
        lbl_h.pack(side="left")
        
        w, h = wallpaper_generator.get_screen_resolution()
        lbl_res = ctk.CTkLabel(
            head, text=f"{w} × {h} (Native)",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=TEXT_MUTED
        )
        lbl_res.pack(side="left", padx=10)
        
        btn_ref = ctk.CTkButton(
            head, text="Refresh Preview",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=COLOR_INPUT, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            corner_radius=4, height=26, width=105,
            command=lambda: self.schedule_preview_update(immediate=True)
        )
        btn_ref.pack(side="right")
        
        # Preview Artboard Bezel
        artboard_box = ctk.CTkFrame(
            parent, fg_color=COLOR_PANEL_ALT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        artboard_box.pack(fill="both", expand=True, padx=16, pady=4)
        
        self.lbl_preview = ctk.CTkLabel(
            artboard_box, text="Rendering live wallpaper...",
            text_color=TEXT_MUTED, font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        self.lbl_preview.pack(expand=True)
        
        # Quick Theme Palette Dock (1-Click Instant Theme Transformation)
        dock_frame = ctk.CTkFrame(parent, fg_color="transparent")
        dock_frame.pack(fill="x", padx=16, pady=(10, 14))
        
        # "Quick Themes:" caption is intentionally not packed (dock pills carry
        # their own labels); keep construction so the widget tree stays stable.
        ctk.CTkLabel(
            dock_frame, text="Quick Themes:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        dock_frame.grid_columnconfigure(0, weight=0)
        
        # Clean Dock of Theme Pills
        theme_keys = list(config.COLOR_THEMES.keys())
        themes_scroll = ctk.CTkScrollableFrame(
            dock_frame, orientation="horizontal", height=42, fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER, scrollbar_button_hover_color=COLOR_BORDER_FOCUS
        )
        themes_scroll.pack(fill="x", side="left", expand=True)
        
        for key in theme_keys:
            t_data = config.COLOR_THEMES[key]
            # Clean pill with theme name
            btn_pill = ctk.CTkButton(
                themes_scroll, text=t_data["name"].split(" (")[0],
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_PRIMARY,
                fg_color=COLOR_INPUT, hover_color=COLOR_HOVER,
                border_width=1, border_color=COLOR_BORDER,
                corner_radius=4, height=28,
                command=lambda k=key: self.apply_theme_preset(k)
            )
            btn_pill.pack(side="left", padx=3)

        # Legend Bar
        legend_bar = ctk.CTkFrame(parent, fg_color="transparent")
        legend_bar.pack(fill="x", side="bottom", padx=16, pady=(0, 10))
        
        leg_text = "● Passed Days     ○ Today (Focus Ring)     · Coming Days"
        lbl_leg = ctk.CTkLabel(
            legend_bar, text=leg_text,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED
        )
        lbl_leg.pack(anchor="center")

    # ==========================================================================
    # B. PRECISION INSPECTOR PANEL
    # ==========================================================================
    def _build_inspector_panel(self, parent):
        # Inspector Navigation Tabs
        nav_box = ctk.CTkFrame(parent, fg_color="transparent")
        nav_box.pack(fill="x", padx=16, pady=(14, 10))
        
        self.nav_tabs = ctk.CTkSegmentedButton(
            nav_box,
            values=["Layout", "Colors", "Quotes", "System"],
            command=self._on_tab_switched,
            selected_color=COLOR_HOVER,
            selected_hover_color=COLOR_BORDER_FOCUS,
            unselected_color=COLOR_INPUT,
            unselected_hover_color=COLOR_HOVER,
            text_color=TEXT_PRIMARY,
            corner_radius=6, height=32,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        )
        self.nav_tabs.set("Layout")
        self.nav_tabs.pack(fill="x")
        
        # Scrollable View Host
        self.tab_host = ctk.CTkFrame(parent, fg_color="transparent")
        self.tab_host.pack(fill="both", expand=True)
        
        self.frame_layout = ctk.CTkScrollableFrame(
            self.tab_host, fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER,
            scrollbar_button_hover_color=COLOR_BORDER_FOCUS
        )
        self.frame_colors = ctk.CTkScrollableFrame(
            self.tab_host, fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER,
            scrollbar_button_hover_color=COLOR_BORDER_FOCUS
        )
        self.frame_quotes = ctk.CTkScrollableFrame(
            self.tab_host, fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER,
            scrollbar_button_hover_color=COLOR_BORDER_FOCUS
        )
        self.frame_system = ctk.CTkScrollableFrame(
            self.tab_host, fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER,
            scrollbar_button_hover_color=COLOR_BORDER_FOCUS
        )
        
        self._build_layout_tab(self.frame_layout)
        self._build_colors_tab(self.frame_colors)
        self._build_quotes_tab(self.frame_quotes)
        self._build_system_tab(self.frame_system)
        
        self.current_tab_frame = self.frame_layout
        self.current_tab_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    def _on_tab_switched(self, tab_name):
        mapping = {
            "Layout": self.frame_layout,
            "Colors": self.frame_colors,
            "Quotes": self.frame_quotes,
            "System": self.frame_system
        }
        target = mapping.get(tab_name, self.frame_layout)
        if target != self.current_tab_frame:
            self.current_tab_frame.pack_forget()
            self.current_tab_frame = target
            self.current_tab_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    # --------------------------------------------------------------------------
    # INSPECTOR TAB 1: LAYOUT & TYPOGRAPHY
    # --------------------------------------------------------------------------
    def _build_layout_tab(self, parent):
        # 1. Typography Selection
        lbl_font = ctk.CTkLabel(
            parent, text="TYPOGRAPHY & FONT",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_font.pack(anchor="w", pady=(4, 4))
        
        self.font_map = {
            "Outfit (Modern Geometric)": "outfit",
            "Montserrat (Architectural)": "montserrat",
            "Inter (Ultra-Clean Technical)": "inter",
            "Cinzel (Stoic Classical)": "cinzel",
            "Bahnschrift (DIN Engineering)": "bahnschrift"
        }
        self.font_map_rev = {v: k for k, v in self.font_map.items()}
        curr_font = self.font_map_rev.get(self.settings.get("font_face", "outfit"), "Outfit (Modern Geometric)")
        
        self.opt_font = ctk.CTkOptionMenu(
            parent, values=list(self.font_map.keys()),
            command=self._on_font_changed,
            fg_color=COLOR_INPUT, button_color=COLOR_HOVER, button_hover_color=COLOR_BORDER_FOCUS,
            dropdown_fg_color=COLOR_PANEL, dropdown_hover_color=COLOR_HOVER,
            dropdown_text_color=TEXT_PRIMARY, text_color=TEXT_PRIMARY,
            height=34, corner_radius=6,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        )
        self.opt_font.set(curr_font)
        self.opt_font.pack(fill="x", pady=(0, 16))
        
        # 2. Grid Arrangement Style
        lbl_grid = ctk.CTkLabel(
            parent, text="GRID ARCHITECTURE",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_grid.pack(anchor="w", pady=(0, 4))
        
        self.layout_map_rev = {v: k for k, v in LAYOUT_MAP.items()}
        current_layout = self.layout_map_rev.get(self.settings.get("layout", "ref_10"), "Reference (10 Col)")
        
        self.seg_layout = ctk.CTkSegmentedButton(
            parent, values=list(LAYOUT_MAP.keys()),
            command=self._on_layout_changed,
            selected_color=COLOR_HOVER, selected_hover_color=COLOR_BORDER_FOCUS,
            unselected_color=COLOR_INPUT, unselected_hover_color=COLOR_HOVER,
            text_color=TEXT_PRIMARY, corner_radius=6, height=32,
            font=ctk.CTkFont(family="Segoe UI", size=10)
        )
        self.seg_layout.set(current_layout)
        self.seg_layout.pack(fill="x", pady=(0, 16))
        
        # 3. Grid Density & Zoom
        lbl_zoom = ctk.CTkLabel(
            parent, text="GRID DENSITY & ZOOM",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_zoom.pack(anchor="w", pady=(0, 4))
        
        zoom_box = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        zoom_box.pack(fill="x", pady=(0, 16))
        
        z_head = ctk.CTkFrame(zoom_box, fg_color="transparent")
        z_head.pack(fill="x", padx=12, pady=(10, 2))
        
        lbl_z_desc = ctk.CTkLabel(
            z_head, text="Dot Scale Multiplier",
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_PRIMARY
        )
        lbl_z_desc.pack(side="left")
        
        curr_zoom = float(self.settings.get("grid_zoom", 1.0))
        self.lbl_zoom_val = ctk.CTkLabel(
            z_head, text=f"{round(curr_zoom * 100)}%",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=TEXT_PRIMARY
        )
        self.lbl_zoom_val.pack(side="right")
        
        slider_frame = ctk.CTkFrame(zoom_box, fg_color="transparent")
        slider_frame.pack(fill="x", padx=12, pady=(2, 6))
        
        self.slider_zoom = ctk.CTkSlider(
            slider_frame, from_=0.5, to=2.0, number_of_steps=30,
            command=self._on_zoom_slider,
            fg_color=COLOR_BORDER, progress_color=COLOR_BORDER_FOCUS,
            button_color=TEXT_PRIMARY, button_hover_color="#FFFFFF",
            height=16
        )
        self.slider_zoom.set(curr_zoom)
        self.slider_zoom.pack(fill="x")
        
        btn_reset_z = ctk.CTkButton(
            zoom_box, text="Reset Default (100%)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            corner_radius=4, height=24, width=120,
            command=self.reset_zoom
        )
        btn_reset_z.pack(anchor="e", padx=12, pady=(0, 10))
        
        # 4. Display Element Toggles
        lbl_el = ctk.CTkLabel(
            parent, text="DISPLAY ELEMENTS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_el.pack(anchor="w", pady=(0, 4))
        
        toggles_card = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        toggles_card.pack(fill="x", pady=(0, 10))
        
        self.sw_ring = ctk.CTkSwitch(
            toggles_card, text="Circular progress ring with percentage",
            command=self._on_option_toggle,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_PRIMARY,
            progress_color=CONTROL_ACTIVE,
            button_color=CONTROL_KNOB,
            fg_color=CONTROL_TRACK,
            button_hover_color=CONTROL_KNOB
        )
        if self.settings.get("show_progress_ring", True):
            self.sw_ring.select()
        self.sw_ring.pack(anchor="w", padx=14, pady=(10, 6))
        
        self.sw_days = ctk.CTkSwitch(
            toggles_card, text="Days remaining text banner",
            command=self._on_option_toggle,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_PRIMARY,
            progress_color=CONTROL_ACTIVE,
            button_color=CONTROL_KNOB,
            fg_color=CONTROL_TRACK,
            button_hover_color=CONTROL_KNOB
        )
        if self.settings.get("show_days_left", True):
            self.sw_days.select()
        self.sw_days.pack(anchor="w", padx=14, pady=6)
        
        self.sw_today = ctk.CTkSwitch(
            toggles_card, text="Highlight today's dot with focus ring",
            command=self._on_option_toggle,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_PRIMARY,
            progress_color=CONTROL_ACTIVE,
            button_color=CONTROL_KNOB,
            fg_color=CONTROL_TRACK,
            button_hover_color=CONTROL_KNOB
        )
        if self.settings.get("highlight_current_day", True):
            self.sw_today.select()
        self.sw_today.pack(anchor="w", padx=14, pady=(6, 10))

    def _on_font_changed(self, choice):
        self.settings["font_face"] = self.font_map.get(choice, "outfit")
        self.schedule_preview_update()

    def _on_layout_changed(self, choice):
        self.settings["layout"] = LAYOUT_MAP.get(choice, "ref_10")
        self.schedule_preview_update()

    def _on_zoom_slider(self, val):
        self.lbl_zoom_val.configure(text=f"{round(float(val) * 100)}%")
        self.settings["grid_zoom"] = round(float(val), 2)
        self.schedule_preview_update()

    def reset_zoom(self):
        self.slider_zoom.set(1.0)
        self.lbl_zoom_val.configure(text="100%")
        self.settings["grid_zoom"] = 1.0
        self.schedule_preview_update()

    def _on_option_toggle(self):
        self.settings["show_progress_ring"] = bool(self.sw_ring.get())
        self.settings["show_days_left"] = bool(self.sw_days.get())
        self.settings["highlight_current_day"] = bool(self.sw_today.get())
        self.schedule_preview_update()

    # --------------------------------------------------------------------------
    # INSPECTOR TAB 2: COLORS & THEMES
    # --------------------------------------------------------------------------
    def _build_colors_tab(self, parent):
        # 1. Preset Library
        lbl_pres = ctk.CTkLabel(
            parent, text="CURATED PALETTE THEMES",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_pres.pack(anchor="w", pady=(4, 4))
        
        themes_grid = ctk.CTkFrame(parent, fg_color="transparent")
        themes_grid.pack(fill="x", pady=(0, 16))
        
        theme_keys = list(config.COLOR_THEMES.keys())
        for idx, key in enumerate(theme_keys):
            t_data = config.COLOR_THEMES[key]
            r = idx // 2
            c = idx % 2
            
            btn_t = ctk.CTkButton(
                themes_grid, text=t_data["name"],
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_PRIMARY,
                fg_color=COLOR_INPUT, hover_color=COLOR_HOVER,
                border_width=1, border_color=COLOR_BORDER,
                corner_radius=6, height=32,
                command=lambda k=key: self.apply_theme_preset(k)
            )
            btn_t.grid(row=r, column=c, padx=3, pady=3, sticky="ew")
        themes_grid.grid_columnconfigure(0, weight=1)
        themes_grid.grid_columnconfigure(1, weight=1)
        
        # 2. Custom Color Matrix
        lbl_cust = ctk.CTkLabel(
            parent, text="CUSTOM COLOR SPECIFICATION",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_cust.pack(anchor="w", pady=(0, 4))
        
        pickers_card = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        pickers_card.pack(fill="x", pady=(0, 10))
        
        self.color_swatches = {}
        self.color_entries = {}
        
        color_rows = [
            ("Background Color", "color_bg"),
            ("Passed Days Dots", "color_passed"),
            ("Today Dot & Focus Ring", "color_current"),
            ("Coming Days Dots", "color_coming"),
            ("Primary Year & Text", "color_text_primary"),
            ("Secondary Text & Quote", "color_text_secondary")
        ]
        
        for idx, (label_text, key) in enumerate(color_rows):
            row_f = ctk.CTkFrame(pickers_card, fg_color="transparent")
            row_f.pack(fill="x", padx=12, pady=5)
            
            lbl = ctk.CTkLabel(
                row_f, text=label_text,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_PRIMARY
            )
            lbl.pack(side="left")
            
            curr_val = self.settings.get(key, "#FFFFFF")
            
            btn_pick = ctk.CTkButton(
                row_f, text="Pick",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                width=52, height=26,
                fg_color=COLOR_HOVER, hover_color=COLOR_BORDER_FOCUS,
                border_width=1, border_color=COLOR_BORDER,
                corner_radius=4,
                command=lambda k=key: self.choose_color_dialog(k)
            )
            btn_pick.pack(side="right", padx=(6, 0))
            
            entry_var = tk.StringVar(value=curr_val)
            entry = ctk.CTkEntry(
                row_f, width=75, height=26,
                textvariable=entry_var,
                font=ctk.CTkFont(family="Consolas", size=10),
                fg_color=COLOR_PANEL,
                border_color=COLOR_BORDER, border_width=1, corner_radius=4,
                text_color=TEXT_PRIMARY
            )
            entry.pack(side="right", padx=6)
            entry.bind("<KeyRelease>", lambda e, k=key, ev=entry_var: self._on_hex_entry_change(k, ev.get()))
            self.color_entries[key] = entry_var
            
            swatch = ctk.CTkFrame(
                row_f, width=24, height=24, corner_radius=4,
                fg_color=curr_val, border_width=1, border_color=COLOR_BORDER_FOCUS
            )
            swatch.pack(side="right")
            swatch.pack_propagate(False)
            self.color_swatches[key] = swatch

    def apply_theme_preset(self, theme_key):
        if theme_key in config.COLOR_THEMES:
            self.settings["color_theme"] = theme_key
            t = config.COLOR_THEMES[theme_key]
            for k, v in t.items():
                if k.startswith("color_"):
                    self.settings[k] = v
                    if k in self.color_entries:
                        self.color_entries[k].set(v)
                    if k in self.color_swatches:
                        self.color_swatches[k].configure(fg_color=v)
            self.schedule_preview_update()

    def choose_color_dialog(self, key):
        initial = self.settings.get(key, "#FFFFFF")
        chosen = colorchooser.askcolor(color=initial, title=f"Select {key.replace('_', ' ').title()}")
        if chosen and chosen[1]:
            hex_code = chosen[1].upper()
            self.settings[key] = hex_code
            if key in self.color_entries:
                self.color_entries[key].set(hex_code)
            if key in self.color_swatches:
                self.color_swatches[key].configure(fg_color=hex_code)
            self.schedule_preview_update()

    def _on_hex_entry_change(self, key, text):
        cleaned = text.strip()
        if (len(cleaned) == 7 and cleaned.startswith("#")) or (len(cleaned) == 6 and not cleaned.startswith("#")):
            if not cleaned.startswith("#"):
                cleaned = "#" + cleaned
            self.settings[key] = cleaned.upper()
            if key in self.color_swatches:
                try:
                    self.color_swatches[key].configure(fg_color=cleaned)
                except Exception as e:
                    print(f"Could not recolor swatch for {key}: {e}")
            self.schedule_preview_update()

    # --------------------------------------------------------------------------
    # INSPECTOR TAB 3: QUOTES & WISDOM
    # --------------------------------------------------------------------------
    def _build_quotes_tab(self, parent):
        # Master Toggle
        self.sw_quote = ctk.CTkSwitch(
            parent, text="Display motivational quote on wallpaper",
            command=self._on_quote_toggle,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_PRIMARY,
            progress_color=CONTROL_ACTIVE,
            button_color=CONTROL_KNOB,
            fg_color=CONTROL_TRACK,
            button_hover_color=CONTROL_KNOB
        )
        if self.settings.get("show_quote", True):
            self.sw_quote.select()
        self.sw_quote.pack(anchor="w", pady=(4, 14))
        
        lbl_mode = ctk.CTkLabel(
            parent, text="QUOTE SOURCE",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_mode.pack(anchor="w", pady=(0, 4))
        
        modes = ["Curated Catalog", "Custom Quote", "Daily Random"]
        mode_val_map = QUOTE_MODE_MAP
        self.mode_val_map_rev = {v: k for k, v in mode_val_map.items()}
        curr_mode = self.mode_val_map_rev.get(self.settings.get("quote_mode", "preset"), "Curated Catalog")
        
        self.seg_quote_mode = ctk.CTkSegmentedButton(
            parent, values=modes, command=self._on_quote_mode_change,
            selected_color=COLOR_HOVER, selected_hover_color=COLOR_BORDER_FOCUS,
            unselected_color=COLOR_INPUT, unselected_hover_color=COLOR_HOVER,
            text_color=TEXT_PRIMARY, corner_radius=6, height=32,
            font=ctk.CTkFont(family="Segoe UI", size=10)
        )
        self.seg_quote_mode.set(curr_mode)
        self.seg_quote_mode.pack(fill="x", pady=(0, 14))
        
        # Mode Panels
        self.panel_curated = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        
        lbl_cur = ctk.CTkLabel(
            self.panel_curated, text="Select from Curated Wisdom:",
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_SECONDARY
        )
        lbl_cur.pack(anchor="w", padx=12, pady=(10, 4))
        
        self.quote_titles = [f'"{q["text"][:55]}..." — {q["author"]}' for q in self.quotes_list]
        curr_p_idx = self.settings.get("preset_index", 0)
        curr_p_idx = max(0, min(curr_p_idx, len(self.quote_titles) - 1))
        
        self.opt_quotes = ctk.CTkOptionMenu(
            self.panel_curated, values=self.quote_titles,
            command=self._on_preset_dropdown_change,
            fg_color=COLOR_PANEL, button_color=COLOR_HOVER, button_hover_color=COLOR_BORDER_FOCUS,
            dropdown_fg_color=COLOR_PANEL, dropdown_hover_color=COLOR_HOVER,
            dropdown_text_color=TEXT_PRIMARY, text_color=TEXT_PRIMARY,
            height=34, corner_radius=6, font=ctk.CTkFont(family="Segoe UI", size=10)
        )
        self.opt_quotes.set(self.quote_titles[curr_p_idx])
        self.opt_quotes.pack(fill="x", padx=12, pady=(0, 8))
        
        btn_rand_quote = ctk.CTkButton(
            self.panel_curated, text="Shuffle Random",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            corner_radius=4, height=26, width=110,
            command=self.pick_random_quote
        )
        btn_rand_quote.pack(anchor="w", padx=12, pady=(0, 10))
        
        # Custom Quote Panel
        self.panel_custom = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        
        lbl_cq = ctk.CTkLabel(
            self.panel_custom, text="Custom Quote Text:",
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_SECONDARY
        )
        lbl_cq.pack(anchor="w", padx=12, pady=(10, 2))
        
        self.txt_custom = ctk.CTkTextbox(
            self.panel_custom, height=70, fg_color=COLOR_PANEL,
            border_color=COLOR_BORDER, border_width=1, corner_radius=6,
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.txt_custom.insert("1.0", self.settings.get("custom_quote", ""))
        self.txt_custom.pack(fill="x", padx=12, pady=(0, 6))
        self.txt_custom.bind("<KeyRelease>", self._on_custom_quote_edit)
        
        lbl_ca = ctk.CTkLabel(
            self.panel_custom, text="Author / Attribution:",
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_SECONDARY
        )
        lbl_ca.pack(anchor="w", padx=12, pady=(0, 2))
        
        self.entry_author_var = tk.StringVar(value=self.settings.get("custom_author", ""))
        self.entry_author = ctk.CTkEntry(
            self.panel_custom, textvariable=self.entry_author_var, height=28,
            fg_color=COLOR_PANEL, border_color=COLOR_BORDER, border_width=1,
            corner_radius=6, text_color=TEXT_PRIMARY, font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.entry_author.pack(fill="x", padx=12, pady=(0, 10))
        self.entry_author.bind("<KeyRelease>", self._on_custom_quote_edit)
        
        # Daily Random Panel
        self.panel_random = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        lbl_rnd = ctk.CTkLabel(
            self.panel_random,
            text="A fresh quote from the curated catalog rotates automatically each midnight.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_SECONDARY, wraplength=420, justify="left"
        )
        lbl_rnd.pack(anchor="w", padx=12, pady=14)
        
        self._refresh_quote_mode_visibility()

    def _refresh_quote_mode_visibility(self):
        mode = self.settings.get("quote_mode", "preset")
        self.panel_curated.pack_forget()
        self.panel_custom.pack_forget()
        self.panel_random.pack_forget()
        
        if mode == "preset":
            self.panel_curated.pack(fill="x", pady=(0, 10))
        elif mode == "custom":
            self.panel_custom.pack(fill="x", pady=(0, 10))
        else:
            self.panel_random.pack(fill="x", pady=(0, 10))

    def _on_quote_toggle(self):
        self.settings["show_quote"] = bool(self.sw_quote.get())
        self.schedule_preview_update()

    def _on_quote_mode_change(self, choice):
        mode_val_map = QUOTE_MODE_MAP
        self.settings["quote_mode"] = mode_val_map.get(choice, "preset")
        self._refresh_quote_mode_visibility()
        self.schedule_preview_update()

    def _on_preset_dropdown_change(self, choice):
        if choice in self.quote_titles:
            idx = self.quote_titles.index(choice)
            self.settings["preset_index"] = idx
            self.schedule_preview_update()

    def pick_random_quote(self):
        idx = random.randint(0, len(self.quotes_list) - 1)
        self.opt_quotes.set(self.quote_titles[idx])
        self.settings["preset_index"] = idx
        self.schedule_preview_update()

    def _on_custom_quote_edit(self, event=None):
        self.settings["custom_quote"] = self.txt_custom.get("1.0", "end-1c").strip()
        self.settings["custom_author"] = self.entry_author_var.get().strip()
        self.schedule_preview_update()

    # --------------------------------------------------------------------------
    # INSPECTOR TAB 4: SYSTEM & AUTOMATION
    # --------------------------------------------------------------------------
    def _build_system_tab(self, parent):
        # 1. Midnight Scheduler
        lbl_sched = ctk.CTkLabel(
            parent, text="AUTOMATION SCHEDULER",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_sched.pack(anchor="w", pady=(4, 4))
        
        sched_card = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        sched_card.pack(fill="x", pady=(0, 14))
        
        self.sw_midnight = ctk.CTkSwitch(
            sched_card, text="Update wallpaper automatically at midnight",
            command=self._on_auto_update_toggle,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_PRIMARY,
            progress_color=CONTROL_ACTIVE,
            button_color=CONTROL_KNOB,
            fg_color=CONTROL_TRACK,
            button_hover_color=CONTROL_KNOB
        )
        if self.settings.get("auto_update_midnight", True):
            self.sw_midnight.select()
        self.sw_midnight.pack(anchor="w", padx=14, pady=(10, 4))
        
        self.lbl_countdown = ctk.CTkLabel(
            sched_card, text="Next midnight update in: calculating...",
            font=ctk.CTkFont(family="Consolas", size=11), text_color=TEXT_SECONDARY
        )
        self.lbl_countdown.pack(anchor="w", padx=14, pady=(0, 10))
        
        # 2. OS Startup
        lbl_boot = ctk.CTkLabel(
            parent, text=platform_info.STARTUP_CARD_HEADER,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_boot.pack(anchor="w", pady=(0, 4))
        
        boot_card = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        boot_card.pack(fill="x", pady=(0, 14))
        
        self.sw_startup = ctk.CTkSwitch(
            boot_card, text=platform_info.STARTUP_SWITCH_TEXT,
            command=self._on_startup_switch,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_PRIMARY,
            progress_color=CONTROL_ACTIVE,
            button_color=CONTROL_KNOB,
            fg_color=CONTROL_TRACK,
            button_hover_color=CONTROL_KNOB
        )
        if startup_manager.is_startup_enabled():
            self.sw_startup.select()
        self.sw_startup.pack(anchor="w", padx=14, pady=(10, 4))
        
        lbl_reg = ctk.CTkLabel(
            boot_card, text=platform_info.STARTUP_NOTE,
            font=ctk.CTkFont(family="Segoe UI", size=10), text_color=TEXT_MUTED
        )
        lbl_reg.pack(anchor="w", padx=14, pady=(0, 10))
        
        # 2b. Lock Screen (Windows only — requires HKLM registry access)
        if platform_info.SUPPORTS_LOCKSCREEN:
            lbl_lock = ctk.CTkLabel(
                parent, text="LOCK SCREEN",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=TEXT_MUTED
            )
            lbl_lock.pack(anchor="w", pady=(0, 4))
            
            lock_card = ctk.CTkFrame(
                parent, fg_color=COLOR_INPUT, corner_radius=6,
                border_width=1, border_color=COLOR_BORDER
            )
            lock_card.pack(fill="x", pady=(0, 14))
            
            btn_lock = ctk.CTkButton(
                lock_card, text="Set Current Wallpaper as Lock Screen",
                command=self._set_lockscreen_now,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color=ACCENT_PRIMARY, hover_color=ACCENT_PRIMARY_HOVER,
                text_color=TEXT_INVERSE
            )
            btn_lock.pack(anchor="w", padx=14, pady=(10, 4))
            
            btn_lock_clear = ctk.CTkButton(
                lock_card, text="Restore Default Lock Screen",
                command=self._clear_lockscreen_now,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                fg_color=COLOR_PANEL, hover_color=COLOR_HOVER,
                text_color=TEXT_SECONDARY
            )
            btn_lock_clear.pack(anchor="w", padx=14, pady=(0, 4))
            
            lbl_lock_hint = ctk.CTkLabel(
                lock_card,
                text="Prompts for administrator permission; applies after you sign out.",
                font=ctk.CTkFont(family="Segoe UI", size=10), text_color=TEXT_MUTED
            )
            lbl_lock_hint.pack(anchor="w", padx=14, pady=(0, 10))
        
        # 2c. Multi-monitor rendering + release updates (Tk parity with the
        # web control panel's System tab)
        lbl_multi = ctk.CTkLabel(
            parent, text="MULTI-MONITOR & UPDATES",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_multi.pack(anchor="w", pady=(0, 4))

        multi_card = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        multi_card.pack(fill="x", pady=(0, 14))

        n_displays = len(displays.list_displays())
        self.sw_multi = ctk.CTkSwitch(
            multi_card,
            text=f"Render one wallpaper per display ({n_displays} detected)",
            command=self._on_multi_monitor_toggle,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_PRIMARY,
            progress_color=CONTROL_ACTIVE,
            button_color=CONTROL_KNOB,
            fg_color=CONTROL_TRACK,
            button_hover_color=CONTROL_KNOB
        )
        if self.settings.get("multi_monitor", True):
            self.sw_multi.select()
        self.sw_multi.pack(anchor="w", padx=14, pady=(10, 4))

        self.sw_checkup = ctk.CTkSwitch(
            multi_card, text="Check GitHub once a day for new versions",
            command=self._on_check_updates_toggle,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_PRIMARY,
            progress_color=CONTROL_ACTIVE,
            button_color=CONTROL_KNOB,
            fg_color=CONTROL_TRACK,
            button_hover_color=CONTROL_KNOB
        )
        if self.settings.get("check_updates", True):
            self.sw_checkup.select()
        self.sw_checkup.pack(anchor="w", padx=14, pady=(4, 4))

        update_row = ctk.CTkFrame(multi_card, fg_color="transparent")
        update_row.pack(fill="x", padx=14, pady=(0, 10))

        btn_check_updates = ctk.CTkButton(
            update_row, text="Check now", width=110,
            command=self._check_updates_now,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=COLOR_PANEL, hover_color=COLOR_HOVER,
            text_color=TEXT_SECONDARY, border_width=1,
            border_color=COLOR_BORDER
        )
        btn_check_updates.pack(side="left")

        self.lbl_update_status = ctk.CTkLabel(
            update_row, text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_SECONDARY, wraplength=380, justify="left"
        )
        self.lbl_update_status.pack(side="left", padx=(12, 0))

        # 3. Hardware Display Info
        w, h = wallpaper_generator.get_screen_resolution()
        lbl_hw = ctk.CTkLabel(
            parent, text="HARDWARE ENVIRONMENT",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED
        )
        lbl_hw.pack(anchor="w", pady=(0, 4))
        
        hw_card = ctk.CTkFrame(
            parent, fg_color=COLOR_INPUT, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        hw_card.pack(fill="x")
        
        lbl_hw_info = ctk.CTkLabel(
            hw_card, text=f"Primary Display: {w} × {h} (High DPI Supersampled)",
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_PRIMARY
        )
        lbl_hw_info.pack(anchor="w", padx=14, pady=10)

    def _on_auto_update_toggle(self):
        self.settings["auto_update_midnight"] = bool(self.sw_midnight.get())

    def _on_multi_monitor_toggle(self):
        self.settings["multi_monitor"] = bool(self.sw_multi.get())

    def _on_check_updates_toggle(self):
        self.settings["check_updates"] = bool(self.sw_checkup.get())

    def _check_updates_now(self):
        self.lbl_update_status.configure(text="Checking GitHub releases…")
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _check_updates_worker(self):
        try:
            info = update_checker.check_now()
        except Exception as e:
            info = {"error": str(e)}
        if "error" in info:
            text = f"Could not reach GitHub ({info['error']})"
        elif info.get("newer"):
            text = f"New release {info['tag']} available (you have {info['current']})"
        else:
            text = f"You're up to date ({info['tag']})"
        self.root.after(
            0, lambda t=text: self.lbl_update_status.configure(text=t)
        )

    def _on_startup_switch(self):
        enable = bool(self.sw_startup.get())
        success, msg = startup_manager.set_startup(enable)
        if success:
            self.var_status.set(f"●  {msg}")
        else:
            messagebox.showerror("Startup Error", msg)
            if startup_manager.is_startup_enabled():
                self.sw_startup.select()
            else:
                self.sw_startup.deselect()

    def _set_lockscreen_now(self):
        threading.Thread(target=self._lockscreen_thread, args=(True,), daemon=True).start()

    def _clear_lockscreen_now(self):
        threading.Thread(target=self._lockscreen_thread, args=(False,), daemon=True).start()

    def _lockscreen_thread(self, set_mode):
        # Runs off the GUI thread; taps back in via root.after. May show a UAC
        # prompt while the app relaunches itself elevated.
        try:
            if set_mode:
                img = wallpaper_generator.current_wallpaper_path()
                if not img:
                    self.root.after(0, lambda: self.var_status.set("●  Apply a wallpaper first."))
                    return
                self.root.after(0, lambda: self.var_status.set("●  Requesting lock screen access..."))
                ok, msg = wallpaper_setter.apply_lockscreen(img)
            else:
                self.root.after(0, lambda: self.var_status.set("●  Restoring default lock screen..."))
                ok, msg = wallpaper_setter.restore_lockscreen()
        except Exception as e:
            ok, msg = False, str(e)
        if ok:
            self.root.after(0, lambda: self.var_status.set(f"●  {msg}"))
        else:
            self.root.after(0, lambda m=msg: self.var_status.set(f"●  {m}"))
            self.root.after(0, lambda m=msg: messagebox.showerror("Lock Screen", m))

    # ==========================================================================
    # 3. BOTTOM STATUS BAR
    # ==========================================================================
    def _build_bottom_status_bar(self):
        bar = ctk.CTkFrame(
            self.root, fg_color=COLOR_BARS, height=36, corner_radius=0,
            border_width=1, border_color=COLOR_BORDER
        )
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        
        self.var_status = tk.StringVar(value="●  Ready • Studio environment active")
        lbl_stat = ctk.CTkLabel(
            bar, textvariable=self.var_status,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_SECONDARY
        )
        lbl_stat.pack(side="left", padx=20)
        
        self.lbl_footer_clock = ctk.CTkLabel(
            bar, text="Daily sync: midnight",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=TEXT_MUTED
        )
        self.lbl_footer_clock.pack(side="right", padx=20)

    # ==========================================================================
    # PREVIEW GENERATION & LIFECYCLE
    # ==========================================================================
    def schedule_preview_update(self, immediate=False):
        """Debounce preview generation so smooth interaction is preserved."""
        if self._preview_job is not None:
            self.root.after_cancel(self._preview_job)
            self._preview_job = None
            
        delay = 0 if immediate else 80
        self._preview_job = self.root.after(delay, self._render_preview)

    def _render_preview(self):
        self._preview_job = None
        try:
            w, h = wallpaper_generator.get_screen_resolution()
            _, prev_path = wallpaper_generator.generate_wallpaper(self.settings, width=w, height=h, preview_only=True)
            if os.path.exists(prev_path):
                img = Image.open(prev_path)
                target_w = 600
                target_h = int(img.size[1] * (target_w / img.size[0]))
                thumb = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                self.preview_image_ref = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(target_w, target_h))
                self.lbl_preview.configure(image=self.preview_image_ref, text="")
        except Exception as e:
            print(f"Error rendering preview: {e}")
            self.lbl_preview.configure(text=f"Preview error: {e}")

    def save_settings(self):
        # config re-reads the volatile keys (stamp, seed, update-check date)
        # from disk under its lock, so this startup-era copy can't revert them.
        if config.save_settings(self.settings, preserve_volatile=True):
            self.var_status.set("●  Settings saved successfully")
        else:
            self.var_status.set("●  Failed to save settings")

    def apply_wallpaper_now(self):
        self.save_settings()
        self.var_status.set("●  Generating and setting wallpaper...")
        self.root.update_idletasks()
        threading.Thread(target=self._apply_wallpaper_worker, daemon=True).start()

    def _apply_wallpaper_worker(self):
        # Runs off the GUI thread; all Tk updates are marshalled via root.after.
        try:
            success, msg, png_path = wallpaper_apply.apply_wallpaper(self.settings)
            now_time = datetime.datetime.now().strftime("%I:%M:%S %p")
            if success:
                config.stamp_rendered_date()
                self.root.after(0, lambda: self.var_status.set(f"●  Wallpaper applied at {now_time}"))
                self.root.after(0, self.schedule_preview_update, True)
            else:
                self.root.after(0, lambda: self.var_status.set(f"●  {msg}"))
                self.root.after(0, lambda m=msg: messagebox.showerror("Wallpaper Error", m))
        except Exception as e:
            err = str(e)
            self.root.after(0, lambda e_=err: self.var_status.set(f"●  Error: {e_}"))
            self.root.after(0, lambda e_=err: messagebox.showerror("Error", f"Failed to generate wallpaper: {e_}"))

    def minimize_to_tray(self):
        self.save_settings()
        self.root.withdraw()
        self.var_status.set("●  Running in background • Minimized to tray")

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.schedule_preview_update(immediate=True)

    def _schedule_countdown_tick(self):
        h, m, s = DailyScheduler.get_time_until_midnight()
        if hasattr(self, "lbl_countdown"):
            self.lbl_countdown.configure(text=f"Next midnight update in: {h:02d}h {m:02d}m {s:02d}s")
        if hasattr(self, "lbl_footer_clock"):
            self.lbl_footer_clock.configure(text=f"Midnight sync: {h:02d}h {m:02d}m {s:02d}s")
        self.root.after(1000, self._schedule_countdown_tick)


if __name__ == "__main__":
    root = ctk.CTk()
    app = YearProgressUI(root)
    root.mainloop()
