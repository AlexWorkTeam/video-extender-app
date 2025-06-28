import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
import tkinter as tk
from tkinter import filedialog, messagebox
import json
import subprocess
import platform
import threading
import locale
import os
import re
import time

class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("YouTube Timestamp Generator")
        self.geometry("700x800")

        self.audio_paths = []
        
        self.load_locales()
        self.setup_ui()
        self.update_ui_texts()

    def load_locales(self):
        try:
            with open("locales.json", "r", encoding="utf-8") as f:
                self.locales = json.load(f)
        except FileNotFoundError:
            messagebox.showerror("Error", "locales.json not found!")
            self.destroy()
            return
        
        system_lang = locale.getdefaultlocale()[0][:2]
        self.available_langs = list(self.locales.keys())
        self.current_lang = system_lang if system_lang in self.available_langs else "en"

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1) # Audio frame
        self.grid_rowconfigure(3, weight=1) # Timestamp frame

        self.lang_var = ctk.StringVar(value=self.current_lang.upper())
        self.lang_menu = ctk.CTkOptionMenu(self, values=[lang.upper() for lang in self.available_langs],
                                           variable=self.lang_var, command=self.change_language)
        self.lang_menu.grid(row=0, column=0, padx=10, pady=10, sticky="ne")

        # --- Audio Selection ---
        self.audio_frame = ctk.CTkFrame(self)
        self.audio_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.audio_frame.grid_columnconfigure(0, weight=1)
        
        self.audio_list_label = ctk.CTkLabel(self.audio_frame, text="Audio Tracks:")
        self.audio_list_label.pack(padx=10, pady=5, anchor="w")
        
        self.audio_listbox = tk.Listbox(self.audio_frame, height=8)
        self.audio_listbox.pack(padx=10, pady=5, fill="both", expand=True)

        self.audio_buttons_frame = ctk.CTkFrame(self.audio_frame)
        self.audio_buttons_frame.pack(padx=10, pady=5, fill="x", expand=True)
        self.add_audio_button = ctk.CTkButton(self.audio_buttons_frame, command=self.add_audio)
        self.add_audio_button.pack(side="left", padx=5)
        self.remove_audio_button = ctk.CTkButton(self.audio_buttons_frame, command=self.remove_audio)
        self.remove_audio_button.pack(side="left", padx=5)
        self.clear_audio_button = ctk.CTkButton(self.audio_buttons_frame, command=self.clear_audio)
        self.clear_audio_button.pack(side="left", padx=5)

        # --- Drag and Drop ---
        self.drop_target = ctk.CTkLabel(self, text="", height=100, fg_color="gray20")
        self.drop_target.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        self.drop_target.drop_target_register(DND_FILES)
        self.drop_target.dnd_bind('<<Drop>>', self.handle_drop)

        # --- Timestamp Generation ---
        self.timestamp_frame = ctk.CTkFrame(self)
        self.timestamp_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")
        self.timestamp_frame.grid_columnconfigure(0, weight=1)
        self.timestamp_frame.grid_rowconfigure(1, weight=1)

        self.generate_button = ctk.CTkButton(self.timestamp_frame, command=self.generate_timestamps)
        self.generate_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.timestamp_textbox = ctk.CTkTextbox(self.timestamp_frame, wrap="word")
        self.timestamp_textbox.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        self.timestamp_actions_frame = ctk.CTkFrame(self.timestamp_frame)
        self.timestamp_actions_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        self.export_button = ctk.CTkButton(self.timestamp_actions_frame, command=self.export_to_txt)
        self.export_button.pack(side="left", padx=5)
        self.copy_button = ctk.CTkButton(self.timestamp_actions_frame, command=self.copy_to_clipboard)
        self.copy_button.pack(side="left", padx=5)

    def change_language(self, new_lang_upper):
        self.current_lang = new_lang_upper.lower()
        self.update_ui_texts()

    def update_ui_texts(self):
        texts = self.locales[self.current_lang]
        self.title(texts.get("title_timestamps", "YouTube Timestamp Generator"))
        self.drop_target.configure(text=texts["drop_files_here"])
        self.audio_list_label.configure(text=texts.get("audio_tracks", "Audio Tracks:"))
        self.add_audio_button.configure(text=texts.get("add_audio", "Add Audio"))
        self.remove_audio_button.configure(text=texts.get("remove_audio", "Remove Selected"))
        self.clear_audio_button.configure(text=texts.get("clear_all_audio", "Clear All"))
        self.generate_button.configure(text=texts.get("generate_timestamps", "Generate Timestamps"))
        self.export_button.configure(text=texts.get("export_txt", "Export to .txt"))
        self.copy_button.configure(text=texts.get("copy_clipboard", "Copy to Clipboard"))

    def add_audio(self):
        paths = filedialog.askopenfilenames(filetypes=[("Audio files", "*.mp3 *.wav *.flac *.aac")])
        for path in paths:
            if path not in self.audio_paths:
                self.audio_paths.append(path)
                self.audio_listbox.insert(tk.END, os.path.basename(path))

    def remove_audio(self):
        selected_indices = self.audio_listbox.curselection()
        for i in reversed(selected_indices):
            self.audio_listbox.delete(i)
            del self.audio_paths[i]

    def clear_audio(self):
        self.audio_listbox.delete(0, tk.END)
        self.audio_paths.clear()

    def handle_drop(self, event):
        files = self.tk.splitlist(event.data)
        for file in files:
            if file.lower().endswith(('.mp3', '.wav', '.flac', '.aac')):
                if file not in self.audio_paths:
                    self.audio_paths.append(file)
                    self.audio_listbox.insert(tk.END, os.path.basename(file))
        self.update_ui_texts()

    def get_audio_duration(self, file_path):
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def generate_timestamps(self):
        if not self.audio_paths:
            messagebox.showwarning("Warning", self.locales[self.current_lang].get("status_no_audio", "Please add audio files first."))
            return

        self.timestamp_textbox.delete("1.0", tk.END)
        
        total_duration_seconds = 0
        timestamp_list = []

        for path in self.audio_paths:
            filename = os.path.basename(path)
            # Sanitize filename for YouTube description
            track_name = os.path.splitext(filename)[0]
            track_name = re.sub(r'[^a-zA-Zа-яА-Я0-9\s-]', '', track_name).strip()

            hours, remainder = divmod(int(total_duration_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if hours > 0:
                timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                timestamp = f"{minutes:02d}:{seconds:02d}"

            timestamp_list.append(f"{timestamp} {track_name}")
            
            duration = self.get_audio_duration(path)
            if duration:
                total_duration_seconds += duration

        self.timestamp_textbox.insert("1.0", "\n".join(timestamp_list))

    def export_to_txt(self):
        content = self.timestamp_textbox.get("1.0", tk.END)
        if not content.strip():
            messagebox.showwarning("Warning", self.locales[self.current_lang].get("status_no_timestamps", "Generate timestamps first."))
            return
        
        filepath = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("Success", self.locales[self.current_lang].get("export_success", "Timestamps exported successfully!"))
            except Exception as e:
                messagebox.showerror("Error", f"Could not save file: {e}")

    def copy_to_clipboard(self):
        content = self.timestamp_textbox.get("1.0", tk.END)
        if not content.strip():
            messagebox.showwarning("Warning", self.locales[self.current_lang].get("status_no_timestamps", "Generate timestamps first."))
            return
        
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("Success", self.locales[self.current_lang].get("copy_success", "Timestamps copied to clipboard!"))


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = App()
    app.mainloop()