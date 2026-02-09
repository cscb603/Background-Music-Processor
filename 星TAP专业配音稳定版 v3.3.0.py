# -*- coding: utf-8 -*-
"""
星TAP专业配音增强器 v3.3（稳定版）
基于能跑通的版本重构，保留专业分析显示，优化混响效果
要求：
 - Python 3.8+
 - PyQt5
 - FFmpeg 3.1+
"""

import sys
import os
import subprocess
try:
    from subprocess import CREATE_NO_WINDOW
except Exception:
    CREATE_NO_WINDOW = 0
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFileDialog, QProgressBar,
                             QMessageBox, QListWidget, QTextEdit, QComboBox,
                             QCheckBox, QSlider, QGroupBox, QSpacerItem, QSizePolicy,
                             QGridLayout, QScrollArea)
try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
except Exception:
    QMediaPlayer = None
    QMediaContent = None

# -------------------------- 广播级核心参数 --------------------------
TARGET_LUFS = -16.0    # 电视广播标准响度
PEAK_THRESHOLD = -1.0  # 峰值限制（广播安全标准）
SAMPLE_RATE = 44100    # 标准采样率
BIT_DEPTH = 16         # 标准位深
# -----------------------------------------------------------------------

def get_ffmpeg_path():
    """获取FFmpeg路径（优先程序同目录）"""
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)  # 打包后路径
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))  # 开发路径
    
    for name in ["ffmpeg.exe", "ffmpeg"]:
        local_ffmpeg = os.path.join(app_dir, name)
        if os.path.exists(local_ffmpeg):
            if os.path.getsize(local_ffmpeg) > 5 * 1024 * 1024:
                try:
                    subprocess.run(
                        [local_ffmpeg, "-version"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True,
                        creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0
                    )
                    return local_ffmpeg
                except:
                    continue
    
    # 检查系统环境变量
    for name in ['ffmpeg.exe', 'ffmpeg']:
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

# -------------------------- 专业配音处理核心 --------------------------
class ProfessionalVocalProcessor:
    @staticmethod
    def analyze_audio_quality(input_path):
        """专业级音频质量分析"""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")
            
        analysis = {
            "format": os.path.splitext(input_path)[1].lower(),
            "is_lossless": False,
            "bitrate": 192,
            "sample_rate": 44100,
            "channels": 2,
            "duration": 0,
            "loudness": -20.0,
            "dynamic_range": 12.0,
            "noise_floor": -60.0,
            "gender": "unknown",
            "high_freq_energy": -20.0,
            "volume_level": 0.0,
            "quality_score": 0.0
        }

        # 获取基础信息
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

        # 解析基础信息
        for line in result.stderr.splitlines():
            if "Duration" in line:
                try:
                    duration_str = line.split(",")[0].split(":")[-1].strip()
                    parts = duration_str.split(":")
                    if len(parts) == 3:
                        hours, minutes, seconds = parts
                        analysis["duration"] = float(hours)*3600 + float(minutes)*60 + float(seconds)
                except:
                    pass
            if "Audio" in line:
                try:
                    if "flac" in line or "wav" in line:
                        analysis["is_lossless"] = True
                    if "kb/s" in line:
                        analysis["bitrate"] = int(line.split("kb/s")[0].split()[-1])
                    if "Hz" in line:
                        analysis["sample_rate"] = int(line.split("Hz")[0].split()[-1])
                    if "stereo" in line:
                        analysis["channels"] = 2
                except:
                    pass

        # 专业级分析
        analysis["loudness"] = ProfessionalVocalProcessor.measure_loudness(input_path)
        analysis["dynamic_range"], analysis["noise_floor"] = ProfessionalVocalProcessor.analyze_dynamics(input_path)
        analysis["gender"], analysis["high_freq_energy"] = ProfessionalVocalProcessor.detect_voice_characteristics(input_path)
        analysis["volume_level"] = ProfessionalVocalProcessor.calculate_perceived_loudness(input_path)
        
        # 质量评分
        analysis["quality_score"] = ProfessionalVocalProcessor.calculate_quality_score(analysis)
        
        return analysis

    @staticmethod
    def measure_loudness(input_path):
        """专业响度测量（符合ITU-R BS.1770标准）"""
        cmd = [FFMPEG_PATH, "-i", input_path, "-af", 
               "loudnorm=I=-16:LRA=8:TP=-1.0:print_format=summary", 
               "-f", "null", "-", "-hide_banner"]
        try:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True, 
                encoding="utf-8", 
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=60
            )
        except Exception as e:
            return -20.0
            
        for line in result.stderr.splitlines():
            if "Input Integrated Loudness" in line:
                try:
                    return float(line.split(":")[-1].strip().split()[0])
                except:
                    pass
        return -20.0

    @staticmethod
    def get_volume_stats(input_path):
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
                timeout=60
            )
        except:
            return {"max": -10.0, "min": -60.0, "mean": -20.0}
        max_vol, min_vol, mean_vol = -10.0, -60.0, -20.0
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
            if "mean_volume" in line:
                try:
                    mean_vol = float(line.split(":")[-1].strip().replace(" dB", ""))
                except:
                    pass
        return {"max": max_vol, "min": min_vol, "mean": mean_vol}

    @staticmethod
    def analyze_dynamics(input_path):
        stats = ProfessionalVocalProcessor.get_volume_stats(input_path)
        return abs(stats["max"] - stats["min"]), stats["min"]

    @staticmethod
    def detect_voice_characteristics(input_path):
        stats = ProfessionalVocalProcessor.get_volume_stats(input_path)
        max_vol = stats["max"]
        if max_vol > -6:
            gender = "male"
        elif max_vol < -12:
            gender = "female"
        else:
            gender = "unknown"
            
        return gender, max_vol

    @staticmethod
    def calculate_perceived_loudness(input_path):
        stats = ProfessionalVocalProcessor.get_volume_stats(input_path)
        return stats["mean"]

    @staticmethod
    def calculate_quality_score(analysis):
        """音频质量评分（0-100分）"""
        score = 50.0
        
        # 格式加分
        if analysis["is_lossless"]:
            score += 15
        elif analysis["bitrate"] >= 320:
            score += 10
        elif analysis["bitrate"] >= 192:
            score += 5
        
        # 采样率加分
        if analysis["sample_rate"] >= 48000:
            score += 5
        
        # 响度标准化加分
        if abs(analysis["loudness"] + 16) <= 2:
            score += 10
        elif abs(analysis["loudness"] + 16) <= 4:
            score += 5
        
        # 动态范围加分
        if analysis["dynamic_range"] >= 15:
            score += 10
        elif analysis["dynamic_range"] >= 12:
            score += 5
        
        # 底噪控制加分
        if analysis["noise_floor"] <= -55:
            score += 10
        elif analysis["noise_floor"] <= -45:
            score += 5
        
        return min(score, 100.0)

    @staticmethod
    def build_gentle_reverb_filter(reverb_amount):
        """
        构建温和的混响滤镜（解决回声过大问题）
        使用简单的延迟和音量控制，确保自然效果
        """
        if reverb_amount == 0:
            return ""
            
        reverb_presets = {
            1: {"delays": "30|55|80|110", "decays": "0.20|0.16|0.13|0.10", "wet": "0.12"},
            2: {"delays": "25|50|75|100|130", "decays": "0.24|0.20|0.16|0.13|0.10", "wet": "0.16"},
            3: {"delays": "20|40|60|85|110|140", "decays": "0.28|0.24|0.20|0.16|0.13|0.10", "wet": "0.20"},
            4: {"delays": "18|36|54|76|98|122|150", "decays": "0.32|0.28|0.24|0.20|0.16|0.13|0.10", "wet": "0.24"},
            5: {"delays": "16|32|48|68|88|110|135|165", "decays": "0.36|0.32|0.28|0.24|0.20|0.16|0.13|0.10", "wet": "0.28"}
        }

        params = reverb_presets.get(reverb_amount, reverb_presets[2])

        return f"""
            asplit=2[dry][wet];
            [wet]aecho=0.6:0.4:{params['delays']}:{params['decays']},highpass=f=180,lowpass=f=8000,volume={params['wet']}[wet_out];
            [dry][wet_out]amix=inputs=2:normalize=0
        """.replace("\n", "").replace(" ", "")

    @staticmethod
    def build_professional_filter_chain(
        preset,              # 预设模式
        voice_clarity,       # 语音清晰度：1-5
        warmth_level,        # 温暖度：1-5
        reverb_amount,      # 混响量：0-5
        noise_reduction,    # 降噪强度：low/medium/high
        analysis            # 分析结果
    ):
        """
        构建专业级滤镜链：
        流程：降噪 → 频率矫正 → 动态处理 → 音色优化 → 温和混响 → 响度标准化
        使用简单可靠的滤镜，确保稳定运行
        """
        filters = []

        # -------------------------- 1. 降噪处理（简化版） --------------------------
        # 使用简单的highpass + lowpass降噪，避免afftdn参数问题
        nr_map = {
            "low": "highpass=f=100,lowpass=f=14000",
            "medium": "highpass=f=150,lowpass=f=12000",
            "high": "highpass=f=200,lowpass=f=10000"
        }
        nr_key = {"轻": "low", "中": "medium", "重": "high"}.get(noise_reduction, noise_reduction)
        filters.append(nr_map.get(nr_key, "highpass=f=150,lowpass=f=12000"))

        # -------------------------- 2. 频率矫正（专业EQ） --------------------------
        eq_settings = []
        
        # 根据预设选择EQ曲线
        if preset == "新闻播报":
            eq_settings = [
                "equalizer=f=100:g=1.5:w=0.707",   # 低频饱满
                "equalizer=f=300:g=-1.0:w=1.0",    # 减少鼻音
                "equalizer=f=1000:g=2.0:w=1.0",   # 清晰度增强
                "equalizer=f=3000:g=1.5:w=1.0",   # 语言信息频段
                "equalizer=f=6000:g=0.5:w=2.0"    # 高频细节
            ]
        elif preset == "纪录片解说":
            eq_settings = [
                "equalizer=f=80:g=2.0:w=0.707",    # 低频温暖
                "equalizer=f=250:g=1.0:w=1.0",    # 中低频饱满
                "equalizer=f=800:g=1.5:w=1.0",    # 清晰度
                "equalizer=f=2000:g=1.0:w=1.0",   # 语言频段
                "equalizer=f=4000:g=0.5:w=1.0"    # 细节
            ]
        elif preset == "广告配音":
            eq_settings = [
                "equalizer=f=120:g=1.5:w=0.707",   # 低频
                "equalizer=f=400:g=1.0:w=1.0",    # 中低频
                "equalizer=f=1500:g=2.0:w=1.0",   # 清晰度
                "equalizer=f=4000:g=2.0:w=1.0",   # 临场感
                "equalizer=f=8000:g=1.0:w=2.0"    # 高频明亮
            ]
        else:  # 通用配音
            eq_settings = [
                "equalizer=f=100:g=1.5:w=0.707",   # 低频饱满
                "equalizer=f=300:g=-0.5:w=1.0",   # 轻微去鼻音
                "equalizer=f=1000:g=1.5:w=1.0",   # 清晰度
                "equalizer=f=3000:g=1.0:w=1.0",   # 语言频段
                "equalizer=f=6000:g=0.5:w=2.0"    # 细节
            ]
        
        # 语音清晰度调节
        clarity_gain = (voice_clarity - 3) * 0.6
        eq_settings.append(f"equalizer=f=2500:g={1.5 + clarity_gain}:w=1.2")
        
        # 温暖度调节
        warmth_gain = (warmth_level - 3) * 0.5
        eq_settings.append(f"equalizer=f=200:g={1.0 + warmth_gain}:w=1.4")
        
        filters.append(",".join(eq_settings))

        # -------------------------- 3. 动态处理（温和版） --------------------------
        # 使用简单的压缩器，避免过度压缩
        filters.append("acompressor=threshold=-20dB:ratio=2.0:attack=50:release=500:makeup=2")

        # -------------------------- 4. 音色优化（简化版） --------------------------
        # 使用简单的EQ提升温暖感
        filters.append("equalizer=f=2000:g=0.5:w=2.0")

        # -------------------------- 5. 温和混响处理 --------------------------
        if reverb_amount > 0:
            reverb_filter = ProfessionalVocalProcessor.build_gentle_reverb_filter(reverb_amount)
            if reverb_filter:
                filters.append(reverb_filter)

        # -------------------------- 6. 广播级响度控制 --------------------------
        # 符合ITU-R BS.1770标准
        loudnorm_filter = (
            f"loudnorm=I={TARGET_LUFS}:LRA=8:TP={PEAK_THRESHOLD}:"
            f"measured_I={analysis['loudness']}:measured_LRA={analysis['dynamic_range']}:measured_TP=-1.0"
        )
        filters.append(loudnorm_filter)

        # -------------------------- 7. 最终限制器 --------------------------
        filters.append("alimiter=level_in=1:level_out=1:limit=0.9:attack=0.1:release=5:asc=0")

        return ",".join(filters).replace("\n", "").replace(" ", "")

    @staticmethod
    def get_professional_output_params(analysis):
        if analysis["format"] in [".mp4", ".mov", ".mkv", ".avi"]:
            return {
                "codec": "aac",
                "params": ["-b:a", "192k", "-profile:a", "aac_low"],
                "ext": ".mp4",
                "sample_rate": SAMPLE_RATE,
                "bit_depth": BIT_DEPTH,
                "is_video": True
            }
        if analysis["is_lossless"] or analysis["bitrate"] >= 320:
            return {
                "codec": "flac",
                "params": ["-compression_level", "6"],
                "ext": ".flac",
                "sample_rate": SAMPLE_RATE,
                "bit_depth": BIT_DEPTH,
                "is_video": False
            }
        if analysis["format"] in [".m4a", ".aac"]:
            return {
                "codec": "aac",
                "params": ["-b:a", "192k", "-profile:a", "aac_low"],
                "ext": ".m4a",
                "sample_rate": SAMPLE_RATE,
                "bit_depth": BIT_DEPTH,
                "is_video": False
            }
        return {
            "codec": "libmp3lame",
            "params": ["-b:a", "192k", "-q:a", "2"],
            "ext": ".mp3",
            "sample_rate": SAMPLE_RATE,
            "bit_depth": BIT_DEPTH,
            "is_video": False
        }

