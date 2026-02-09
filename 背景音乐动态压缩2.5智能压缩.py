# 背景音乐动态压缩工具 2.5版本
# 版权所有 (C) 2025 星TAP团队
# 本软件采用MIT许可证授权，详情参见LICENSE文件

import sys
import os
import subprocess
from subprocess import CREATE_NO_WINDOW  # Windows静默参数
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtWidgets import (QApplication, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFileDialog, QProgressBar, 
                             QMessageBox, QListWidget, QTextEdit, QCheckBox, 
                             QComboBox, QSlider, QGroupBox)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

# 行业标准响度（-16 LUFS，背景音乐最佳实践）
TARGET_LUFS = -16.0
# 支持的音频格式
SUPPORTED_FORMATS = [".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"]

# 查找FFmpeg可执行文件路径（静默模式）
def find_ffmpeg():
    # 检查当前目录
    if getattr(sys, 'frozen', False):
        current_dir = os.path.dirname(sys.executable)  # 打包后路径
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))  # 开发路径
    
    if sys.platform.startswith('win'):
        ffmpeg_names = ['ffmpeg.exe']
    else:
        ffmpeg_names = ['ffmpeg']
    
    # 优先检查程序同目录
    for name in ffmpeg_names:
        ffmpeg_path = os.path.join(current_dir, name)
        if os.path.exists(ffmpeg_path) and os.path.isfile(ffmpeg_path):
            # 验证是否为有效可执行文件
            try:
                # 关键修正：不同时使用capture_output和stdout/stderr
                subprocess.run(
                    [ffmpeg_path, "-version"], 
                    stdout=subprocess.DEVNULL,  # 静默输出
                    stderr=subprocess.DEVNULL,
                    check=True,
                    creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
                )
                return ffmpeg_path
            except:
                continue
    
    # 检查系统环境变量
    for name in ffmpeg_names:
        try:
            subprocess.run(
                [name, "-version"], 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
            )
            return name
        except:
            continue
    
    return None


