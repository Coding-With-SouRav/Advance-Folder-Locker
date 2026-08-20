import configparser
import ctypes
import math
import os
import shutil
import sys
import zipfile
import base64
import secrets
import threading
import json
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFilter
import customtkinter as ctk
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")
LOCK_EXT = ".flock"
SALT_SIZE = 16
ITERATIONS = 390_000
ACCENT = "#7B5CFA"
ACCENT_HOVER = "#6A4AE0"
BG_DARK = "#0F0F14"
CARD_BG = "#1A1A22"
SUCCESS = "#2FC481"
DANGER = "#FF5C5C"
TEXT_MUTED = "#8A8A9A"
HISTORY_FILE = Path.home() / ".FolderLock&Hide" / "config.json"

def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def zip_folder(folder_path: Path, zip_path: Path):

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(folder_path):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(folder_path.parent)
                zf.write(file_path, arcname)

def unzip_to(zip_path: Path, dest_parent: Path):

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_parent)

class FolderLockerApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("VaultLock — Folder Locker")
        self.geometry("820x660")
        self.minsize(820, 660)
        self.configure(fg_color=BG_DARK)

        if sys.platform == "win32":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.example.folderlockerapp")
        self.iconbitmap(True, self.resource_path(r'icons/icon.ico'))
        self.data_dir = os.path.join(os.path.expanduser("~"), ".FolderLock&Hide")
        os.makedirs(self.data_dir, exist_ok=True)
        self.config_file = os.path.join(self.data_dir, 'config.ini')
        self.config = self._load_or_create_config()
        self.master_password = None
        self.load_images()
        self._build_sidebar()
        self._build_main_area()
        self._show_login_screen()
        self._vault_refresh_job = None
        self._schedule_vault_refresh()
        self.load_window_geometry()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def resource_path(self, relative_path):

        try:
            base_path = sys._MEIPASS

        except Exception:
            base_path = os.path.abspath(".")

        if 'icons' in relative_path:
            full_path = os.path.join(base_path, relative_path.replace('\\', os.sep))
        else:
            full_path = os.path.join(base_path, relative_path)

        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Resource not found: {full_path}")
        return full_path

    def load_images(self):
        protected_img = Image.open(self.resource_path(r"icons\protected.png"))
        locker_img = Image.open(self.resource_path(r"icons\locker.png"))
        lock_folder_img = Image.open(self.resource_path(r"icons\locker.png"))
        unlock_img = Image.open(self.resource_path(r"icons\unlock.png"))
        set_img = Image.open(self.resource_path(r"icons\set.png"))
        lock_fd_img = Image.open(self.resource_path(r"icons\lock_folder.png"))
        vault_img = Image.open(self.resource_path(r"icons\vault.png"))
        key_img = Image.open(self.resource_path(r"icons\key.png"))
        unlock_seleced_img = Image.open(self.resource_path(r"icons\unlock_selected.png"))
        settings_img = Image.open(self.resource_path(r"icons\settings.png"))
        change_password_img = Image.open(self.resource_path(r"icons\change_password.png"))
        settings_label_img = Image.open(self.resource_path(r"icons\settings_label.png"))
        self.protected_icon  = ctk.CTkImage(light_image=protected_img, dark_image=protected_img, size=(40, 40))
        self.locker_icon  = ctk.CTkImage(light_image=locker_img, dark_image=locker_img, size=(40, 40))
        self.key_icon  = ctk.CTkImage(light_image=key_img, dark_image=key_img, size=(40, 40))
        self.settings_label_icon  = ctk.CTkImage(light_image=settings_label_img, dark_image=settings_label_img, size=(40, 40))
        self.lock_folder_icon  = ctk.CTkImage(light_image=lock_folder_img, dark_image=lock_folder_img, size=(20, 20))
        self.unlock_icon  = ctk.CTkImage(light_image=unlock_img, dark_image=unlock_img, size=(20, 20))
        self.set_icon  = ctk.CTkImage(light_image=set_img, dark_image=set_img, size=(30, 30))
        self.lock_fd_icon  = ctk.CTkImage(light_image=lock_fd_img, dark_image=lock_fd_img, size=(25, 25))
        self.vault_icon  = ctk.CTkImage(light_image=vault_img, dark_image=vault_img, size=(20, 20))
        self.unlock_seleced_icon  = ctk.CTkImage(light_image=unlock_seleced_img, dark_image=unlock_seleced_img, size=(20, 20))
        self.settings_icon  = ctk.CTkImage(light_image=settings_img, dark_image=settings_img, size=(20, 20))
        self.change_password_icon  = ctk.CTkImage(light_image=change_password_img, dark_image=change_password_img, size=(30, 30))

    def _load_or_create_config(self):

        if HISTORY_FILE.exists():

            with open(HISTORY_FILE, "r") as f:
                config = json.load(f)
            config.setdefault("master_hash", "")
            config.setdefault("master_salt", "")
            config.setdefault("locked_files", [])
            return config
        else:
            return {"master_hash": "", "master_salt": "", "locked_files": []}

    def load_window_geometry(self):

        if os.path.exists(self.config_file):
            config = configparser.ConfigParser()
            config.read(self.config_file)

            if "Geometry" in config:
                geometry = config["Geometry"].get("size", "")
                state = config["Geometry"].get("state", "normal")

                if geometry:
                    self.geometry(geometry)
                    self.update_idletasks()
                    self.update()

                if state == "zoomed":
                    self.state("zoomed")
                elif state == "iconic":
                    self.iconify()

    def save_window_geometry(self):
        config = configparser.ConfigParser()
        config["Geometry"] = {
            "size": self.geometry(),
            "state": self.state()
        }

        with open(self.config_file, "w") as f:
            config.write(f)

    def on_closing(self):
        self.save_window_geometry()
        self.destroy()

    def _save_config(self):

        with open(HISTORY_FILE, "w") as f:
            json.dump(self.config, f, indent=2)

    def _show_login_screen(self):

        if hasattr(self, "login_frame"):
            self.login_frame.destroy()
        self.login_frame = ctk.CTkFrame(self.main, fg_color=BG_DARK, corner_radius=0)
        self.login_frame.pack(fill="both", expand=True)
        card = ctk.CTkFrame(self.login_frame, fg_color=CARD_BG, corner_radius=20,
                            width=460, height=380)
        card.place(relx=0.5, rely=0.5, anchor="center")
        title = ctk.CTkLabel(card, image=self.locker_icon, text="  SET PASSWORD", compound="left", font=ctk.CTkFont(size=28, weight="bold"))
        title.pack(pady=(30, 5))
        ctk.CTkLabel(card, text="Secure folder encryption", font=ctk.CTkFont(size=14), text_color=TEXT_MUTED).pack(pady=(0, 20))
        has_master = bool(self.config.get("master_hash") and self.config.get("master_salt"))

        if not has_master:
            ctk.CTkLabel(card, text="Create a new master password", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 15))
            self.pw_entry = ctk.CTkEntry(card, placeholder_text="Password", show="•", height=40, width=300)
            self.pw_entry.pack(padx=20, pady=5)
            self.confirm_entry = ctk.CTkEntry(card, placeholder_text="Confirm password", show="•", height=40, width=300)
            self.confirm_entry.pack(padx=40, pady=5)
            self.pw_show_var = ctk.BooleanVar(value=False)
            show_btn = ctk.CTkCheckBox(card, text="Show passwords", variable=self.pw_show_var,
                                    command=self._toggle_pw_visibility)
            show_btn.pack(pady=(5, 15))
            self.login_btn = ctk.CTkButton(card,image=self.set_icon, compound = "left", text="Set Password", height=44, width=150,
                                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                        font=ctk.CTkFont(size=14, weight="bold"),
                                        command=self._setup_new_password)
            self.login_btn.pack(pady=5)
            self.login_status = ctk.CTkLabel(card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12))
            self.login_status.pack(pady=(5, 0))
        else:
            title.configure(text="  LOGIN")
            ctk.CTkLabel(card, text="Enter your master password", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 15))
            self.pw_entry = ctk.CTkEntry(card, placeholder_text="Password", show="•", height=40, width=300)
            self.pw_entry.pack(padx=40, pady=5)
            self.confirm_entry = None
            self.pw_show_var = ctk.BooleanVar(value=False)
            show_btn = ctk.CTkCheckBox(card, text="Show password", variable=self.pw_show_var,
                                    command=self._toggle_pw_visibility)
            show_btn.pack(pady=(5, 15))
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(pady=5)
            self.login_btn = ctk.CTkButton(btn_frame, image=self.unlock_icon, compound="left", text="Unlock Vault", height=44, width=160,
                                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                        font=ctk.CTkFont(size=14, weight="bold"),
                                        command=self._authenticate)
            self.login_btn.pack(side="left", padx=5)
            self.forgot_btn = ctk.CTkButton(btn_frame, text="Forgot Password?", width=120, height=44,
                                            fg_color="transparent", text_color='red',
                                            hover_color="#25252F", font=ctk.CTkFont(size=12),
                                            command=self._forgot_password)
            self.forgot_btn.pack(side="left", padx=5)
            self.login_status = ctk.CTkLabel(card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12))
            self.login_status.pack(pady=(5, 0))
        self.pw_entry.bind("<Return>", lambda e: self.login_btn.invoke())

    def _forgot_password(self):
        result = messagebox.askyesno(
            "Reset Master Password",
            " Resetting your master password will permanently prevent you from unlocking any currently locked folders.\n\n"
            "All locked files will remain encrypted and cannot be recovered without the original password.\n\n"
            "Are you sure you want to continue?",
            icon='warning'
        )

        if result:
            self.config["master_hash"] = ""
            self.config["master_salt"] = ""
            self.config["locked_files"] = []
            self._save_config()
            self.master_password = None
            self._show_login_screen()

            if hasattr(self, "login_status"):
                self.login_status.configure(text="", text_color=TEXT_MUTED)

    def _toggle_pw_visibility(self):
        show = self.pw_show_var.get()
        self.pw_entry.configure(show="" if show else "•")

        if self.confirm_entry:
            self.confirm_entry.configure(show="" if show else "•")

    def _setup_new_password(self):
        pw = self.pw_entry.get()
        confirm = self.confirm_entry.get() if self.confirm_entry else ""

        if len(pw) < 6:
            self.login_status.configure(text="Password must be at least 6 characters.", text_color=DANGER)
            return

        if pw != confirm:
            self.login_status.configure(text="Passwords do not match.", text_color=DANGER)
            return
        self.master_password = pw
        salt = secrets.token_bytes(SALT_SIZE)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
        hash_val = kdf.derive(pw.encode())
        self.config["master_hash"] = base64.b64encode(hash_val).decode()
        self.config["master_salt"] = base64.b64encode(salt).decode()
        self.config["locked_files"] = []
        self._save_config()
        self._login_success()

    def _authenticate(self):
        pw = self.pw_entry.get()

        if not pw:
            self.login_status.configure(text="Please enter your password.", text_color=DANGER)
            return
        stored_hash = base64.b64decode(self.config["master_hash"])
        stored_salt = base64.b64decode(self.config["master_salt"])
        test_key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=stored_salt, iterations=ITERATIONS)
        test_hash = test_key.derive(pw.encode())

        if test_hash != stored_hash:
            self.login_status.configure(text="Incorrect master password.", text_color=DANGER)
            return
        self.master_password = pw
        self._login_success()

    def _login_success(self):
        self.login_frame.destroy()
        self._show_nav_buttons()
        self.show_lock_view()
        self._refresh_vault()

    def _add_locked_file(self, path: Path):
        abs_path = str(path.absolute())

        if abs_path not in self.config["locked_files"]:
            self.config["locked_files"].append(abs_path)
            self._save_config()

    def _remove_locked_file(self, path: Path):
        abs_path = str(path.absolute())

        if abs_path in self.config["locked_files"]:
            self.config["locked_files"].remove(abs_path)
            self._save_config()

    def _cleanup_missing_files(self):

        if "locked_files" not in self.config:
            self.config["locked_files"] = []
            self._save_config()
            return
        removed = False
        for path_str in self.config["locked_files"][:]:

            if not Path(path_str).exists():
                self.config["locked_files"].remove(path_str)
                removed = True

        if removed:
            self._save_config()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=240, corner_radius=10, fg_color=CARD_BG)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ctk.CTkLabel(sidebar,image=self.protected_icon, text="  Folder Locker", compound="left",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(30, 5), padx=20, anchor="w")
        ctk.CTkLabel(sidebar, text="Secure folder encryption",
                     font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(pady=(0, 30), padx=40, anchor="w")
        self.lock_nav_btn = ctk.CTkButton(
            sidebar,image = self.lock_folder_icon, compound="left", text="  Lock Folder", anchor="w", height=44,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"), command=self.show_lock_view)
        self.lock_nav_btn.pack(pady=6, padx=20, fill="x")
        self.vault_nav_btn = ctk.CTkButton(
            sidebar, image = self.vault_icon, compound="left", text="  Vault", anchor="w", height=44,
            fg_color="transparent", hover_color=ACCENT_HOVER, corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"), command=self.show_vault_view)
        self.vault_nav_btn.pack(pady=6, padx=20, fill="x")
        self.unlock_nav_btn = ctk.CTkButton(
            sidebar,image=self.unlock_seleced_icon, text="  Unlock Folder", anchor="w", height=44,
            fg_color="transparent", hover_color=ACCENT_HOVER, corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"), command=self.show_unlock_view)
        self.unlock_nav_btn.pack(pady=6, padx=20, fill="x")
        self.settings_nav_btn = ctk.CTkButton(
            sidebar, image=self.settings_icon, compound="left", text="  Settings", anchor="w", height=44,
            fg_color="transparent", hover_color=ACCENT_HOVER, corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"), command=self.show_settings_view)
        self.settings_nav_btn.pack(pady=6, padx=20, fill="x")
        self.lock_nav_btn.pack_forget()
        self.vault_nav_btn.pack_forget()
        self.unlock_nav_btn.pack_forget()
        self.settings_nav_btn.pack_forget()

    def _show_nav_buttons(self):
        self.lock_nav_btn.pack(pady=6, padx=20, fill="x")
        self.vault_nav_btn.pack(pady=6, padx=20, fill="x")
        self.unlock_nav_btn.pack(pady=6, padx=20, fill="x")
        self.settings_nav_btn.pack(pady=6, padx=20, fill="x")

    def _build_main_area(self):
        self.main = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        self.main.pack(side="left", fill="both", expand=True)
        self.lock_view = self._build_lock_view(self.main)
        self.unlock_view = self._build_unlock_view(self.main)
        self.vault_view = self._build_vault_view(self.main)
        self.settings_view = self._build_settings_view(self.main)

    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=16)

    def _build_lock_view(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(frame, image = self.locker_icon, compound="left",  text="  Lock a Folder",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w", padx=40, pady=(40, 4))
        ctk.CTkLabel(frame, text="Encrypt and hide a folder behind your master password.",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=40, pady=(0, 20))
        card = self._card(frame)
        card.pack(padx=40, fill="x")
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=24, pady=(24, 10))
        self.lock_path_entry = ctk.CTkEntry(row1, placeholder_text="No folder selected", height=42, corner_radius=10)
        self.lock_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(row1, text="Browse", width=100, height=42, corner_radius=10,
                      fg_color="#25252F", hover_color="#32323F",
                      command=self.browse_folder_to_lock).pack(side="left")
        self.lock_progress = ctk.CTkProgressBar(card, progress_color=ACCENT)
        self.lock_progress.set(0)
        self.lock_progress.pack(fill="x", padx=24, pady=(10, 0))
        self.lock_status = ctk.CTkLabel(card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12))
        self.lock_status.pack(anchor="w", padx=24, pady=(8, 0))
        ctk.CTkButton(card,image=self.lock_fd_icon, compound="left", text="  Lock Folder", height=46, corner_radius=10,
                     fg_color=ACCENT, hover_color=ACCENT_HOVER,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     command=self.start_lock_folder).pack(fill="x", padx=24, pady=(16, 24))
        ctk.CTkLabel(frame, text="⚠  Forgetting your master password means permanent data loss. There is no recovery.",
                    text_color=DANGER, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=40, pady=(16, 0))
        return frame

    def _build_unlock_view(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(frame, text="Unlock a Folder",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w", padx=40, pady=(40, 4))
        ctk.CTkLabel(frame, text="Select a .flock file and restore it using your master password.",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=40, pady=(0, 20))
        card = self._card(frame)
        card.pack(padx=40, fill="x")
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=24, pady=(24, 10))
        self.unlock_path_entry = ctk.CTkEntry(row1, placeholder_text="No file selected", height=42, corner_radius=10)
        self.unlock_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(row1, text="Browse", width=100, height=42, corner_radius=10,
                     fg_color="#25252F", hover_color="#32323F",
                     command=self.browse_file_to_unlock).pack(side="left")
        self.unlock_progress = ctk.CTkProgressBar(card, progress_color=SUCCESS)
        self.unlock_progress.set(0)
        self.unlock_progress.pack(fill="x", padx=24, pady=(10, 0))
        self.unlock_status = ctk.CTkLabel(card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12))
        self.unlock_status.pack(anchor="w", padx=24, pady=(8, 0))
        ctk.CTkButton(card,image=self.unlock_seleced_icon, text="  Unlock Folder", height=46, corner_radius=10,
                     fg_color=SUCCESS, hover_color="#33B87C",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     command=self.start_unlock_folder).pack(fill="x", padx=24, pady=(16, 24))
        return frame

    def _build_vault_view(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(frame,image=self.key_icon,compound="left", text="Vault",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w", padx=40, pady=(40, 4))
        ctk.CTkLabel(frame, text="All your locked folders - select one to unlock.",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=40, pady=(0, 20))
        card = self._card(frame)
        card.pack(padx=40,pady=(0,40), fill="both", expand=True)
        tree_frame = ctk.CTkFrame(card, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=20, pady=(20, 10))
        self.vault_tree = ttk.Treeview(tree_frame, columns=("path",), show="headings", height=12)
        self.vault_tree.heading("path", text="Locked Folder Path")
        self.vault_tree.column("path", anchor="w", width=400)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background=BG_DARK,
                        foreground="white",
                        fieldbackground=BG_DARK,
                        font = ("arial",12),
                        borderwidth=0)
        style.map('Treeview',
                  background=[('selected', ACCENT)],
                  foreground=[('selected', 'white')])
        style.configure("Treeview.Heading",
                        background=CARD_BG,
                        foreground="cyan",
                        font = ("Arial",14),
                        padding =(5,5),
                        relief="flat")
        style.map("Treeview.Heading",
                    background=[('active', CARD_BG)],
                    foreground=[('active', 'white')])
        self.vault_scrollbar = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=self.vault_tree.yview)
        self.vault_tree.configure(yscrollcommand=self.vault_scrollbar.set)
        self.vault_tree.pack(side="left", fill="both", expand=True)
        self.vault_scrollbar.pack(side="right", fill="y")
        self.vault_tree.bind("<Double-1>", lambda e: self._unlock_from_vault())
        self.vault_progress = ctk.CTkProgressBar(card, progress_color=SUCCESS)
        self.vault_progress.set(0)
        self.vault_progress.pack(fill="x", padx=20, pady=(10, 0))
        self.vault_status = ctk.CTkLabel(card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12))
        self.vault_status.pack(anchor="w", padx=20, pady=(8, 0))
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 20))
        ctk.CTkButton(btn_frame,image = self.unlock_seleced_icon, text="  Unlock Selected", height=40, corner_radius=10,
                      fg_color=SUCCESS, hover_color="#33B87C",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      command=self._unlock_from_vault).pack(side="left")
        ctk.CTkLabel(btn_frame, text="(or double-click a file)", text_color=TEXT_MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(15, 0))
        return frame

    def _build_settings_view(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(frame, image=self.settings_label_icon, compound="left", text="  Settings",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w", padx=40, pady=(40, 4))
        ctk.CTkLabel(frame, text="Change your master password. All locked folders will be re‑encrypted automatically.",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=40, pady=(0, 20))
        card = self._card(frame)
        card.pack(padx=40, fill="x")
        ctk.CTkLabel(card, text="Current Password", font=ctk.CTkFont(size=13), anchor="w").pack(anchor="w", padx=24, pady=(20, 4))
        self.settings_old_entry = ctk.CTkEntry(card, placeholder_text="Enter current password", show="•", height=40)
        self.settings_old_entry.pack(padx=24, pady=(0, 10), fill="x")
        ctk.CTkLabel(card, text="New Password", font=ctk.CTkFont(size=13), anchor="w").pack(anchor="w", padx=24, pady=(10, 4))
        self.settings_new_entry = ctk.CTkEntry(card, placeholder_text="Enter new password (min 6 chars)", show="•", height=40)
        self.settings_new_entry.pack(padx=24, pady=(0, 10), fill="x")
        ctk.CTkLabel(card, text="Confirm New Password", font=ctk.CTkFont(size=13), anchor="w").pack(anchor="w", padx=24, pady=(10, 4))
        self.settings_confirm_entry = ctk.CTkEntry(card, placeholder_text="Re-enter new password", show="•", height=40)
        self.settings_confirm_entry.pack(padx=24, pady=(0, 10), fill="x")
        self.settings_show_var = ctk.BooleanVar(value=False)
        show_btn = ctk.CTkCheckBox(card, text="Show passwords", variable=self.settings_show_var,
                                   command=self._toggle_settings_pw_visibility)
        show_btn.pack(anchor="w", padx=24, pady=(0, 16))
        self.settings_progress = ctk.CTkProgressBar(card, progress_color=ACCENT)
        self.settings_progress.set(0)
        self.settings_progress.pack(fill="x", padx=24, pady=(0, 8))
        self.settings_status = ctk.CTkLabel(card, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=12))
        self.settings_status.pack(anchor="w", padx=24, pady=(0, 8))
        self.settings_change_btn = ctk.CTkButton(card, image=self.change_password_icon, compound="left", text="  Change Password",
                      height=46, corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      command=self._change_password)
        self.settings_change_btn.pack(fill="x", padx=24, pady=(8, 24))
        ctk.CTkLabel(frame, text="⚠  Changing your password will re-encrypt every locked folder with the new password.\n Dont worry there is no data loss.",
                     text_color=SUCCESS, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=40, pady=(16, 0))
        return frame

    def _toggle_settings_pw_visibility(self):
        show = self.settings_show_var.get()
        self.settings_old_entry.configure(show="" if show else "•")
        self.settings_new_entry.configure(show="" if show else "•")
        self.settings_confirm_entry.configure(show="" if show else "•")

    def _change_password(self):
        old = self.settings_old_entry.get()
        new = self.settings_new_entry.get()
        confirm = self.settings_confirm_entry.get()

        if not old:
            self.settings_status.configure(text="Please enter your current password.", text_color=DANGER)
            return
        stored_hash = base64.b64decode(self.config["master_hash"])
        stored_salt = base64.b64decode(self.config["master_salt"])
        test_key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=stored_salt, iterations=ITERATIONS)
        test_hash = test_key.derive(old.encode())

        if test_hash != stored_hash:
            self.settings_status.configure(text="Current password is incorrect.", text_color=DANGER)
            return

        if len(new) < 6:
            self.settings_status.configure(text="New password must be at least 6 characters.", text_color=DANGER)
            return

        if new != confirm:
            self.settings_status.configure(text="New passwords do not match.", text_color=DANGER)
            return
        self.settings_change_btn.configure(state="disabled")
        self.settings_status.configure(text="Re-encrypting locked files…", text_color=TEXT_MUTED)
        self.settings_progress.set(0)

        def reencrypt_worker():

            try:
                self._cleanup_missing_files()
                locked_paths = self.config.get("locked_files", [])
                total = len(locked_paths)
                self.after(0, lambda: self.settings_progress.set(0))
                for idx, path_str in enumerate(locked_paths):
                    lock_file = Path(path_str)

                    if not lock_file.exists():
                        continue

                    with open(lock_file, "rb") as f:
                        raw = f.read()
                    salt_old = raw[:SALT_SIZE]
                    encrypted_data = raw[SALT_SIZE:]
                    key_old = derive_key(old, salt_old)
                    fernet_old = Fernet(key_old)

                    try:
                        data = fernet_old.decrypt(encrypted_data)

                    except InvalidToken:
                        self.after(0, lambda: self.settings_status.configure(
                            text=f"Decryption failed for {lock_file.name}. Aborting.", text_color=DANGER))
                        return
                    salt_new = secrets.token_bytes(SALT_SIZE)
                    key_new = derive_key(new, salt_new)
                    fernet_new = Fernet(key_new)
                    encrypted_new = fernet_new.encrypt(data)

                    with open(lock_file, "wb") as f:
                        f.write(salt_new + encrypted_new)
                    progress = (idx + 1) / total
                    self.after(0, lambda p=progress: self.settings_progress.set(p))
                salt = secrets.token_bytes(SALT_SIZE)
                kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
                hash_val = kdf.derive(new.encode())
                self.config["master_hash"] = base64.b64encode(hash_val).decode()
                self.config["master_salt"] = base64.b64encode(salt).decode()
                self._save_config()
                self.master_password = new
                self.after(0, self._password_change_success)

            except Exception as e:
                self.after(0, lambda: self._password_change_fail(str(e)))
        threading.Thread(target=reencrypt_worker, daemon=True).start()

    def _password_change_success(self):
        self.settings_status.configure(text="Password changed and all files re-encrypted successfully!", text_color=SUCCESS)
        self.settings_progress.set(1.0)
        self.settings_change_btn.configure(state="normal")
        self.settings_old_entry.delete(0, "end")
        self.settings_new_entry.delete(0, "end")
        self.settings_confirm_entry.delete(0, "end")
        messagebox.showinfo("Folder Locker", "Master password changed.\nAll locked folders have been re‑encrypted with the new password.")

    def _password_change_fail(self, msg):
        self.settings_status.configure(text=f"Error: {msg}", text_color=DANGER)
        self.settings_progress.set(0)
        self.settings_change_btn.configure(state="normal")
        messagebox.showerror("Folder Locker", f"Password change failed: {msg}")

    def show_lock_view(self):
        self.unlock_view.pack_forget()
        self.vault_view.pack_forget()
        self.settings_view.pack_forget()
        self.lock_view.pack(fill="both", expand=True)
        self.lock_nav_btn.configure(fg_color=ACCENT)
        self.unlock_nav_btn.configure(fg_color="transparent")
        self.vault_nav_btn.configure(fg_color="transparent")
        self.settings_nav_btn.configure(fg_color="transparent")

    def show_unlock_view(self):
        self.lock_view.pack_forget()
        self.vault_view.pack_forget()
        self.settings_view.pack_forget()
        self.unlock_view.pack(fill="both", expand=True)
        self.unlock_nav_btn.configure(fg_color=ACCENT)
        self.lock_nav_btn.configure(fg_color="transparent")
        self.vault_nav_btn.configure(fg_color="transparent")
        self.settings_nav_btn.configure(fg_color="transparent")

    def show_vault_view(self):
        self.lock_view.pack_forget()
        self.unlock_view.pack_forget()
        self.settings_view.pack_forget()
        self.vault_view.pack(fill="both", expand=True)
        self.vault_nav_btn.configure(fg_color=ACCENT)
        self.lock_nav_btn.configure(fg_color="transparent")
        self.unlock_nav_btn.configure(fg_color="transparent")
        self.settings_nav_btn.configure(fg_color="transparent")
        self._refresh_vault()

    def show_settings_view(self):
        self.lock_view.pack_forget()
        self.unlock_view.pack_forget()
        self.vault_view.pack_forget()
        self.settings_view.pack(fill="both", expand=True)
        self.settings_nav_btn.configure(fg_color=ACCENT)
        self.lock_nav_btn.configure(fg_color="transparent")
        self.unlock_nav_btn.configure(fg_color="transparent")
        self.vault_nav_btn.configure(fg_color="transparent")
        self.settings_status.configure(text="", text_color=TEXT_MUTED)
        self.settings_progress.set(0)

    def _refresh_vault(self):
        self._cleanup_missing_files()
        for item in self.vault_tree.get_children():
            self.vault_tree.delete(item)
        locked_paths = self.config.get("locked_files", [])

        if not locked_paths:
            self.vault_tree.insert("", "end", values=("No locked files found in vault",))
        else:
            for p in sorted(locked_paths):
                self.vault_tree.insert("", "end", values=(p,))

    def _schedule_vault_refresh(self):

        if hasattr(self, "vault_view") and self.vault_view.winfo_ismapped():
            self._refresh_vault()
        self._vault_refresh_job = self.after(5000, self._schedule_vault_refresh)

    def _unlock_from_vault(self):
        selected = self.vault_tree.selection()

        if not selected:
            messagebox.showerror("Folder Locker", "Please select a locked file from the list.")
            return
        item = selected[0]
        values = self.vault_tree.item(item, "values")

        if not values or values[0].startswith("No locked files"):
            return
        filepath = Path(values[0])

        if not filepath.exists() or filepath.suffix != LOCK_EXT:
            messagebox.showerror("Folder Locker", "Selected file is not valid.")
            return

        if self.master_password is None:
            messagebox.showerror("Folder Locker", "Master password not set. Please restart app.")
            return
        self.vault_status.configure(text="Unlocking…", text_color=TEXT_MUTED)
        self.vault_progress.set(0.1)
        threading.Thread(target=self._unlock_worker,
                         args=(filepath, self.vault_progress, self.vault_status),
                         daemon=True).start()

    def browse_folder_to_lock(self):
        path = filedialog.askdirectory(title="Select folder to lock")

        if path:
            self.lock_path_entry.delete(0, "end")
            self.lock_path_entry.insert(0, path)

    def browse_file_to_unlock(self):
        path = filedialog.askopenfilename(title="Select locked file",
                                           filetypes=[("VaultLock files", f"*{LOCK_EXT}")])

        if path:
            self.unlock_path_entry.delete(0, "end")
            self.unlock_path_entry.insert(0, path)

    def start_lock_folder(self):
        folder_text = self.lock_path_entry.get().strip()

        if not folder_text:
            messagebox.showerror("Folder Locker", "Please select a folder first.")
            return
        folder = Path(folder_text)

        if not folder.exists() or not folder.is_dir():
            messagebox.showerror("Folder Locker", "Selected folder does not exist.")
            return

        if self.master_password is None:
            messagebox.showerror("Folder Locker", "Master password not set. Please restart app.")
            return
        target = Path(str(folder) + LOCK_EXT)

        if target.exists():
            messagebox.showerror("Folder Locker", "A locked file already exists for this folder.")
            return
        self.lock_status.configure(text="Locking…", text_color=TEXT_MUTED)
        self.lock_progress.set(0.1)
        threading.Thread(target=self._lock_worker, args=(folder, target, self.lock_progress, self.lock_status), daemon=True).start()

    def _lock_worker(self, folder: Path, target: Path, progress_bar, status_label):

        try:
            tmp_zip = target.with_suffix(target.suffix + ".tmp")
            self._set_progress(progress_bar, 0.3, status_label, "Compressing folder…")
            zip_folder(folder, tmp_zip)
            self._set_progress(progress_bar, 0.6, status_label, "Encrypting…")
            salt = secrets.token_bytes(SALT_SIZE)
            key = derive_key(self.master_password, salt)
            fernet = Fernet(key)

            with open(tmp_zip, "rb") as f:
                data = f.read()
            encrypted = fernet.encrypt(data)

            with open(target, "wb") as f:
                f.write(salt + encrypted)
            tmp_zip.unlink(missing_ok=True)
            self._set_progress(progress_bar, 0.9, status_label, "Removing original folder…")
            shutil.rmtree(folder)
            self._set_progress(progress_bar, 1.0, status_label, f"Locked ✔  →  {target.name}")
            self._add_locked_file(target)
            self.after(0, self._success_reset_lock_form)

        except Exception as e:
            self.after(0, lambda: self._fail(status_label, progress_bar, str(e)))

    def _success_reset_lock_form(self):
        self.lock_path_entry.delete(0, "end")
        messagebox.showinfo("Folder Locker", "Folder locked successfully.")

    def start_unlock_folder(self):
        file_text = self.unlock_path_entry.get().strip()

        if not file_text:
            messagebox.showerror("Folder Locker", "Please select a locked file first.")
            return
        lockfile = Path(file_text)

        if not lockfile.exists() or lockfile.suffix != LOCK_EXT:
            messagebox.showerror("Folder Locker", "Please select a valid .flock file.")
            return

        if self.master_password is None:
            messagebox.showerror("Folder Locker", "Master password not set. Please restart app.")
            return
        self.unlock_status.configure(text="Unlocking…", text_color=TEXT_MUTED)
        self.unlock_progress.set(0.1)
        threading.Thread(target=self._unlock_worker,
                         args=(lockfile, self.unlock_progress, self.unlock_status),
                         daemon=True).start()

    def _unlock_worker(self, lockfile: Path, progress_bar, status_label):

        try:
            self._set_progress(progress_bar, 0.3, status_label, "Reading file…")

            with open(lockfile, "rb") as f:
                raw = f.read()
            salt, encrypted = raw[:SALT_SIZE], raw[SALT_SIZE:]
            key = derive_key(self.master_password, salt)
            fernet = Fernet(key)
            self._set_progress(progress_bar, 0.5, status_label, "Decrypting…")

            try:
                data = fernet.decrypt(encrypted)

            except InvalidToken:
                self.after(0, lambda: self._fail(status_label, progress_bar, "Incorrect master password."))
                return
            tmp_zip = lockfile.with_suffix(".tmp.zip")

            with open(tmp_zip, "wb") as f:
                f.write(data)
            self._set_progress(progress_bar, 0.8, status_label, "Restoring folder…")
            unzip_to(tmp_zip, lockfile.parent)
            tmp_zip.unlink(missing_ok=True)
            folder_name = lockfile.stem
            folder_path = lockfile.parent / folder_name

            if not folder_path.exists():
                folder_path.mkdir()
            lockfile.unlink(missing_ok=True)
            self._set_progress(progress_bar, 1.0, status_label, "Unlocked ✔")
            self._remove_locked_file(lockfile)
            self.after(0, self._success_reset_unlock_form)

            if self.vault_view.winfo_ismapped():
                self.after(500, self._refresh_vault)

        except Exception as e:
            self.after(0, lambda: self._fail(status_label, progress_bar, str(e)))

    def _success_reset_unlock_form(self):
        self.unlock_path_entry.delete(0, "end")
        messagebox.showinfo("Folder Locker", "Folder unlocked successfully.")

    def _set_progress(self, bar, value, label, text):
        self.after(0, lambda: (bar.set(value), label.configure(text=text, text_color=TEXT_MUTED)))

    def _fail(self, label, bar, msg):
        bar.set(0)
        label.configure(text=f"✖ {msg}", text_color=DANGER)
        messagebox.showerror("Folder Locker", msg)

if __name__ == "__main__":
    app = FolderLockerApp()
    app.mainloop()
