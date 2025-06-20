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
        self.geometry("600x650")

        self.video_path = ""
        self.audio_path = ""
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
                if line.startswith('V'):
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
        self.grid_rowconfigure(3, weight=1)

        self.lang_var = ctk.StringVar(value=self.current_lang.upper())
        self.lang_menu = ctk.CTkOptionMenu(self, values=[lang.upper() for lang in self.available_langs],
                                           variable=self.lang_var, command=self.change_language)
        self.lang_menu.grid(row=0, column=0, padx=10, pady=10, sticky="ne")

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

        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
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
        self.resolution_var = ctk.StringVar()
        self.resolution_menu = ctk.CTkOptionMenu(self.options_frame, variable=self.resolution_var)
        self.resolution_menu.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        # Quality
        self.quality_label = ctk.CTkLabel(self.options_frame, text="Quality:")
        self.quality_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.quality_var = ctk.StringVar(value="high")
        self.quality_menu = ctk.CTkOptionMenu(self.options_frame, variable=self.quality_var)
        self.quality_menu.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        # FPS
        self.fps_label = ctk.CTkLabel(self.options_frame, text="FPS:")
        self.fps_label.grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.fps_var = ctk.StringVar(value="60")
        self.fps_entry = ctk.CTkEntry(self.options_frame, textvariable=self.fps_var)
        self.fps_entry.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

        self.drop_target = ctk.CTkLabel(self, text="", height=100, fg_color="gray20")
        self.drop_target.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")
        self.drop_target.drop_target_register(DND_FILES)
        self.drop_target.dnd_bind('<<Drop>>', self.handle_drop)

        self.bottom_frame = ctk.CTkFrame(self)
        self.bottom_frame.grid(row=4, column=0, padx=10, pady=10, sticky="ew")
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
        self.progress_bar.grid(row=5, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()

        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.grid(row=6, column=0, padx=10, pady=5, sticky="ew")

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
        self.codec_label.configure(text=texts.get("codec_label", "Codec:"))
        self.resolution_label.configure(text=texts.get("resolution_label", "Resolution:"))
        self.quality_label.configure(text=texts.get("quality_label", "Quality:"))
        self.fps_label.configure(text=texts.get("fps_label", "FPS:"))

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
            if platform.system() == "Darwin" and self.codec_display_map['h264_videotoolbox'] in self.active_codec_map:
                default_codec_desc = self.codec_display_map['h264_videotoolbox']
            elif self.codec_display_map['libx264'] in self.active_codec_map:
                default_codec_desc = self.codec_display_map['libx264']
            else:
                default_codec_desc = list(self.active_codec_map.keys())[0]
            
            self.codec_var.set(default_codec_desc)

        self.quality_map = {
            texts.get("quality_fast"): "fast",
            texts.get("quality_standard"): "standard",
            texts.get("quality_high"): "high"
        }
        self.quality_menu.configure(values=list(self.quality_map.keys()))
        self.quality_var.set(texts.get("quality_high"))

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
        self.get_video_info()
        self.update_ui_texts()

    def get_audio_duration(self, file_path):
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_video_info(self):
        if not self.video_path:
            return
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate', '-of', 'csv=s=x:p=0', self.video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            
            res_match = re.search(r'(\d+x\d+)', output)
            if res_match:
                self.original_resolution = res_match.group(1)

            fps_match = re.search(r'(\d+)/(\d+)', output)
            if fps_match:
                num, den = map(int, fps_match.groups())
                self.original_fps = str(round(num / den)) if den != 0 else "30"

        except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
            print(f"Could not get video info: {e}")
            self.original_resolution = "1920x1080"
            self.original_fps = "30"

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
            if not command: return

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
                    if platform.system() == "Darwin" and "videotoolbox" in " ".join(command) and not self.stop_requested:
                        print("VideoToolbox encoding failed. Retrying with CPU (libx264)...")
                        cpu_command = self.build_ffmpeg_command(output_path, audio_duration, fade_enabled, force_cpu=True)
                        if cpu_command:
                            self.run_ffmpeg(cpu_command)
                            monitor_thread = threading.Thread(target=self.monitor_progress, args=(audio_duration,))
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
                             self.after(0, self.on_render_error, "Failed to build CPU fallback command.")
                    else:
                        if not self.stop_requested:
                            self.after(0, self.on_render_error, stderr)

        except Exception as e:
            if self.winfo_exists() and "main thread is not in main loop" not in str(e):
                self.after(0, self.on_render_error, str(e))

    def build_ffmpeg_command(self, output_path, audio_duration, fade_enabled, force_cpu=False):
        system = platform.system()

        if system == "Darwin" and fade_enabled:
            force_cpu = True
            print("Fade filter enabled on macOS. Forcing CPU encoding for stability.")
        
        selected_codec_display = self.codec_var.get()
        video_codec = self.active_codec_map.get(selected_codec_display)

        if not video_codec:
            self.after(0, self.on_render_error, "Selected codec is not available.")
            return None
        
        if force_cpu:
            video_codec = 'libx264'
            if video_codec not in self.available_encoders:
                 self.after(0, self.on_render_error, "libx264 is not available for CPU fallback.")
                 return None

        resolution_display = self.resolution_var.get()
        resolution = self.resolution_display_map.get(resolution_display, self.original_resolution)
        if resolution == "Original":
            resolution = self.original_resolution
        
        fps = self.fps_var.get()
        
        selected_quality_display = self.quality_var.get()
        quality = self.quality_map.get(selected_quality_display, "high")

        command = ['ffmpeg', '-y']
        
        use_gpu = False
        if system == "Darwin" and "videotoolbox" in video_codec and not force_cpu:
            command.extend(['-hwaccel', 'videotoolbox'])
            use_gpu = True
        
        command.extend(['-stream_loop', '-1', '-i', self.video_path])
        command.extend(['-i', self.audio_path])

        video_filters = []
        if use_gpu:
            video_filters.append(f"scale_videotoolbox={resolution}")
        else:
            video_filters.append(f"scale={resolution}")
        video_filters.append(f"fps={fps}")

        video_input = "[0:v]"
        audio_input = "[1:a]"
        
        filter_complex_parts = []

        if fade_enabled:
            fade_duration = 1
            fade_filter = f"fade=t=in:st=0:d={fade_duration},fade=t=out:st={audio_duration - fade_duration}:d={fade_duration}"
            
            if use_gpu:
                video_filters.insert(0, "hwdownload,format=nv12")
                video_filters.append(fade_filter)
                video_filters.append("hwupload")
            else:
                video_filters.append(fade_filter)
            
            audio_fade_filter = f"{audio_input}afade=t=in:st=0:d={fade_duration},afade=t=out:st={audio_duration - fade_duration}:d={fade_duration}[a_out]"
            filter_complex_parts.append(audio_fade_filter)
            audio_output = "[a_out]"
        else:
            audio_output = audio_input

        video_filter_str = f"{video_input}{','.join(video_filters)}[v_out]"
        filter_complex_parts.insert(0, video_filter_str)
        
        command.extend(['-filter_complex', ";".join(filter_complex_parts)])
        command.extend(['-map', '[v_out]', '-map', audio_output])
        
        command.extend(['-c:v', video_codec])
        command.extend(['-pix_fmt', 'yuv420p'])

        if "videotoolbox" in video_codec:
            if 'prores' in video_codec:
                 command.extend(['-profile:v', '3' if quality == 'high' else '2'])
            else:
                bitrates = {'fast': '10M', 'standard': '15M', 'high': '20M'}
                command.extend(['-b:v', bitrates.get(quality, '15M')])
        elif 'nvenc' in video_codec or 'amf' in video_codec:
             command.extend(['-cq', '19' if quality == 'high' else '23'])
        elif 'qsv' in video_codec:
             command.extend(['-global_quality', '19' if quality == 'high' else '23'])
        else:
            crf = {'fast': '28', 'standard': '23', 'high': '18'}
            preset = {'fast': 'ultrafast', 'standard': 'fast', 'high': 'medium'}
            command.extend(['-crf', crf.get(quality, '23')])
            command.extend(['-preset', preset.get(quality, 'fast')])

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
                if not line: break
                if "out_time_ms" in line:
                    time_str = line.split("=")[1].strip()
                    if time_str == "N/A": continue
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