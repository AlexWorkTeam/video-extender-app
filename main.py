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
import time
import re

class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("Video Extender")
        self.geometry("500x500")

        self.video_path = ""
        self.audio_path = ""
        self.render_process = None
        self.stop_requested = False

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
        self.grid_rowconfigure(2, weight=1)

        # Language selection
        self.lang_var = ctk.StringVar(value=self.current_lang.upper())
        self.lang_menu = ctk.CTkOptionMenu(self, values=[lang.upper() for lang in self.available_langs],
                                           variable=self.lang_var, command=self.change_language)
        self.lang_menu.grid(row=0, column=0, padx=10, pady=10, sticky="ne")

        # File selection frame
        self.file_frame = ctk.CTkFrame(self)
        self.file_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.file_frame.grid_columnconfigure(1, weight=1)

        self.select_video_button = ctk.CTkButton(self.file_frame, command=self.select_video)
        self.select_video_button.grid(row=0, column=0, padx=10, pady=5)
        self.video_label = ctk.CTkLabel(self.file_frame, text="", anchor="w")
        self.video_label.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        self.select_audio_button = ctk.CTkButton(self.file_frame, command=self.select_audio)
        self.select_audio_button.grid(row=1, column=0, padx=10, pady=5)
        self.audio_label = ctk.CTkLabel(self.file_frame, text="", anchor="w")
        self.audio_label.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        # Drag and drop area
        self.drop_target = ctk.CTkLabel(self, text="", height=100, fg_color="gray20")
        self.drop_target.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        self.drop_target.drop_target_register(DND_FILES)
        self.drop_target.dnd_bind('<<Drop>>', self.handle_drop)

        # Bottom frame for options and buttons
        self.bottom_frame = ctk.CTkFrame(self)
        self.bottom_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        self.fade_var = ctk.BooleanVar(value=False)
        self.fade_checkbox = ctk.CTkCheckBox(self.bottom_frame, variable=self.fade_var)
        self.fade_checkbox.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.render_button = ctk.CTkButton(self.bottom_frame, command=self.start_render_thread)
        self.render_button.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        
        self.stop_button = ctk.CTkButton(self.bottom_frame, command=self.stop_render, fg_color="darkred", hover_color="red")
        self.stop_button.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.stop_button.grid_remove()

        # Progress and Status
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(row=4, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()

        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.grid(row=5, column=0, padx=10, pady=5, sticky="ew")

    def change_language(self, new_lang_upper):
        self.current_lang = new_lang_upper.lower()
        self.update_ui_texts()

    def update_ui_texts(self):
        texts = self.locales[self.current_lang]
        self.title(texts["title"])
        self.select_video_button.configure(text=texts["select_video"])
        self.select_audio_button.configure(text=texts["select_audio"])
        self.fade_checkbox.configure(text=texts["fade_in_out"])
        self.render_button.configure(text=texts["render"])
        self.stop_button.configure(text=texts.get("stop_render", "Stop"))
        self.status_label.configure(text=texts["status_ready"])
        self.video_label.configure(text=f"{texts['video_label']} {os.path.basename(self.video_path) if self.video_path else ''}")
        self.audio_label.configure(text=f"{texts['audio_label']} {os.path.basename(self.audio_path) if self.audio_path else ''}")
        self.drop_target.configure(text=texts["drop_files_here"])

    def select_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mov *.avi")])
        if path:
            self.video_path = path
            self.update_ui_texts()

    def select_audio(self):
        path = filedialog.askopenfilename(filetypes=[("Audio files", "*.mp3 *.wav *.flac *.aac")])
        if path:
            self.audio_path = path
            self.update_ui_texts()

    def handle_drop(self, event):
        files = self.tk.splitlist(event.data)
        for file in files:
            if file.lower().endswith(('.mp4', '.mov', '.avi')):
                self.video_path = file
            elif file.lower().endswith(('.mp3', '.wav', '.flac', '.aac')):
                self.audio_path = file
        self.update_ui_texts()

    def get_audio_duration(self, file_path):
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def start_render_thread(self):
        if not self.video_path or not self.audio_path:
            messagebox.showwarning("Warning", self.locales[self.current_lang]["status_select_files"])
            return

        output_path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 files", "*.mp4")])
        if not output_path:
            return

        self.stop_requested = False
        fade_enabled = self.fade_var.get()

        self.render_button.grid_remove()
        self.stop_button.grid()
        self.progress_bar.grid()
        self.status_label.configure(text=self.locales[self.current_lang]["status_rendering"])
        
        render_thread = threading.Thread(target=self.render_video, args=(output_path, fade_enabled))
        render_thread.daemon = True
        render_thread.start()

    def stop_render(self):
        if self.render_process and self.render_process.poll() is None:
            self.stop_requested = True
            self.render_process.terminate()

    def reset_ui_after_render(self):
        self.stop_button.grid_remove()
        self.progress_bar.grid_remove()
        self.render_button.grid()
        self.render_button.configure(state="normal")
        self.status_label.configure(text=self.locales[self.current_lang]["status_ready"])
        self.render_process = None

    def render_video(self, output_path, fade_enabled):
        start_time = time.time()
        try:
            audio_duration = self.get_audio_duration(self.audio_path)
            if audio_duration is None:
                if self.winfo_exists(): self.after(0, self.on_render_error, "Could not get audio duration.")
                return

            command = self.build_ffmpeg_command(output_path, audio_duration, fade_enabled)
            self.run_ffmpeg(command)
            
            monitor_thread = threading.Thread(target=self.monitor_progress, args=(audio_duration,))
            monitor_thread.daemon = True
            monitor_thread.start()

            stdout, stderr = self.render_process.communicate()
            return_code = self.render_process.returncode

            if self.stop_requested:
                if self.winfo_exists(): self.after(0, self.on_render_cancel)
                return

            if self.winfo_exists():
                duration = time.time() - start_time
                if return_code == 0:
                    self.after(0, self.on_render_success, duration)
                else:
                    self.after(0, self.on_render_error, stderr)

        except Exception as e:
            if self.winfo_exists() and "main thread is not in main loop" not in str(e):
                self.after(0, self.on_render_error, str(e))

    def build_ffmpeg_command(self, output_path, audio_duration, fade_enabled):
        command = ['ffmpeg', '-y']
        
        system = platform.system()
        video_codec = 'libx264'
        hwaccel_args = []
        if system == "Darwin":
            hwaccel_args = ['-hwaccel', 'videotoolbox']
            video_codec = 'h264_videotoolbox'
        
        command.extend(hwaccel_args)
        command.extend(['-stream_loop', '-1', '-i', self.video_path])
        command.extend(['-i', self.audio_path])

        filter_complex_parts = []
        map_video = "0:v"
        map_audio = "1:a"

        if fade_enabled:
            fade_duration = 1
            video_fade = f"[0:v]fade=t=in:st=0:d={fade_duration},fade=t=out:st={audio_duration - fade_duration}:d={fade_duration}[v_fade]"
            audio_fade = f"[1:a]afade=t=in:st=0:d={fade_duration},afade=t=out:st={audio_duration - fade_duration}:d={fade_duration}[a_out]"
            filter_complex_parts.extend([video_fade, audio_fade])
            map_video = "[v_fade]"
            map_audio = "[a_out]"
        
        if filter_complex_parts:
            command.extend(['-filter_complex', ";".join(filter_complex_parts)])

        command.extend(['-map', map_video, '-map', map_audio])
        command.extend(['-c:v', video_codec])
        
        if video_codec == 'h264_videotoolbox':
            command.extend(['-b:v', '15M'])
        else:
            command.extend(['-preset', 'ultrafast', '-crf', '23'])

        command.extend(['-c:a', 'aac', '-b:a', '192k', '-shortest', output_path])
        print(" ".join(command))
        return command

    def run_ffmpeg(self, command):
        startupinfo = None
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        command.insert(1, "-progress")
        command.insert(2, "pipe:2")

        self.render_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo, universal_newlines=True)

    def monitor_progress(self, total_duration):
        while True:
            if self.render_process is None or self.render_process.poll() is not None:
                break
            try:
                line = self.render_process.stderr.readline()
                if not line:
                    break
                if "out_time_ms" in line:
                    time_str = line.split("=")[1].strip()
                    if time_str == "N/A":
                        continue
                    time_ms = int(time_str)
                    progress = (time_ms / 1000000) / total_duration
                    progress = min(max(progress, 0), 1)
                    
                    eta_seconds = 0
                    if "speed=" in line:
                        speed_match = re.search(r'speed=\s*([\d\.]+)x', line)
                        if speed_match:
                            speed = float(speed_match.group(1))
                            if speed > 0:
                                eta_seconds = (total_duration - (time_ms / 1000000)) / speed
                    
                    eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds)) if eta_seconds > 0 else "..."

                    def update_gui():
                        if self.winfo_exists():
                            self.progress_bar.set(progress)
                            self.status_label.configure(text=self.locales[self.current_lang]["status_progress"].format(progress=progress * 100, eta=eta_str))
                    
                    if self.winfo_exists():
                        self.after(0, update_gui)
            except (IOError, ValueError):
                break
            time.sleep(0.1)

    def on_render_success(self, duration):
        if not self.winfo_exists(): return
        success_message = f"Video rendered successfully in {duration:.2f} seconds!"
        messagebox.showinfo("Success", success_message)
        self.reset_ui_after_render()

    def on_render_error(self, error_message):
        if not self.winfo_exists(): return
        error_text = f"FFmpeg error:\n{error_message}"
        print(error_text)
        messagebox.showerror("Error", error_text)
        self.reset_ui_after_render()

    def on_ffmpeg_not_found(self):
        if not self.winfo_exists(): return
        messagebox.showerror("Error", "ffmpeg not found. Please ensure it is installed and in your system's PATH.")
        self.reset_ui_after_render()
        
    def on_render_cancel(self):
        if not self.winfo_exists(): return
        self.reset_ui_after_render()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = App()
    app.mainloop()