# -------------------------- 智能动态压缩核心模块 --------------------------
class SmartCompressor:
    """封装智能动态压缩算法：多频段处理+瞬态检测+自适应参数"""
    
    @staticmethod
    def detect_dynamic_range(input_path, ffmpeg_path):
        """检测音频动态范围（dB）"""
        cmd = [
            ffmpeg_path, "-i", input_path,
            "-af", "volumedetect",
            "-vn", "-f", "null", "-",
            "-hide_banner"
        ]
        # 修正：使用stdout/stderr而非capture_output，确保静默
        result = subprocess.run(
            cmd, 
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True, 
            encoding="utf-8", 
            errors="ignore",
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
        )
        if result.returncode != 0:
            return 15.0  # 默认中等动态范围
        
        max_vol, min_vol = -10.0, -30.0
        for line in result.stderr.splitlines():
            if "max_volume" in line:
                max_vol = float(line.split(":")[-1].strip().replace(" dB", ""))
            if "min_volume" in line:
                min_vol = float(line.split(":")[-1].strip().replace(" dB", ""))
        return abs(max_vol - min_vol)

    @staticmethod
    def detect_transient(input_path, ffmpeg_path):
        """检测瞬态比例，返回建议的攻击/释放时间（ms）"""
        cmd = [
            ffmpeg_path, "-i", input_path,
            "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.PeakFactor:file=-",
            "-vn", "-f", "null", "-", "-hide_banner"
        ]
        result = subprocess.run(
            cmd, 
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True, 
            encoding="utf-8", 
            errors="ignore",
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
        )
        
        transient_count = 0
        total_count = 0
        for line in result.stderr.splitlines():
            if "PeakFactor" in line:
                try:
                    peak_factor = float(line.split("=")[-1])
                    if peak_factor > 6:  # 峰值因子>6dB判定为瞬态
                        transient_count += 1
                    total_count += 1
                except:
                    continue
        
        transient_ratio = transient_count / total_count if total_count > 0 else 0.3
        # 瞬态多→短攻击；瞬态少→长攻击
        attack = 5 if transient_ratio > 0.4 else 30
        release = 200 if transient_ratio > 0.4 else 500
        return attack, release, transient_ratio

    @staticmethod
    def detect_lufs(input_path, ffmpeg_path):
        """检测输入音频的响度（LUFS）"""
        cmd = [
            ffmpeg_path, "-i", input_path,
            "-af", "loudnorm=print_format=json",
            "-vn", "-f", "null", "-", "-hide_banner"
        ]
        result = subprocess.run(
            cmd, 
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True, 
            encoding="utf-8", 
            errors="ignore",
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
        )
        try:
            for line in result.stderr.splitlines():
                if '"input_i"' in line:
                    return float(line.split(":")[-1].strip(','))
        except:
            return -20.0  # 默认响度
        return -20.0

    @staticmethod
    def get_multi_band_params(dynamic_range, attack, release, eq_freq=2000, eq_gain=-6):
        """生成多频段压缩参数（低频/中频/高频独立处理），并整合EQ"""
        base_ratio = 2 if dynamic_range < 15 else 3 if dynamic_range < 20 else 4
        
        # 低频（20-250Hz）：保留冲击力，软拐点
        low_compress = (
            f"acompressor=threshold=-22dB:ratio={base_ratio}:attack={attack}:release={release}:knee=12dB:makeup=4dB"
        )
        # 中频（250-2000Hz）：人声核心区，低比率+EQ避让
        mid_compress = (
            f"acompressor=threshold=-20dB:ratio={max(1.5, base_ratio-0.5)}:attack={min(attack+20, 50)}:release={min(release+300, 800)}:knee=8dB:makeup=3dB,"
            f"equalizer=f={eq_freq}:g={eq_gain}:w=1.0"
        )
        # 高频（2000-16000Hz）：保护细节，最低比率
        high_compress = (
            f"acompressor=threshold=-18dB:ratio={max(1.2, base_ratio-1)}:attack={max(attack-2, 3)}:release={min(release+100, 500)}:knee=6dB:makeup=2dB"
        )
        
        # 多频段分离与合并滤镜链
        return (
            f"asplit=3[low][mid][high];"
            f"[low]lowpass=250,{low_compress}[low_out];"  # 低频过滤+压缩
            f"[mid]highpass=250,lowpass=2000,{mid_compress}[mid_out];"  # 中频过滤+压缩+EQ
            f"[high]highpass=2000,{high_compress}[high_out];"  # 高频过滤+压缩
            f"[low_out][mid_out][high_out]amix=inputs=3:weights=1.2 1 0.8"  # 频段加权合并
        )

    @staticmethod
    def get_adaptive_loudnorm(input_lufs):
        """根据输入响度调整目标响度（避免过度提升噪声）"""
        target_lufs = TARGET_LUFS
        if input_lufs < (TARGET_LUFS - 10):  # 输入过安静
            target_lufs = input_lufs + 8  # 最多提升8dB
        return f"loudnorm=I={target_lufs}:LRA=11:TP=-1.5"


