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

        self.title("Video Extender - Multi Audio")
        self.geometry("600x850")

        self.video_path = ""
        self.audio_paths = []
        self.render_process = None
        self.stop_requested = False
        self.original_fps = "30"
        self.original_resolution = "1920x1080"

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
        
        system_lang = locale.getdefaultlocale()[0][:2]
        self.available_langs = list(self.locales.keys())
        self.current_lang = system_lang if system_lang in self.available_langs else "en"

    def get_available_encoders(self):
        try:
            result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, check=True)
            available = set()
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('V'): # Check if it's a video encoder line
                    parts = line.split()
                    if len(parts) > 1:
                        available.add(parts[1])
            return available
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            messagebox.showerror("FFmpeg Error", "Could not find or run ffmpeg. Please ensure it's installed and in your system's PATH.")
            self.after(100, self.destroy)
            return set()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.lang_var = ctk.StringVar(value=self.current_lang.upper())
        self.lang_menu = ctk.CTkOptionMenu(self, values=[lang.upper() for lang in self.available_langs],
                                           variable=self.lang_var, command=self.change_language)
        self.lang_menu.grid(row=0, column=0, padx=10, pady=10, sticky="ne")

        self.video_frame = ctk.CTkFrame(self)
        self.video_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.video_frame.grid_columnconfigure(1, weight=1)
        self.select_video_button = ctk.CTkButton(self.video_frame, command=self.select_video)
        self.select_video_button.grid(row=0, column=0, padx=10, pady=5)
        self.video_label = ctk.CTkLabel(self.video_frame, text="", anchor="w")
        self.video_label.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        self.audio_frame = ctk.CTkFrame(self)
        self.audio_frame.grid(row=2, column=0, padx=10, pady=0, sticky="ew")
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

        # Render Options Frame
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
        self.options_frame.grid_columnconfigure(1, weight=1)

        # Codec
        self.codec_label = ctk.CTkLabel(self.options_frame, text="Codec:")
        self.codec_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.codec_var = ctk.StringVar()
        self.codec_menu = ctk.CTkOptionMenu(self.options_frame, variable=self.codec_var, dynamic_resizing=False)
        self.codec_menu.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        # Resolution
        self.resolution_label = ctk.CTkLabel(self.options_frame, text="Resolution:")
        self.resolution_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.resolution_var = ctk.StringVar(value="3840x2160")
        self.resolution_menu = ctk.CTkOptionMenu(self.options_frame, variable=self.resolution_var)
        self.resolution_menu.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        # Quality
        self.quality_label = ctk.CTkLabel(self.options_frame, text="Quality:")
        self.quality_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.quality_var = ctk.StringVar(value="high")
        self.quality_menu = ctk.CTkOptionMenu(self.options_frame, variable=self.quality_var,
                                               values=["fast", "standard", "high"])
        self.quality_menu.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        # FPS
        self.fps_label = ctk.CTkLabel(self.options_frame, text="FPS:")
        self.fps_label.grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.fps_var = ctk.StringVar(value="60")
        self.fps_entry = ctk.CTkEntry(self.options_frame, textvariable=self.fps_var)
        self.fps_entry.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

        self.drop_target = ctk.CTkLabel(self, text="", height=100, fg_color="gray20")
        self.drop_target.grid(row=4, column=0, padx=10, pady=10, sticky="nsew")
        self.drop_target.drop_target_register(DND_FILES)
        self.drop_target.dnd_bind('<<Drop>>', self.handle_drop)

        self.bottom_frame = ctk.CTkFrame(self)
        self.bottom_frame.grid(row=5, column=0, padx=10, pady=10, sticky="ew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        self.fade_var = ctk.BooleanVar(value=False)
        self.fade_checkbox = ctk.CTkCheckBox(self.bottom_frame, variable=self.fade_var)
        self.fade_checkbox.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.render_button = ctk.CTkButton(self.bottom_frame, command=self.start_render_thread)
        self.render_button.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        
        self.stop_button = ctk.CTkButton(self.bottom_frame, command=self.stop_render, fg_color="darkred", hover_color="red")
        self.stop_button.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.stop_button.grid_remove()

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(row=6, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove() # Hide initially

        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.grid(row=7, column=0, padx=10, pady=5, sticky="ew")

    def change_language(self, new_lang_upper):
        self.current_lang = new_lang_upper.lower()
        self.update_ui_texts()

    def update_ui_texts(self):
        texts = self.locales[self.current_lang]
        self.title(texts.get("title_multi", "Video Extender - Multi Audio"))
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
        # --- Codec List ---
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
        
        # Filter available codecs and populate menu
        self.active_codec_map = {
            desc: name for name, desc in self.codec_display_map.items() if name in self.available_encoders
        }
        
        if not self.active_codec_map:
            messagebox.showerror("Error", "No supported video encoders found in your ffmpeg build.")
            self.codec_menu.configure(values=["No codecs found"], state="disabled")
        else:
            self.codec_menu.configure(values=list(self.active_codec_map.keys()))
            
            # Set default codec
            default_codec_desc = None
            if platform.system() == "Darwin" and self.codec_display_map['h264_videotoolbox'] in self.active_codec_map:
                default_codec_desc = self.codec_display_map['h264_videotoolbox']
            elif self.codec_display_map['libx264'] in self.active_codec_map:
                default_codec_desc = self.codec_display_map['libx264']
            else: # Fallback to first available
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
            elif file.lower().endswith(('.mp3', '.wav', '.flac', '.aac')):
                if file not in self.audio_paths:
                    self.audio_paths.append(file)
                    self.audio_listbox.insert(tk.END, os.path.basename(file))
        self.get_video_info()
        self.update_ui_texts()

    def get_video_info(self):
        if not self.video_path:
            return
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate', '-of', 'csv=s=x:p=0', self.video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            
            # Resolution
            res_match = re.search(r'(\d+x\d+)', output)
            if res_match:
                self.original_resolution = res_match.group(1)
                self.resolution_var.set(self.original_resolution)

            # FPS
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
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
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
            total_audio_duration = sum(self.get_audio_duration(p) for p in self.audio_paths if p)
            if total_audio_duration == 0:
                if self.winfo_exists(): self.after(0, self.on_render_error, "Could not get total audio duration.")
                return

            command = self.build_ffmpeg_command(output_path, total_audio_duration, fade_enabled)
            if not command:
                return

            self.run_ffmpeg(command)
            
            # Start a thread to monitor progress
            monitor_thread = threading.Thread(target=self.monitor_progress, args=(total_audio_duration,))
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
                    # Fallback for macOS if VideoToolbox fails
                    if platform.system() == "Darwin" and "videotoolbox" in " ".join(command):
                         print("VideoToolbox encoding failed. Retrying with CPU (libx264)...")
                         command = self.build_ffmpeg_command(output_path, total_audio_duration, fade_enabled, force_cpu=True)
                         self.run_ffmpeg(command)
                         
                         monitor_thread = threading.Thread(target=self.monitor_progress, args=(total_audio_duration,))
                         monitor_thread.daemon = True
                         monitor_thread.start()

                         stdout, stderr = self.render_process.communicate()
                         return_code = self.render_process.returncode
                         if self.winfo_exists():
                            if self.stop_requested:
                                self.after(0, self.on_render_cancel)
                                return
                            duration = time.time() - start_time
                            if return_code == 0:
                                self.after(0, self.on_render_success, duration)
                            else:
                                self.after(0, self.on_render_error, stderr)
                    else:
                        self.after(0, self.on_render_error, stderr)

        except Exception as e:
            if self.winfo_exists() and "main thread is not in main loop" not in str(e):
                self.after(0, self.on_render_error, str(e))

    def build_ffmpeg_command(self, output_path, total_audio_duration, fade_enabled, force_cpu=False):
        system = platform.system()

        # On macOS, fade filter is often incompatible with videotoolbox hwaccel in complex filtergraphs.
        # Force CPU rendering if fade is enabled to prevent a crash and fallback cycle.
        if system == "Darwin" and fade_enabled:
            force_cpu = True
            print("Fade filter enabled on macOS. Forcing CPU encoding for stability.")
        
        # --- Get UI settings ---
        selected_codec_display = self.codec_var.get()
        video_codec = self.active_codec_map.get(selected_codec_display)

        if not video_codec:
            self.after(0, self.on_render_error, "Selected codec is not available. Please restart the application.")
            return None

        resolution_display = self.resolution_var.get()
        resolution = self.resolution_display_map.get(resolution_display, self.original_resolution)
        if resolution == "Original":
            resolution = self.original_resolution
        
        fps = self.fps_var.get()
        
        selected_quality_display = self.quality_var.get()
        quality = self.quality_map.get(selected_quality_display, "high")

        # --- Build Command ---
        command = ['ffmpeg', '-y']
        
        # --- Hardware Acceleration ---
        hwaccel_args = []
        video_codec_is_hw = any(c in video_codec for c in ['nvenc', 'amf', 'qsv', 'videotoolbox'])
        use_gpu = False

        if system == "Darwin" and "videotoolbox" in video_codec and not force_cpu:
            command.extend(['-hwaccel', 'videotoolbox'])
            use_gpu = True
        # Add other OS hwaccel logic here if needed (e.g., NVENC, VAAPI)
        
        # --- Inputs ---
        command.extend(['-stream_loop', '-1', '-i', self.video_path])
        for path in self.audio_paths:
            command.extend(['-i', path])

        # --- Filter Complex ---
        filter_complex_parts = []
        
        # Audio processing
        audio_concat_inputs = "".join([f"[{i+1}:a]" for i in range(len(self.audio_paths))])
        audio_concat_filter = f"{audio_concat_inputs}concat=n={len(self.audio_paths)}:v=0:a=1[a_concat]"
        filter_complex_parts.append(audio_concat_filter)
        
        video_input = "[0:v]"
        audio_output = "[a_concat]"

        # Video processing (scaling and framerate)
        video_filters = []
        if use_gpu and 'videotoolbox' in video_codec:
            # Use videotoolbox-native scaling for performance
            video_filters.append(f"scale_videotoolbox={resolution}")
        else:
            video_filters.append(f"scale={resolution}")
        
        video_filters.append(f"fps={fps}")

        # Fading (CPU-based, so it requires download/upload if GPU is used)
        if fade_enabled:
            fade_duration = 1
            if use_gpu and 'videotoolbox' in video_codec:
                # This is a performance bottleneck, but necessary for the filter
                video_filters.insert(0, "hwdownload,format=nv12")
                video_filters.append(f"fade=t=in:st=0:d={fade_duration},fade=t=out:st={total_audio_duration - fade_duration}:d={fade_duration}")
                video_filters.append("hwupload")
            else:
                video_filters.append(f"fade=t=in:st=0:d={fade_duration},fade=t=out:st={total_audio_duration - fade_duration}:d={fade_duration}")
            
            audio_fade = f"[a_concat]afade=t=in:st=0:d={fade_duration},afade=t=out:st={total_audio_duration - fade_duration}:d={fade_duration}[a_out]"
            filter_complex_parts.append(audio_fade)
            audio_output = "[a_out]"

        filter_complex_parts.insert(0, f"{video_input}{','.join(video_filters)}[v_out]")
        
        command.extend(['-filter_complex', ";".join(filter_complex_parts)])
        command.extend(['-map', '[v_out]', '-map', audio_output])
        
        # --- Codec and Quality Settings ---
        command.extend(['-c:v', video_codec])
        command.extend(['-pix_fmt', 'yuv420p']) # Good for compatibility

        if "videotoolbox" in video_codec:
            if 'prores' in video_codec:
                 command.extend(['-profile:v', '3' if quality == 'high' else '2']) # Profile for ProRes: 0=proxy, 1=lt, 2=standard, 3=hq
            else: # H.264/HEVC bitrates
                bitrates = {'fast': '25M', 'standard': '50M', 'high': '80M'} # Example for 4K
                command.extend(['-b:v', bitrates.get(quality, '50M')])
        elif 'nvenc' in video_codec or 'amf' in video_codec:
             command.extend(['-cq', '19' if quality == 'high' else '23'])
        elif 'qsv' in video_codec:
             command.extend(['-global_quality', '19' if quality == 'high' else '23'])
        else: # libx264, libx265, libvpx etc.
            crf = {'fast': '28', 'standard': '23', 'high': '18'}
            preset = {'fast': 'ultrafast', 'standard': 'fast', 'high': 'medium'}
            command.extend(['-crf', crf.get(quality, '23')])
            command.extend(['-preset', preset.get(quality, 'fast')])

        # --- Audio Codec and Final Args ---
        command.extend(['-c:a', 'aac', '-b:a', '320k', '-shortest', output_path])
        
        print(" ".join(command))
        return command

    def run_ffmpeg(self, command):
        startupinfo = None
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        # Add progress argument to ffmpeg command
        command.insert(1, "-progress")
        command.insert(2, "pipe:1") # Redirect progress to stdout

        self.render_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo, universal_newlines=True)

    def monitor_progress(self, total_duration):
        while True:
            if self.render_process is None or self.render_process.poll() is not None:
                break

            try:
                line = self.render_process.stdout.readline()
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