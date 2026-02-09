import sys
import os
import subprocess
from subprocess import CREATE_NO_WINDOW  # Windows静默参数
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFileDialog, QProgressBar,
                             QMessageBox, QListWidget, QTextEdit, QComboBox,
                             QCheckBox)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

# 核心参数（广播级音频标准）
TARGET_LUFS = -16.0    # 目标响度（符合广播规范）
LRA = 10               # 动态范围
PEAK_THRESHOLD = -1.5  # 峰值限制（避免爆音）
NOISE_REDUCTION = -35  # 智能降噪强度

# -------------------------- FFmpeg路径处理 --------------------------
def get_ffmpeg_path():
    """优先读取程序同目录的ffmpeg.exe，确保静默处理"""
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)  # 打包后路径
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))  # 开发路径
    
    local_ffmpeg = os.path.join(app_dir, "ffmpeg.exe")
    if os.path.exists(local_ffmpeg) and os.path.getsize(local_ffmpeg) > 30 * 1024 * 1024:  # 精简版约30MB+
        return local_ffmpeg
    return "ffmpeg"  #  fallback到系统环境变量

FFMPEG_PATH = get_ffmpeg_path()
# --------------------------------------------------------------------------

class BackgroundMusicProcessor:
    @staticmethod
    def analyze_file(input_path):
        ext = os.path.splitext(input_path)[1].lower()
        is_lossless = ext in [".flac", ".wav", ".alac", ".aiff"]
        
        # 调用FFmpeg分析（静默模式）
        cmd = [FFMPEG_PATH, "-i", input_path, "-hide_banner"]
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding="utf-8", 
            errors="ignore",
            creationflags=CREATE_NO_WINDOW  # 禁止终端窗口
        )
        bitrate = 192
        for line in result.stderr.splitlines():
            if "bitrate" in line and "kb/s" in line:
                try:
                    bitrate = int(line.split("bitrate:")[-1].split("kb/s")[0].strip())
                except:
                    pass
        
        dr = BackgroundMusicProcessor.detect_dynamic_range(input_path)
        loudness = BackgroundMusicProcessor.detect_loudness(input_path)
        return {
            "is_lossless": is_lossless, "ext": ext, "bitrate": min(bitrate, 320),
            "dynamic_range": dr, "loudness": loudness
        }

    @staticmethod
    def detect_dynamic_range(input_path):
        cmd = [FFMPEG_PATH, "-i", input_path, "-af", "volumedetect", "-vn", "-f", "null", "-", "-hide_banner"]
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding="utf-8", 
            errors="ignore",
            creationflags=CREATE_NO_WINDOW
        )
        max_vol, min_vol = -10.0, -40.0
        for line in result.stderr.splitlines():
            if "max_volume" in line:
                max_vol = float(line.split(":")[-1].strip().replace(" dB", ""))
            if "min_volume" in line:
                min_vol = float(line.split(":")[-1].strip().replace(" dB", ""))
        return abs(max_vol - min_vol)

    @staticmethod
    def detect_loudness(input_path):
        cmd = [FFMPEG_PATH, "-i", input_path, "-af", "loudnorm=I=-16:LRA=10:print_format=summary", "-f", "null", "-", "-hide_banner"]
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding="utf-8", 
            errors="ignore",
            creationflags=CREATE_NO_WINDOW
        )
        for line in result.stderr.splitlines():
            if "Input Integrated Loudness" in line:
                return float(line.split(":")[-1].strip().split()[0])
        return -20.0

    @staticmethod
    def build_processing_chain(use_compress, sound_field, avoid_vocal, analysis):
        filters = [
            f"afftdn=nf={NOISE_REDUCTION}:nt=w,highpass=f=50"  # 基础降噪+低切
        ]
        
        if avoid_vocal:
            filters.append("equalizer=f=1500:g=-4:w=2.0,equalizer=f=300:g=1.5:w=1.0,equalizer=f=8000:g=1.5:w=2.0")
        else:
            filters.append("equalizer=f=200:g=1:w=1.0,equalizer=f=5000:g=1:w=2.0")
        
        if use_compress:
            ratio = 3.0 if analysis["dynamic_range"] > 20 else 2.0
            filters.append(f"""asplit=3[low][mid][high];
                [low]lowpass=f=300,acompressor=threshold=-24dB:ratio=3.5:attack=50:release=1000[low_out];
                [mid]highpass=f=300,lowpass=f=3000,acompressor=threshold=-22dB:ratio={ratio}:attack=30:release=800[mid_out];
                [high]highpass=f=3000,acompressor=threshold=-20dB:ratio=2.0:attack=20:release=500[high_out];
                [low_out][mid_out][high_out]amix=inputs=3:weights=1.1 1.0 0.9""")
        
        sound_field_presets = {
            "原声相": "stereo|c0=1.0*c0+0.0*c1|c1=0.0*c0+1.0*c1",
            "轻微扩展": "stereo|c0=0.8*c0+0.2*c1|c1=0.2*c0+0.8*c1",
            "宽声场": "stereo|c0=0.7*c0+0.3*c1|c1=0.3*c0+0.7*c1"
        }
        filters.append(f"pan={sound_field_presets[sound_field]}")
        
        return ",".join(filters).replace("\n", "").replace(" ", "")  # 移除空格换行，避免FFmpeg解析错误

    @staticmethod
    def get_output_params(analysis):
        loudnorm = f"loudnorm=I={TARGET_LUFS}:LRA={LRA}:TP={PEAK_THRESHOLD}:measured_I={analysis['loudness']}"
        if analysis["is_lossless"]:
            return {"codec": "flac", "params": "-compression_level 5", "ext": ".flac", "loudnorm": loudnorm}
        elif analysis["ext"] in [".m4a", ".aac"]:
            return {"codec": "aac", "params": f"-b:a {analysis['bitrate']}k -profile:a aac_low", "ext": ".m4a", "loudnorm": loudnorm}
        else:
            return {"codec": "libmp3lame", "params": f"-b:a {analysis['bitrate']}k -q:a 2", "ext": ".mp3", "loudnorm": loudnorm}