# -------------------------- 专业处理线程 --------------------------
class ProfessionalProcessingThread(QThread):
    progress_updated = pyqtSignal(int)
    all_finished = pyqtSignal()
    error = pyqtSignal(str)
    log = pyqtSignal(str)
    file_processed = pyqtSignal(str, str)
    quality_report = pyqtSignal(dict)

    def __init__(self, file_list,
                 preset="通用配音",
                 voice_clarity=3,
                 warmth_level=3,
                 reverb_amount=2,
                 noise_reduction="medium"):
        super().__init__()
        self.file_list = file_list
        self.preset = preset
        self.voice_clarity = voice_clarity
        self.warmth_level = warmth_level
        self.reverb_amount = reverb_amount
        self.noise_reduction = noise_reduction
        self.processor = ProfessionalVocalProcessor()
        self.abort = False

    def run(self):
        total = len(self.file_list)
        for idx, input_path in enumerate(self.file_list, start=1):
            if self.abort:
                self.log.emit("处理已终止")
                return
                
            filename = os.path.basename(input_path)
            self.log.emit(f"开始专业处理：{filename}")
            try:
                # 专业级分析
                self.log.emit("  执行专业音频分析...")
                analysis = self.processor.analyze_audio_quality(input_path)
                
                # 生成质量报告
                self.quality_report.emit(analysis)
                
                # 详细分析报告
                gender_text = "女声" if analysis["gender"] == "female" else "男声" if analysis["gender"] == "male" else "未知"
                quality_level = "优秀" if analysis["quality_score"] >= 80 else "良好" if analysis["quality_score"] >= 60 else "一般"
                
                self.log.emit(f"  质量评估：{quality_level} ({analysis['quality_score']:.1f}分)")
                self.log.emit(f"  声音特征：{gender_text} | 响度{analysis['loudness']:.1f}LUFS | 动态范围{analysis['dynamic_range']:.1f}dB")
                self.log.emit(f"  技术参数：{analysis['sample_rate']}Hz | {'无损' if analysis['is_lossless'] else f'{analysis['bitrate']}kbps'}")
                
                # 构建专业滤镜链
                self.log.emit("  构建专业滤镜链...")
                filter_chain = self.processor.build_professional_filter_chain(
                    self.preset, self.voice_clarity, self.warmth_level,
                    self.reverb_amount, self.noise_reduction, analysis
                )
                self.log.emit(f"  滤镜链复杂度：{len(filter_chain)} 字符")
                
                # 执行专业处理
                output_params = self.processor.get_professional_output_params(analysis)
                output_path = self._professional_process_safe(input_path, filter_chain, output_params)
                self.file_processed.emit(input_path, output_path)
                
            except Exception as e:
                self.error.emit(f"{filename} 处理失败：{str(e)}")
            
            progress = int(idx / total * 100)
            self.progress_updated.emit(progress)
        
        self.all_finished.emit()

    def _professional_process(self, input_path, filter_chain, output_params):
        base = os.path.splitext(input_path)[0]
        temp_wav = f"{base}_professional_temp.wav"
        output_path = f"{base}_专业优化后{output_params['ext']}"

        # 清理旧文件
        for f in [temp_wav, output_path]:
            if os.path.exists(f):
                os.remove(f)

        try:
            # 专业预处理：高质量转换
            pre_cmd = [
                FFMPEG_PATH, "-y", "-hide_banner", "-i", input_path,
                "-filter_complex", filter_chain,
                "-c:a", f"pcm_s{output_params['bit_depth']}le",
                "-ar", str(output_params['sample_rate']),
                "-ac", "2",
                "-vn",
                "-avoid_negative_ts", "make_zero",
                temp_wav
            ]
            self.log.emit("  执行专业预处理...")
            
            
            

            

            
            
            
            
            

            

            
            
        except Exception as e:
            # 捕获并重新抛出异常，确保上层能收到错误信息
            raise e
        




            

            
            result = subprocess.run(
                pre_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=600
            )
            
            if result.returncode != 0:
                error_msg = result.stderr[:200].replace(chr(10), ' ')
                raise Exception(f"预处理失败：{error_msg}")

            # 检查临时文件质量
            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1024:
                raise Exception("预处理未生成有效文件")

            if output_params.get("is_video"):
                post_cmd = [
                    FFMPEG_PATH, "-y", "-hide_banner", "-i", input_path, "-i", temp_wav,
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy",
                    "-c:a", output_params["codec"]
                ] + output_params["params"] + [
                    "-ar", str(output_params['sample_rate']),
                    "-ac", "2",
                    "-movflags", "+faststart",
                    "-shortest",
                    output_path
                ]
            else:
                post_cmd = [
                    FFMPEG_PATH, "-y", "-hide_banner", "-i", temp_wav,
                    "-c:a", output_params["codec"]
                ] + output_params["params"] + [
                    "-ar", str(output_params['sample_rate']),
                    "-ac", "2",
                    "-write_xing", "0",
                    output_path
                ]
            
            self.log.emit("  执行专业编码...")
            result = subprocess.run(
                post_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=600
            )
            
            if result.returncode != 0:
                error_msg = result.stderr[:200].replace(chr(10), ' ')
                raise Exception(f"编码失败：{error_msg}")

            # 质量验证
            if not os.path.exists(output_path) or os.path.getsize(output_path) < 8 * 1024:
                raise Exception("输出文件无效")

            self.log.emit(f"专业处理完成：{os.path.basename(output_path)}")
            return output_path
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_wav):
                os.remove(temp_wav)
        
    def stop(self):
        """停止处理"""
        self.abort = True

    def _professional_process_safe(self, input_path, filter_chain, output_params):
        base = os.path.splitext(input_path)[0]
        temp_wav = f"{base}_professional_temp.wav"
        output_path = f"{base}_专业优化后{output_params['ext']}"

        for f in [temp_wav, output_path]:
            if os.path.exists(f):
                os.remove(f)

        try:
            pre_cmd = [
                FFMPEG_PATH, "-y", "-hide_banner", "-i", input_path,
                "-filter_complex", filter_chain,
                "-c:a", f"pcm_s{output_params['bit_depth']}le",
                "-ar", str(output_params['sample_rate']),
                "-ac", "2",
                "-vn",
                "-avoid_negative_ts", "make_zero",
                temp_wav
            ]
            self.log.emit("  执行专业预处理...")
            result = subprocess.run(
                pre_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=600
            )
            if result.returncode != 0:
                error_msg = result.stderr[:200].replace(chr(10), ' ')
                raise Exception(f"预处理失败：{error_msg}")

            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1024:
                raise Exception("预处理未生成有效文件")

            if output_params.get("is_video"):
                post_cmd = [
                    FFMPEG_PATH, "-y", "-hide_banner", "-i", input_path, "-i", temp_wav,
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy",
                    "-c:a", output_params["codec"]
                ] + output_params["params"] + [
                    "-ar", str(output_params['sample_rate']),
                    "-ac", "2",
                    "-movflags", "+faststart",
                    "-shortest",
                    output_path
                ]
            else:
                post_cmd = [
                    FFMPEG_PATH, "-y", "-hide_banner", "-i", temp_wav,
                    "-c:a", output_params["codec"]
                ] + output_params["params"] + [
                    "-ar", str(output_params['sample_rate']),
                    "-ac", "2",
                    "-write_xing", "0",
                    output_path
                ]

            self.log.emit("  执行专业编码...")
            result = subprocess.run(
                post_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                timeout=600
            )
            if result.returncode != 0:
                error_msg = result.stderr[:200].replace(chr(10), ' ')
                raise Exception(f"编码失败：{error_msg}")

            if not os.path.exists(output_path) or os.path.getsize(output_path) < 8 * 1024:
                raise Exception("输出文件无效")

            self.log.emit(f"专业处理完成：{os.path.basename(output_path)}")
            return output_path

        finally:
            if os.path.exists(temp_wav):
                os.remove(temp_wav)

