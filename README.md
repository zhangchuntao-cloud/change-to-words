# change-to-words

本地离线的音频 / 视频转文字工具，基于 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)。

拖入文件即自动转写，输出 TXT、SRT 或 VTT。音频只在本机处理，不需要 API Key。

## 最快用法

```bash
cd change_to_words
./ctw serve
```

打开 `http://127.0.0.1:8000`，把音频或视频拖进去，等结果出来即可复制或下载。

- 不需要选模型、不需要点“开始”
- 语言默认自动识别
- 模型、语言、术语提示、静音过滤都折叠在“高级设置”里
- 首次使用会自动下载模型，需要稍等一下

## 功能

- Web：拖拽 / 点击上传 / 麦克风录音，自动开始转写
- Web：单行进度、结果文本、复制、TXT / SRT / VTT 下载
- Web：默认只监听本机，音频不会上传到第三方
- CLI：单文件、批量文件、目录扫描、递归扫描
- CLI：TXT / SRT / VTT 输出，支持术语提示和静音过滤
- 自动识别语言，也可以指定 `zh`、`en`、`ja` 等
- 模型只需下载一次，之后可完全离线使用

## 安装

### 方式一：venv（推荐，普通终端）

```bash
cd change_to_words
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

安装后得到两个等价命令：`change-to-words` 和 `ctw`。

需要测试依赖时：

```bash
python -m pip install -e ".[dev]"
```

### 方式二：项目内本地依赖（当前受限环境可用）

如果无法执行 `.venv` 内的解释器：

```bash
cd change_to_words
./setup_local.sh        # 安装依赖到 .deps/
./ctw serve
```

`.deps/` 已被 `.gitignore` 忽略。默认使用 PATH 中的 `python3`，需要换解释器时：

```bash
CTW_PYTHON=/path/to/python3 ./setup_local.sh
CTW_PYTHON=/path/to/python3 ./ctw 录音.m4a
```

## Web 界面

```bash
./ctw serve
```

默认地址是 `http://127.0.0.1:8000`，并会尝试自动打开浏览器。

操作只有三步：

1. 拖入文件、点击选择，或点“直接录音”
2. 自动开始转写，显示加载模型 / 转写进度
3. 完成后复制文本，或下载 TXT / SRT / VTT

高级设置默认收起，里面可以改：

- 模型：`tiny` / `base` / `small` / `medium` / `large-v3`
- 语言：自动识别 / 中文 / English / 日本語 / 한국어 / 粤语
- 术语提示：人名、专有名词、行业词汇
- 静音过滤

启动参数：

```bash
./ctw serve --port 9000                 # 换端口
./ctw serve -m medium                   # 默认模型
./ctw serve --offline                   # 只用已缓存模型
./ctw serve --download-root ~/models    # 模型缓存目录
./ctw serve --max-upload-mb 4096        # 上传大小上限
./ctw serve --no-browser                # 不自动打开浏览器
```

默认只监听 `127.0.0.1`。使用 `--host 0.0.0.0` 会允许局域网访问，请自行确认网络环境。

国内网络下载模型：

```bash
HF_ENDPOINT=https://hf-mirror.com ./ctw serve
```

### Web API

界面之外也可以直接调用本地 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查、版本、默认模型 |
| `POST` | `/api/jobs` | 上传文件并创建任务（multipart） |
| `GET` | `/api/jobs/{id}` | 任务详情和分段结果 |
| `GET` | `/api/jobs/{id}/download?fmt=txt\|srt\|vtt` | 下载结果 |
| `GET` | `/api/jobs/{id}/media` | 读取原始音频 |
| `GET` | `/api/jobs` | 最近任务列表 |
| `DELETE` | `/api/jobs/{id}` | 删除已完成任务 |

任务在内存中执行，服务重启后任务列表会清空。

## 命令行

```bash
# 转写单个文件，输出同目录的 audio.txt
./ctw audio.mp3

# 中文 + 更大的模型
./ctw -l zh -m medium 会议录音.m4a

# 生成 SRT / VTT
./ctw --format srt 视频.mp4
./ctw --format vtt -o output/ 视频.mp4

# 术语提示
./ctw -l zh --initial-prompt "百度智能云，CTranslate2，昆仑芯片" 录音.m4a

# 批量 / 目录 / 递归
./ctw -o output/ 录音1.mp3 录音2.wav
./ctw -r -o output/ 我的音频/

# 覆盖已有输出
./ctw --overwrite audio.mp3
```

如果已安装到 venv，把 `./ctw` 换成 `ctw` 即可。

### 命令行参数