class ProcessingThread(QThread):
    progress_updated = pyqtSignal(int)
    all_finished = pyqtSignal()
    error = pyqtSignal(str)
    log = pyqtSignal(str)
    file_processed = pyqtSignal(str, str)

    def __init__(self, file_list, use_compress, sound_field, avoid_vocal):
        super().__init__()
        self.file_list = file_list
        self.use_compress = use_compress
        self.sound_field = sound_field
        self.avoid_vocal = avoid_vocal
        self.processor = BackgroundMusicProcessor()

    def run(self):
        for i, input_path in enumerate(self.file_list, 1):
            filename = os.path.basename(input_path)
            self.log.emit(f"开始处理：{filename}")
            try:
                analysis = self.processor.analyze_file(input_path)
                self.log.emit(f"  响度：{analysis['loudness']:.1f}LUFS | 动态范围：{analysis['dynamic_range']:.1f}dB")
                if self.use_compress and analysis["dynamic_range"] < 15:
                    self.log.emit("  提示：动态范围较小，可关闭压缩保留细节")
                
                filter_chain = self.processor.build_processing_chain(
                    self.use_compress, self.sound_field, self.avoid_vocal, analysis
                )
                self.log.emit(f"  处理链：{filter_chain[:50]}...")  # 简化显示
                
                output_params = self.processor.get_output_params(analysis)
                output_path = self._process(input_path, filter_chain, output_params)
                self.file_processed.emit(input_path, output_path)
            except Exception as e:
                self.error.emit(f"{filename} 处理失败：{str(e)}")
            self.progress_updated.emit(int(i/len(self.file_list)*100))
        self.all_finished.emit()

    def _process(self, input_path, filter_chain, output_params):
        base = os.path.splitext(input_path)[0]
        temp_wav = f"{base}_bgm_temp.wav"
        output_path = f"{base}_背景音乐适配后{output_params['ext']}"

        try:
            # 预处理（静默模式）
            pre_cmd = [FFMPEG_PATH, "-y", "-hide_banner", "-i", input_path, "-filter_complex", filter_chain, "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", temp_wav]
            result = subprocess.run(
                pre_cmd, 
                capture_output=True, 
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                raise Exception(f"预处理失败：{result.stderr[:100].replace('\n', ' ')}")

            # 响度标准化（静默模式）
            post_cmd = [FFMPEG_PATH, "-y", "-hide_banner", "-i", temp_wav, "-af", output_params["loudnorm"], "-c:a", output_params["codec"], *output_params["params"].split(), output_path]
            result = subprocess.run(
                post_cmd, 
                capture_output=True, 
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                raise Exception(f"标准化失败：{result.stderr[:100].replace('\n', ' ')}")

            if not os.path.exists(output_path) or os.path.getsize(output_path) < 10 * 1024:
                raise Exception("输出文件无效")

            self.log.emit(f"处理完成：{os.path.basename(output_path)}")
            return output_path
        finally:
            if os.path.exists(temp_wav):
                os.remove(temp_wav)


class BgmAdaptTool(QWidget):
    def __init__(self):
        super().__init__()
        self.file_list = []
        self.processed_files = {}
        self.origin_player = QMediaPlayer()
        self.processed_player = QMediaPlayer()
        self.VERSION = "v2.7.0"
        self.BRAND = "星TAP工作室"
        self.TOOL_NAME = f"星TAP广播级背景音乐处理工具{self.VERSION}"
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(self.TOOL_NAME)
        self.setMinimumSize(950, 780)
        self.setStyleSheet("""
            QWidget { background-color: #f0f2f5; font-family: 'Microsoft YaHei', sans-serif; }
            QPushButton { background-color: #1677ff; color: white; border: none; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background-color: #0f62d9; }
            QPushButton:disabled { background-color: #d9d9d9; color: #8c8c8c; }
            QProgressBar { height: 12px; border-radius: 6px; background: #e5e6eb; }
            QProgressBar::chunk { background: #1677ff; border-radius: 6px; }
            QListWidget, QTextEdit, QComboBox { 
                border: 1px solid #d9d9d9; border-radius: 4px; padding: 6px; background: white; 
            }
            .version-info { color: #666; font-size: 12px; margin-top: 10px; }
        """)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel(self.TOOL_NAME)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # 处理选项
        options_layout = QVBoxLayout()
        row1 = QHBoxLayout()
        self.compress_check = QCheckBox("开启动态压缩（音量起伏大时用）")
        row1.addWidget(self.compress_check)
        row1.addWidget(QLabel("声场模式：", styleSheet="font-weight: 500; margin-left: 20px;"))
        self.sound_field_combo = QComboBox()
        self.sound_field_combo.addItems(["原声相", "轻微扩展", "宽声场"])
        self.sound_field_combo.setCurrentIndex(1)
        row1.addWidget(self.sound_field_combo)
        row1.addStretch()
        options_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.avoid_vocal_check = QCheckBox("开启人声避让（适合带解说场景）")
        self.avoid_vocal_check.setChecked(True)
        row2.addWidget(self.avoid_vocal_check)
        row2.addStretch()
        options_layout.addLayout(row2)
        main_layout.addLayout(options_layout)

        # 文件列表和按钮
        file_layout = QHBoxLayout()
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.addWidget(QLabel("待处理文件："))
        self.file_list_widget = QListWidget()
        self.file_list_widget.setFixedHeight(120)
        list_layout.addWidget(self.file_list_widget)
        file_layout.addWidget(list_widget, 3)

        btn_widget = QWidget()
        btn_layout = QVBoxLayout(btn_widget)
        self.add_btn = QPushButton("添加音乐文件")
        self.add_btn.clicked.connect(self.add_files)
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.clicked.connect(self.clear_list)
        self.process_btn = QPushButton("开始广播级处理")
        self.process_btn.clicked.connect(self.start_processing)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.process_btn)
        btn_layout.setSpacing(10)
        file_layout.addWidget(btn_widget, 1)
        main_layout.addLayout(file_layout)

        # 进度条
        self.progress = QProgressBar()
        main_layout.addWidget(self.progress)

        # 播放控制
        play_layout = QHBoxLayout()
        self.play_origin = QPushButton("播放原文件")
        self.play_origin.clicked.connect(lambda: self.play("origin"))
        self.play_origin.setEnabled(False)
        self.prev_origin = QPushButton("←1/8")
        self.prev_origin.clicked.connect(lambda: self.jump("origin", -1))
        self.prev_origin.setEnabled(False)
        self.next_origin = QPushButton("1/8→")
        self.next_origin.clicked.connect(lambda: self.jump("origin", 1))
        self.next_origin.setEnabled(False)
        self.play_processed = QPushButton("播放处理后")
        self.play_processed.clicked.connect(lambda: self.play("processed"))
        self.play_processed.setEnabled(False)
        self.prev_processed = QPushButton("←1/8")
        self.prev_processed.clicked.connect(lambda: self.jump("processed", -1))
        self.prev_processed.setEnabled(False)
        self.next_processed = QPushButton("1/8→")
        self.next_processed.clicked.connect(lambda: self.jump("processed", 1))
        self.next_processed.setEnabled(False)
        self.stop_btn = QPushButton("停止播放")
        self.stop_btn.clicked.connect(self.stop_play)
        self.stop_btn.setEnabled(False)
        play_layout.addWidget(self.play_origin)
        play_layout.addWidget(self.prev_origin)
        play_layout.addWidget(self.next_origin)
        play_layout.addSpacing(30)
        play_layout.addWidget(self.play_processed)
        play_layout.addWidget(self.prev_processed)
        play_layout.addWidget(self.next_processed)
        play_layout.addSpacing(30)
        play_layout.addWidget(self.stop_btn)
        play_layout.addStretch()
        main_layout.addLayout(play_layout)

        # 日志显示
        log_layout = QVBoxLayout()
        log_layout.addWidget(QLabel("处理日志："))
        self.log_display = QTextEdit()
        self.log_display.setFixedHeight(220)
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        main_layout.addLayout(log_layout)

        # 版本声明
        version_label = QLabel(f"© {self.BRAND} | {self.TOOL_NAME} | 版权所有")
        version_label.setProperty("class", "version-info")
        version_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(version_label)

        self.setLayout(main_layout)
        self.origin_player.stateChanged.connect(lambda: self.update_play_btn("origin"))
        self.processed_player.stateChanged.connect(lambda: self.update_play_btn("processed"))

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "", "支持格式 (*.mp3 *.flac *.wav *.m4a *.ogg *.aac)"
        )
        if not files:
            return
        valid = [f for f in files if os.path.splitext(f)[1].lower() in [".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac"] 
                 and f not in self.file_list and os.path.getsize(f) > 10*1024]
        self.file_list.extend(valid)
        self.file_list_widget.addItems([os.path.basename(f) for f in valid])
        self.log(f"添加 {len(valid)} 个文件")
        if valid:
            self.play_origin.setEnabled(True)
            self.prev_origin.setEnabled(True)
            self.next_origin.setEnabled(True)

    def clear_list(self):
        self.stop_play()
        self.file_list = []
        self.file_list_widget.clear()
        self.processed_files = {}
        self.log("清空文件列表")
        self.play_origin.setEnabled(False)
        self.prev_origin.setEnabled(False)
        self.next_origin.setEnabled(False)
        self.play_processed.setEnabled(False)
        self.prev_processed.setEnabled(False)
        self.next_processed.setEnabled(False)

    def start_processing(self):
        if not self.file_list:
            QMessageBox.warning(self, "提示", "请先添加文件")
            return
        self.thread = ProcessingThread(
            self.file_list, 
            self.compress_check.isChecked(), 
            self.sound_field_combo.currentText(), 
            self.avoid_vocal_check.isChecked()
        )
        self.thread.progress_updated.connect(self.progress.setValue)
        self.thread.all_finished.connect(self.on_finish)
        self.thread.error.connect(self.on_error)
        self.thread.log.connect(self.log)
        self.thread.file_processed.connect(self.on_file_done)
        self.add_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.process_btn.setEnabled(False)
        self.progress.setValue(0)
        self.thread.start()

    def on_file_done(self, input_path, output_path):
        self.processed_files[input_path] = output_path

    def on_finish(self):
        self.progress.setValue(100)
        QMessageBox.information(self, "完成", "所有文件处理完成！")
        self.play_processed.setEnabled(True)
        self.prev_processed.setEnabled(True)
        self.next_processed.setEnabled(True)
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.process_btn.setEnabled(True)

    def on_error(self, msg):
        self.progress.setValue(0)
        QMessageBox.critical(self, "错误", msg)
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.log(f"错误：{msg}")

    def play(self, play_type):
        idx = self.file_list_widget.currentRow() if self.file_list_widget.currentRow() != -1 else 0
        if idx >= len(self.file_list):
            return
        file_path = self.file_list[idx] if play_type == "origin" else self.processed_files.get(self.file_list[idx])
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "提示", "文件不存在")
            return

        player = self.origin_player if play_type == "origin" else self.processed_player
        other_player = self.processed_player if play_type == "origin" else self.origin_player
        other_player.stop()

        if player.state() == QMediaPlayer.PlayingState:
            player.pause()
        elif player.state() == QMediaPlayer.PausedState:
            player.play()
        else:
            player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            player.play()
        self.stop_btn.setEnabled(True)

    def jump(self, play_type, direction):
        player = self.origin_player if play_type == "origin" else self.processed_player
        if player.media().isNull():
            self.play(play_type)
            return
        if player.duration() == 0:
            self.log("音频加载中，请稍候...")
            return
        
        step = player.duration() // 8
        new_pos = player.position() + direction * step
        new_pos = max(0, min(new_pos, player.duration()))
        player.setPosition(new_pos)
        current = f"{new_pos//60000:02d}:{(new_pos//1000)%60:02d}"
        total = f"{player.duration()//60000:02d}:{(player.duration()//1000)%60:02d}"
        self.log(f"{'原文件' if play_type == 'origin' else '处理后'} 跳转至 {current}/{total}")

    def stop_play(self):
        self.origin_player.stop()
        self.processed_player.stop()
        self.stop_btn.setEnabled(False)
        self.update_play_btn("origin")
        self.update_play_btn("processed")
        self.log("停止播放")

    def update_play_btn(self, play_type):
        player = self.origin_player if play_type == "origin" else self.processed_player
        btn = self.play_origin if play_type == "origin" else self.play_processed
        btn.setText("暂停原文件" if (play_type == "origin" and player.state() == QMediaPlayer.PlayingState) else 
                   "暂停处理后" if (play_type == "processed" and player.state() == QMediaPlayer.PlayingState) else 
                   "播放原文件" if play_type == "origin" else "播放处理后")

    def log(self, msg):
        from datetime import datetime
        self.log_display.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())


if __name__ == "__main__":
    try:
        # 启动时检查FFmpeg（静默模式）
        subprocess.run(
            [FFMPEG_PATH, "-version"], 
            capture_output=True, 
            check=True,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception as e:
        QMessageBox.critical(None, "依赖缺失", f"未找到FFmpeg！\n请将ffmpeg.exe放在程序同目录。\n错误：{str(e)}")
        sys.exit(1)

    app = QApplication(sys.argv)
    window = BgmAdaptTool()
    window.show()
    sys.exit(app.exec_())