# -------------------------- 专业配音增强器界面 --------------------------
class ProfessionalVocalEnhancer(QWidget):
    def __init__(self):
        super().__init__()
        self.file_list = []
        self.processed_files = {}
        self.origin_player = QMediaPlayer() if QMediaPlayer else None
        self.processed_player = QMediaPlayer() if QMediaPlayer else None
        self.VERSION = "v3.3（稳定版）"
        self.BRAND = "星TAP工作室"
        self.TOOL_NAME = f"星TAP专业配音增强器 {self.VERSION}"
        self.processing_thread = None
        self.current_analysis = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(self.TOOL_NAME)
        self.setMinimumSize(1000, 800)
        # 专业蓝色配色方案
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
            QSlider::groove:horizontal { background: #e5e6eb; height: 8px; border-radius: 4px; }
            QSlider::handle:horizontal { background: #1677ff; width: 18px; height: 18px; border-radius: 9px; margin: -5px 0; }
            QCheckBox { font-size: 13px; padding: 4px; }
            QGroupBox { border: 1px solid #d9d9d9; border-radius: 6px; margin: 5px; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            .title { font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }
            .subtitle { font-size: 14px; font-weight: 500; color: #495057; margin: 8px 0; }
            .version-info { color: #666; font-size: 12px; margin-top: 10px; }
            .preset-btn { background-color: #52c41a; margin: 2px; padding: 4px 8px; font-size: 12px; }
            .preset-btn:hover { background-color: #389e0d; }
            .quality-high { color: #52c41a; font-weight: bold; }
            .quality-medium { color: #faad14; font-weight: bold; }
            .quality-low { color: #f5222d; font-weight: bold; }
            .small-btn { padding: 4px 8px; font-size: 11px; }
            .analysis-group { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 10px; margin: 5px 0; }
            .analysis-label { font-size: 13px; margin: 3px 0; }
            .analysis-value { font-size: 13px; font-weight: 500; color: #2c3e50; }
        """)

        root_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        root_layout.addWidget(scroll)

        # 标题
        title = QLabel(self.TOOL_NAME)
        title.setProperty("class", "title")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # FFmpeg状态显示
        ffmpeg_status_layout = QHBoxLayout()
        ffmpeg_status_layout.setContentsMargins(0, 5, 0, 10)
        
        if FFMPEG_PATH:
            status_label = QLabel("✅ FFmpeg已就绪")
            status_label.setStyleSheet("color: #52c41a; font-weight: bold;")
            
            # 显示FFmpeg路径信息
            path_info = os.path.basename(FFMPEG_PATH)
            path_label = QLabel(f"路径: {path_info}")
            path_label.setStyleSheet("font-size: 11px; color: #666;")
            
            ffmpeg_status_layout.addWidget(status_label)
            ffmpeg_status_layout.addWidget(path_label)
            ffmpeg_status_layout.addStretch()
        else:
            warning_label = QLabel("⚠️ 未找到FFmpeg！请将ffmpeg.exe放在程序同目录")
            warning_label.setStyleSheet("color: #f5222d; font-weight: bold;")
            ffmpeg_status_layout.addWidget(warning_label)
            ffmpeg_status_layout.addStretch()
        
        main_layout.addLayout(ffmpeg_status_layout)

        # -------------------------- 专业预设区域 --------------------------
        preset_group = QGroupBox("专业预设选择")
        preset_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        preset_layout = QVBoxLayout(preset_group)
        
        # 第一行：配音类型选择
        preset_row1 = QHBoxLayout()
        lbl_type = QLabel("配音类型：")
        lbl_type.setStyleSheet("font-weight: 500; min-width: 80px;")
        preset_row1.addWidget(lbl_type)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["通用配音", "新闻播报", "纪录片解说", "广告配音"])
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.setFixedWidth(150)
        preset_row1.addWidget(self.preset_combo)
        preset_row1.addStretch()
        
        # 第二行：快速预设按钮
        preset_row2 = QHBoxLayout()
        lbl_quick = QLabel("快速应用：")
        lbl_quick.setStyleSheet("font-weight: 500; min-width: 80px;")
        preset_row2.addWidget(lbl_quick)
        
        self.apply_news = QPushButton("新闻腔")
        self.apply_news.setProperty("class", "preset-btn")
        self.apply_news.clicked.connect(lambda: self.apply_professional_preset("news"))
        
        self.apply_documentary = QPushButton("纪录片")
        self.apply_documentary.setProperty("class", "preset-btn")
        self.apply_documentary.clicked.connect(lambda: self.apply_professional_preset("documentary"))
        
        self.apply_advertisement = QPushButton("广告风")
        self.apply_advertisement.setProperty("class", "preset-btn")
        self.apply_advertisement.clicked.connect(lambda: self.apply_professional_preset("advertisement"))
        
        preset_row2.addWidget(self.apply_news)
        preset_row2.addWidget(self.apply_documentary)
        preset_row2.addWidget(self.apply_advertisement)
        preset_row2.addStretch()
        
        preset_layout.addLayout(preset_row1)
        preset_layout.addLayout(preset_row2)
        main_layout.addWidget(preset_group)

        # -------------------------- 核心参数调节区 --------------------------
        params_group = QGroupBox("核心参数调节")
        params_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        params_layout = QVBoxLayout(params_group)
        params_grid = QHBoxLayout()
        params_grid.setSpacing(15)
        
        # 语音清晰度
        clarity_layout = QVBoxLayout()
        clarity_layout.setContentsMargins(0, 0, 0, 0)
        clarity_layout.setSpacing(5)
        clarity_label = QLabel("语音清晰度")
        clarity_label.setStyleSheet("font-weight: 500;")
        self.clarity_slider = QSlider(Qt.Horizontal)
        self.clarity_slider.setRange(1, 5)
        self.clarity_slider.setValue(3)
        self.clarity_value = QLabel("3（标准）")
        self.clarity_value.setStyleSheet("font-size: 11px; text-align: center;")
        self.clarity_slider.valueChanged.connect(self.update_clarity_display)
        
        clarity_layout.addWidget(clarity_label)
        clarity_layout.addWidget(self.clarity_slider)
        clarity_layout.addWidget(self.clarity_value)
        params_grid.addLayout(clarity_layout)
        
        # 声音温暖度
        warmth_layout = QVBoxLayout()
        warmth_layout.setContentsMargins(0, 0, 0, 0)
        warmth_layout.setSpacing(5)
        warmth_label = QLabel("声音温暖度")
        warmth_label.setStyleSheet("font-weight: 500;")
        self.warmth_slider = QSlider(Qt.Horizontal)
        self.warmth_slider.setRange(1, 5)
        self.warmth_slider.setValue(3)
        self.warmth_value = QLabel("3（适中）")
        self.warmth_value.setStyleSheet("font-size: 11px; text-align: center;")
        self.warmth_slider.valueChanged.connect(self.update_warmth_display)
        
        warmth_layout.addWidget(warmth_label)
        warmth_layout.addWidget(self.warmth_slider)
        warmth_layout.addWidget(self.warmth_value)
        params_grid.addLayout(warmth_layout)
        
        # 自然混响
        reverb_layout = QVBoxLayout()
        reverb_layout.setContentsMargins(0, 0, 0, 0)
        reverb_layout.setSpacing(5)
        reverb_label = QLabel("自然混响")
        reverb_label.setStyleSheet("font-weight: 500;")
        self.reverb_slider = QSlider(Qt.Horizontal)
        self.reverb_slider.setRange(0, 5)
        self.reverb_slider.setValue(2)
        self.reverb_value = QLabel("2（轻微）")
        self.reverb_value.setStyleSheet("font-size: 11px; text-align: center;")
        self.reverb_slider.valueChanged.connect(self.update_reverb_display)
        
        reverb_layout.addWidget(reverb_label)
        reverb_layout.addWidget(self.reverb_slider)
        reverb_layout.addWidget(self.reverb_value)
        params_grid.addLayout(reverb_layout)
        
        # 降噪强度
        noise_layout = QVBoxLayout()
        noise_layout.setContentsMargins(0, 0, 0, 0)
        noise_layout.setSpacing(5)
        noise_label = QLabel("降噪强度")
        noise_label.setStyleSheet("font-weight: 500;")
        self.noise_combo = QComboBox()
        self.noise_combo.addItems(["轻（高质量录音）", "中（标准环境）", "重（嘈杂环境）"])
        self.noise_combo.setCurrentIndex(1)
        self.noise_combo.setFixedWidth(160)
        
        noise_layout.addWidget(noise_label)
        noise_layout.addWidget(self.noise_combo)
        params_grid.addLayout(noise_layout)
        
        
        params_layout.addLayout(params_grid)
        main_layout.addWidget(params_group)

        # -------------------------- 音频质量分析区（恢复专业显示） --------------------------
        analysis_group = QGroupBox("音频质量分析")
        analysis_group.setMinimumHeight(140)
        analysis_group.setProperty("class", "analysis-group")
        analysis_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        analysis_layout = QVBoxLayout(analysis_group)
        
        self.analysis_display = QWidget()
        self.analysis_layout = QVBoxLayout(self.analysis_display)
        self.analysis_layout.setContentsMargins(0, 0, 0, 0)
        self.analysis_layout.setSpacing(3)
        
        # 默认分析信息
        default_info = QLabel("选择文件后将显示专业分析结果...")
        default_info.setStyleSheet("font-size: 13px; color: #666; text-align: center; padding: 20px 0;")
        self.analysis_layout.addWidget(default_info)
        
        analysis_layout.addWidget(self.analysis_display)
        main_layout.addWidget(analysis_group)

        # -------------------------- 文件管理区 --------------------------
        file_group = QGroupBox("文件管理")
        file_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        file_layout = QHBoxLayout(file_group)
        
        # 文件列表
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(QLabel("待处理配音文件："))
        self.file_list_widget = QListWidget()
        self.file_list_widget.setMinimumHeight(160)
        self.file_list_widget.itemSelectionChanged.connect(self.on_file_selected)
        list_layout.addWidget(self.file_list_widget)
        file_layout.addWidget(list_widget, 3)

        # 操作按钮
        btn_widget = QWidget()
        btn_layout = QVBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)
        
        self.add_btn = QPushButton("添加配音文件")
        self.add_btn.clicked.connect(self.add_files)
        
        self.analyze_btn = QPushButton("分析选中文件")
        self.analyze_btn.clicked.connect(self.analyze_selected_file)
        self.analyze_btn.setEnabled(False)
        
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.clicked.connect(self.clear_list)
        
        self.process_btn = QPushButton("开始专业处理")
        self.process_btn.clicked.connect(self.start_professional_processing)
        
        self.cancel_btn = QPushButton("取消处理")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.analyze_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.process_btn)
        btn_layout.addWidget(self.cancel_btn)
        
        file_layout.addWidget(btn_widget, 1)
        main_layout.addWidget(file_group)

        # 进度条
        self.progress = QProgressBar()
        main_layout.addWidget(self.progress)

        # -------------------------- 专业播放控制区 --------------------------
        play_group = QGroupBox("专业播放控制")
        play_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        play_group.setMinimumHeight(160)
        play_layout = QVBoxLayout(play_group)
        
        # 播放控制布局
        play_controls = QHBoxLayout()
        play_controls.setSpacing(15)
        
        # 原文件播放控制
        original_layout = QVBoxLayout()
        original_layout.setContentsMargins(0, 0, 0, 0)
        original_layout.setSpacing(5)
        original_label = QLabel("原文件")
        original_label.setStyleSheet("font-weight: 500; text-align: center;")
        
        original_btns = QHBoxLayout()
        self.play_origin = QPushButton("播放")
        self.play_origin.setProperty("class", "small-btn")
        self.play_origin.clicked.connect(lambda: self.play_audio("origin"))
        self.play_origin.setEnabled(False)
        
        self.prev_origin = QPushButton("←1/8")
        self.prev_origin.setProperty("class", "small-btn")
        self.prev_origin.clicked.connect(lambda: self.jump_audio("origin", -1))
        self.prev_origin.setEnabled(False)
        
        self.next_origin = QPushButton("1/8→")
        self.next_origin.setProperty("class", "small-btn")
        self.next_origin.clicked.connect(lambda: self.jump_audio("origin", 1))
        self.next_origin.setEnabled(False)
        
        original_btns.addWidget(self.play_origin)
        original_btns.addWidget(self.prev_origin)
        original_btns.addWidget(self.next_origin)
        
        original_layout.addWidget(original_label)
        original_layout.addLayout(original_btns)
        play_controls.addLayout(original_layout)

        # 处理后播放控制
        processed_layout = QVBoxLayout()
        processed_layout.setContentsMargins(0, 0, 0, 0)
        processed_layout.setSpacing(5)
        processed_label = QLabel("处理后")
        processed_label.setStyleSheet("font-weight: 500; text-align: center;")
        
        processed_btns = QHBoxLayout()
        self.play_processed = QPushButton("播放")
        self.play_processed.setProperty("class", "small-btn")
        self.play_processed.clicked.connect(lambda: self.play_audio("processed"))
        self.play_processed.setEnabled(False)
        
        self.prev_processed = QPushButton("←1/8")
        self.prev_processed.setProperty("class", "small-btn")
        self.prev_processed.clicked.connect(lambda: self.jump_audio("processed", -1))
        self.prev_processed.setEnabled(False)
        
        self.next_processed = QPushButton("1/8→")
        self.next_processed.setProperty("class", "small-btn")
        self.next_processed.clicked.connect(lambda: self.jump_audio("processed", 1))
        self.next_processed.setEnabled(False)
        
        processed_btns.addWidget(self.play_processed)
        processed_btns.addWidget(self.prev_processed)
        processed_btns.addWidget(self.next_processed)
        
        processed_layout.addWidget(processed_label)
        processed_layout.addLayout(processed_btns)
        play_controls.addLayout(processed_layout)

        # 停止播放按钮
        stop_layout = QVBoxLayout()
        stop_layout.setContentsMargins(0, 0, 0, 0)
        stop_layout.setSpacing(5)
        stop_spacer = QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding)
        stop_layout.addItem(stop_spacer)
        
        self.stop_btn = QPushButton("停止播放")
        self.stop_btn.clicked.connect(self.stop_all_playback)
        self.stop_btn.setEnabled(False)
        stop_layout.addWidget(self.stop_btn)
        
        play_controls.addLayout(stop_layout)
        play_controls.addStretch()
        
        play_layout.addLayout(play_controls)
        main_layout.addWidget(play_group)

        # -------------------------- 专业日志区 --------------------------
        log_group = QGroupBox("专业处理日志")
        log_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout = QVBoxLayout(log_group)
        self.log_display = QTextEdit()
        self.log_display.setFixedHeight(120)
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        main_layout.addWidget(log_group)

        # 版本信息
        version_label = QLabel(f"© {self.BRAND} | {self.TOOL_NAME} | 符合广播级标准")
        version_label.setProperty("class", "version-info")
        version_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(version_label)

        scroll.setWidget(content)

        # 播放器状态监听
        if self.origin_player:
            self.origin_player.stateChanged.connect(self.update_play_buttons)
            self.origin_player.error.connect(lambda: self.log_message(f"原文件播放错误: {self.origin_player.errorString()}"))
        if self.processed_player:
            self.processed_player.stateChanged.connect(self.update_play_buttons)
            self.processed_player.error.connect(lambda: self.log_message(f"处理后播放错误: {self.processed_player.errorString()}"))

        # 初始化日志
        if FFMPEG_PATH:
            self.log_message(f"程序启动成功，FFmpeg路径：{os.path.basename(FFMPEG_PATH)}")
            self.log_message("使用说明：添加文件 → 选择预设 → 开始处理")
        else:
            self.log_message("警告：未找到FFmpeg，处理功能将不可用")
        if not QMediaPlayer:
            self.log_message("提示：当前环境未加载QtMultimedia，播放功能不可用")

    # 参数显示更新
    def update_clarity_display(self):
        """更新清晰度显示"""
        level = self.clarity_slider.value()
        labels = {
            1: "1（自然）",
            2: "2（清晰）",
            3: "3（标准）",
            4: "4（锐利）",
            5: "5（突出）"
        }
        self.clarity_value.setText(labels.get(level, "3（标准）"))

    def update_warmth_display(self):
        """更新温暖度显示"""
        level = self.warmth_slider.value()
        labels = {
            1: "1（明亮）",
            2: "2（适中）",
            3: "3（温暖）",
            4: "4（醇厚）",
            5: "5（深沉）"
        }
        self.warmth_value.setText(labels.get(level, "3（适中）"))

    def update_reverb_display(self):
        """更新混响显示"""
        level = self.reverb_slider.value()
        labels = {
            0: "0（无）",
            1: "1（极轻）",
            2: "2（轻微）",
            3: "3（自然）",
            4: "4（适中）",
            5: "5（丰富）"
        }
        self.reverb_value.setText(labels.get(level, "1（极轻）"))

    # 专业预设应用
    def apply_professional_preset(self, preset_type):
        """应用专业预设"""
        presets = {
            "news": {
                "preset": "新闻播报",
                "clarity": 4,
                "warmth": 2,
                "reverb": 0,  # 新闻播报通常无混响
                "noise": "轻"
            },
            "documentary": {
                "preset": "纪录片解说",
                "clarity": 3,
                "warmth": 4,
                "reverb": 1,  # 极轻混响
                "noise": "中"
            },
            "advertisement": {
                "preset": "广告配音",
                "clarity": 5,
                "warmth": 3,
                "reverb": 2,  # 轻微混响
                "noise": "中"
            }
        }
        
        preset = presets.get(preset_type, presets["news"])
        self.preset_combo.setCurrentText(preset["preset"])
        self.clarity_slider.setValue(preset["clarity"])
        self.warmth_slider.setValue(preset["warmth"])
        self.reverb_slider.setValue(preset["reverb"])
        
        noise_index = 0 if preset["noise"] == "轻" else 1 if preset["noise"] == "中" else 2
        self.noise_combo.setCurrentIndex(noise_index)
        
        preset_names = {
            "news": "新闻播报",
            "documentary": "纪录片解说", 
            "advertisement": "广告配音"
        }
        self.log_message(f"应用专业预设：{preset_names.get(preset_type, '新闻播报')}")

    # 文件管理功能
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择配音文件或视频", "", "支持格式 (*.wav *.flac *.mp3 *.m4a *.aac *.mp4 *.mov *.mkv *.avi)"
        )
        if not files:
            return
        valid = [f for f in files if os.path.splitext(f)[1].lower() in [".wav", ".flac", ".mp3", ".m4a", ".aac", ".mp4", ".mov", ".mkv", ".avi"]
                 and f not in self.file_list and os.path.getsize(f) > 3*1024]
        self.file_list.extend(valid)
        self.file_list_widget.addItems([os.path.basename(f) for f in valid])
        self.log_message(f"添加 {len(valid)} 个配音文件")
        
        if valid:
            self.play_origin.setEnabled(True)
            self.prev_origin.setEnabled(True)
            self.next_origin.setEnabled(True)
            self.analyze_btn.setEnabled(True)

    def clear_list(self):
        self.stop_all_playback()
        if self.processing_thread and self.processing_thread.isRunning():
            self.cancel_processing()
            
        self.file_list = []
        self.file_list_widget.clear()
        self.processed_files = {}
        self.current_analysis = None
        
        # 重置分析显示
        self.clear_analysis_display()
        self.log_message("清空文件列表")
        
        self.play_origin.setEnabled(False)
        self.prev_origin.setEnabled(False)
        self.next_origin.setEnabled(False)
        self.play_processed.setEnabled(False)
        self.prev_processed.setEnabled(False)
        self.next_processed.setEnabled(False)
        self.analyze_btn.setEnabled(False)

    def clear_analysis_display(self):
        """清空分析显示"""
        for i in reversed(range(self.analysis_layout.count())):
            widget = self.analysis_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        default_info = QLabel("选择文件后将显示专业分析结果...")
        default_info.setStyleSheet("font-size: 13px; color: #666; text-align: center; padding: 20px 0;")
        self.analysis_layout.addWidget(default_info)

    def on_file_selected(self):
        """文件选中时更新分析显示"""
        if self.file_list_widget.currentRow() != -1:
            self.analyze_btn.setEnabled(True)

    def analyze_selected_file(self):
        """分析选中文件"""
        idx = self.file_list_widget.currentRow()
        if idx < 0 or idx >= len(self.file_list):
            return
            
        file_path = self.file_list[idx]
        filename = os.path.basename(file_path)
        
        self.log_message(f"开始专业分析：{filename}")
        try:
            analysis = ProfessionalVocalProcessor.analyze_audio_quality(file_path)
            self.current_analysis = analysis
            
            # 清空之前的分析显示
            self.clear_analysis_display()
            
            # 生成专业分析报告（恢复好看的底色显示）
            gender_text = "女声" if analysis["gender"] == "female" else "男声" if analysis["gender"] == "male" else "未知性别"
            quality_level = "优秀" if analysis["quality_score"] >= 80 else "良好" if analysis["quality_score"] >= 60 else "一般"
            quality_color = "quality-high" if analysis["quality_score"] >= 80 else "quality-medium" if analysis["quality_score"] >= 60 else "quality-low"
            
            # 创建分析信息标签
            analysis_info = [
                (f"文件名：{filename}", "analysis-label"),
                (f"质量评估：<span class='{quality_color}'>{quality_level} ({analysis['quality_score']:.1f}分)</span>", "analysis-value"),
                (f"声音特征：{gender_text} | 响度 {analysis['loudness']:.1f} LUFS | 动态范围 {analysis['dynamic_range']:.1f} dB", "analysis-value"),
                (f"技术参数：{analysis['sample_rate']} Hz | {'无损' if analysis['is_lossless'] else f'{analysis['bitrate']} kbps'} | {analysis['channels']}声道", "analysis-value"),
                (f"时长：{analysis['duration']:.1f} 秒 | 底噪：{analysis['noise_floor']:.1f} dB", "analysis-value"),
                (f"建议：{self.get_improvement_suggestions(analysis)}", "analysis-value")
            ]
            
            for text, style_class in analysis_info:
                label = QLabel(text)
                label.setProperty("class", style_class)
                label.setTextInteractionFlags(Qt.TextBrowserInteraction)
                label.setOpenExternalLinks(False)
                self.analysis_layout.addWidget(label)
            
            self.log_message(f"专业分析完成：{quality_level}级音频")
            
        except Exception as e:
            self.log_message(f"分析失败：{str(e)}")
            self.clear_analysis_display()
            error_label = QLabel(f"<span style='color: red;'>分析失败：{str(e)}</span>")
            error_label.setStyleSheet("font-size: 13px; text-align: center; padding: 20px 0;")
            error_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            self.analysis_layout.addWidget(error_label)

    def get_improvement_suggestions(self, analysis):
        """生成改进建议"""
        suggestions = []
        
        if analysis["loudness"] < -18:
            suggestions.append("建议提升整体响度")
        elif analysis["loudness"] > -14:
            suggestions.append("建议降低整体响度")
            
        if analysis["dynamic_range"] > 18:
            suggestions.append("建议增加压缩量")
        elif analysis["dynamic_range"] < 10:
            suggestions.append("建议减少压缩量")
            
        if analysis["noise_floor"] > -45:
            suggestions.append("建议加强降噪")
            
        if analysis["high_freq_energy"] < -25:
            suggestions.append("建议提升高频细节")
            
        if not suggestions:
            return "音频质量良好，适合专业使用"
        return " | ".join(suggestions)

    # 专业处理控制
    def start_professional_processing(self):
        if not FFMPEG_PATH:
            QMessageBox.critical(self, "错误", "未找到FFmpeg！请将ffmpeg.exe放在程序同目录")
            return
            
        if not self.file_list:
            QMessageBox.warning(self, "提示", "请先添加配音文件")
            return

        # 获取专业参数
        preset = self.preset_combo.currentText()
        voice_clarity = self.clarity_slider.value()
        warmth_level = self.warmth_slider.value()
        reverb_amount = self.reverb_slider.value()
        noise_reduction = self.noise_combo.currentText().split("（")[0]

        self.processing_thread = ProfessionalProcessingThread(
            self.file_list,
            preset=preset,
            voice_clarity=voice_clarity,
            warmth_level=warmth_level,
            reverb_amount=reverb_amount,
            noise_reduction=noise_reduction
        )
        self.processing_thread.progress_updated.connect(self.progress.setValue)
        self.processing_thread.all_finished.connect(self.on_processing_finished)
        self.processing_thread.error.connect(self.on_processing_error)
        self.processing_thread.log.connect(self.log_message)
        self.processing_thread.file_processed.connect(self.on_file_processed)
        self.processing_thread.quality_report.connect(self.on_quality_report)

        self.add_btn.setEnabled(False)
        self.analyze_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.process_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.processing_thread.start()
        self.log_message("开始专业配音处理...")

    def cancel_processing(self):
        if self.processing_thread and self.processing_thread.isRunning():
            self.log_message("正在取消专业处理...")
            self.processing_thread.stop()
            self.processing_thread.wait()
            self.processing_thread = None
            self.on_processing_canceled()

    def on_processing_canceled(self):
        self.progress.setValue(0)
        self.add_btn.setEnabled(True)
        self.analyze_btn.setEnabled(len(self.file_list) > 0)
        self.clear_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.log_message("专业处理已取消")

    def on_file_processed(self, input_path, output_path):
        self.processed_files[input_path] = output_path

    def on_quality_report(self, analysis):
        """接收质量报告并显示"""
        quality_level = "优秀" if analysis["quality_score"] >= 80 else "良好" if analysis["quality_score"] >= 60 else "一般"
        self.log_message(f"质量报告：{quality_level}级音频")

    def on_processing_finished(self):
        self.progress.setValue(100)
        QMessageBox.information(self, "专业处理完成", "所有配音文件已完成专业级优化！")
        
        self.play_processed.setEnabled(True)
        self.prev_processed.setEnabled(True)
        self.next_processed.setEnabled(True)
        self.add_btn.setEnabled(True)
        self.analyze_btn.setEnabled(len(self.file_list) > 0)
        self.clear_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.processing_thread = None
        self.log_message("专业处理全部完成，符合广播级标准")

    def on_processing_error(self, msg):
        self.progress.setValue(0)
        QMessageBox.critical(self, "处理错误", f"专业处理失败：{msg}")
        
        self.add_btn.setEnabled(True)
        self.analyze_btn.setEnabled(len(self.file_list) > 0)
        self.clear_btn.setEnabled(True)
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.processing_thread = None
        self.log_message(f"专业处理错误：{msg}")

    # 专业播放控制
    def play_audio(self, audio_type):
        if not self.origin_player or not self.processed_player:
            QMessageBox.warning(self, "播放提示", "当前环境不支持播放模块")
            return
        idx = self.file_list_widget.currentRow() if self.file_list_widget.currentRow() != -1 else 0
        if idx < 0 or idx >= len(self.file_list):
            return
            
        file_path = self.file_list[idx] if audio_type == "origin" else self.processed_files.get(self.file_list[idx])
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "播放提示", "文件不存在或尚未处理")
            return

        player = self.origin_player if audio_type == "origin" else self.processed_player
        other_player = self.processed_player if audio_type == "origin" else self.origin_player
        other_player.stop()

        if player.state() == QMediaPlayer.PlayingState:
            player.pause()
        elif player.state() == QMediaPlayer.PausedState:
            player.play()
        else:
            player.setMedia(QMediaContent())
            player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            player.play()
        self.stop_btn.setEnabled(True)

    def jump_audio(self, audio_type, direction):
        """专业前进后退功能"""
        if not self.origin_player or not self.processed_player:
            return
        player = self.origin_player if audio_type == "origin" else self.processed_player
        if player.media().isNull():
            self.play_audio(audio_type)
            return
        if player.duration() == 0:
            self.log_message("音频加载中，请稍候...")
            return
            
        step = player.duration() // 8
        new_pos = player.position() + direction * step
        new_pos = max(0, min(new_pos, player.duration()))
        player.setPosition(new_pos)
        
        current = f"{new_pos//60000:02d}:{(new_pos//1000)%60:02d}"
        total = f"{player.duration()//60000:02d}:{(player.duration()//1000)%60:02d}"
        self.log_message(f"{'原文件' if audio_type == 'origin' else '处理后'} 跳转至 {current}/{total}")

    def stop_all_playback(self):
        if self.origin_player:
            self.origin_player.stop()
            self.origin_player.setMedia(QMediaContent())
        if self.processed_player:
            self.processed_player.stop()
            self.processed_player.setMedia(QMediaContent())
        self.stop_btn.setEnabled(False)
        self.update_play_buttons()
        self.log_message("停止所有播放")

    def update_play_buttons(self):
        """更新播放按钮状态"""
        if not self.origin_player:
            self.play_origin.setEnabled(False)
        elif self.origin_player.state() == QMediaPlayer.PlayingState:
            self.play_origin.setText("暂停")
        else:
            self.play_origin.setText("播放")
        if not self.processed_player:
            self.play_processed.setEnabled(False)
        elif self.processed_player.state() == QMediaPlayer.PlayingState:
            self.play_processed.setText("暂停")
        else:
            self.play_processed.setText("播放")

    # 专业日志功能
    def log_message(self, msg):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {msg}")
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())

    # 窗口关闭处理
    def closeEvent(self, event):
        self.stop_all_playback()
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.processing_thread.wait()
        event.accept()

# -------------------------- 程序入口 --------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = app.font()
    font.setFamily("Microsoft YaHei")
    app.setFont(font)
    
    window = ProfessionalVocalEnhancer()
    window.show()
    sys.exit(app.exec_())