| 参数 | 说明 |
| --- | --- |
| `INPUT...` | 音频/视频文件或目录，可传多个 |
| `-m, --model NAME` | 模型名或 Hugging Face 仓库 ID，默认 `small` |
| `--model-path DIR` | 本地 CTranslate2 模型目录（与 `--model` 二选一） |
| `-l, --language CODE` | 语言代码，如 `zh`、`en`、`ja`；默认 `auto` |
| `--format FORMAT` | `txt`（默认）、`srt`、`vtt` |
| `-o, --output PATH` | 单文件时可为具体输出文件；否则为输出目录 |
| `-r, --recursive` | 递归扫描目录 |
| `--overwrite` | 覆盖已存在的输出 |
| `--no-vad` | 关闭静音过滤（默认开启） |
| `--initial-prompt TEXT` | 术语提示 |
| `--download-root DIR` | 模型缓存目录 |
| `--hf-endpoint URL` | Hugging Face 镜像 |
| `--offline` | 只使用已缓存或本地模型 |
| `-q, --quiet` | 不显示进度和状态 |
| `--version` | 显示版本 |

默认行为：

- 不指定 `-o` 时，输出写在源文件旁边，例如 `audio.mp3` → `audio.txt`
- `--format srt` / `vtt` 时，默认输出 `audio.srt` / `audio.vtt`
- `-o` 指向具体文件时，扩展名必须与 `--format` 一致
- 已存在的输出默认跳过
- 批量处理时单个文件失败不会中断其他文件

## 输出格式

### TXT（默认）

每个 Whisper 分段一行，不带时间戳：

```text
大家好，今天的会议主要讨论三件事。
第一是项目进度，第二是资源安排。
```

### SRT

```srt
1
00:00:00,000 --> 00:00:02,345
大家好，今天的会议主要讨论三件事。
```

### VTT

```vtt
WEBVTT

00:00:00.000 --> 00:00:02.345
大家好，今天的会议主要讨论三件事。
```

## 模型选择

| 模型 | 大致大小 | 特点 |
| --- | --- | --- |
| `tiny` | ~75 MB | 最快，适合测试 |
| `base` | ~140 MB | 快，准确率一般 |
| `small` | ~500 MB | 默认，速度和准确率平衡 |
| `medium` | ~1.5 GB | 中文更好，CPU 上明显变慢 |
| `large-v3` | ~3 GB | 效果最好，CPU 上很慢 |

中文会议、访谈建议：

```bash
./ctw -l zh -m medium 录音.m4a
```

## 国内网络与离线使用

```bash
# 使用镜像
./ctw --hf-endpoint https://hf-mirror.com -m small audio.mp3
HF_ENDPOINT=https://hf-mirror.com ./ctw serve

# 固定模型缓存目录
./ctw --download-root ~/models/whisper -m small audio.mp3

# 之后离线使用
./ctw --offline --download-root ~/models/whisper audio.mp3
```

已有 CTranslate2 模型目录时：

```bash
./ctw --model-path ./faster-whisper-small audio.mp3
```

`--model-path` 需要包含 `model.bin`、`config.json`、tokenizer 文件等，不是原始 `.pt` 文件。

## 支持的输入格式

音频：`.mp3` `.wav` `.m4a` `.aac` `.flac` `.ogg` `.opus` `.wma` `.aiff` `.aif` `.caf` `.amr`

视频：`.mp4` `.mov` `.m4v` `.mkv` `.webm` `.avi` `.flv` `.mpeg` `.mpg` `.wmv` `.ts`

命令行显式指定的文件不检查扩展名，能否解码由 PyAV 决定；Web 上传会做基本扩展名校验。

## 项目结构

```text
src/change_to_words/
├── cli.py          # 命令行入口、批量编排、serve 分发
├── web.py          # FastAPI 应用、任务队列、模型池、API
├── web/index.html  # 极简单页界面
├── transcriber.py  # faster-whisper 加载与转写
├── subtitle.py     # SRT / VTT 生成
├── jobs.py         # 文件扫描、输出路径与冲突检查
├── text.py         # TXT 拼接
└── writer.py       # 原子写入
```

## 测试

```bash
# 核心测试（Web 测试会跳过）
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 连同 Web 测试一起跑
PYTHONPATH=src:.deps python3 -m unittest discover -s tests -v
```

端到端冒烟测试（会下载 `tiny` 模型）：

```bash
say -o /tmp/ctw-smoke.aiff "Hello, this is a local transcription smoke test."
./ctw -m tiny -l en -o /tmp/ctw-smoke.txt /tmp/ctw-smoke.aiff
cat /tmp/ctw-smoke.txt
```

## 说明

- 使用 faster-whisper 的 CPU 推理（CTranslate2 在 macOS 上不支持 Metal）
- CLI 和 Web 共用同一套转写、字幕和文本生成逻辑
- Web 使用单工作线程队列，模型按名称缓存，切换模型时释放旧模型以控制内存
- 输出采用临时文件 + 原子替换，失败时不会留下半截文件
- 转写逻辑通过 `Transcriber` 协议解耦，后续可以接入 mlx-whisper 等更快的 Apple Silicon 后端

## 退出码（CLI）

| 退出码 | 含义 |
| --- | --- |
| `0` | 全部写入或按预期跳过 |
| `1` | 模型加载失败，或至少一个文件转写失败 |
| `2` | 参数、输入或输出路径错误 |
| `130` | 用户按 Ctrl-C 取消 |