# -------------------------- 处理线程 --------------------------
class BGMMusicMasteringThread(QThread):
    progress_updated = pyqtSignal(int)
    all_finished = pyqtSignal()
    error = pyqtSignal(str)
    log = pyqtSignal(str)
    file_processed = pyqtSignal(str, str)

    def __init__(self, file_list, pan_type, eq_enabled, eq_freq, eq_gain, 
                 compress_enabled, use_smart_compress, ffmpeg_path, test_mode=False):
        super().__init__()
        self.file_list = file_list
        self.total = len(file_list)
        self.pan_type = pan_type
        self.eq_enabled = eq_enabled
        self.eq_freq = eq_freq
        self.eq_gain = eq_gain
        self.compress_enabled = compress_enabled
        self.use_smart_compress = use_smart_compress  # 是否启用智能压缩
        self.ffmpeg_path = ffmpeg_path  # FFmpeg路径
        self.test_mode = test_mode  # 测试模式：只输出参数不实际处理
        self.running = True
        self.smart_compressor = SmartCompressor()  # 智能压缩实例

    def run(self):
        try:
            for i, input_path in enumerate(self.file_list, 1):
                if not self.running:
                    break
                self.log.emit(f"开始处理: {os.path.basename(input_path)}")
                
                try:
                    # 智能压缩参数计算
                    if self.compress_enabled and self.use_smart_compress:
                        self.log.emit("→ 启用智能动态压缩（多频段+瞬态适配）")
                        dynamic_range = self.smart_compressor.detect_dynamic_range(input_path, self.ffmpeg_path)
                        attack, release, transient_ratio = self.smart_compressor.detect_transient(input_path, self.ffmpeg_path)
                        input_lufs = self.smart_compressor.detect_lufs(input_path, self.ffmpeg_path)
                        
                        self.log.emit(f"  动态范围：{dynamic_range:.1f}dB | 瞬态比例：{transient_ratio:.1%}")
                        self.log.emit(f"  输入响度：{input_lufs:.1f}LUFS | 建议攻击/释放：{attack}/{release}ms")
                        
                        compress_filter = self.smart_compressor.get_multi_band_params(
                            dynamic_range, attack, release, self.eq_freq, self.eq_gain
                        )
                        loudnorm_filter = self.smart_compressor.get_adaptive_loudnorm(input_lufs)
                    elif self.compress_enabled:
                        # 传统压缩（兼容原有逻辑）
                        self.log.emit("→ 启用传统动态压缩")
                        dynamic_range = self.smart_compressor.detect_dynamic_range(input_path, self.ffmpeg_path)
                        compress_params = self._get_traditional_compress_params(dynamic_range)
                        compress_filter = f"acompressor={compress_params}"
                        loudnorm_filter = f"loudnorm=I={TARGET_LUFS}:LRA=11:TP=-1.5"
                    else:
                        self.log.emit("→ 未启用动态压缩")
                        compress_filter = "anull"  # 无压缩
                        loudnorm_filter = f"loudnorm=I={TARGET_LUFS}:LRA=11:TP=-1.5"

                    # 测试模式：只输出参数，不实际处理
                    if self.test_mode:
                        self.log.emit(f"【测试模式】压缩滤镜：{compress_filter[:100]}...")
                        self.log.emit(f"【测试模式】响度滤镜：{loudnorm_filter}")
                        output_path = input_path + "_test_mode.txt"
                        with open(output_path, "w") as f:
                            f.write(f"测试参数已生成：\n{compress_filter}\n{loudnorm_filter}")
                    else:
                        # 实际处理流程
                        output_path = self._process_audio(input_path, compress_filter, loudnorm_filter)
                    
                    self.file_processed.emit(input_path, output_path)
                except Exception as e:
                    self.error.emit(f"处理失败：{str(e)}")
                
                self.progress_updated.emit(int(i / self.total * 100))
            self.all_finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _get_traditional_compress_params(self, dynamic_range):
        """传统单频段压缩参数（兼容原有逻辑）"""
        if dynamic_range >= 20:
            return "threshold=-20dB:ratio=4:attack=10:release=100:knee=8dB:makeup=6dB"
        elif 10 <= dynamic_range < 20:
            return "threshold=-18dB:ratio=3:attack=8:release=80:knee=6dB:makeup=4dB"
        else:
            return "threshold=-16dB:ratio=2:attack=5:release=60:knee=4dB:makeup=2dB"

    def _process_audio(self, input_path, compress_filter, loudnorm_filter):
        """实际音频处理流程（预处理+后处理）"""
        base, ext = os.path.splitext(input_path)
        temp_path = f"{base}_temp.wav"
        output_path = f"{base}_母带处理后.mp3"

        try:
            # 1. 预处理：EQ+压缩+声相
            pre_filters = []
            if self.eq_enabled:
                pre_filters.append(f"equalizer=f={self.eq_freq}:g={self.eq_gain}:w=1.0")
            pre_filters.append(compress_filter)  # 智能/传统压缩滤镜
            
            # 声相处理
            pan_options = {
                "宽声相（远离人声）": "stereo|c0=0.9*c0+0.1*c1|c1=0.1*c0+0.9*c1",
                "极宽声相（环绕感）": "stereo|c0=1.0*c0+0.0*c1|c1=0.0*c0+1.0*c1",
                "默认（轻微拉宽）": "stereo|c0=0.8*c0+0.2*c1|c1=0.2*c0+0.8*c1"
            }
            if self.pan_type:
                pre_filters.append(f"pan={pan_options[self.pan_type]}")

            pre_filter_complex = ",".join(pre_filters)
            pre_cmd = [
                self.ffmpeg_path, "-y", "-hide_banner",
                "-i", input_path,
                "-filter_complex", pre_filter_complex,
                "-codec:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
                temp_path
            ]
            self.log.emit(f"预处理命令: {' '.join(pre_cmd[:10])}...")
            result = subprocess.run(
                pre_cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
            )
            if result.returncode != 0:
                raise Exception(f"预处理失败：{result.stderr[:200]}")

            # 2. 后处理：响度标准化
            post_cmd = [
                self.ffmpeg_path, "-y", "-hide_banner",
                "-i", temp_path,
                "-af", loudnorm_filter,
                "-codec:a", "libmp3lame", "-qscale:a", "2",
                output_path
            ]
            self.log.emit(f"后处理命令: {' '.join(post_cmd[:10])}...")
            result = subprocess.run(
                post_cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
            )
            if result.returncode != 0:
                raise Exception(f"后处理失败：{result.stderr[:200]}")

            self.log.emit(f"处理完成: {os.path.basename(output_path)}")
            return output_path

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


