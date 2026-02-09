# 星TAP | 背景音乐智能动态压缩工具 (Background Music Processor)

[English](#english) | [中文](#chinese)

---

<a name="chinese"></a>
## 中文说明

**专为短视频创作者、播客主播及音频工程师打造的背景音乐优化神器！**

在制作视频或播客时，背景音乐（BGM）往往存在响度不一、动态范围过大导致遮盖人声，或者低频浑浊等问题。本工具集成了专业的广播级音频处理算法，能够一键解决这些烦恼，让你的背景音乐听起来既“高级”又“专业”。

### 🚀 核心功能
-   **广播级响度标准**：严格遵循 `-16.0 LUFS` 目标响度，确保背景音乐在各平台播放时音量统一稳定。
-   **多频带智能压缩**：将音频分为高中低三频段独立压缩。在保留音乐细节的同时，让整体听感更加扎实、有力。
-   **智能避让人声 (Vocal Avoidance)**：内置专业 EQ 曲线，自动调优 1500Hz 左右的人声敏感频段，确保 BGM 不抢戏。
-   **声场扩展增强**：提供“原声相”、“轻微扩展”、“宽声场”三种模式，营造沉浸式的空间感。
-   **智能降噪与低切**：自动过滤 50Hz 以下的超低频杂音和环境底噪，让音频更纯净。
-   **双版本可选**：
    -   **2.5 母带级 (Mastering)**：侧重于音质的极致细腻。
    -   **2.7 广播级 (Broadcast)**：侧重于符合行业规范的响度与动态控制。

### 💻 跨平台支持
-   **Windows 版**：绿色免安装，内置 FFmpeg 驱动，拖拽即用。
-   **macOS 版**：完美适配苹果系统，支持 `.app` 原生运行。

---

<a name="english"></a>
## English Description

**The ultimate BGM optimization tool for short video creators, podcasters, and audio engineers!**

Struggling with background music that's either too loud, masks the vocals, or sounds muddy? This tool integrates professional broadcast-grade audio processing algorithms to make your BGM sound polished and professional with just one click.

### 🚀 Key Features
-   **Broadcast Loudness Standard**: Strictly follows the `-16.0 LUFS` target to ensure consistent volume across all platforms.
-   **Intelligent Multi-band Compression**: Splits audio into Low, Mid, and High bands for independent compression, delivering a solid and powerful sound.
-   **Smart Vocal Avoidance**: Built-in professional EQ curves to optimize the ~1500Hz vocal frequency range, ensuring the BGM never masks the narrator.
-   **Sound Field Enhancement**: Three presets (Original, Slight Expansion, Wide Sound Field) to create an immersive spatial experience.
-   **Denoising & Low-cut**: Automatically filters out sub-50Hz noise and ambient hiss for crystal-clear audio.

---

### 🛠️ 简单易用 (Easy to Use)
- **小白用户 (For Beginners)**：
  - **直接下载**：请在 [Releases](https://github.com/cscb603/Background-Music-Processor/releases) 页面下载对应系统的压缩包。
  - **独立运行**：下载后解压，直接运行 `.exe` (Win) 或 `.app` (Mac) 即可。**无需安装 Python，无需手动配置 FFmpeg**，所有依赖已内置。
  - **安全提示**：本工具基于开源的音频标准 FFmpeg 开发，绿色安全，不会修改您的系统设置。
- **开发者/源码运行 (For Developers)**：
  - 环境要求：Python 3.8+
  - 依赖库：`pip install PyQt5`
  - 音频引擎：确保 `ffmpeg` 在程序同目录下或已添加至系统环境变量。

---

### 📥 下载 / Download
请前往 [Releases](https://github.com/cscb603/Background-Music-Processor/releases) 页面下载最新版本的成品。

---
**Powered by StarTAP (星TAP) & FFmpeg**
