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

class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("Video Extender - Multi Audio")
        self.geometry("650x750")

        self.video_path = ""
        self.audio_paths = []
        self.render_process = None
        self.stop_requested = False
        self.original_fps = "30"
        self.original_resolution = "1920x1080"
        self.last_render_errors = ""
        self.ffmpeg_path = "ffmpeg"
        self.ffprobe_path = "ffprobe"

        self.find_ffmpeg()
        self.load_locales()
        self.available_encoders = self.get_available_encoders()
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

    def get_available_encoders(self):
        try:
            result = subprocess.run([self.ffmpeg_path, '-encoders'], capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
            available = set()
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('V'):
                    parts = line.split()
                    if len(parts) > 1:
                        available.add(parts[1])
            return available
        except (FileNotFoundError, subprocess.CalledProcessError):
            messagebox.showerror("FFmpeg Error", "Could not find or run ffmpeg. Please ensure it's installed and in your system's PATH.")
            self.after(100, self.destroy)
            return set()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.lang_var = ctk.StringVar(value=self.current_lang.upper())
        self.lang_menu = ctk.CTkOptionMenu(self, values=[lang.upper() for lang in self.available_langs],
                                           variable=self.lang_var, command=self.change_language)
        self.lang_menu.grid(row=0, column=0, padx=10, pady=10, sticky="ne")

        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.tab_view.add("render_tab")
        self.tab_view.add("timestamps_tab")
        
        self.render_tab = self.tab_view.tab("render_tab")
        self.timestamps_tab = self.tab_view.tab("timestamps_tab")

        self.tab_display_map = {}
        self.original_tab_callback = self.tab_view._segmented_button.cget("command")
        self.tab_view._segmented_button.configure(command=self.custom_tab_callback)
        
        # --- Render Tab ---
        self.render_tab.grid_columnconfigure(0, weight=1)
        
        self.video_frame = ctk.CTkFrame(self.render_tab)
        self.video_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.video_frame.grid_columnconfigure(1, weight=1)
        self.select_video_button = ctk.CTkButton(self.video_frame, command=self.select_video)
        self.select_video_button.grid(row=0, column=0, padx=10, pady=5)
        self.video_label = ctk.CTkLabel(self.video_frame, text="", anchor="w")
        self.video_label.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        self.audio_frame = ctk.CTkFrame(self.render_tab)
        self.audio_frame.grid(row=1, column=0, padx=10, pady=0, sticky="ew")
        self.audio_frame.grid_columnconfigure(0, weight=1)
        self.audio_list_label = ctk.CTkLabel(self.audio_frame, text="Audio Tracks:")
        self.audio_list_label.pack(padx=10, pady=5, anchor="w")
        self.audio_listbox = tk.Listbox(self.audio_frame, height=6)
        self.audio_listbox.pack(padx=10, pady=5, fill="x", expand=True)
        self.audio_buttons_frame = ctk.CTkFrame(self.audio_frame)
        self.audio_buttons_frame.pack(padx=10, pady=5, fill="x", expand=True)
        self.add_audio_button = ctk.CTkButton(self.audio_buttons_frame, command=self.add_audio)
        self.add_audio_button.pack(side="left", padx=5)
        self.remove_audio_button = ctk.CTkButton(self.audio_buttons_frame, command=self.remove_audio)
        self.remove_audio_button.pack(side="left", padx=5)
        self.clear_audio_button = ctk.CTkButton(self.audio_buttons_frame, command=self.clear_audio)
        self.clear_audio_button.pack(side="left", padx=5)

        self.options_frame = ctk.CTkFrame(self.render_tab)
        self.options_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        self.options_frame.grid_columnconfigure(1, weight=1)
        self.codec_label = ctk.CTkLabel(self.options_frame, text="Codec:")
        self.codec_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.codec_var = ctk.StringVar()
        self.codec_menu = ctk.CTkOptionMenu(self.options_frame, variable=self.codec_var, dynamic_resizing=False)
        self.codec_menu.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        self.resolution_label = ctk.CTkLabel(self.options_frame, text="Resolution:")
        self.resolution_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.resolution_var = ctk.StringVar(value="3840x2160")
        self.resolution_menu = ctk.CTkOptionMenu(self.options_frame, variable=self.resolution_var)
        self.resolution_menu.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.quality_label = ctk.CTkLabel(self.options_frame, text="Quality:")
        self.quality_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.quality_var = ctk.StringVar(value="high")
        self.quality_menu = ctk.CTkOptionMenu(self.options_frame, variable=self.quality_var, values=["fast", "standard", "high"])
        self.quality_menu.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        self.fps_label = ctk.CTkLabel(self.options_frame, text="FPS:")
        self.fps_label.grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.fps_var = ctk.StringVar(value="60")
        self.fps_entry = ctk.CTkEntry(self.options_frame, textvariable=self.fps_var)
        self.fps_entry.grid(row=3, column=1, padx=10, pady=5, sticky="ew")
        self.fade_var = ctk.BooleanVar(value=False)
        self.fade_checkbox = ctk.CTkCheckBox(self.options_frame, variable=self.fade_var)
        self.fade_checkbox.grid(row=4, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        self.bottom_frame = ctk.CTkFrame(self.render_tab)
        self.bottom_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)
        self.render_button = ctk.CTkButton(self.bottom_frame, command=self.start_render_thread)
        self.render_button.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.stop_button = ctk.CTkButton(self.bottom_frame, command=self.stop_render, fg_color="darkred", hover_color="red")
        self.stop_button.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.stop_button.grid_remove()

        # --- Timestamps Tab ---
        self.timestamps_tab.grid_columnconfigure(0, weight=1)
        self.timestamps_tab.grid_rowconfigure(1, weight=1)
        self.timestamp_frame = ctk.CTkFrame(self.timestamps_tab)
        self.timestamp_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
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

        # --- Global Elements ---
        self.drop_target = ctk.CTkLabel(self, text="", height=80, fg_color="gray20")
        self.drop_target.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        self.drop_target.drop_target_register(DND_FILES)
        self.drop_target.dnd_bind('<<Drop>>', self.handle_drop)
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()
        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

    def change_language(self, new_lang_upper):
        self.current_lang = new_lang_upper.lower()
        self.update_ui_texts()

    def update_ui_texts(self):
        texts = self.locales[self.current_lang]
        self.title(texts.get("title_multi", "Video Extender - Multi Audio"))
        
        new_render_text = texts.get("tab_render", "Render")
        new_timestamps_text = texts.get("tab_timestamps", "Timestamps")
        # The line below was causing a crash and is not the correct way to set tab text.
        # self.tab_view.tab("render_tab").configure(text=new_render_text)
        current_selection_internal = self.tab_view.get()
        self.tab_display_map = {
            new_render_text: "render_tab",
            new_timestamps_text: "timestamps_tab"
        }
        self.tab_view._segmented_button.configure(values=list(self.tab_display_map.keys()))
        current_selection_display = next((display for display, internal in self.tab_display_map.items() if internal == current_selection_internal), current_selection_internal)
        if current_selection_display != self.tab_view._segmented_button.get():
             self.tab_view._segmented_button.set(current_selection_display)

        self.select_video_button.configure(text=texts["select_video"])
        self.fade_checkbox.configure(text=texts["fade_in_out"])
        self.render_button.configure(text=texts["render"])
        self.status_label.configure(text=texts["status_ready"])
        self.video_label.configure(text=f"{texts['video_label']} {os.path.basename(self.video_path) if self.video_path else ''}")
        self.drop_target.configure(text=texts["drop_files_here"])
        self.audio_list_label.configure(text=texts.get("audio_tracks", "Audio Tracks:"))
        self.add_audio_button.configure(text=texts.get("add_audio", "Add Audio"))
        self.remove_audio_button.configure(text=texts.get("remove_audio", "Remove Selected"))
        self.clear_audio_button.configure(text=texts.get("clear_all_audio", "Clear All"))
        self.stop_button.configure(text=texts.get("stop_render", "Stop"))
        self.codec_label.configure(text=texts.get("codec_label", "Codec:"))
        self.resolution_label.configure(text=texts.get("resolution_label", "Resolution:"))
        self.quality_label.configure(text=texts.get("quality_label", "Quality:"))
        self.fps_label.configure(text=texts.get("fps_label", "FPS:"))
        self.quality_menu.configure(values=[
            texts.get("quality_fast", "Fast"),
            texts.get("quality_standard", "Standard"),
            texts.get("quality_high", "High")
        ])
        self.generate_button.configure(text=texts.get("generate_timestamps", "Generate Timestamps"))
        self.export_button.configure(text=texts.get("export_txt", "Export to .txt"))
        self.copy_button.configure(text=texts.get("copy_clipboard", "Copy to Clipboard"))
        
        self.codec_display_map = {
            'libx265': texts.get("codec_libx265"),
            'libx264': texts.get("codec_libx264"),
            'h264_nvenc': texts.get("codec_h264_nvenc"),
            'h264_amf': texts.get("codec_h264_amf"),
            'h264_qsv': texts.get("codec_h264_qsv"),
            'h264_videotoolbox': texts.get("codec_h264_videotoolbox"),
            'hevc_videotoolbox': texts.get("codec_hevc_videotoolbox"),
            'libxvid': texts.get("codec_libxvid"),
            'prores_ks': texts.get("codec_prores_ks"),
            'libvpx': texts.get("codec_libvpx"),
            'libvpx-vp9': texts.get("codec_libvpx-vp9"),
            'libaom-av1': texts.get("codec_libaom-av1"),
            'svt-av1': texts.get("codec_svt-av1"),
        }
        
        self.active_codec_map = {
            desc: name for name, desc in self.codec_display_map.items() if name in self.available_encoders
        }
        
        if not self.active_codec_map:
            messagebox.showerror("Error", "No supported video encoders found in your ffmpeg build.")
            self.codec_menu.configure(values=["No codecs found"], state="disabled")
        else:
            self.codec_menu.configure(values=list(self.active_codec_map.keys()))
            
            default_codec_desc = None
            if platform.system() == "Darwin" and 'h264_videotoolbox' in self.available_encoders and self.codec_display_map.get('h264_videotoolbox') in self.active_codec_map:
                default_codec_desc = self.codec_display_map['h264_videotoolbox']
            elif 'libx264' in self.available_encoders and self.codec_display_map.get('libx264') in self.active_codec_map:
                default_codec_desc = self.codec_display_map['libx264']
            else:
                default_codec_desc = list(self.active_codec_map.keys())[0]
            
            self.codec_var.set(default_codec_desc)

        self.quality_map = {
            texts.get("quality_fast"): "fast",
            texts.get("quality_standard"): "standard",
            texts.get("quality_high"): "high"
        }
        
        self.resolution_display_map = {
            texts.get("res_original"): "Original",
            texts.get("res_fullhd"): "1920x1080",
            texts.get("res_2k"): "2560x1440",
            texts.get("res_4k_uhd"): "3840x2160",
            texts.get("res_4k_dci"): "4096x2160",
        }
        self.resolution_menu.configure(values=list(self.resolution_display_map.keys()))
        self.resolution_var.set(texts.get("res_4k_uhd"))

    def select_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mov *.avi")])
        if path:
            self.video_path = path
            self.get_video_info()
            self.update_ui_texts()

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
            if file.lower().endswith(('.mp4', '.mov', '.avi')):
                self.video_path = file
                self.get_video_info()
            elif file.lower().endswith(('.mp3', '.wav', '.flac', '.aac')):
                if file not in self.audio_paths:
                    self.audio_paths.append(file)
                    self.audio_listbox.insert(tk.END, os.path.basename(file))
        self.update_ui_texts()

    def get_video_info(self):
        if not self.video_path:
            return
        try:
            cmd = [self.ffprobe_path, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate', '-of', 'csv=s=x:p=0', self.video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            
            res_match = re.search(r'(\d+x\d+)', output)
            if res_match:
                self.original_resolution = res_match.group(1)
                self.resolution_var.set(self.original_resolution)

            fps_match = re.search(r'(\d+)/(\d+)', output)
            if fps_match:
                num, den = map(int, fps_match.groups())
                self.original_fps = str(round(num / den)) if den != 0 else "30"
                self.fps_var.set(self.original_fps)

        except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
            print(f"Could not get video info: {e}")
            self.original_resolution = "1920x1080"
            self.original_fps = "30"

    def get_audio_duration(self, file_path):
        try:
            cmd = [self.ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def start_render_thread(self):
        if not self.video_path or not self.audio_paths:
            messagebox.showwarning("Warning", self.locales[self.current_lang]["status_select_files"])
            return

        output_path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 files", "*.mp4")])
        if not output_path:
            return

        self.stop_requested = False
        fade_enabled = self.fade_var.get()

        self.render_button.grid_remove()
        self.stop_button.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
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
        self.render_button.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.grid_remove()
        self.render_button.configure(state="normal")
        self.status_label.configure(text=self.locales[self.current_lang]["status_ready"])
        self.render_process = None

    def render_video(self, output_path, fade_enabled):
        start_time = time.time()
        try:
            total_audio_duration = sum(self.get_audio_duration(p) or 0 for p in self.audio_paths)
            if total_audio_duration == 0:
                if self.winfo_exists(): self.after(0, self.on_render_error, "Could not get total audio duration or duration is zero.")
                return

            command = self.build_ffmpeg_command(output_path, total_audio_duration, fade_enabled, force_cpu=False)
            if not command:
                return

            self.run_ffmpeg(command)
            
            self.last_render_errors = ""
            monitor_thread = threading.Thread(target=self.monitor_progress, args=(total_audio_duration,))
            monitor_thread.daemon = True
            monitor_thread.start()

            self.render_process.wait()
            monitor_thread.join()
            return_code = self.render_process.returncode

            if self.stop_requested:
                if self.winfo_exists(): self.after(0, self.on_render_cancel)
                return
            
            if self.winfo_exists():
                duration = time.time() - start_time
                if return_code == 0:
                    self.after(0, self.on_render_success, duration, output_path)
                else:
                    if platform.system() == "Darwin" and "videotoolbox" in " ".join(command):
                         print("VideoToolbox encoding failed. Retrying with CPU (libx264)...")
                         command = self.build_ffmpeg_command(output_path, total_audio_duration, fade_enabled, force_cpu=True)
                         self.run_ffmpeg(command)
                         
                         self.last_render_errors = ""
                         monitor_thread = threading.Thread(target=self.monitor_progress, args=(total_audio_duration,))
                         monitor_thread.daemon = True
                         monitor_thread.start()

                         self.render_process.wait()
                         monitor_thread.join()
                         return_code = self.render_process.returncode

                         if self.winfo_exists():
                            if self.stop_requested:
                                self.after(0, self.on_render_cancel)
                                return
                            duration = time.time() - start_time
                            if return_code == 0:
                                self.after(0, self.on_render_success, duration, output_path)
                            else:
                                self.after(0, self.on_render_error, self.last_render_errors)
                    else:
                        self.after(0, self.on_render_error, self.last_render_errors)

        except Exception as e:
            if self.winfo_exists() and "main thread is not in main loop" not in str(e):
                self.after(0, self.on_render_error, str(e))

    def build_ffmpeg_command(self, output_path, total_audio_duration, fade_enabled, force_cpu=False):
        selected_codec_display = self.codec_var.get()
        video_codec = self.active_codec_map.get(selected_codec_display)

        if not video_codec:
            self.after(0, self.on_render_error, "Selected codec is not available. Please restart the application.")
            return None

        use_gpu_potential = any(c in video_codec for c in ['nvenc', 'amf', 'qsv', 'videotoolbox'])
        if fade_enabled and use_gpu_potential:
            force_cpu = True
            print("Fade filter is enabled; this requires CPU filtering. Forcing CPU encoding for stability.")
        
        if force_cpu:
            video_codec = 'libx264'
            if 'libx264' not in self.available_encoders:
                self.after(0, self.on_render_error, "libx264 codec not available for forced CPU encoding.")
                return None

        resolution_display = self.resolution_var.get()
        resolution = self.resolution_display_map.get(resolution_display, self.original_resolution)
        if resolution == "Original":
            resolution = self.original_resolution
        
        fps = self.fps_var.get()
        
        selected_quality_display = self.quality_var.get()
        quality = self.quality_map.get(selected_quality_display, "high")

        command = [self.ffmpeg_path, '-y']
        
        use_gpu = any(c in video_codec for c in ['nvenc', 'amf', 'qsv', 'videotoolbox']) and not force_cpu
        
        # Inputs are always decoded on CPU for stability. No -hwaccel flags here.
        command.extend(['-stream_loop', '-1', '-i', self.video_path])
        for path in self.audio_paths:
            command.extend(['-i', path])

        filter_complex_parts = []
        
        # Audio chain
        audio_concat_inputs = "".join([f"[{i+1}:a]" for i in range(len(self.audio_paths))])
        audio_output_stream = "[a_concat]"
        audio_filter = f"{audio_concat_inputs}concat=n={len(self.audio_paths)}:v=0:a=1{audio_output_stream}"
        filter_complex_parts.append(audio_filter)
        
        # Video chain
        video_input_stream = "[0:v]"
        video_output_stream = "[v_out]"
        video_filters = []

        # CPU-based filtering
        video_filters.append(f"scale={resolution}")
        video_filters.append(f"fps={fps}")

        if fade_enabled:
            fade_duration = 1
            video_filters.append(f"fade=t=in:st=0:d={fade_duration},fade=t=out:st={total_audio_duration - fade_duration}:d={fade_duration}")
            audio_output_stream = "[a_out]"
            audio_fade_filter = f"[a_concat]afade=t=in:st=0:d={fade_duration},afade=t=out:st={total_audio_duration - fade_duration}:d={fade_duration}{audio_output_stream}"
            filter_complex_parts.append(audio_fade_filter)

        # Upload to GPU only for encoding, if GPU is used
        if use_gpu:
            video_filters.append("format=nv12") 

        video_filter_chain = f"{video_input_stream}{','.join(video_filters)}{video_output_stream}"
        filter_complex_parts.insert(0, video_filter_chain)
        
        command.extend(['-filter_complex', ";".join(filter_complex_parts)])
        command.extend(['-map', video_output_stream, '-map', audio_output_stream])
        
        command.extend(['-c:v', video_codec])
        command.extend(['-pix_fmt', 'yuv420p'])

        # Quality settings
        if "videotoolbox" in video_codec:
            if 'prores' in video_codec:
                 command.extend(['-profile:v', '3' if quality == 'high' else '2'])
            else:
                bitrates = {'fast': '25M', 'standard': '50M', 'high': '80M'}
                command.extend(['-b:v', bitrates.get(quality, '50M')])
        elif 'nvenc' in video_codec or 'amf' in video_codec:
             command.extend(['-cq', '19' if quality == 'high' else '23'])
        elif 'qsv' in video_codec:
             command.extend(['-global_quality', '19' if quality == 'high' else '23'])
        else: # libx264
            crf = {'fast': '28', 'standard': '23', 'high': '18'}
            preset = {'fast': 'ultrafast', 'standard': 'fast', 'high': 'medium'}
            command.extend(['-crf', crf.get(quality, '23')])
            command.extend(['-preset', preset.get(quality, 'fast')])

        command.extend(['-c:a', 'aac', '-b:a', '320k', '-shortest', output_path])
        
        print(" ".join(command))
        return command

    def run_ffmpeg(self, command):
        startupinfo = None
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        command.insert(1, "-progress")
        command.insert(2, "pipe:2")

        self.render_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo, encoding='utf-8', errors='replace')

    def monitor_progress(self, total_duration):
        error_output = []
        while True:
            if self.render_process is None or self.render_process.poll() is not None:
                break

            try:
                line = self.render_process.stderr.readline()
                if not line:
                    break
                
                error_output.append(line)

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
        self.last_render_errors = "".join(error_output)

    def on_render_success(self, duration, output_path):
        if not self.winfo_exists(): return
        success_message = f"Video rendered successfully in {duration:.2f} seconds!"
        
        self.generate_timestamps()
        if output_path:
            txt_path = os.path.splitext(output_path)[0] + "_timestamps.txt"
            try:
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(self.timestamp_textbox.get("1.0", tk.END))
                success_message += f"\n\nTimestamps saved to:\n{txt_path}"
            except Exception as e:
                success_message += f"\n\nCould not save timestamps: {e}"

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

    def generate_timestamps(self):
        if not self.audio_paths:
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

    def custom_tab_callback(self, displayed_value):
        internal_key = self.tab_display_map.get(displayed_value, displayed_value)
        if self.original_tab_callback:
            self.original_tab_callback(internal_key)


if __name__ == "__main__":
    try:
        ctk.set_appearance_mode("dark")
        app = App()
        app.mainloop()
    except Exception as e:
        import traceback
        with open("error.log", "w", encoding="utf-8") as f:
            f.write(f"An error occurred:\n{e}\n\n")
            f.write(traceback.format_exc())
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Fatal Error", "A fatal error occurred. Please check error.log for details.")
        except:
            pass