# -------------------------- 主界面 --------------------------
class 母带级背景音乐工具(QWidget):
    def __init__(self, cmd_files=None, ffmpeg_path=None):
        super().__init__()
        self.file_list = []
        self.processed_files = {}
        self.origin_player = QMediaPlayer()
        self.processed_player = QMediaPlayer()
        self.is_playing = False
        self.current_play_type = None
        self.cmd_files = cmd_files or []
        self.ffmpeg_path = ffmpeg_path
        self.init_ui()
        if self.cmd_files:
            self.add_files_to_list(self.cmd_files)

    def init_ui(self):
        self.setWindowTitle("星TAP母带级背景音乐工具（智能压缩版 2.5）")
        self.setMinimumSize(950, 700)
        self.setMaximumSize(1200, 800)
        
        # 样式表
        self.setStyleSheet("""
            QWidget { 
                background-color: #f8f9fa; 
                font-family: 'Microsoft YaHei', 'Arial', sans-serif; 
                font-size: 12px;
            }
            QPushButton { 
                background-color: #2c82c9; 
                color: white; 
                border: none; 
                border-radius: 4px; 
                padding: 6px 12px; 
                min-width: 80px;
            }
            QPushButton:hover { background-color: #1a73e8; }
            QPushButton:disabled { background-color: #b0b0b0; color: #f0f0f0; }
            QProgressBar { 
                height: 12px; 
                border-radius: 6px; 
                background-color: #e0e0e0; 
            }
            QProgressBar::chunk { 
                background-color: #2c82c9; 
                border-radius: 6px; 
            }
            QListWidget, QTextEdit { 
                border: 1px solid #ddd; 
                border-radius: 4px; 
                padding: 6px; 
                background-color: white; 
            }
            QGroupBox { 
                font-size: 13px; 
                font-weight: bold; 
                margin-top: 6px;
                margin-bottom: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
            }
            QComboBox { padding: 3px 5px; font-size: 11px; }
            QSlider { margin: 0 6px; }
            .title { font-size: 14px; font-weight: bold; }
            .hint { font-size: 10px; color: #666; }
            .small-btn { padding: 4px 8px; min-width: 60px; font-size: 10px; }
            .main-btn { background-color: #1a73e8; font-size: 13px; padding: 8px 16px; }
            .test-btn { background-color: #4CAF50; }  /* 测试按钮绿色 */
        """)

        # 主布局（3:2列比例）
        main_layout = QGridLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setColumnStretch(0, 3)
        main_layout.setColumnStretch(1, 2)

        # 标题区域（含版权声明）
        title = QLabel("星TAP背景音乐工具（智能压缩版 2.5）")
        title.setProperty("class", "title")
        title.setAlignment(Qt.AlignCenter)
        copyright_hint = QLabel("© 2025 星TAP团队 版权所有 | 母带级音频处理标准")
        copyright_hint.setProperty("class", "hint")
        copyright_hint.setAlignment(Qt.AlignCenter)
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        title_layout.addWidget(title)
        title_layout.addWidget(copyright_hint)
        main_layout.addLayout(title_layout, 0, 0, 1, 2)

        # 设置区（左：EQ；右：声相+压缩选项）
        ## 左列：EQ设置
        self.eq_group = QGroupBox("EQ设置（避让人声频段）")
        eq_layout = QVBoxLayout()
        eq_layout.setSpacing(8)
        eq_layout.setContentsMargins(10, 10, 10, 10)
        
        self.eq_enabled = QCheckBox("启用EQ")
        self.eq_enabled.setChecked(False)
        eq_layout.addWidget(self.eq_enabled)
        
        # EQ频率
        eq_freq_layout = QHBoxLayout()
        eq_freq_label = QLabel("频率：")
        eq_freq_label.setFixedWidth(50)
        self.eq_freq_slider = QSlider(Qt.Horizontal)
        self.eq_freq_slider.setRange(200, 3000)
        self.eq_freq_slider.setValue(2000)
        self.eq_freq_display = QLabel("2000Hz")
        self.eq_freq_display.setFixedWidth(60)
        self.eq_freq_display.setAlignment(Qt.AlignRight)
        eq_freq_layout.addWidget(eq_freq_label)
        eq_freq_layout.addWidget(self.eq_freq_slider)
        eq_freq_layout.addWidget(self.eq_freq_display)
        
        # EQ增益
        eq_gain_layout = QHBoxLayout()
        eq_gain_label = QLabel("增益：")
        eq_gain_label.setFixedWidth(50)
        self.eq_gain_slider = QSlider(Qt.Horizontal)
        self.eq_gain_slider.setRange(-12, 0)
        self.eq_gain_slider.setValue(-6)
        self.eq_gain_display = QLabel("-6dB")
        self.eq_gain_display.setFixedWidth(60)
        self.eq_gain_display.setAlignment(Qt.AlignRight)
        eq_gain_layout.addWidget(eq_gain_label)
        eq_gain_layout.addWidget(self.eq_gain_slider)
        eq_gain_layout.addWidget(self.eq_gain_display)
        
        eq_layout.addLayout(eq_freq_layout)
        eq_layout.addLayout(eq_gain_layout)
        self.eq_group.setLayout(eq_layout)
        main_layout.addWidget(self.eq_group, 1, 0)

        ## 右列：声相+压缩选项
        right_settings_layout = QVBoxLayout()
        right_settings_layout.setSpacing(10)

        # 声相设置
        pan_group = QGroupBox("声相类型")
        pan_layout = QVBoxLayout()
        pan_layout.setContentsMargins(10, 10, 10, 10)
        self.pan_combo = QComboBox()
        self.pan_combo.addItems(["默认（轻微拉宽）", "宽声相（远离人声）", "极宽声相（环绕感）"])
        self.pan_combo.setCurrentIndex(0)
        pan_layout.addWidget(self.pan_combo)
        pan_group.setLayout(pan_layout)
        right_settings_layout.addWidget(pan_group)

        # 压缩选项
        compress_group = QGroupBox("动态压缩设置")
        compress_layout = QVBoxLayout()
        compress_layout.setSpacing(6)
        compress_layout.setContentsMargins(10, 10, 10, 10)
        
        self.compress_enabled = QCheckBox("启用动态压缩")
        self.compress_enabled.setChecked(True)
        self.use_smart_compress = QCheckBox("使用智能压缩（多频段+瞬态适配）")
        self.use_smart_compress.setChecked(True)
        self.test_mode = QCheckBox("测试模式（只输出参数，不处理音频）")
        self.test_mode.setChecked(False)
        
        compress_hint = QLabel("智能压缩：自动适配不同频段和瞬态特性，听感更自然")
        compress_hint.setProperty("class", "hint")
        compress_hint.setWordWrap(True)
        
        compress_layout.addWidget(self.compress_enabled)
        compress_layout.addWidget(self.use_smart_compress)
        compress_layout.addWidget(self.test_mode)
        compress_layout.addWidget(compress_hint)
        compress_group.setLayout(compress_layout)
        right_settings_layout.addWidget(compress_group)

        main_layout.addLayout(right_settings_layout, 1, 1)

        # 文件处理区
        file_process_layout = QHBoxLayout()
        file_process_layout.setSpacing(10)

        ## 文件列表
        file_list_widget = QWidget()
        file_list_layout = QVBoxLayout(file_list_widget)
        file_list_layout.setSpacing(5)
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        
        file_list_label = QLabel("处理列表：")
        self.file_list_widget = QListWidget()
        self.file_list_widget.setFixedHeight(100)
        file_list_layout.addWidget(file_list_label)
        file_list_layout.addWidget(self.file_list_widget)
        file_process_layout.addWidget(file_list_widget, 3)

        ## 操作按钮
        btn_group = QWidget()
        btn_layout = QVBoxLayout(btn_group)
        btn_layout.setSpacing(10)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        
        self.add_btn = QPushButton("添加音乐文件")
        self.add_btn.clicked.connect(self.add_files)
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.clicked.connect(self.clear_list)
        self.process_btn = QPushButton("开始母带级自动处理")
        self.process_btn.setProperty("class", "main-btn")
        self.process_btn.clicked.connect(self.start_processing)
        self.test_btn = QPushButton("仅测试压缩参数")
        self.test_btn.setProperty("class", "test-btn")
        self.test_btn.clicked.connect(self.test_compress_params)
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.process_btn)
        btn_layout.addWidget(self.test_btn)
        file_process_layout.addWidget(btn_group, 2)

        main_layout.addLayout(file_process_layout, 2, 0, 1, 2)

        # 进度条
        self.progress = QProgressBar()
        main_layout.addWidget(self.progress, 3, 0, 1, 2)

        # 播放控制区
        play_control_layout = QHBoxLayout()
        play_control_layout.setSpacing(8)
        
        self.play_origin_btn = QPushButton("播放原文件")
        self.play_origin_btn.clicked.connect(lambda: self.play_audio("origin"))
        self.play_origin_btn.setEnabled(False)
        self.prev_16_origin_btn = QPushButton("←1/16")
        self.prev_16_origin_btn.setProperty("class", "small-btn")
        self.prev_16_origin_btn.clicked.connect(lambda: self.jump_audio("origin", -1))
        self.prev_16_origin_btn.setEnabled(False)
        self.next_16_origin_btn = QPushButton("1/16→")
        self.next_16_origin_btn.setProperty("class", "small-btn")
        self.next_16_origin_btn.clicked.connect(lambda: self.jump_audio("origin", 1))
        self.next_16_origin_btn.setEnabled(False)

        self.play_processed_btn = QPushButton("播放处理后")
        self.play_processed_btn.clicked.connect(lambda: self.play_audio("processed"))
        self.play_processed_btn.setEnabled(False)
        self.prev_16_processed_btn = QPushButton("←1/16")
        self.prev_16_processed_btn.setProperty("class", "small-btn")
        self.prev_16_processed_btn.clicked.connect(lambda: self.jump_audio("processed", -1))
        self.prev_16_processed_btn.setEnabled(False)
        self.next_16_processed_btn = QPushButton("1/16→")
        self.next_16_processed_btn.setProperty("class", "small-btn")
        self.next_16_processed_btn.clicked.connect(lambda: self.jump_audio("processed", 1))
        self.next_16_processed_btn.setEnabled(False)

        self.stop_btn = QPushButton("停止播放")
        self.stop_btn.clicked.connect(self.stop_audio)
        self.stop_btn.setEnabled(False)

        play_control_layout.addWidget(self.play_origin_btn)
        play_control_layout.addWidget(self.prev_16_origin_btn)
        play_control_layout.addWidget(self.next_16_origin_btn)
        play_control_layout.addSpacing(20)
        play_control_layout.addWidget(self.play_processed_btn)
        play_control_layout.addWidget(self.prev_16_processed_btn)
        play_control_layout.addWidget(self.next_16_processed_btn)
        play_control_layout.addSpacing(20)
        play_control_layout.addWidget(self.stop_btn)
        play_control_layout.addStretch()
        main_layout.addLayout(play_control_layout, 4, 0, 1, 2)

        # 日志区
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setSpacing(5)
        log_layout.setContentsMargins(0, 0, 0, 0)
        
        log_label = QLabel("处理日志：")
        self.log_display = QTextEdit()
        self.log_display.setFixedHeight(150)
        self.log_display.setReadOnly(True)
        
        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log_display)
        main_layout.addWidget(log_widget, 5, 0, 1, 2)

        self.setLayout(main_layout)
        self.thread = None

        # 信号连接
        self.eq_freq_slider.valueChanged.connect(self.update_eq_freq_display)
        self.eq_gain_slider.valueChanged.connect(self.update_eq_gain_display)
        self.origin_player.stateChanged.connect(lambda: self.update_play_btn_state("origin"))
        self.processed_player.stateChanged.connect(lambda: self.update_play_btn_state("processed"))
        self.compress_enabled.stateChanged.connect(self.toggle_smart_compress)

    def toggle_smart_compress(self):
        """压缩总开关控制智能压缩选项的可用性"""
        self.use_smart_compress.setEnabled(self.compress_enabled.isChecked())

    def update_eq_freq_display(self, value):
        self.eq_freq_display.setText(f"{value}Hz")

    def update_eq_gain_display(self, value):
        self.eq_gain_display.setText(f"{value}dB")

    # 文件操作
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "", 
            f"支持格式 ({' '.join([f'*{ext}' for ext in SUPPORTED_FORMATS])})"
        )
        if files:
            self.add_files_to_list(files)

    def add_files_to_list(self, files):
        valid_files = []
        for file in files:
            file_ext = os.path.splitext(file)[1].lower()
            if file_ext in SUPPORTED_FORMATS and file not in self.file_list:
                self.file_list.append(file)
                valid_files.append(file)
        for file in valid_files:
            self.file_list_widget.addItem(os.path.basename(file))
        self.log(f"添加文件：{[os.path.basename(f) for f in valid_files]}")
        if valid_files:
            self.play_origin_btn.setEnabled(True)
            self.prev_16_origin_btn.setEnabled(True)
            self.next_16_origin_btn.setEnabled(True)

    def clear_list(self):
        self.stop_audio()
        self.file_list = []
        self.file_list_widget.clear()
        self.processed_files = {}
        self.log("已清空处理列表")
        self.play_origin_btn.setEnabled(False)
        self.prev_16_origin_btn.setEnabled(False)
        self.next_16_origin_btn.setEnabled(False)
        self.play_processed_btn.setEnabled(False)
        self.prev_16_processed_btn.setEnabled(False)
        self.next_16_processed_btn.setEnabled(False)

    # 处理控制
    def start_processing(self):
        """正式处理音频文件"""
        if not self.file_list:
            QMessageBox.warning(self, "提示", "请先添加文件")
            return

        self._start_thread(test_mode=False)

    def test_compress_params(self):
        """仅测试压缩参数，不生成处理后的音频"""
        if not self.file_list:
            QMessageBox.warning(self, "提示", "请先添加文件")
            return

        # 强制开启测试模式
        self.test_mode.setChecked(True)
        self._start_thread(test_mode=True)

    def _start_thread(self, test_mode):
        pan_type = self.pan_combo.currentText()
        eq_enabled = self.eq_enabled.isChecked()
        eq_freq = self.eq_freq_slider.value()
        eq_gain = self.eq_gain_slider.value()
        compress_enabled = self.compress_enabled.isChecked()
        use_smart_compress = self.use_smart_compress.isChecked()

        self.thread = BGMMusicMasteringThread(
            self.file_list, pan_type, eq_enabled, eq_freq, eq_gain,
            compress_enabled, use_smart_compress, self.ffmpeg_path, test_mode
        )
        self.thread.progress_updated.connect(self.progress.setValue)
        self.thread.all_finished.connect(self.on_process_complete)
        self.thread.error.connect(self.on_process_error)
        self.thread.log.connect(self.log)
        self.thread.file_processed.connect(self.on_file_processed)

        self.process_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.test_btn.setEnabled(False)
        self.progress.setValue(0)

        self.thread.start()

    def on_file_processed(self, input_path, output_path):
        self.processed_files[input_path] = output_path
        self.log(f"处理完成：{os.path.basename(output_path)}")

    def on_process_complete(self):
        self.progress.setValue(100)
        msg = "测试完成，参数已输出到日志和文本文件" if self.test_mode.isChecked() else "所有文件处理完成！"
        QMessageBox.information(self, "完成", msg)
        if not self.test_mode.isChecked():
            self.play_processed_btn.setEnabled(True)
            self.prev_16_processed_btn.setEnabled(True)
            self.next_16_processed_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.test_btn.setEnabled(True)

    def on_process_error(self, error_msg):
        self.progress.setValue(0)
        QMessageBox.critical(self, "处理失败", f"出错信息：\n{error_msg}")
        self.process_btn.setEnabled(True)
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.test_btn.setEnabled(True)
        self.log(f"错误：{error_msg}")

    # 播放控制
    def get_selected_audio_path(self, play_type):
        selected_idx = self.file_list_widget.currentRow()
        if selected_idx == -1:
            selected_idx = 0
        if len(self.file_list) <= selected_idx:
            QMessageBox.warning(self, "提示", "无可用音频文件")
            return None
        
        if play_type == "origin":
            return self.file_list[selected_idx]
        else:
            origin_path = self.file_list[selected_idx]
            processed_path = self.processed_files.get(origin_path)
            if not processed_path or not os.path.exists(processed_path):
                QMessageBox.warning(self, "提示", "处理后文件不存在")
                return None
            return processed_path

    def play_audio(self, play_type):
        audio_path = self.get_selected_audio_path(play_type)
        if not audio_path:
            return

        player = self.origin_player if play_type == "origin" else self.processed_player
        other_player = self.processed_player if play_type == "origin" else self.origin_player
        other_player.stop()

        if player.state() == QMediaPlayer.PlayingState:
            player.pause()
        elif player.state() == QMediaPlayer.PausedState:
            player.play()
        else:
            player.setMedia(QMediaContent(QUrl.fromLocalFile(audio_path)))
            player.play()
        
        self.current_play_type = play_type
        self.is_playing = player.state() == QMediaPlayer.PlayingState
        self.stop_btn.setEnabled(player.state() in (QMediaPlayer.PlayingState, QMediaPlayer.PausedState))
        self.update_play_btn_state(play_type)

    def jump_audio(self, play_type, direction):
        player = self.origin_player if play_type == "origin" else self.processed_player
        audio_path = self.get_selected_audio_path(play_type)
        if not audio_path:
            return

        if player.media().isNull():
            player.setMedia(QMediaContent(QUrl.fromLocalFile(audio_path)))
        
        if player.duration() == 0:
            QMessageBox.warning(self, "提示", "音频未加载完成，请稍候")
            return
        
        step = player.duration() // 16
        current_pos = player.position()
        new_pos = current_pos + (direction * step)
        new_pos = max(0, min(new_pos, player.duration()))
        player.setPosition(new_pos)
        
        # 格式化时间显示
        current_sec = new_pos // 1000
        total_sec = player.duration() // 1000
        current_min, current_s = divmod(current_sec, 60)
        total_min, total_s = divmod(total_sec, 60)
        time_str = f"{current_min:02d}:{current_s:02d}/{total_min:02d}:{total_s:02d}"
        self.log(f"跳转{'向前' if direction > 0 else '向后'}1/16：{time_str}")

        if not (player.state() == QMediaPlayer.PlayingState or player.state() == QMediaPlayer.PausedState):
            player.play()
            self.is_playing = True
            self.stop_btn.setEnabled(True)
            self.current_play_type = play_type

    def stop_audio(self):
        self.origin_player.stop()
        self.processed_player.stop()
        self.is_playing = False
        self.current_play_type = None
        self.stop_btn.setEnabled(False)
        self.update_play_btn_state("origin")
        self.update_play_btn_state("processed")
        self.log("已停止播放")

    def update_play_btn_state(self, play_type):
        player = self.origin_player if play_type == "origin" else self.processed_player
        btn = self.play_origin_btn if play_type == "origin" else self.play_processed_btn
        
        if player.state() == QMediaPlayer.PlayingState:
            btn.setText("暂停")
        elif player.state() == QMediaPlayer.PausedState:
            btn.setText("继续")
        else:
            btn.setText("播放原文件" if play_type == "origin" else "播放处理后")
        
        self.stop_btn.setEnabled(player.state() in (QMediaPlayer.PlayingState, QMediaPlayer.PausedState))
        self.is_playing = player.state() == QMediaPlayer.PlayingState

    # 日志输出
    def log(self, msg):
        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{time_str}] {msg}")
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())


# -------------------------- 启动程序 --------------------------
if __name__ == "__main__":
    cmd_files = [os.path.abspath(f) for f in sys.argv[1:] if os.path.exists(f)]
    
    # 检查FFmpeg依赖（静默模式）
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        QMessageBox.critical(None, "依赖缺失", "请先安装FFmpeg并添加到系统环境变量或放置在程序同目录下\n下载地址：https://ffmpeg.org/download.html")
        sys.exit(1)
    
    app = QApplication(sys.argv)
    window = 母带级背景音乐工具(cmd_files=cmd_files, ffmpeg_path=ffmpeg_path)
    window.show()
    sys.exit(app.exec_())
