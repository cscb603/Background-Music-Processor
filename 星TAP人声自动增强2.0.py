# -*- coding: utf-8 -*-
"""
星TAP 自动人声增强器 v2.0（短视频配音专属版）
核心升级：
1. 自动适配不同人声（音量/动态/干净度），保持高保真
2. 小白友好：3个场景档位 + 2个核心调节滑块
3. 听感优化：温暖音色/自适应齿音/软峰值限制，适配短视频播放
要求：
 - Python 3.8+
 - PyQt5
 - FFmpeg 可用（程序同目录放 ffmpeg.exe 更稳妥）
"""

import sys
import os
import subprocess
from subprocess import CREATE_NO_WINDOW
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFileDialog, QProgressBar,
                             QMessageBox, QListWidget, QTextEdit, QComboBox,
                             QCheckBox, QSlider)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

# -------------------------- 全局核心参数（可调） --------------------------
TARGET_LUFS = -16.0    # 短视频人声标准响度（广播规范）
LRA = 8                # 动态范围目标（短视频建议8-10）
PEAK_THRESHOLD = -1.5  # 峰值限制（避免手机/耳机爆音）
NOISE_REDUCTION = -30  # 基础降噪强度
# -----------------------------------------------------------------------

def get_ffmpeg_path():
    """优先读取程序同目录的ffmpeg.exe，确保静默处理"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ffmpeg_names = ['ffmpeg.exe', 'ffmpeg']
    
    # 优先检查程序同目录
    for name in ffmpeg_names:
        ffmpeg_path = os.path.join(current_dir, name)
        if os.path.exists(ffmpeg_path) and os.path.isfile(ffmpeg_path):
            # 验证是否为有效可执行文件
            try:
                # 使用stdout/stderr而非capture_output，确保静默
                subprocess.run(
                    [ffmpeg_path, "-version"], 
                    stdout=subprocess.DEVNULL,
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

FFMPEG_PATH = get_ffmpeg_path()

# -------------------------- 人声处理核心逻辑（带自动适配） --------------------------
class VocalProcessor:
    @staticmethod
    def analyze_file(input_path):
        """分析输入文件：属性+响度+动态范围+底噪+高频能量（为自动适配做准备）"""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")
            
        ext = os.path.splitext(input_path)[1].lower()
        is_lossless = ext in [".flac", ".wav", ".alac", ".aiff"]
        
        # 1. 获取比特率等基础信息
        cmd = [FFMPEG_PATH, "-i", input_path, "-hide_banner"]
        try:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
            )
        except Exception as e:
            raise RuntimeError(f"分析文件失败: {str(e)}")

        bitrate = 192
        for line in result.stderr.splitlines():
            if "bitrate" in line and "kb/s" in line:
                try:
                    bitrate = int(line.split("bitrate:")[-1].split("kb/s")[0].strip())
                except:
                    pass

        # 2. 检测响度（loudnorm）
        loudness = VocalProcessor.detect_loudness(input_path)
        # 3. 检测动态范围+底噪（volumedetect）
        dr, noise_floor = VocalProcessor.detect_dynamic_range_and_noise(input_path)
        # 4. 检测高频能量（用于自适应齿音抑制）
        high_freq_energy = VocalProcessor.detect_high_freq_energy(input_path)
        
        return {
            "is_lossless": is_lossless, "ext": ext, "bitrate": min(bitrate, 320),
            "loudness": loudness, "dynamic_range": dr, "noise_floor": noise_floor,
            "high_freq_energy": high_freq_energy, "input_path": input_path
        }

    @staticmethod
    def detect_dynamic_range_and_noise(input_path):
        """同时检测动态范围+底噪（减少FFmpeg调用次数）"""
        cmd = [FFMPEG_PATH, "-i", input_path, "-af", "volumedetect", "-vn", "-f", "null", "-", "-hide_banner"]
        try:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=30
            )
        except Exception as e:
            raise RuntimeError(f"动态范围/底噪检测失败: {str(e)}")
            
        max_vol, min_vol = -10.0, -40.0  # 默认值（参考参考代码）
        for line in result.stderr.splitlines():
            if "max_volume" in line:
                try:
                    max_vol = float(line.split(":")[-1].strip().replace(" dB", ""))
                except:
                    pass
            if "min_volume" in line:
                try:
                    min_vol = float(line.split(":")[-1].strip().replace(" dB", ""))
                except:
                    pass
        dynamic_range = abs(max_vol - min_vol)
        noise_floor = min_vol  # 底噪≈最小音量（简化逻辑）
        return dynamic_range, noise_floor

    @staticmethod
    def detect_loudness(input_path):
        """用loudnorm分析输入响度（短视频标准：-16 LUFS）"""
        cmd = [FFMPEG_PATH, "-i", input_path, "-af", "loudnorm=I=-16:LRA=10:print_format=summary", "-f", "null", "-", "-hide_banner"]
        try:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=30
            )
        except Exception as e:
            raise RuntimeError(f"响度检测失败: {str(e)}")
            
        for line in result.stderr.splitlines():
            if "Input Integrated Loudness" in line:
                try:
                    return float(line.split(":")[-1].strip().split()[0])
                except:
                    pass
        return -20.0  # 检测失败用默认值

    @staticmethod
    def detect_high_freq_energy(input_path):
        """检测高频（3-8kHz）能量，判断齿音强弱"""
        cmd = [FFMPEG_PATH, "-i", input_path, "-af", "bandpass=f=5000:w=2,volumedetect", "-vn", "-f", "null", "-", "-hide_banner"]
        try:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=20
            )
        except Exception as e:
            return -20.0  # 检测失败用默认值
        
        max_vol = -20.0
        for line in result.stderr.splitlines():
            if "max_volume" in line:
                try:
                    max_vol = float(line.split(":")[-1].strip().replace(" dB", ""))
                except:
                    pass
        return max_vol

    @staticmethod
    def build_vocal_filter_chain(
        scene_mode,  # 场景档位：口播/情感/旁白
        voice_clarity_level,  # 人声突出度：1-5
        deesser_on, 
        sound_field, 
        denoise_level, 
        analysis  # 分析结果（响度/底噪/动态范围/高频能量）
    ):
        """
        构建自适应滤镜链（核心优化部分）：
        流程：智能降噪 → EQ调节 → 动态压缩 → 声场处理
        参考广播级代码，简化滤镜链，确保稳定性
        """
        filters = []

        # -------------------------- 1. 智能降噪（不丢细节） --------------------------
        # 底噪越高中降噪越强（nf值：负数绝对值越大，降噪越强）
        dn_map = {"low": "-20", "mid": "-30", "high": "-40"}
        base_dn = int(dn_map.get(denoise_level, "-30"))
        noise_floor = analysis.get("noise_floor", -50.0)
        if noise_floor > -45:  # 高底噪（嘈杂环境）
            final_dn = base_dn
        elif noise_floor < -55:  # 低底噪（干净录音）
            final_dn = base_dn + 10  # 减弱降噪
        else:  # 中等底噪
            final_dn = base_dn + 5   # 适度减弱
        filters.append(f"afftdn=nf={final_dn}:nt=w,highpass=f=80")  # 加低切（滤风噪）


        # -------------------------- 2. EQ调节（场景+人声突出度适配） --------------------------
        eq_parts = []
        # 场景模式对应的基础EQ
        if scene_mode == "口播清晰档":
            # 突出咬字（中频）+ 减弱齿音（高频）
            eq_parts.append("equalizer=f=160:g=2.0:w=1.6")  # 低频适度饱满
            eq_parts.append("equalizer=f=1200:g=2.5:w=1.0") # 中频（咬字）增强
            eq_parts.append("equalizer=f=8000:g=2.0:w=2.0") # 高频适度增强
        elif scene_mode == "情感饱满档":
            # 增强低频+保留动态
            eq_parts.append("equalizer=f=160:g=3.5:w=1.6")  # 低频更饱满
            eq_parts.append("equalizer=f=1200:g=2.0:w=1.0") # 中频正常
            eq_parts.append("equalizer=f=8000:g=2.2:w=2.0") # 高频保留
        else:  # 柔和旁白档
            # 减弱高频+降低动态
            eq_parts.append("equalizer=f=160:g=2.0:w=1.6")  # 低频自然
            eq_parts.append("equalizer=f=1200:g=2.0:w=1.0") # 中频正常
            eq_parts.append("equalizer=f=8000:g=1.5:w=2.0") # 高频减弱（避免刺耳）
        
        # 人声突出度：档位越高，中频（3.5kHz）增益越高
        clarity_gain = (voice_clarity_level - 3) * 0.5  # 1档=-1dB，5档=+1dB
        eq_parts.append(f"equalizer=f=3500:g={2.0 + clarity_gain}:w=1.0") # 清晰度频段增强
        filters.append(",".join(eq_parts))


        # -------------------------- 3. 动态压缩（完全参考广播级参数） --------------------------
        dr = analysis.get("dynamic_range", 12)
        # 根据动态范围调整压缩比（参考参考代码）
        ratio = 3.0 if dr > 20 else 2.0
        
        # 使用多段压缩（参考广播级代码的结构）
        filters.append(f"""asplit=3[low][mid][high];
            [low]lowpass=f=300,acompressor=threshold=-24dB:ratio=3.5:attack=50:release=1000[low_out];
            [mid]highpass=f=300,lowpass=f=3000,acompressor=threshold=-22dB:ratio={ratio}:attack=30:release=800[mid_out];
            [high]highpass=f=3000,acompressor=threshold=-20dB:ratio=2.0:attack=20:release=500[high_out];
            [low_out][mid_out][high_out]amix=inputs=3:weights=1.1 1.0 0.9""")


        # -------------------------- 4. 自适应齿音抑制 --------------------------
        if deesser_on:
            # 从analysis中获取高频能量（已在analyze_file中检测）
            high_freq_energy = analysis.get("high_freq_energy", -20.0)
            i_val = 0.6 if high_freq_energy > -15 else 0.4  # 触发强度
            m_val = 0.6 if high_freq_energy > -15 else 0.4  # 抑制量
            filters.append(f"deesser=i={i_val}:m={m_val}:f=0.5")


        # -------------------------- 5. 声场处理（短视频播放友好） --------------------------
        sound_field_presets = {
            "原声相": "stereo|c0=1.0*c0+0.0*c1|c1=0.0*c0+1.0*c1",
            "轻微扩展": "stereo|c0=0.8*c0+0.2*c1|c1=0.2*c0+0.8*c1",  # 参考参考代码
            "广播立体声": "stereo|c0=0.7*c0+0.3*c1|c1=0.3*c0+0.7*c1,adelay=1ms|0ms"
        }
        pan_expr = sound_field_presets.get(sound_field, sound_field_presets["轻微扩展"])
        filters.append(f"pan={pan_expr}")


        # 构建最终滤镜链，移除空格和换行符（关键！）
        chain = ",".join([f for f in filters if f])
        # 移除所有空格和换行符，确保FFmpeg能正确解析
        chain = chain.replace("\n", "").replace(" ", "")
        return chain

    @staticmethod
    def get_output_params(analysis):
        """根据输入类型选择编码器（短视频常用mp3/m4a）"""
        loudnorm = f"loudnorm=I={TARGET_LUFS}:LRA={LRA}:TP={PEAK_THRESHOLD}:measured_I={analysis.get('loudness', -20.0)}"
        
        if analysis["is_lossless"]:
            return {
                "codec": "flac", 
                "params": ["-compression_level", "5"], 
                "ext": ".flac", 
                "loudnorm": loudnorm
            }
        elif analysis["ext"] in [".m4a", ".aac"]:
            return {
                "codec": "aac", 
                "params": ["-b:a", f"{analysis['bitrate']}k", "-profile:a", "aac_low"], 
                "ext": ".m4a", 
                "loudnorm": loudnorm
            }
        else:
            # 短视频优先mp3（兼容性好）
            return {
                "codec": "libmp3lame", 
                "params": ["-b:a", f"{analysis['bitrate']}k", "-q:a", "2"], 
                "ext": ".mp3", 
                "loudnorm": loudnorm
            }

# -------------------------- 后台处理线程（保持批处理能力） --------------------------
class VocalProcessingThread(QThread):
    progress_updated = pyqtSignal(int)
    all_finished = pyqtSignal()
    error = pyqtSignal(str)
    log = pyqtSignal(str)
    file_processed = pyqtSignal(str, str)

    def __init__(self, file_list,
                 scene_mode="口播清晰档",
                 voice_clarity_level=3,
                 deesser_on=True,
                 sound_field="轻微扩展",
                 denoise_level="mid"):
        super().__init__()
        self.file_list = file_list
        self.scene_mode = scene_mode
        self.voice_clarity_level = voice_clarity_level
        self.deesser_on = deesser_on
        self.sound_field = sound_field
        self.denoise_level = denoise_level
        self.processor = VocalProcessor()
        self.abort = False  # 线程中断标记

    def run(self):
        total = len(self.file_list)
        for idx, input_path in enumerate(self.file_list, start=1):
            if self.abort:
                self.log.emit("处理已终止")
                return
                
            filename = os.path.basename(input_path)
            self.log.emit(f"开始处理：{filename}")
            try:
                # 1. 分析文件（获取响度/底噪/动态范围/高频能量）
                analysis = self.processor.analyze_file(input_path)
                self.log.emit(f"  状态：响度{analysis['loudness']:.1f}LUFS | 动态范围{analysis['dynamic_range']:.1f}dB | 底噪{analysis['noise_floor']:.1f}dB")
                
                # 2. 构建自适应滤镜链
                filter_chain = self.processor.build_vocal_filter_chain(
                    self.scene_mode, self.voice_clarity_level, self.deesser_on,
                    self.sound_field, self.denoise_level, analysis
                )
                self.log.emit(f"  处理链长度：{len(filter_chain)} 字符")
                
                # 3. 执行处理
                output_params = self.processor.get_output_params(analysis)
                output_path = self._process(input_path, filter_chain, output_params)
                self.file_processed.emit(input_path, output_path)
            except Exception as e:
                self.error.emit(f"{filename} 处理失败：{str(e)}")
            progress = int(idx / total * 100)
            self.progress_updated.emit(progress)
        
        self.all_finished.emit()

    def _process(self, input_path, filter_chain, output_params):
        """执行FFmpeg处理（分两步：预处理→编码，避免失真）"""
        base = os.path.splitext(input_path)[0]
        temp_wav = f"{base}_vocal_temp.wav"  # 中间wav（无损处理）
        output_path = f"{base}_配音优化后{output_params['ext']}"

        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        # 清理旧临时文件
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

        try:
            # Step 1: 预处理（无损wav，避免中间编码损失）
            pre_cmd = [
                FFMPEG_PATH, "-y", "-hide_banner", "-i", input_path, 
                "-filter_complex", filter_chain,
                "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",  # 标准人声格式
                temp_wav
            ]
            self.log.emit(f"  执行预处理（无损wav）...")
            result = subprocess.run(
                pre_cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=300  # 长音频超时设为5分钟
            )
            
            if result.returncode != 0:
                error_msg = result.stderr[:200].replace(chr(10), ' ')
                raise Exception(f"预处理失败：{error_msg}")

            # 检查临时文件有效性
            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1024:
                raise Exception("预处理未生成有效文件")

            # Step 2: 响度标准化+编码（输出目标格式）
            post_cmd = [
                FFMPEG_PATH, "-y", "-hide_banner", "-i", temp_wav, 
                "-af", output_params["loudnorm"],
                "-c:a", output_params["codec"]
            ] + output_params["params"] + [output_path]
            
            self.log.emit("  执行编码（适配短视频格式）...")
            result = subprocess.run(
                post_cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=300
            )
            
            if result.returncode != 0:
                error_msg = result.stderr[:200].replace(chr(10), ' ')
                raise Exception(f"编码失败：{error_msg}")

            # 验证输出文件
            if not os.path.exists(output_path) or os.path.getsize(output_path) < 8 * 1024:
                raise Exception("输出文件无效（过小）")

            self.log.emit(f"处理完成：{os.path.basename(output_path)}")
            return output_path
            
        finally:
            # 清理临时文件
            try:
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
            except Exception as e:
                self.log.emit(f"警告：临时文件清理失败: {str(e)}")
        
    def stop(self):
        """停止线程处理"""
        self.abort = True

# -------------------------- 小白友好的UI界面 --------------------------
class VocalEnhancerTool(QWidget):
    def __init__(self):
        super().__init__()
        self.file_list = []
        self.processed_files = {}
        self.origin_player = QMediaPlayer()
        self.processed_player = QMediaPlayer()
        self.VERSION = "v2.0（短视频配音版）"
        self.BRAND = "星TAP工作室"
        self.TOOL_NAME = f"星TAP 自动人声增强器 {self.VERSION}"
        self.processing_thread = None  # 线程引用
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(self.TOOL_NAME)
        self.setMinimumSize(1000, 800)
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
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 18, 18, 18)

        # 标题
        title = QLabel(self.TOOL_NAME)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # -------------------------- 核心调节区（小白友好） --------------------------
        options_layout = QVBoxLayout()
        
        # 行1：场景模式 + 人声突出度
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("场景模式：", styleSheet="font-weight: 500;"))
        self.scene_combo = QComboBox()
        self.scene_combo.addItems(["口播清晰档", "情感饱满档", "柔和旁白档"])
        self.scene_combo.setCurrentIndex(0)
        row1.addWidget(self.scene_combo)
        
        row1.addWidget(QLabel("人声突出度：", styleSheet="font-weight: 500; margin-left: 20px;"))
        self.voice_clarity_slider = QSlider(Qt.Horizontal)
        self.voice_clarity_slider.setRange(1, 5)
        self.voice_clarity_slider.setValue(3)
        self.voice_clarity_slider.setToolTip("1=自然融合，5=人声更突出（适配背景音乐）")
        self.clarity_label = QLabel("3")  # 显示当前档位
        self.voice_clarity_slider.valueChanged.connect(lambda v: self.clarity_label.setText(str(v)))
        row1.addWidget(self.voice_clarity_slider)
        row1.addWidget(self.clarity_label)
        row1.addStretch()
        options_layout.addLayout(row1)

        # 行2：齿音抑制 + 声场模式
        row2 = QHBoxLayout()
        self.deesser_check = QCheckBox("开启齿音抑制（避免刺耳）")
        self.deesser_check.setChecked(True)
        row2.addWidget(self.deesser_check)
        
        row2.addWidget(QLabel("声场模式：", styleSheet="font-weight: 500; margin-left: 20px;"))
        self.sound_field_combo = QComboBox()
        self.sound_field_combo.addItems(["原声相", "轻微扩展", "广播立体声"])
        self.sound_field_combo.setCurrentIndex(1)
        row2.addWidget(self.sound_field_combo)
        row2.addStretch()
        options_layout.addLayout(row2)

        # 行3：降噪强度
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("降噪强度：", styleSheet="font-weight: 500;"))
        self.denoise_combo = QComboBox()
        self.denoise_combo.addItems(["轻（干净录音）", "中（默认）", "重（嘈杂环境）"])
        self.denoise_combo.setCurrentIndex(1)
        row3.addWidget(self.denoise_combo)
        row3.addStretch()
        options_layout.addLayout(row3)

        main_layout.addLayout(options_layout)

        # -------------------------- 文件管理区 --------------------------
        file_layout = QHBoxLayout()
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.addWidget(QLabel("待处理配音文件："))
        self.file_list_widget = QListWidget()
        self.file_list_widget.setFixedHeight(120)
        list_layout.addWidget(self.file_list_widget)
        file_layout.addWidget(list_widget, 3)

        btn_widget = QWidget()
        btn_layout = QVBoxLayout(btn_widget)
        self.add_btn = QPushButton("添加配音/人声文件")
        self.add_btn.clicked.connect(self.add_files)
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.clicked.connect(self.clear_list)
        self.process_btn = QPushButton("开始配音优化")
        self.process_btn.clicked.connect(self.start_processing)
        self.cancel_btn = QPushButton("取消处理")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.process_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.setSpacing(10)
        file_layout.addWidget(btn_widget, 1)
        main_layout.addLayout(file_layout)

        # 进度条
        self.progress = QProgressBar()
        main_layout.addWidget(self.progress)

        # -------------------------- 播放控制区 --------------------------
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

        self.play_processed = QPushButton("播放优化后")
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

        # -------------------------- 日志区 --------------------------
        log_layout = QVBoxLayout()
        log_layout.addWidget(QLabel("处理日志："))
        self.log_display = QTextEdit()
        self.log_display.setFixedHeight(220)
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        main_layout.addLayout(log_layout)

        # 版本信息
        version_label = QLabel(f"© {self.BRAND} | {self.TOOL_NAME} | 短视频配音专用")
        version_label.setProperty("class", "version-info")
        version_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(version_label)

        self.setLayout(main_layout)

        # 播放器状态监听
        self.origin_player.stateChanged.connect(lambda: self.update_play_btn("origin"))
        self.processed_player.stateChanged.connect(lambda: self.update_play_btn("processed"))
        self.origin_player.error.connect(lambda: self.log(f"原文件播放错误: {self.origin_player.errorString()}"))
        self.processed_player.error.connect(lambda: self.log(f"优化后播放错误: {self.processed_player.errorString()}"))

    # -------------------------- 文件管理功能 --------------------------
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "", "支持格式 (*.wav *.flac *.mp3 *.m4a *.aac)"
        )
        if not files:
            return
        # 过滤有效文件
        valid = [f for f in files if os.path.splitext(f)[1].lower() in [".wav", ".flac", ".mp3", ".m4a", ".aac"]
                 and f not in self.file_list and os.path.getsize(f) > 3*1024]
        self.file_list.extend(valid)
        self.file_list_widget.addItems([os.path.basename(f) for f in valid])
        self.log(f"添加 {len(valid)} 个文件")
        if valid:
            self.play_origin.setEnabled(True)
            self.prev_origin.setEnabled(True)
            self.next_origin.setEnabled(True)

    def clear_list(self):
        self.stop_play()
        if self.processing_thread and self.processing_thread.isRunning():
            self.cancel_processing()
            
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

    # -------------------------- 处理控制功能 --------------------------
    def start_processing(self):
        if not self.file_list:
            QMessageBox.warning(self, "提示", "请先添加文件")
            return

        # 获取用户选择的参数（小白友好的简化参数）
        scene_mode = self.scene_combo.currentText()
        voice_clarity_level = self.voice_clarity_slider.value()
        deesser_on = self.deesser_check.isChecked()
        sound_field = self.sound_field_combo.currentText()
        denoise_level = self.denoise_combo.currentText().split("（")[0]  # 提取“轻/中/重”

        # 启动处理线程
        self.processing_thread = VocalProcessingThread(
            self.file_list,
            scene_mode=scene_mode,
            voice_clarity_level=voice_clarity_level,
            deesser_on=deesser_on,
            sound_field=sound_field,
            denoise_level=denoise_level
        )
        self.processing_thread.progress_updated.connect(self.progress.setValue)
        self.processing_thread.all_finished.connect(self.on_finish)
        self.processing_thread.error.connect(self.on_error)
        self.processing_thread.log.connect(self.log)
        self.processing_thread.file_processed.connect(self.on_file_done)

        # 禁用按钮，防止重复操作
        self.add_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.process_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.processing_thread.start()
        self.log("处理线程已启动（短视频配音模式）")

    def cancel_processing(self):
        if self.processing_thread and self.processing_thread.isRunning():
            self.log("正在取消处理...")
            self.processing_thread.stop()
            self.processing_thread.wait()
            self.processing_thread = None
            self.on_process_canceled()

    def on_process_canceled(self):
        self.progress.setValue(0)
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.log("处理已取消")

    def on_file_done(self, input_path, output_path):
        self.processed_files[input_path] = output_path

    def on_finish(self):
        self.progress.setValue(100)
        QMessageBox.information(self, "完成", "所有配音优化完成！")
        self.play_processed.setEnabled(True)
        self.prev_processed.setEnabled(True)
        self.next_processed.setEnabled(True)
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.processing_thread = None
        self.log("全部任务完成")

    def on_error(self, msg):
        self.progress.setValue(0)
        QMessageBox.critical(self, "错误", msg)
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.processing_thread = None
        self.log(f"错误：{msg}")

    # -------------------------- 播放控制功能 --------------------------
    def play(self, play_type):
        idx = self.file_list_widget.currentRow() if self.file_list_widget.currentRow() != -1 else 0
        if idx < 0 or idx >= len(self.file_list):
            return
            
        file_path = self.file_list[idx] if play_type == "origin" else self.processed_files.get(self.file_list[idx])
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "提示", "文件不存在或尚未处理")
            return

        player = self.origin_player if play_type == "origin" else self.processed_player
        other_player = self.processed_player if play_type == "origin" else self.origin_player
        other_player.stop()

        if player.state() == QMediaPlayer.PlayingState:
            player.pause()
        elif player.state() == QMediaPlayer.PausedState:
            player.play()
        else:
            player.setMedia(QMediaContent())  # 释放旧资源
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
        self.log(f"{'原文件' if play_type == 'origin' else '优化后'} 跳转至 {current}/{total}")

    def stop_play(self):
        self.origin_player.stop()
        self.processed_player.stop()
        self.origin_player.setMedia(QMediaContent())
        self.processed_player.setMedia(QMediaContent())
        self.stop_btn.setEnabled(False)
        self.update_play_btn("origin")
        self.update_play_btn("processed")
        self.log("停止播放")

    def update_play_btn(self, play_type):
        player = self.origin_player if play_type == "origin" else self.processed_player
        btn = self.play_origin if play_type == "origin" else self.play_processed
        if player.state() == QMediaPlayer.PlayingState:
            btn.setText("暂停原文件" if play_type == "origin" else "暂停优化后")
        else:
            btn.setText("播放原文件" if play_type == "origin" else "播放优化后")

    # -------------------------- 日志功能 --------------------------
    def log(self, msg):
        from datetime import datetime
        self.log_display.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())

    # 窗口关闭时释放资源
    def closeEvent(self, event):
        self.stop_play()
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.processing_thread.wait()
        event.accept()

# -------------------------- 程序入口（检查依赖+启动） --------------------------
if __name__ == "__main__":
    # 启动时检查FFmpeg是否可用
    if FFMPEG_PATH is None:
        err = f"未找到FFmpeg！\n请将ffmpeg.exe放在程序同目录，或配置系统PATH。"
        print(err)
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "依赖缺失", err)
        sys.exit(1)

    app = QApplication(sys.argv)
    # 确保中文字体正常显示
    font = app.font()
    font.setFamily("Microsoft YaHei")
    app.setFont(font)
    
    window = VocalEnhancerTool()
    window.show()
    sys.exit(app.exec_())