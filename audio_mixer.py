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
import sys
import random

class AudioMixerApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("Audio Mixer Pro")
        self.geometry("600x800")

        self.audio_paths = []
        self.audio_durations = {}
        self.render_process = None
        self.stop_requested = False
        self.last_render_errors = ""
        self.ffmpeg_path = "ffmpeg"
        self.ffprobe_path = "ffprobe"
        
        self.button_font = ("Arial", 14)

        self.find_ffmpeg()
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
        
        try:
            system_lang = locale.getdefaultlocale()[0][:2]
        except (ValueError, IndexError):
            system_lang = "en"
        self.available_langs = list(self.locales.keys())
        self.current_lang = system_lang if system_lang in self.available_langs else "en"

    def find_ffmpeg(self):
        base_path = ""
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        ffmpeg_exe = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        ffprobe_exe = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"

        local_ffmpeg = os.path.join(base_path, ffmpeg_exe)
        local_ffprobe = os.path.join(base_path, ffprobe_exe)

        if os.path.exists(local_ffmpeg):
            self.ffmpeg_path = local_ffmpeg
        
        if os.path.exists(local_ffprobe):
            self.ffprobe_path = local_ffprobe

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Top Bar ---
        self.top_bar = ctk.CTkFrame(self)
        self.top_bar.grid(row=0, column=0, padx=10, pady=(10,0), sticky="ew")
        self.top_bar.grid_columnconfigure(0, weight=1)

        self.theme_label = ctk.CTkLabel(self.top_bar, text="Theme:")
        self.theme_label.pack(side="left", padx=(10, 5))
        self.theme_menu = ctk.CTkOptionMenu(self.top_bar, command=self.change_theme)
        self.theme_menu.pack(side="left", padx=5)
        
        self.lang_menu = ctk.CTkOptionMenu(self.top_bar, command=self.change_language)
        self.lang_menu.pack(side="right", padx=10)

        # --- Tab View ---
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.tab_view.add("mixer_tab")
        self.tab_view.add("timestamps_tab")
        
        self.mixer_tab = self.tab_view.tab("mixer_tab")
        self.timestamps_tab = self.tab_view.tab("timestamps_tab")

        self.setup_mixer_tab()
        self.setup_timestamps_tab()

        self.tab_display_map = {}
        self.original_tab_callback = self.tab_view._segmented_button.cget("command")
        self.tab_view._segmented_button.configure(command=self.custom_tab_callback)
        
        # --- Global Elements ---
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()
        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

    def setup_mixer_tab(self):
        self.mixer_tab.grid_columnconfigure(0, weight=1)
        self.mixer_tab.grid_rowconfigure(1, weight=1)

        # --- Input Frame ---
        self.input_frame = ctk.CTkFrame(self.mixer_tab)
        self.input_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.input_frame.grid_columnconfigure(1, weight=1)

        self.select_files_button = ctk.CTkButton(self.input_frame, command=self.select_files, font=self.button_font)
        self.select_files_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.select_folder_button = ctk.CTkButton(self.input_frame, command=self.select_folder, font=self.button_font)
        self.select_folder_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.drop_target = ctk.CTkLabel(self.input_frame, text="", height=80, fg_color="gray20")
        self.drop_target.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        self.drop_target.drop_target_register(DND_FILES)
        self.drop_target.dnd_bind('<<Drop>>', self.handle_drop)

        # --- Track List Frame ---
        self.track_list_frame = ctk.CTkFrame(self.mixer_tab)
        self.track_list_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=0, sticky="nsew")
        self.track_list_frame.grid_columnconfigure(0, weight=1)
        self.track_list_frame.grid_rowconfigure(1, weight=1)
        
        self.playlist_label = ctk.CTkLabel(self.track_list_frame, text="", font=("Arial", 16, "bold"))
        self.playlist_label.grid(row=0, column=0, padx=10, pady=(5,0), sticky="w")

        self.listbox_container = ctk.CTkFrame(self.track_list_frame, corner_radius=10)
        self.listbox_container.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
        self.listbox_container.grid_columnconfigure(0, weight=1)
        self.listbox_container.grid_rowconfigure(0, weight=1)

        self.track_listbox = tk.Listbox(
            self.listbox_container, height=10, bg="#2B2B2B", fg="#DCE4EE",
            selectbackground="#1F6AA5", selectforeground="#DCE4EE", borderwidth=0, highlightthickness=0,
            font=("Arial", 12)
        )
        self.track_listbox.grid(row=0, column=0, padx=1, pady=1, sticky="nsew")

        self.track_buttons_frame = ctk.CTkFrame(self.track_list_frame)
        self.track_buttons_frame.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        
        self.move_up_button = ctk.CTkButton(self.track_buttons_frame, command=self.move_up, font=self.button_font)
        self.move_up_button.pack(side="left", padx=5)
        self.move_down_button = ctk.CTkButton(self.track_buttons_frame, command=self.move_down, font=self.button_font)
        self.move_down_button.pack(side="left", padx=5)
        self.remove_button = ctk.CTkButton(self.track_buttons_frame, command=self.remove_track, font=self.button_font)
        self.remove_button.pack(side="left", padx=5)
        self.clear_button = ctk.CTkButton(self.track_buttons_frame, command=self.clear_list, font=self.button_font)
        self.clear_button.pack(side="right", padx=5)

        # --- Action Frame ---
        self.action_frame = ctk.CTkFrame(self.mixer_tab)
        self.action_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        self.shuffle_button = ctk.CTkButton(self.action_frame, command=self.shuffle_list, font=self.button_font)
        self.shuffle_button.pack(side="left", padx=5, pady=5)
        self.sort_button = ctk.CTkButton(self.action_frame, command=self.sort_list, font=self.button_font)
        self.sort_button.pack(side="left", padx=5, pady=5)
        
        self.total_duration_label = ctk.CTkLabel(self.mixer_tab, text="", font=("Arial", 12, "italic"))
        self.total_duration_label.grid(row=3, column=0, padx=10, pady=5, sticky="w")

        # --- Export Frame ---
        self.export_frame = ctk.CTkFrame(self.mixer_tab)
        self.export_frame.grid(row=4, column=0, padx=10, pady=10, sticky="ew")
        self.export_frame.grid_columnconfigure(1, weight=1)

        self.format_label = ctk.CTkLabel(self.export_frame, text="Format:")
        self.format_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.format_var = ctk.StringVar(value="wav")
        self.format_menu = ctk.CTkOptionMenu(self.export_frame, variable=self.format_var, values=["wav", "mp3"], command=self.toggle_bitrate_menu)
        self.format_menu.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        self.bitrate_label = ctk.CTkLabel(self.export_frame, text="Bitrate:")
        self.bitrate_var = ctk.StringVar(value="192")
        self.bitrate_menu = ctk.CTkOptionMenu(self.export_frame, variable=self.bitrate_var, values=["128", "192", "256", "320"])

        # --- Bottom Frame ---
        self.bottom_frame = ctk.CTkFrame(self.mixer_tab)
        self.bottom_frame.grid(row=5, column=0, padx=10, pady=10, sticky="ew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        self.save_mix_button = ctk.CTkButton(self.bottom_frame, command=self.start_render_thread, fg_color="#28A745", hover_color="#218838", font=self.button_font)
        self.save_mix_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        self.stop_button = ctk.CTkButton(self.bottom_frame, command=self.stop_render, fg_color="darkred", hover_color="red", font=self.button_font)
        self.stop_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.stop_button.grid_remove()

        self.playlist_frame = ctk.CTkFrame(self.bottom_frame)
        self.playlist_frame.grid(row=1, column=0, padx=0, pady=5, sticky="ew")
        self.playlist_frame.grid_columnconfigure(0, weight=1)
        self.playlist_frame.grid_columnconfigure(1, weight=1)
        
        self.save_playlist_button = ctk.CTkButton(self.playlist_frame, command=self.save_playlist, font=self.button_font)
        self.save_playlist_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.load_playlist_button = ctk.CTkButton(self.playlist_frame, command=self.load_playlist, font=self.button_font)
        self.load_playlist_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    def setup_timestamps_tab(self):
        self.timestamps_tab.grid_columnconfigure(0, weight=1)
        self.timestamps_tab.grid_rowconfigure(1, weight=1)
        
        self.timestamp_frame = ctk.CTkFrame(self.timestamps_tab)
        self.timestamp_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.timestamp_frame.grid_columnconfigure(0, weight=1)
        self.timestamp_frame.grid_rowconfigure(1, weight=1)

        self.generate_button = ctk.CTkButton(self.timestamp_frame, command=self.generate_timestamps, font=self.button_font)
        self.generate_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        self.timestamp_textbox = ctk.CTkTextbox(self.timestamp_frame, wrap="word", font=("Arial", 12))
        self.timestamp_textbox.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        
        self.timestamp_actions_frame = ctk.CTkFrame(self.timestamp_frame)
        self.timestamp_actions_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        
        self.export_button = ctk.CTkButton(self.timestamp_actions_frame, command=self.export_to_txt, font=self.button_font)
        self.export_button.pack(side="left", padx=5)
        self.copy_button = ctk.CTkButton(self.timestamp_actions_frame, command=self.copy_to_clipboard, font=self.button_font)
        self.copy_button.pack(side="left", padx=5)

    def change_language(self, new_lang_upper):
        self.current_lang = new_lang_upper.lower()
        self.update_ui_texts()

    def change_theme(self, new_theme_display):
        theme_map = {
            self.locales[self.current_lang].get("theme_light", "Light"): "light",
            self.locales[self.current_lang].get("theme_dark", "Dark"): "dark"
        }
        new_theme_internal = theme_map.get(new_theme_display, "dark")
        ctk.set_appearance_mode(new_theme_internal)

    def update_ui_texts(self):
        texts = self.locales.get(self.current_lang, self.locales["en"])
        self.title(texts.get("app_title", "Audio Mixer Pro"))
        
        # Top Bar
        self.lang_menu.configure(values=[lang.upper() for lang in self.available_langs])
        self.lang_menu.set(self.current_lang.upper())
        self.theme_label.configure(text=texts.get("theme_label", "Theme:"))
        self.theme_menu.configure(values=[texts.get("theme_light", "Light"), texts.get("theme_dark", "Dark")])
        current_mode = ctk.get_appearance_mode()
        self.theme_menu.set(texts.get(f"theme_{current_mode.lower()}", "Dark"))

        # Update tab names
        new_mixer_text = texts.get("tab_render", "Mixer")
        new_timestamps_text = texts.get("tab_timestamps", "Timestamps")
        current_selection_internal = self.tab_view.get()
        
        self.tab_display_map = {
            new_mixer_text: "mixer_tab",
            new_timestamps_text: "timestamps_tab"
        }
        
        self.tab_view._segmented_button.configure(values=list(self.tab_display_map.keys()))
        
        current_selection_display = next((display for display, internal in self.tab_display_map.items() if internal == current_selection_internal), current_selection_internal)
        if current_selection_display != self.tab_view._segmented_button.get():
             self.tab_view._segmented_button.set(current_selection_display)

        # Mixer Tab
        self.select_files_button.configure(text="📂 " + texts.get("select_files", "Select Files"))
        self.select_folder_button.configure(text="🗂️ " + texts.get("select_folder", "Select Folder"))
        self.drop_target.configure(text=texts.get("drop_files_here", "Drag & Drop files here"))
        self.playlist_label.configure(text=texts.get("playlist_label", "Playlist"))
        self.move_up_button.configure(text="⬆️ " + texts.get("move_up", "Up"))
        self.move_down_button.configure(text="⬇️ " + texts.get("move_down", "Down"))
        self.remove_button.configure(text="❌ " + texts.get("remove", "Remove"))
        self.clear_button.configure(text="🗑️ " + texts.get("clear_list", "Clear"))
        self.shuffle_button.configure(text="🔀 " + texts.get("shuffle", "Shuffle"))
        self.sort_button.configure(text="🔡 " + texts.get("sort_alpha", "Sort A-Z"))
        self.format_label.configure(text=texts.get("format_label", "Format:"))
        self.bitrate_label.configure(text=texts.get("bitrate_label", "Bitrate (kbps):"))
        self.save_mix_button.configure(text="▶️ " + texts.get("save_mix", "Start Exporting Mix"))
        self.stop_button.configure(text="🛑 " + texts.get("stop_render", "Stop"))
        self.save_playlist_button.configure(text="💾 " + texts.get("save_playlist", "Save Playlist"))
        self.load_playlist_button.configure(text="📂 " + texts.get("load_playlist", "Load Playlist"))
        self.status_label.configure(text=texts.get("status_ready", "Ready"))
        self.update_total_duration()
        self.toggle_bitrate_menu()

        # Timestamps Tab
        self.generate_button.configure(text="⏱️ " + texts.get("generate_timestamps", "Generate Timestamps"))
        self.export_button.configure(text="📄 " + texts.get("export_txt", "Export to .txt"))
        self.copy_button.configure(text="📋 " + texts.get("copy_clipboard", "Copy to Clipboard"))

    def select_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Audio files", "*.mp3 *.wav *.flac *.aac")])
        self.add_audio_paths(paths)

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            paths = []
            for filename in os.listdir(folder_path):
                if filename.lower().endswith(('.mp3', '.wav', '.flac', '.aac')):
                    paths.append(os.path.join(folder_path, filename))
            self.add_audio_paths(paths)

    def handle_drop(self, event):
        files = self.tk.splitlist(event.data)
        self.add_audio_paths(files)

    def add_audio_paths(self, paths):
        for path in paths:
            if path.lower().endswith(('.mp3', '.wav', '.flac', '.aac')):
                if path not in self.audio_paths:
                    duration = self.get_audio_duration(path)
                    self.audio_paths.append(path)
                    self.audio_durations[path] = duration
                    
                    display_text = f"{os.path.basename(path)} ({self.format_duration(duration)})"
                    self.track_listbox.insert(tk.END, display_text)
        self.update_total_duration()

    def remove_track(self):
        selected_indices = self.track_listbox.curselection()
        if not selected_indices:
            return
        for i in reversed(selected_indices):
            path_to_remove = self.audio_paths[i]
            self.track_listbox.delete(i)
            del self.audio_paths[i]
            if path_to_remove in self.audio_durations:
                del self.audio_durations[path_to_remove]
        self.update_total_duration()

    def clear_list(self):
        self.track_listbox.delete(0, tk.END)
        self.audio_paths.clear()
        self.audio_durations.clear()
        self.update_total_duration()

    def move_up(self):
        selected_indices = self.track_listbox.curselection()
        if not selected_indices:
            return
        for i in selected_indices:
            if i > 0:
                self.audio_paths[i], self.audio_paths[i-1] = self.audio_paths[i-1], self.audio_paths[i]
                item = self.track_listbox.get(i)
                self.track_listbox.delete(i)
                self.track_listbox.insert(i-1, item)
                self.track_listbox.selection_set(i-1)

    def move_down(self):
        selected_indices = self.track_listbox.curselection()
        if not selected_indices:
            return
        for i in reversed(selected_indices):
            if i < self.track_listbox.size() - 1:
                self.audio_paths[i], self.audio_paths[i+1] = self.audio_paths[i+1], self.audio_paths[i]
                item = self.track_listbox.get(i)
                self.track_listbox.delete(i)
                self.track_listbox.insert(i+1, item)
                self.track_listbox.selection_set(i+1)

    def shuffle_list(self):
        if not self.audio_paths: return
        
        display_items = self.track_listbox.get(0, tk.END)
        combined = list(zip(self.audio_paths, display_items))
        random.shuffle(combined)
        
        self.audio_paths, display_names = zip(*combined)
        self.audio_paths = list(self.audio_paths)
        
        self.track_listbox.delete(0, tk.END)
        for name in display_names:
            self.track_listbox.insert(tk.END, name)

    def sort_list(self):
        if not self.audio_paths: return

        display_items = self.track_listbox.get(0, tk.END)
        combined = sorted(zip(self.audio_paths, display_items), key=lambda x: os.path.basename(x[0]).lower())
        
        self.audio_paths, display_names = zip(*combined)
        self.audio_paths = list(self.audio_paths)

        self.track_listbox.delete(0, tk.END)
        for name in display_names:
            self.track_listbox.insert(tk.END, name)

    def get_audio_duration(self, file_path):
        try:
            cmd = [self.ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            return 0

    def save_playlist(self):
        if not self.audio_paths:
            messagebox.showwarning("Warning", self.locales[self.current_lang].get("status_no_audio", "Please add audio files first."))
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.audio_paths, f, indent=4)
            messagebox.showinfo("Success", self.locales[self.current_lang].get("playlist_saved", "Playlist saved successfully!"))

    def load_playlist(self):
        filepath = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not filepath:
            return
        
        with open(filepath, 'r', encoding='utf-8') as f:
            loaded_paths = json.load(f)

        self.clear_list()
        
        missing_files = []
        for path in loaded_paths:
            if os.path.exists(path):
                self.add_audio_paths([path])
            else:
                missing_files.append(path)
        
        if missing_files:
            self.handle_missing_files(missing_files)

    def handle_missing_files(self, missing_files):
        for path in missing_files:
            response = messagebox.askyesnocancel(
                "File Not Found",
                f"File not found:\n{path}\n\nDo you want to locate it manually?\n(No to remove, Cancel to stop)"
            )
            if response is True: # Yes
                new_path = filedialog.askopenfilename(title=f"Locate {os.path.basename(path)}")
                if new_path:
                    self.add_audio_paths([new_path])
            elif response is None: # Cancel
                break
        self.update_total_duration()

    def start_render_thread(self):
        if not self.audio_paths:
            messagebox.showwarning("Warning", self.locales[self.current_lang].get("status_no_audio", "Please add audio files first."))
            return

        file_format = self.format_var.get()
        output_path = filedialog.asksaveasfilename(defaultextension=f".{file_format}", filetypes=[(f"{file_format.upper()} files", f"*.{file_format}")])
        if not output_path:
            return

        self.stop_requested = False
        self.save_mix_button.grid_remove()
        self.stop_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.progress_bar.grid()
        self.status_label.configure(text=self.locales[self.current_lang].get("status_rendering", "Rendering..."))
        
        render_thread = threading.Thread(target=self.render_mix, args=(output_path,))
        render_thread.daemon = True
        render_thread.start()

    def stop_render(self):
        if self.render_process and self.render_process.poll() is None:
            self.stop_requested = True
            try:
                self.render_process.terminate()
            except Exception as e:
                print(f"Error terminating process: {e}")

    def reset_ui_after_render(self):
        self.stop_button.grid_remove()
        self.save_mix_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.save_mix_button.configure(state="normal")
        self.progress_bar.grid_remove()
        self.status_label.configure(text=self.locales[self.current_lang].get("status_ready", "Ready"))
        self.render_process = None

    def render_mix(self, output_path):
        start_time = time.time()
        try:
            command = [self.ffmpeg_path, '-y']
            for path in self.audio_paths:
                command.extend(['-i', path])
            
            filter_inputs = "".join([f"[{i}:a]" for i in range(len(self.audio_paths))])
            filter_complex = f"{filter_inputs}concat=n={len(self.audio_paths)}:v=0:a=1[outa]"
            
            command.extend(['-filter_complex', filter_complex, '-map', '[outa]'])

            file_format = self.format_var.get()
            if file_format == 'mp3':
                bitrate = self.bitrate_var.get() + "k"
                command.extend(['-c:a', 'libmp3lame', '-b:a', bitrate])
            else: # wav
                command.extend(['-c:a', 'pcm_s16le'])
            command.append(output_path)

            self.log_render_start(output_path)
            self.run_ffmpeg(command)
            
            stdout, stderr = self.render_process.communicate()
            return_code = self.render_process.returncode
            duration = time.time() - start_time

            if self.stop_requested:
                if self.winfo_exists(): self.after(0, self.on_render_cancel)
                return
            
            if self.winfo_exists():
                if return_code == 0:
                    self.after(0, self.on_render_success, output_path, duration)
                else:
                    self.after(0, self.on_render_error, stderr)

        except Exception as e:
            if self.winfo_exists():
                self.after(0, self.on_render_error, str(e))

    def run_ffmpeg(self, command):
        startupinfo = None
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        self.render_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo, encoding='utf-8', errors='replace')

    def on_render_success(self, output_path, duration):
        if not self.winfo_exists(): return
        
        self.generate_timestamps(silent=True)
        txt_path = os.path.splitext(output_path)[0] + "_timestamps.txt"
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(self.timestamp_textbox.get("1.0", tk.END))
            timestamps_message = f"\n\nTimestamps saved to:\n{txt_path}"
        except Exception as e:
            timestamps_message = f"\n\nCould not save timestamps: {e}"

        success_message = self.locales[self.current_lang].get("mix_saved", "Mix saved successfully!")
        success_message += f"\nRendered in {duration:.2f} seconds."
        success_message += timestamps_message
        
        messagebox.showinfo("Success", success_message)
        self.reset_ui_after_render()
        try:
            if platform.system() == "Windows":
                os.startfile(os.path.dirname(output_path))
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", os.path.dirname(output_path)])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(output_path)])
        except Exception as e:
            print(f"Could not open output directory: {e}")

    def on_render_error(self, error_message):
        if not self.winfo_exists(): return
        messagebox.showerror("Error", f"Render Error:\n{error_message}")
        self.reset_ui_after_render()

    def on_render_cancel(self):
        if not self.winfo_exists(): return
        self.reset_ui_after_render()
        self.status_label.configure(text=self.locales[self.current_lang].get("status_cancelled", "Cancelled"))

    def log_render_start(self, output_path):
        with open("mix_log.txt", "a", encoding="utf-8") as f:
            f.write(f"--- New Mix --- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(f"Output File: {output_path}\n")
            f.write(f"Format: {self.format_var.get()}\n")
            if self.format_var.get() == 'mp3':
                f.write(f"Bitrate: {self.bitrate_var.get()} kbps\n")
            f.write("Track Order:\n")
            for i, path in enumerate(self.audio_paths):
                f.write(f"  {i+1}. {os.path.basename(path)}\n")
            f.write("--------------------------------------------------\n\n")

    def format_duration(self, seconds):
        if seconds is None:
            return "N/A"
        minutes, seconds = divmod(int(seconds), 60)
        return f"{minutes:02d}:{seconds:02d}"

    def update_total_duration(self):
        total_seconds = sum(self.audio_durations.values())
        formatted_duration = self.format_duration(total_seconds)
        text = self.locales[self.current_lang].get("total_duration_label", "Total Duration: {duration}").format(duration=formatted_duration)
        self.total_duration_label.configure(text=text)

    def toggle_bitrate_menu(self, *args):
        if self.format_var.get() == "mp3":
            self.bitrate_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")
            self.bitrate_menu.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        else:
            self.bitrate_label.grid_remove()
            self.bitrate_menu.grid_remove()

    def generate_timestamps(self, silent=False):
        if not self.audio_paths:
            if not silent:
                messagebox.showwarning("Warning", self.locales[self.current_lang].get("status_no_audio", "Please add audio files first."))
            return

        self.timestamp_textbox.delete("1.0", tk.END)
        
        total_duration_seconds = 0
        timestamp_list = []

        for path in self.audio_paths:
            filename = os.path.basename(path)
            track_name = os.path.splitext(filename)[0]
            track_name = re.sub(r'[^a-zA-Zа-яА-Я0-9\s-]', '', track_name).strip()

            hours, remainder = divmod(int(total_duration_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if hours > 0:
                timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                timestamp = f"{minutes:02d}:{seconds:02d}"

            timestamp_list.append(f"{timestamp} {track_name}")
            
            duration = self.audio_durations.get(path)
            if duration:
                total_duration_seconds += duration

        self.timestamp_textbox.insert("1.0", "\n".join(timestamp_list))
        if not silent:
            timestamps_display_name = next((display for display, internal in self.tab_display_map.items() if internal == "timestamps_tab"), "timestamps_tab")
            self.tab_view.set(timestamps_display_name)

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

    def custom_tab_callback(self, displayed_value):
        internal_key = self.tab_display_map.get(displayed_value, displayed_value)
        if self.original_tab_callback:
            self.original_tab_callback(internal_key)


if __name__ == "__main__":
    try:
        ctk.set_appearance_mode("dark")
        app = AudioMixerApp()
        app.mainloop()
    except Exception as e:
        import traceback
        print(f"A fatal error occurred: {e}")
        print(traceback.format_exc())
        with open("error.log", "w", encoding="utf-8") as f:
            f.write(f"An error occurred:\n{e}\n\n")
            f.write(traceback.format_exc())
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Fatal Error", "A fatal error occurred. Please check error.log and the console for details.")
        except:
            pass