#!/usr/bin/env python3
"""
ocr_shell.py — OCR 工具链的交互式外壳(shell)。

它本身不做 OCR,只做两件事:
  1. 交互模式:**面板式配置**(类似 Claude Code)—— 一屏显示全部当前设置,
     用斜杠命令随手改任何一项,最后 `/run` 一条命令执行。
     旧版「一个问题接一个问题」的向导已经全部换成面板 + 斜杠命令。
  2. 非交互模式:`--exec <目标> -- <参数...>` 直接转发给底层脚本,
     方便写进脚本 / CI 里跑。配合 `--dry-run` 只打印不执行,可在没有模型服务
     的机器上验证整条链路。

面板命令(都带 `/` 前缀,不带前缀也能用):
    /task       切换任务            /input      设置输入(路径 / 浏览 / 文件夹)
    /output     设置输出目录        /dpi        渲染分辨率
    /quality    JPEG 质量           /start      起始页码
    /end        结束页码            /preprocess 预处理强度
    /prompt     提示模式            /deskew     自动纠偏开关
    /trim       裁白边开关          /staging    保留中间图开关
    /scale      放大倍数            /max-side   最长边上限
    /num-thread 并发页数           /gray       灰度输出开关
    /prefix     文件名前缀          /server     地址 / 端口 / 模型
    /run        执行当前配置       /print-argv 只打印 argv 不执行
    /set        设置页(分组菜单)   /preset     预设(内置 + 自定义)
    /save       立即保存会话       /reload     丢弃改动重新载入
    /history    查看命令历史       /reset      恢复默认
    /preflight  依赖 + 服务预检    /config     查看环境变量与默认值
    /help       命令帮助           /quit       退出

流水线用法:
    面板常驻不退出。把文件拖到终端里 → 路径出现在提示符 → 直接回车,
    面板会把该路径设为输入并立刻执行;跑完回到面板,再拖下一个文件即可。
    输出目录设过一次之后就直接用,不再每次询问。

会话持久化(默认开启):
    * 会话文件位置优先级:
        1. `$OCR_SESSION_FILE`
        2. `$XDG_CONFIG_HOME/ocr/session.json`
        3. `~/.config/ocr/session.json`
      命令行 `--session <路径>` 覆盖以上全部;`--no-session` 完全不读不写。
    * 优先级规则(重要):**环境变量只作为「基线默认值」**。
      `Config.from_env()` 先按环境变量造一份基线;如果会话文件存在,
      文件里的值覆盖基线(也就是说你上次在面板里改过的设置优先于环境变量);
      面板里改了东西会写回会话文件。
      换句话说:环境变量决定「第一次打开面板长什么样」,
      会话文件决定「以后每次打开面板长什么样」。
    * 退出时自动保存;文件损坏只警告不崩溃。

用法示例:
    # 交互面板
    python ocr/scripts/ocr_shell.py

    # 交互面板但不执行,只打印 argv
    python ocr/scripts/ocr_shell.py --dry-run
    python ocr/scripts/ocr_shell.py            # 然后在面板里输入 /print-argv

    # 非交互(脚本 / CI)
    python ocr/scripts/ocr_shell.py --exec note_to_markdown -- note.jpg -o out/
    python ocr/scripts/ocr_shell.py --exec pdf_to_images -- doc.pdf -o imgs/
    python ocr/scripts/ocr_shell.py --exec parser -- doc.pdf
    python ocr/scripts/ocr_shell.py --exec check_imports
    python ocr/scripts/ocr_shell.py --exec smoke_test -- --check-only

    # 只打印将要执行的 argv,不真的跑(无模型服务也能验证)
    python ocr/scripts/ocr_shell.py --exec note_to_markdown --dry-run -- note.jpg -o out/

    # 列出 dots.mocr 支持的 prompt 模式
    python ocr/scripts/ocr_shell.py --list-prompts

环境变量:
    OCR_SHELL_FORCE_TTY=1   把 stdin 当成交互终端(测试 / 管道里跑面板用)
    OCR_SHELL_YES=1         交互模式下跳过「确认」直接执行
    OCR_OUTPUT_DIR          默认输出目录(与 note_to_markdown 一致)
    OCR_IMAGES_DIR          默认图片输出目录(pdf_to_images)
    OCR_HOST / OCR_PORT / OCR_MODEL / OCR_DPI / OCR_PREPROCESS /
    OCR_SCALE / OCR_MAX_SIDE / OCR_PROMPT / OCR_NUM_THREAD / OCR_QUALITY
    OCR_SESSION_FILE      会话文件路径(覆盖 XDG / ~/.config 默认位置)
    OCR_NO_SESSION=1      不读不写会话文件(等价于 --no-session)

设计约束:
    * 没有任何硬编码绝对路径,所有脚本位置都由 __file__ 推导。
    * 只用标准库,不引入 questionary / rich 之类的第三方依赖。
    * stdin 不是 TTY 时绝不进面板(避免 CI 卡死),必须显式 --exec。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── 自举 ────────────────────────────────────────────────────────────────────
# 和兄弟脚本同样的两件事,顺序不能变:
#   1. 把 `ocr/` 放进 sys.path,`dots_mocr` / `scripts` 才 import 得到;
#   2. 切到项目自带的 venv(系统 python3 可能没装 pillow/numpy)。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts._bootstrap import (
        env_float,
        env_int,
        env_str,
        reexec_in_venv,
    )
except ImportError:  # pragma: no cover - 源码树不完整时的兜底
    def reexec_in_venv() -> None:
        """找不到 scripts._bootstrap 时跳过 venv 自举。"""
        return None

    def env_str(*names: str, default: str) -> str:
        """第一个非空的环境变量,都没有就用 default。"""
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
        return default

    def env_int(*names: str, default: int) -> int:
        """第一个能解析成 int 的环境变量,都没有就用 default。"""
        for name in names:
            raw = os.environ.get(name)
            if raw:
                try:
                    return int(raw)
                except ValueError:
                    continue
        return default

    def env_float(*names: str, default: float) -> float:
        """第一个能解析成 float 的环境变量,都没有就用 default。"""
        for name in names:
            raw = os.environ.get(name)
            if raw:
                try:
                    return float(raw)
                except ValueError:
                    continue
        return default

reexec_in_venv()

import argparse
import json
import re
import shlex
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, fields, replace

try:  # readline 是 stdlib,但某些精简的 Python 可能没编进来
    import readline  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - 没有 readline 就退化(无历史、无 Ctrl-R)
    readline = None  # type: ignore[assignment]

# ── 常量 ────────────────────────────────────────────────────────────────────
#: 本文件所在目录(所有兄弟脚本都从这里推导,没有绝对路径)
SCRIPTS_DIR = Path(__file__).resolve().parent

#: 兄弟脚本路径表
SCRIPT_FILES = {
    "note_to_markdown": SCRIPTS_DIR / "note_to_markdown.py",
    "pdf_to_images": SCRIPTS_DIR / "pdf_to_images.py",
    "check_imports": SCRIPTS_DIR / "check_imports.py",
    "smoke_test": SCRIPTS_DIR / "smoke_test.py",
}

#: --exec 可用目标 → 人类可读名
EXEC_TARGETS = {
    "note_to_markdown": "手写笔记 / 图片 / PDF → Markdown",
    "pdf_to_images": "PDF → 图片",
    "parser": "dots.mocr parser(原始版面 JSON)",
    "check_imports": "依赖预检",
    "smoke_test": "冒烟测试",
}

#: 面板里的三个任务(顺序即 /task 菜单顺序)
TASK_NAMES = ("note_to_markdown", "pdf_to_images", "parser")

#: note_to_markdown 的预处理模式 → 说明
PREPROCESS_MODES = {
    "none": "完全不预处理,直接送原图(原图已经很干净时用)",
    "gray": "转灰度 + 去噪 + 自动对比度(轻度,保留原有墨迹浓淡)",
    "enhance": "灰度 + 中值去噪 + 自动对比度(默认;最保守,适合真手写)",
    "binarize": "在 enhance 基础上做 Otsu 二值化(最接近印刷体,潦草字可能丢笔画)",
}

#: 常用提示模式(完整列表见 dots_mocr/utils/prompts.py,--list-prompts 会打印真值)
PROMPT_HINTS = {
    "prompt_layout_all_en": "版面 + 文字,输出 JSON(默认,信息最全)",
    "prompt_layout_only_en": "只做版面检测,不要文字",
    "prompt_ocr": "只要纯文字,不要版面(潦草字更稳)",
    "prompt_grounding_ocr": "只识别指定 bbox 内的文字",
    "prompt_web_parsing": "网页截图版面解析",
    "prompt_scene_spotting": "场景文字识别",
    "prompt_image_to_svg": "图片转 SVG",
    "prompt_general": "通用问答(自由文本)",
}

#: 输入浏览时关心的扩展名
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
PDF_SUFFIXES = {".pdf"}
BROWSABLE_SUFFIXES = IMAGE_SUFFIXES | PDF_SUFFIXES

#: 提示模式下拉菜单最多列几行
MAX_LIST_ROWS = 30

#: 面板里的分隔线宽度
PANEL_WIDTH = 64

#: 内置预设 → (中文说明, 要覆盖的字段)
#:
#: 内置预设只读:不能被覆盖、不能删除。用户自定义预设存在会话文件的
#: `presets` 键里,可以删。
PRESETS: dict[str, tuple[str, dict]] = {
    "handwriting": (
        "手写笔记:二值化 + 高分辨率,适合潦草手写",
        {
            "preprocess": "binarize",
            "dpi": 300,
            "scale": 1.0,
            "max_side": 2000,
            "prompt": "prompt_ocr",
            "deskew": True,
            "trim": True,
        },
    ),
    "document": (
        "印刷文档:轻处理 + 版面 + 英文,适合扫描件",
        {
            "preprocess": "none",
            "dpi": 200,
            "scale": 1.0,
            "max_side": 1600,
            "prompt": "prompt_layout_all_en",
        },
    ),
    "fast": (
        "快速预览:低分辨率 + 纯文字,先看个大概",
        {
            "preprocess": "gray",
            "dpi": 120,
            "scale": 1.0,
            "max_side": 1200,
            "prompt": "prompt_ocr",
        },
    ),
    "precise": (
        "高精度:增强 + 最高分辨率,慢但最准",
        {
            "preprocess": "enhance",
            "dpi": 400,
            "scale": 1.0,
            "max_side": 2400,
            "prompt": "prompt_layout_all_en",
        },
    ),
}

#: 面板命令表 → (说明, 用法提示)
COMMANDS: dict[str, tuple[str, str]] = {
    "task": ("切换任务", "/task"),
    "input": ("设置输入(路径 / 浏览 / 文件夹)", "/input"),
    "output": ("设置输出目录", "/output"),
    "dpi": ("渲染分辨率", "/dpi"),
    "quality": ("JPEG 质量", "/quality"),
    "start": ("起始页码", "/start"),
    "end": ("结束页码(0=到末页)", "/end"),
    "preprocess": ("预处理强度", "/preprocess"),
    "prompt": ("提示模式", "/prompt"),
    "deskew": ("自动纠偏开关", "/deskew"),
    "trim": ("裁白边开关", "/trim"),
    "staging": ("保留中间图开关", "/staging"),
    "scale": ("放大倍数", "/scale"),
    "max-side": ("最长边像素上限(0=不限制)", "/max-side"),
    "num-thread": ("并发页数", "/num-thread"),
    "gray": ("灰度输出开关", "/gray"),
    "prefix": ("文件名前缀", "/prefix"),
    "server": ("地址 / 端口 / 模型", "/server"),
    "set": ("设置页(分组菜单)", "/set"),
    "preset": ("预设(内置 + 自定义)", "/preset"),
    "run": ("执行当前配置(可加 --dry-run)", "/run"),
    "print-argv": ("只打印 argv 不执行", "/print-argv"),
    "save": ("立即保存会话到文件", "/save"),
    "reload": ("丢弃改动,重新载入会话", "/reload"),
    "history": ("查看命令历史", "/history"),
    "reset": ("恢复默认", "/reset"),
    "preflight": ("依赖 + 模型服务预检", "/preflight"),
    "config": ("查看环境变量与默认值", "/config"),
    "help": ("命令帮助", "/help"),
    "quit": ("退出", "/quit"),
}

#: 退出命令的别名
QUIT_WORDS = {"quit", "exit", "q", "退出"}

#: 清屏用的 ANSI 序列
ANSI_CLEAR = "\033[2J\033[H"

#: 会话文件里保留的历史条数上限
MAX_HISTORY = 100

#: 面板底部显示的最近命令条数
RECENT_COMMANDS = 3


# ── 小工具 ──────────────────────────────────────────────────────────────────
def is_interactive() -> bool:
    """stdin 是终端(或被 OCR_SHELL_FORCE_TTY 强制)才算交互模式。"""
    if env_str("OCR_SHELL_FORCE_TTY", default="") not in ("", "0", "false", "no"):
        return True
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def stdout_is_tty() -> bool:
    """stdout 是终端吗?不是就别清屏(管道 / CI 里日志要能看)。"""
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def expand_path(raw: str) -> Path:
    """展开 `~`、环境变量,相对路径按 CWD 解析。"""
    text = os.path.expandvars(raw.strip())
    text = os.path.expanduser(text)
    return Path(text)


def unescape_shell_path(raw: str) -> str:
    """还原终端拖拽/粘贴带来的 shell 转义。

    macOS 终端把带空格的路径插入成 `扫描文稿\\ 2.pdf`(空格被反斜杠转义),
    直接当文件名用会找不到。这里把 `\\ `、`\\'`、`\\"`、`\\\\` 还原成原字符。
    """
    return re.sub(r"\\([ '\"\\])", r"\1", raw)


def resolve_input(target: Path) -> Path:
    """把可能带 shell 转义的路径解析成真实存在的路径。

    优先复用 note_to_markdown 里的同名 helper(行为完全一致),
    拿不到就本地实现一份等价逻辑。
    """
    try:
        from scripts.note_to_markdown import resolve_input as _upstream
    except Exception:
        _upstream = None
    if _upstream is not None:
        try:
            return _upstream(target)
        except Exception:
            pass

    if target.exists():
        return target

    candidates = [Path(unescape_shell_path(str(target)))]
    for cand in candidates:
        if cand.exists():
            return cand

    # 兜底:同一目录里找忽略空格、忽略大小写的匹配
    for cand in candidates:
        parent = cand.parent
        if not parent.is_dir():
            continue
        key = cand.name.replace(" ", "").lower()
        for item in parent.iterdir():
            if item.name.replace(" ", "").lower() == key:
                return item
    return target


def load_prompt_modes() -> list[str]:
    """从 dots_mocr.utils.prompts 读取真实的 prompt 模式名。

    读不到就退回 PROMPT_HINTS 的键(顺序一致),保证 --list-prompts 永远有输出。
    """
    try:
        from dots_mocr.utils.prompts import dict_promptmode_to_prompt
        names = list(dict_promptmode_to_prompt.keys())
        if names:
            return names
    except Exception:
        pass
    return list(PROMPT_HINTS.keys())


def format_argv(argv: list[str]) -> str:
    """把 argv 拼成一行可复制的命令(带引号,空格安全)。"""
    return " ".join(shlex.quote(a) for a in argv)


def print_argv(argv: list[str], header: str = "将执行:") -> None:
    """打印完整 argv —— shell-quoted,可以直接复制到终端跑。"""
    print(header)
    print("  " + format_argv(argv))


def on_off(value: bool, true_word: str = "开", false_word: str = "关") -> str:
    """布尔值的中文显示。"""
    return true_word if value else false_word


# ── 交互原语 ────────────────────────────────────────────────────────────────
def ask_yes_no(label: str, default: bool = True) -> bool:
    """是/否提问。空回车取默认值。"""
    hint = "Y/n" if default else "y/N"
    while True:
        print()
        raw = input(f"{label} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes", "是", "好"):
            return True
        if raw in ("n", "no", "否", "不"):
            return False
        print("  请输入 y 或 n。")


def ask_choice(label: str, options: list[str], current: str | None = None) -> str:
    """数值菜单选一项,返回选中的字符串。

    options 里的每一项是「值 | 显示文本」或纯文本(值=文本)。
    current 会高亮显示(仍需输入编号,避免误操作直接回车)。
    """
    print(f"\n{label}")
    for idx, opt in enumerate(options, start=1):
        value, text = split_option(opt)
        mark = " (当前)" if current is not None and value == current else ""
        print(f"  {idx:>2}. {text}{mark}")
    while True:
        print()
        raw = input(f"请选择 [1-{len(options)}]: ").strip()
        if not raw:
            if current is not None:
                print(f"  保持当前: {current}")
                return current
            print("  请输入编号。")
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return split_option(options[int(raw) - 1])[0]
        print("  编号超出范围,请重试。")


def split_option(option: str) -> tuple[str, str]:
    """把 `值 | 显示文本` 拆成 (值, 文本);没有 `|` 就原样返回。"""
    if "|" in option:
        value, text = option.split("|", 1)
        return value.strip(), text.strip()
    return option, option


def range_hint(minimum: int | float | None, maximum: int | float | None) -> str:
    """把允许的范围拼成提示文本。"""
    if minimum is not None and maximum is not None:
        return f", 范围 {minimum}-{maximum}"
    if minimum is not None:
        return f", 最小 {minimum}"
    if maximum is not None:
        return f", 最大 {maximum}"
    return ""


def ask_int(label: str, current: int, minimum: int | None = None,
            maximum: int | None = None) -> int:
    """整数输入,带范围校验。空回车保持当前值。

    标签里会带上允许的范围,用户一眼就知道该填什么。
    """
    hint = range_hint(minimum, maximum)
    while True:
        print()
        raw = input(f"{label} [当前 {current}{hint}]: ").strip()
        if not raw:
            return current
        try:
            value = int(raw)
        except ValueError:
            print("  请输入一个整数。")
            continue
        if minimum is not None and value < minimum:
            print(f"  不能小于 {minimum}。")
            continue
        if maximum is not None and value > maximum:
            print(f"  不能大于 {maximum}。")
            continue
        return value


def ask_float(label: str, current: float, minimum: float | None = None,
              maximum: float | None = None) -> float:
    """浮点输入,带范围校验。空回车保持当前值。"""
    hint = range_hint(minimum, maximum)
    while True:
        print()
        raw = input(f"{label} [当前 {current:g}{hint}]: ").strip()
        if not raw:
            return current
        try:
            value = float(raw)
        except ValueError:
            print("  请输入一个数字。")
            continue
        if minimum is not None and value < minimum:
            print(f"  不能小于 {minimum}。")
            continue
        if maximum is not None and value > maximum:
            print(f"  不能大于 {maximum}。")
            continue
        return value


def ask_toggle(label: str, current: bool, true_word: str = "开",
               false_word: str = "关") -> bool:
    """布尔开关。空回车保持当前值。"""
    state = true_word if current else false_word
    while True:
        print()
        raw = input(f"{label} [当前 {state}]: ").strip().lower()
        if not raw:
            return current
        if raw in ("y", "yes", "1", "on", "是", "开", "true"):
            return True
        if raw in ("n", "no", "0", "off", "否", "关", "false"):
            return False
        print("  请输入 y/n 或直接回车保持不变。")


def ask_text(label: str, current: str) -> str:
    """自由文本。空回车保持当前值。"""
    print()
    raw = input(f"{label} [当前 {current}]: ").strip()
    return raw or current


def ask_host(label: str, current: str) -> str:
    """模型服务地址输入,带合法性校验。

    裸数字肯定不是合法地址 —— 用户在数值菜单里顺手按的「1」不该被
    当成主机名。接受:主机名、IPv4、IPv6、`[::1]:1234`、`http://host`。
    """
    while True:
        print()
        raw = input(f"{label} [当前 {current}]: ").strip()
        if not raw:
            return current
        if raw.isdigit():
            print("  地址不能是纯数字(主机名 / IP 才合法)。")
            continue
        if not is_valid_host(raw):
            print("  这不像一个合法的地址,请再检查一下。")
            continue
        return raw


def is_valid_host(raw: str) -> bool:
    """粗略判断一个字符串能不能当主机地址用。

    规则:
      * 不能是纯数字(那样更像端口号);
      * 允许 `scheme://host`、`[::1]:1234`、IPv4、IPv6、主机名;
      * 主机名只允许字母 / 数字 / 点 / 横线 / 下划线。
    """
    text = raw.strip()
    if not text:
        return False
    if text.isdigit():
        return False

    # 去掉 scheme
    if "://" in text:
        text = text.split("://", 1)[1]
    # 去掉 path
    text = text.split("/", 1)[0]
    if not text:
        return False

    # 去掉端口([::1]:1234 / host:1234)
    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            return False
        host_part = text[1:end]
        rest = text[end + 1:]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return False
        return bool(host_part) and all(c in "0123456789abcdefABCDEF:." for c in host_part)

    if ":" in text:
        host_part, _, port_part = text.rpartition(":")
        if not port_part.isdigit():
            # 裸 IPv6,例如 ::1 / fe80::1
            return all(c in "0123456789abcdefABCDEF:." for c in text)
        if not host_part:
            # 形如 ":1234" —— 主机部分为空,不合法
            return False
        # 裸 IPv6 后面跟端口(不带方括号)也允许,例如 ::1:1234
        if ":" in host_part:
            return all(c in "0123456789abcdefABCDEF:." for c in host_part)
        text = host_part

    if not text:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_")
    return all(c in allowed for c in text)


# ── 路径浏览 ────────────────────────────────────────────────────────────────
class Browser:
    """目录浏览器:列出候选文件、进入子目录、返回上级。

    状态:
        cwd   当前所在目录
    """

    def __init__(self, start: Path | None = None) -> None:
        self.cwd = (start or Path.cwd()).expanduser().resolve()

    def _entries(self) -> tuple[list[Path], list[Path]]:
        """返回 (子目录列表, 可选文件列表),都已排序。

        子目录只保留「里面可能还有图片 / PDF」的那些,否则一个普通目录
        动辄几十个无关子目录,列表就没法看了。
        """
        dirs: list[Path] = []
        files: list[Path] = []
        try:
            for item in sorted(self.cwd.iterdir(), key=lambda p: p.name.lower()):
                if item.name.startswith("."):
                    continue
                if item.is_dir():
                    if self._has_content(item):
                        dirs.append(item)
                elif item.suffix.lower() in BROWSABLE_SUFFIXES:
                    files.append(item)
        except OSError as exc:
            print(f"[警告] 无法读取目录 {self.cwd}: {exc}")
        return dirs, files

    @staticmethod
    def _has_content(directory: Path) -> bool:
        """目录里(含下一层)有没有图片 / PDF。"""
        try:
            for item in directory.iterdir():
                if item.name.startswith("."):
                    continue
                if item.is_file() and item.suffix.lower() in BROWSABLE_SUFFIXES:
                    return True
                if item.is_dir() and Browser._has_content(item):
                    return True
        except OSError:
            return False
        return False

    def all_subdirs(self) -> list[Path]:
        """当前目录下全部子目录(选输出目录时用,不过滤内容)。"""
        dirs: list[Path] = []
        try:
            for item in sorted(self.cwd.iterdir(), key=lambda p: p.name.lower()):
                if item.name.startswith("."):
                    continue
                if item.is_dir():
                    dirs.append(item)
        except OSError as exc:
            print(f"[警告] 无法读取目录 {self.cwd}: {exc}")
        return dirs

    def _show(self) -> list[Path]:
        """打印当前目录内容,返回「可选编号 → 路径」的映射表。"""
        dirs, files = self._entries()
        options: list[Path] = []

        print(f"\n当前目录: {self.cwd}")
        if self.cwd.parent != self.cwd:
            options.append(self.cwd.parent)
            print(f"  0. .. (返回上级: {self.cwd.parent})")

        index = 1
        if dirs:
            print("  子目录:")
            for d in dirs:
                print(f"  {index:>2}. {d.name}/")
                options.append(d)
                index += 1
        if files:
            print("  文件:")
            for f in files:
                print(f"  {index:>2}. {f.name}")
                options.append(f)
                index += 1
        if not options or (len(options) == 1 and options[0] == self.cwd.parent):
            print("  (这里没有可浏览的图片 / PDF)")
        return options

    def browse(self, purpose: str = "输入", allow_dir: bool = True) -> Path | None:
        """交互浏览直到用户选定一个文件(或目录)。返回 None 表示取消。

        allow_dir=False 时目录仍然可以「进去看看」,只是不能被选作最终答案
        —— 否则用户永远下不到子目录里找文件。
        """
        while True:
            options = self._show()
            raw = input(f"\n请选择{purpose}的编号 (直接回车取消): ").strip()
            if not raw:
                print("  已取消。")
                return None
            if not raw.isdigit():
                print("  请输入编号。")
                continue
            idx = int(raw)
            if idx == 0 and options and options[0] == self.cwd.parent:
                self.cwd = self.cwd.parent
                continue
            if not (1 <= idx <= len(options)):
                print("  编号超出范围。")
                continue
            chosen = options[idx - 1]
            if not chosen.is_dir():
                return chosen
            # 目录:可以进去继续挑,也可以(如果允许)整个目录当输入
            dir_options = ["enter | 进入这个目录继续浏览"]
            if allow_dir:
                dir_options.append("pick | 就用这个目录(整个文件夹当输入)")
            dir_options.append("back | 回到上一层")
            while True:
                action = ask_choice(
                    f"选中了目录: {chosen.name}/",
                    dir_options,
                    current="enter",
                )
                if action == "enter":
                    self.cwd = chosen
                    break
                if action == "pick":
                    return chosen
                if action == "back":
                    break
            continue

    def choose(self, purpose: str, allow_dir: bool = True) -> Path | None:
        """选一个路径:浏览 / 手输 / 取消 三选一。"""
        print(f"\n=== 选择{purpose} ===")
        options = [
            "browse | 浏览目录挑选",
            "manual | 手动输入路径",
            "cancel | 取消",
        ]
        while True:
            action = ask_choice("请选择方式:", options, current="browse")
            if action == "cancel":
                return None
            if action == "manual":
                raw = input(f"请输入{purpose}路径 (空回车返回): ").strip()
                if not raw:
                    continue
                return expand_path(unescape_shell_path(raw))
            picked = self.browse(purpose=purpose, allow_dir=allow_dir)
            if picked is not None:
                return picked
            # browse 里取消了 → 回主菜单重来


# ── 模型服务探测 ────────────────────────────────────────────────────────────
def fetch_model_ids(host: str, port: int, timeout: float = 3.0) -> list[str] | None:
    """GET http://host:port/v1/models 拿模型 id 列表。

    连不上返回 None(调用方据此提示「服务不可达」)。
    """
    url = f"http://{host}:{port}/v1/models"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    entries = data.get("data") or []
    ids: list[str] = []
    for item in entries:
        if isinstance(item, dict):
            mid = item.get("id")
            if mid:
                ids.append(str(mid))
        elif isinstance(item, str):
            ids.append(item)
    return ids


def probe_server(host: str, port: int, model_name: str) -> bool:
    """探测模型服务是否可达 / 模型在不在。"""
    print(f"[探测] http://{host}:{port}/v1/models")
    ids = fetch_model_ids(host, port)
    if ids is None:
        print("[结果] 连不上(服务没起?端口不对?)")
        return False
    if not ids:
        print("[结果] 服务可达,但 /v1/models 没有列出任何模型")
        return False
    print(f"[结果] 服务可达,共 {len(ids)} 个模型:")
    for mid in ids[:MAX_LIST_ROWS]:
        mark = " ← 当前" if mid == model_name else ""
        print(f"        - {mid}{mark}")
    if model_name not in ids:
        print(f"[提示] 当前模型 '{model_name}' 不在列表里,可能是别名或没加载。")
    return True


def ask_model_name(host: str, port: int, current: str) -> str:
    """模型名:自由输入,也可以从服务端自动探测。"""
    print("\n=== 模型服务 ===")
    print(f"  地址: {host}:{port}")
    print(f"  当前模型名: {current}")
    ids = fetch_model_ids(host, port)
    if ids:
        print("  服务端可用模型:")
        for idx, mid in enumerate(ids[:MAX_LIST_ROWS], start=1):
            print(f"    {idx}. {mid}")
    else:
        print("  (探测不到服务端的 /v1/models,可能是服务没起或端口不对)")

    options = [
        "keep | 保持当前模型名",
        "manual | 手动输入模型名",
        "detect | 从服务端自动挑选",
    ]
    if not ids:
        options = options[:2]
    action = ask_choice("请选择:", options, current="keep")
    if action == "keep":
        return current
    if action == "manual":
        return ask_text("模型名", current)
    # detect
    if not ids:
        return current
    choices = [f"{mid} | {mid}" for mid in ids[:MAX_LIST_ROWS]]
    picked = ask_choice("从这些模型里挑一个:", choices, current=current)
    return picked


# ── 配置状态 ────────────────────────────────────────────────────────────────
@dataclass
class Config:
    """面板的持久状态:一屏能看到的全部设置。

    每个字段的默认值都来自环境变量(env var 优先),所以
    `OCR_DPI=300 python ocr_shell.py` 一进来面板上就是 300。
    """

    task: str = "note_to_markdown"
    input: str = ""
    output: str = ""
    dpi: int = 150
    quality: int = 80
    start: int = 1
    end: int = 0
    gray: bool = False
    max_side: int = 1600
    scale: float = 1.0
    preprocess: str = "enhance"
    deskew: bool = True
    trim: bool = True
    keep_staging: bool = False
    prompt: str = "prompt_layout_all_en"
    host: str = "127.0.0.1"
    port: int = 1234
    model: str = "dots.mocr"
    num_thread: int = 1
    prefix: str = ""

    # ── 构造 ──
    @classmethod
    def from_env(cls) -> "Config":
        """按环境变量造一份默认配置。"""
        preprocess = env_str("OCR_PREPROCESS", default="enhance")
        if preprocess not in PREPROCESS_MODES:
            preprocess = "enhance"
        output_dir = env_str("OCR_OUTPUT_DIR", default="./note_md")
        images_dir = env_str("OCR_IMAGES_DIR", default="")
        cfg = cls(
            task="note_to_markdown",
            input="",
            output=str(expand_path(output_dir)),
            dpi=env_int("OCR_DPI", default=150),
            quality=env_int("OCR_QUALITY", default=80),
            start=1,
            end=0,
            gray=False,
            max_side=env_int("OCR_MAX_SIDE", default=1600),
            scale=env_float("OCR_SCALE", default=1.0),
            preprocess=preprocess,
            deskew=True,
            trim=True,
            keep_staging=False,
            prompt=env_str("OCR_PROMPT", default="prompt_layout_all_en"),
            host=env_str("OCR_HOST", "LMSTUDIO_IP", default="127.0.0.1"),
            port=env_int("OCR_PORT", "LMSTUDIO_PORT", default=1234),
            model=env_str("OCR_MODEL", "LMSTUDIO_MODEL", default="dots.mocr"),
            num_thread=env_int("OCR_NUM_THREAD", default=1),
            prefix="",
        )
        # pdf_to_images 的默认输出目录不一样,先存着,切任务时再取用
        cfg._images_dir = images_dir  # type: ignore[attr-defined]
        return cfg

    # ── 任务相关的默认值 ──
    def default_output_for(self, task: str) -> str:
        """某个任务的默认输出目录。"""
        if task == "pdf_to_images":
            images_dir = getattr(self, "_images_dir", "") or ""
            if images_dir and images_dir != ".":
                return str(expand_path(images_dir))
            stem = Path(self.input).stem if self.input else "output"
            return str(Path.cwd() / f"{stem}_images")
        if task == "parser":
            return str(expand_path(env_str("OCR_OUTPUT_DIR", default="./output")))
        return str(expand_path(env_str("OCR_OUTPUT_DIR", default="./note_md")))

    def apply_task_defaults(self, task: str) -> None:
        """切换任务时,把这个任务特有的字段重置成合理默认值。"""
        self.task = task
        self.output = self.default_output_for(task)
        if task == "pdf_to_images":
            # PDF → 图片 用的是 --quality / --start / --end / --gray / --prefix
            self.quality = env_int("OCR_QUALITY", default=80)
            self.start = 1
            self.end = 0
            self.gray = False
            self.max_side = env_int("OCR_MAX_SIDE", default=1280)
            self.prefix = ""
        else:
            self.preprocess = env_str("OCR_PREPROCESS", default="enhance")
            if self.preprocess not in PREPROCESS_MODES:
                self.preprocess = "enhance"
            self.deskew = True
            self.trim = True
            self.keep_staging = False
            self.scale = env_float("OCR_SCALE", default=1.0)
            self.max_side = env_int("OCR_MAX_SIDE", default=1600)
            self.prompt = env_str("OCR_PROMPT", default="prompt_layout_all_en")
            self.num_thread = env_int("OCR_NUM_THREAD", default=1)

    # ── 序列化 ──
    def as_dict(self) -> dict:
        """字段名 → 值(方便 /config 打印)。"""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def copy(self) -> "Config":
        """浅拷贝。"""
        return replace(self)

    @classmethod
    def field_names(cls) -> list[str]:
        """全部字段名(会话文件里做白名单校验用)。"""
        return [f.name for f in fields(cls)]

    @classmethod
    def from_dict(cls, data: dict, base: "Config | None" = None) -> "Config":
        """从会话文件里的 dict 恢复一份配置。

        base 是「基线」(通常来自环境变量)。会话文件里出现的字段覆盖基线,
        没出现的字段保持基线值 —— 这样老版本会话文件缺字段也不会炸。
        非法类型 / 非法取值的字段直接忽略(回落到基线)。
        """
        cfg = base.copy() if base is not None else cls.from_env()
        if not isinstance(data, dict):
            return cfg
        names = set(cls.field_names())
        for name, value in data.items():
            if name not in names:
                continue
            current = getattr(cfg, name)
            try:
                if isinstance(current, bool):
                    if not isinstance(value, bool):
                        continue
                elif isinstance(current, int):
                    if isinstance(value, bool) or not isinstance(value, int):
                        continue
                elif isinstance(current, float):
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                elif isinstance(current, str):
                    if not isinstance(value, str):
                        continue
            except TypeError:
                continue
            setattr(cfg, name, value)
        return cfg


# ── 会话持久化 ──────────────────────────────────────────────────────────────
def default_session_path() -> Path:
    """会话文件的默认位置。

    优先级:
        1. `$OCR_SESSION_FILE`
        2. `$XDG_CONFIG_HOME/ocr/session.json`
        3. `~/.config/ocr/session.json`
    """
    explicit = env_str("OCR_SESSION_FILE", default="")
    if explicit:
        return expand_path(explicit)
    xdg = env_str("XDG_CONFIG_HOME", default="")
    if xdg:
        return expand_path(xdg) / "ocr" / "session.json"
    return Path.home() / ".config" / "ocr" / "session.json"


class Session:
    """面板的「磁盘状态」:配置 + 用户预设 + 命令历史。

    职责:
        * 启动时把会话文件读进来(文件不存在 / 损坏都不致命);
        * 退出时把当前状态写回去(原子写:先写临时文件再 os.replace)。

    会话文件长这样(缩进 2、UTF-8 不转义,方便人直接改):
        {
          "version": 1,
          "config": { "dpi": 300, ... },
          "output_fixed": true,
          "presets": { "我的": { "dpi": 200, ... } },
          "history": ["/dpi 300", ...]
        }
    """

    VERSION = 1

    def __init__(self, path: Path | None = None, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled and path is not None
        self.loaded = False          # 是否真的从磁盘读到了内容
        self.saved = False           # 是否成功写回磁盘
        self.presets: dict[str, dict] = {}
        self.history: list[str] = []
        self.output_fixed = False    # 输出目录是「固定」还是「每次询问」
        self.last_output = ""        # 清空输出前记住的目录(供「每次询问」时当默认)

    # ── 路径 ──
    @property
    def display_path(self) -> str:
        """面板底部显示用的路径文本。"""
        if not self.enabled or self.path is None:
            return "(未启用会话文件)"
        return str(self.path)

    def status_word(self) -> str:
        """状态词:已载入 / 已保存 / 新建 / 未启用。"""
        if not self.enabled:
            return "未启用"
        if self.loaded:
            return "已载入"
        if self.saved:
            return "已保存"
        return "新建"

    # ── 读 ──
    def load(self, base: Config) -> Config:
        """从磁盘读会话,返回合并后的配置。

        文件不存在 → 用基线;文件损坏 → 打印警告后用基线(绝不崩溃)。
        """
        cfg = base.copy()
        if not self.enabled or self.path is None:
            return cfg
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cfg
        except OSError as exc:
            print(f"[警告] 读不到会话文件 {self.path}: {exc}")
            print("       继续用默认设置。")
            return cfg
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[警告] 会话文件格式坏了 {self.path}: {exc}")
            print("       已忽略,继续用默认设置。")
            return cfg
        if not isinstance(data, dict):
            print(f"[警告] 会话文件内容不是对象 {self.path},已忽略。")
            return cfg

        cfg = Config.from_dict(data.get("config") or {}, base=base)
        fixed = data.get("output_fixed")
        self.output_fixed = bool(fixed)
        last = data.get("last_output")
        self.last_output = last if isinstance(last, str) else ""
        presets = data.get("presets")
        if isinstance(presets, dict):
            for name, values in presets.items():
                if isinstance(name, str) and isinstance(values, dict):
                    self.presets[name] = dict(values)
        history = data.get("history")
        if isinstance(history, list):
            self.history = [str(h) for h in history if isinstance(h, str)][-MAX_HISTORY:]
        self.loaded = True
        return cfg

    # ── 写 ──
    def save(self, cfg: Config, history: list[str] | None = None) -> bool:
        """把当前状态原子写回会话文件。返回是否成功。"""
        if not self.enabled or self.path is None:
            return False
        payload = {
            "version": self.VERSION,
            "config": cfg.as_dict(),
            "output_fixed": self.output_fixed,
            "last_output": self.last_output,
            "presets": self.presets,
            "history": list(history or [])[-MAX_HISTORY:],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"[警告] 建不了会话目录 {self.path.parent}: {exc}")
            return False
        tmp = self.path.with_name(self.path.name + f".tmp{os.getpid()}")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except OSError as exc:
            print(f"[警告] 写不了会话文件 {self.path}: {exc}")
            try:
                tmp.unlink()
            except OSError:
                pass
            return False
        self.saved = True
        return True

    # ── 用户预设 ──
    def user_preset_names(self) -> list[str]:
        """用户自定义预设的名字(按字典序)。"""
        return sorted(self.presets.keys())

    def all_preset_names(self) -> list[str]:
        """内置 + 用户预设的名字(内置在前)。"""
        return list(PRESETS.keys()) + self.user_preset_names()

    def preset_values(self, name: str) -> dict:
        """取某个预设的字段值(内置优先)。"""
        if name in PRESETS:
            return dict(PRESETS[name][1])
        return dict(self.presets.get(name, {}))

    def preset_desc(self, name: str) -> str:
        """预设的中文说明。"""
        if name in PRESETS:
            return PRESETS[name][0]
        return self.presets.get(name, {}).get("__desc__", "自定义预设")

    def set_user_preset(self, name: str, values: dict, desc: str = "") -> None:
        """保存一个用户预设。"""
        payload = {k: v for k, v in values.items() if k in Config.field_names()}
        payload["__desc__"] = desc or "自定义预设"
        self.presets[name] = payload

    def delete_user_preset(self, name: str) -> bool:
        """删除一个用户预设(内置的删不掉)。"""
        if name in PRESETS or name not in self.presets:
            return False
        del self.presets[name]
        return True


# ── argv 构造 ───────────────────────────────────────────────────────────────
def build_argv(target: str, args: list[str]) -> list[str]:
    """按目标算出最终 argv。

    note_to_markdown / pdf_to_images / check_imports / smoke_test:
        [sys.executable, <脚本路径>, *args]
    parser:
        [sys.executable, "-m", "dots_mocr.parser", *args]
    """
    if target == "parser":
        return [sys.executable, "-m", "dots_mocr.parser", *args]
    script = SCRIPT_FILES.get(target)
    if script is None:
        raise KeyError(target)
    return [sys.executable, str(script), *args]


def build_argv_from_config(cfg: Config) -> list[str]:
    """把当前面板状态拼成目标脚本的参数片段(不含脚本路径)。

    和旧版向导产出的参数完全一致,行为不变。

    注意 deskew / trim 的反转:
        CLI 上是 `--no-deskew` / `--no-trim`(反向开关),
        所以只有「关掉」时才加这两个参数。写反过一次,别再写反。
    """
    if cfg.task == "pdf_to_images":
        args: list[str] = [
            cfg.input,
            "-o", cfg.output,
            "--dpi", str(cfg.dpi),
            "--quality", str(cfg.quality),
            "--start", str(cfg.start),
            "--end", str(cfg.end),
        ]
        if cfg.gray:
            args.append("--gray")
        args += ["--max-side", str(cfg.max_side), "--prefix", cfg.prefix]
        return args

    # note_to_markdown 与 parser 共用服务端 / prompt 参数
    args = [
        cfg.input,
        "--prompt", cfg.prompt,
        "--ip", cfg.host,
        "--port", str(cfg.port),
    ]
    if cfg.task == "parser":
        # dots.mocr parser 用下划线版本的参数名,而且没有输出目录
        args += [
            "--model_name", cfg.model,
            "--num_thread", str(cfg.num_thread),
            "--dpi", str(cfg.dpi),
        ]
        return args

    args = [
        cfg.input,
        "-o", cfg.output,
        "--dpi", str(cfg.dpi),
        "--preprocess", cfg.preprocess,
    ]
    if not cfg.deskew:
        args.append("--no-deskew")
    if not cfg.trim:
        args.append("--no-trim")
    if cfg.keep_staging:
        args.append("--keep-staging")
    args += [
        "--scale", f"{cfg.scale:g}",
        "--max-side", str(cfg.max_side),
        "--prompt", cfg.prompt,
        "--ip", cfg.host,
        "--port", str(cfg.port),
        "--model-name", cfg.model,
        "--num-thread", str(cfg.num_thread),
    ]
    return args


def build_full_argv(cfg: Config) -> list[str]:
    """当前任务的完整 argv(含解释器与脚本路径)。"""
    return build_argv(cfg.task, build_argv_from_config(cfg))


# ── 面板渲染 ────────────────────────────────────────────────────────────────
def _panel_line(left: str, right: str = "", width: int = PANEL_WIDTH) -> str:
    """面板里的一行「左字段 / 右字段」。"""
    left_part = f"  {left}"
    if right:
        pad = max(width - 4 - _display_len(left_part), 1)
        return f"{left_part}{' ' * pad}{right}"
    return left_part.rstrip()


def _display_len(text: str) -> int:
    """字符串的终端显示宽度(中文算两列)。"""
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text: str, width: int) -> str:
    """按终端显示宽度右补空格(中文算两列)。"""
    gap = width - _display_len(text)
    return text + " " * gap if gap > 0 else text


def _fit(text: str, limit: int) -> str:
    """把文本截到不超过 limit 个显示列(超长时尾部加 …)。"""
    if _display_len(text) <= limit:
        return text
    out = ""
    width = 0
    for ch in text:
        step = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + step > limit - 1:
            break
        out += ch
        width += step
    return out + "…"


def _field(label: str, value: str, limit: int = 34) -> str:
    """面板里的一行「标签  值」,标签按显示宽度对齐,值超长就截断。"""
    return "  " + _pad(label, 10) + _fit(value, limit)


def _two(l1: str, v1: str, l2: str, v2: str, limit: int = 26) -> str:
    """面板里的一行「标签 值  标签 值」,两列都按显示宽度对齐。"""
    left = "  " + _pad(l1, 10) + _pad(_fit(v1, limit), limit + 2)
    return left + _pad(l2, 10) + _fit(v2, limit)


def render_panel(cfg: Config, clear: bool = True, session: "Session | None" = None,
                 recent: list[str] | None = None) -> None:
    """打印一屏面板:所有当前设置 + 可用命令。

    clear=True 且 stdout 是终端时才清屏;管道 / CI 里只打印,
    这样日志仍然可读。
    """
    if clear and stdout_is_tty():
        sys.stdout.write(ANSI_CLEAR)
        sys.stdout.flush()

    task_desc = EXEC_TARGETS.get(cfg.task, cfg.task)
    inp = cfg.input or "(未设置, /input 指定)"
    # 输出目录有两种模式:「固定用这个目录」和「每次都问」。
    fixed = session.output_fixed if session is not None else False
    if cfg.output:
        out = cfg.output
        out_tag = "固定" if fixed else "每次询问"
    else:
        remembered = session.last_output if session is not None else ""
        if remembered:
            out = remembered
            out_tag = "每次询问"
        else:
            out = "(未设置,用 /output 指定)"
            out_tag = "每次询问"

    # ── 标题框 ──
    print("╭" + "─" * (PANEL_WIDTH - 2) + "╮")
    title = "  OCR 工具链 · 交互式面板"
    print("│" + title + " " * max(PANEL_WIDTH - 2 - _display_len(title), 0) + "│")
    print("╰" + "─" * (PANEL_WIDTH - 2) + "╯")
    print()

    # ── 任务 / 输入 / 输出 ──
    print("  " + _pad("任务", 10) + _pad(cfg.task, 22) + task_desc)
    print(_field("输入", inp, 52))
    print("  " + _pad("输出", 10) + _fit(out, 40) + f"  ({out_tag})")
    print("  " + "─" * (PANEL_WIDTH - 4))
    print()

    # ── 图像 / 渲染参数 ──
    print(_two("DPI", str(cfg.dpi), "scale", f"{cfg.scale:g}"))
    print(_two("预处理", cfg.preprocess, "max-side", str(cfg.max_side)))
    print(_two("纠偏", on_off(cfg.deskew, "开", "关"),
               "裁白边", on_off(cfg.trim, "开", "关")))
    print(_field("中间图", on_off(cfg.keep_staging, "保留", "不留")))
    print("  " + "─" * (PANEL_WIDTH - 4))
    print()

    # ── PDF → 图片 专用参数 ──
    if cfg.task == "pdf_to_images":
        print(_two("质量", str(cfg.quality),
                   "页码", f"{cfg.start} → {cfg.end or '末页'}"))
        print(_field("灰度", on_off(cfg.gray, "开", "关")))
        print(_field("前缀", cfg.prefix or "(用 PDF 文件名)"))
        print("  " + "─" * (PANEL_WIDTH - 4))
        print()

    # ── 服务端 ──
    print(_two("服务", f"{cfg.host}:{cfg.port}", "模型", cfg.model))
    if cfg.task != "pdf_to_images":
        print(_two("提示模式", cfg.prompt, "并发", str(cfg.num_thread)))
    print()

    # ── 命令表(两列) ──
    print("  可用命令:")
    items = list(COMMANDS.items())
    half = (len(items) + 1) // 2
    left_col = items[:half]
    right_col = items[half:]
    for idx in range(half):
        lname, (ldesc, _) = left_col[idx]
        cell = f"    {_pad('/' + lname, 13)}{ldesc}"
        if idx < len(right_col):
            rname, (rdesc, _) = right_col[idx]
            pad = max(36 - _display_len(cell), 1)
            print(f"{cell}{' ' * pad}{_pad('/' + rname, 13)}{rdesc}")
        else:
            print(cell)
    print()

    # ── 最近命令(像 Claude Code 那样显示在底部)──
    if recent:
        print("  最近命令:")
        for item in recent[-RECENT_COMMANDS:]:
            print(f"    {item}")
        print()

    # ── 页脚:会话文件 ──
    if session is not None:
        print(f"  会话: {session.display_path} ({session.status_word()})")
    print("  提示: 命令可省略 `/`;直接拖入一个存在的路径 = 设输入并立即执行。")
    print("        /set 进设置页, /print-argv 只打印 argv 不执行。")
    print()


# ── 面板命令实现 ────────────────────────────────────────────────────────────
def cmd_task(cfg: Config, browser: Browser, args: list[str]) -> None:
    """/task — 切换任务。"""
    options = [f"{name} | {name} — {EXEC_TARGETS.get(name, name)}" for name in TASK_NAMES]
    picked = ask_choice("请选择任务:", options, current=cfg.task)
    if picked != cfg.task:
        cfg.apply_task_defaults(picked)
        print(f"[已切换] 任务 → {picked}")
    else:
        print("[提示] 任务没变。")


def cmd_input(cfg: Config, browser: Browser, args: list[str]) -> None:
    """/input — 设置输入:手输 / 浏览 / 整个文件夹 / 清空。"""
    options = [
        "manual | 手动输入路径",
        "browse | 浏览目录挑选",
        "folder | 就用一整个文件夹",
        "clear | 清空输入",
    ]
    action = ask_choice("请选择设置输入的方式:", options, current="manual")
    if action == "clear":
        cfg.input = ""
        print("[已清空] 输入")
        return
    if action == "manual":
        while True:
            raw = input("请输入输入路径 (空回车取消): ").strip()
            if not raw:
                print("[取消]")
                return
            target = expand_path(unescape_shell_path(raw))
            resolved = resolve_input(target)
            if resolved.exists():
                cfg.input = str(resolved)
                print(f"[已设置] 输入 → {resolved}")
                return
            print(f"[错误] 找不到: {raw}")
            if not ask_yes_no("  再输一次吗?", default=True):
                print("[取消]")
                return
    if action == "browse":
        # 直接进目录浏览器,不再套一层「浏览 / 手输 / 取消」菜单
        while True:
            picked = browser.browse(purpose="输入文件或文件夹", allow_dir=True)
            if picked is None:
                print("[取消]")
                return
            resolved = resolve_input(picked)
            if resolved.exists():
                if resolved != picked:
                    print(f"[提示] 路径已修正: {picked} → {resolved}")
                cfg.input = str(resolved)
                print(f"[已设置] 输入 → {resolved}")
                return
            print(f"[错误] 找不到: {picked}")
            if not ask_yes_no("  再选一次吗?", default=True):
                print("[取消]")
                return
    # folder:整个目录当输入
    while True:
        raw = input("请输入文件夹路径 (空回车取消): ").strip()
        if not raw:
            print("[取消]")
            return
        target = expand_path(unescape_shell_path(raw))
        if target.is_dir():
            cfg.input = str(target)
            print(f"[已设置] 输入 → {target}")
            return
        print(f"[错误] 不是文件夹: {raw}")
        if not ask_yes_no("  再输一次吗?", default=True):
            print("[取消]")
            return


def cmd_output(cfg: Config, browser: Browser, args: list[str],
              session: "Session | None" = None) -> None:
    """/output — 设置输出目录:手输 / 浏览 / 默认 / 每次都问。

    「每次都问」= 清空输出目录(记住它,下次当默认值);
    选定一个目录 = 「固定用这个目录」,以后不再询问。
    """
    default = cfg.default_output_for(cfg.task)
    options = [
        f"default | 用默认目录({default})",
        "manual | 手动输入路径",
        "browse | 浏览目录挑选",
        "ask | 每次都问(不定死目录)",
    ]
    action = ask_choice("请选择设置输出目录的方式:", options, current="default")
    if action == "ask":
        _clear_output(cfg, session)
        return
    if action == "default":
        cfg.output = default
        _mark_output_fixed(cfg, session)
        print(f"[已设置] 输出 → {cfg.output}(固定)")
        return
    if action == "manual":
        raw = input("请输入输出目录 (空回车取消): ").strip()
        if not raw:
            print("[取消]")
            return
        cfg.output = str(expand_path(unescape_shell_path(raw)))
        _mark_output_fixed(cfg, session)
        print(f"[已设置] 输出 → {cfg.output}(固定)")
        return
    # browse:目录树挑一个
    while True:
        dirs = browser.all_subdirs()
        print(f"\n当前目录: {browser.cwd}")
        if browser.cwd.parent != browser.cwd:
            print(f"  0. .. (返回上级: {browser.cwd.parent})")
        for idx, d in enumerate(dirs, start=1):
            print(f"  {idx:>2}. {d.name}/")
        if not dirs and browser.cwd.parent == browser.cwd:
            print("  (这里没有子目录)")
        raw = input("请选择子目录编号 (空回车用默认): ").strip()
        if not raw:
            cfg.output = default
            _mark_output_fixed(cfg, session)
            print(f"[已设置] 输出 → {cfg.output}(固定)")
            return
        if not raw.isdigit():
            print("  请输入编号。")
            continue
        idx = int(raw)
        if idx == 0 and browser.cwd.parent != browser.cwd:
            browser.cwd = browser.cwd.parent
            continue
        if not (1 <= idx <= len(dirs)):
            print("  编号超出范围。")
            continue
        browser.cwd = dirs[idx - 1]


def _mark_output_fixed(cfg: Config, session: "Session | None") -> None:
    """用户明确选了输出目录 → 标记成「固定」。"""
    if session is not None:
        session.output_fixed = True
        session.last_output = cfg.output


def _clear_output(cfg: Config, session: "Session | None") -> None:
    """清空输出目录 → 变成「每次都问」(记住旧值当默认)。"""
    if cfg.output and session is not None:
        session.last_output = cfg.output
    cfg.output = ""
    if session is not None:
        session.output_fixed = False
    remembered = session.last_output if session is not None else ""
    if remembered:
        print(f"[已切换] 输出 → 每次都问(默认 {remembered})")
    else:
        print("[已切换] 输出 → 每次都问")


def cmd_server(cfg: Config, browser: Browser, args: list[str]) -> None:
    """/server — 子菜单:地址 / 端口 / 模型。"""
    options = [
        "host | 模型服务地址",
        "port | 模型服务端口",
        "model | 模型名",
    ]
    action = ask_choice("请选择要改的服务端配置:", options, current="host")
    if action == "host":
        cfg.host = ask_host("模型服务地址 --ip", cfg.host)
        print(f"[已设置] 地址 → {cfg.host}")
    elif action == "port":
        cfg.port = ask_int("模型服务端口 --port", cfg.port, minimum=1, maximum=65535)
        print(f"[已设置] 端口 → {cfg.port}")
    else:
        cfg.model = ask_model_name(cfg.host, cfg.port, cfg.model)
        print(f"[已设置] 模型 → {cfg.model}")


# ── 设置页(/set)────────────────────────────────────────────────────────────
#: 设置页分组 → (分组名, [(选项值, 说明)])
#:
#: 选项值最终会映射到 dispatch 里的单条命令名,复用现有的交互原语,
#: 保证 /set 和 /dpi 这类单条命令行为完全一致。
SETTINGS_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("输出与输入", [
        ("task", "任务"),
        ("input", "输入文件 / 文件夹"),
        ("output", "输出目录"),
        ("prefix", "输出文件名前缀"),
    ]),
    ("图片质量(DPI / 缩放 / 最长边)", [
        ("dpi", "DPI 渲染分辨率"),
        ("scale", "额外放大倍数"),
        ("max-side", "最长边像素上限"),
        ("quality", "JPEG 质量"),
    ]),
    ("预处理", [
        ("preprocess", "预处理强度"),
        ("deskew", "自动纠偏"),
        ("trim", "裁白边"),
        ("staging", "保留中间图"),
        ("gray", "灰度输出"),
    ]),
    ("提示模式", [
        ("prompt", "prompt 模式"),
    ]),
    ("模型服务", [
        ("host", "服务地址"),
        ("port", "服务端口"),
        ("model", "模型名"),
        ("num-thread", "并发页数"),
    ]),
    ("任务与页码", [
        ("start", "起始页"),
        ("end", "结束页(0=末页)"),
    ]),
]

#: 设置项 → 当前值文本
SETTING_VALUES: dict[str, str] = {
    "task": "任务",
    "input": "输入",
    "output": "输出目录",
    "prefix": "前缀",
    "dpi": "DPI",
    "scale": "scale",
    "max-side": "max-side",
    "quality": "JPEG 质量",
    "preprocess": "预处理",
    "deskew": "纠偏",
    "trim": "裁白边",
    "staging": "中间图",
    "gray": "灰度",
    "prompt": "提示模式",
    "host": "服务地址",
    "port": "服务端口",
    "model": "模型名",
    "num-thread": "并发",
    "start": "起始页",
    "end": "结束页",
}


def setting_current_value(cfg: Config, key: str) -> str:
    """某个设置项的当前值(中文显示)。"""
    if key == "task":
        return cfg.task
    if key == "input":
        return cfg.input or "(未设置)"
    if key == "output":
        return cfg.output or "(未设置,每次询问)"
    if key == "prefix":
        return cfg.prefix or "(用原文件名)"
    if key == "dpi":
        return str(cfg.dpi)
    if key == "scale":
        return f"{cfg.scale:g}"
    if key == "max-side":
        return str(cfg.max_side) if cfg.max_side else "(不限制)"
    if key == "quality":
        return str(cfg.quality)
    if key == "preprocess":
        return cfg.preprocess
    if key == "deskew":
        return on_off(cfg.deskew, "开", "关")
    if key == "trim":
        return on_off(cfg.trim, "开", "关")
    if key == "staging":
        return on_off(cfg.keep_staging, "保留", "不留")
    if key == "gray":
        return on_off(cfg.gray, "开", "关")
    if key == "prompt":
        return cfg.prompt
    if key == "host":
        return cfg.host
    if key == "port":
        return str(cfg.port)
    if key == "model":
        return cfg.model
    if key == "num-thread":
        return str(cfg.num_thread)
    if key == "start":
        return str(cfg.start)
    if key == "end":
        return str(cfg.end) if cfg.end else "末页"
    return "(未知)"


#: 设置项 → 一行提示
SETTING_HINTS: dict[str, str] = {
    "task": "选一个要执行的任务",
    "input": "只设路径,不会自动执行",
    "output": "固定目录,以后不再询问",
    "prefix": "输出文件名前缀,留空用原名",
    "dpi": "渲染分辨率,越高越准也越慢",
    "scale": "额外放大倍数",
    "max-side": "最长边上限,0 = 不限制",
    "quality": "JPEG 质量 1-95",
    "preprocess": "none / gray / enhance / binarize",
    "deskew": "自动把歪掉的页面转正",
    "trim": "裁掉四周白边",
    "staging": "保留预处理中间图(调试用)",
    "gray": "输出灰度图",
    "prompt": "dots.mocr 的提示模式",
    "host": "模型服务地址",
    "port": "模型服务端口",
    "model": "模型名",
    "num-thread": "同时处理几页",
    "start": "起始页(1-based)",
    "end": "结束页,0 = 到末页",
}


def cmd_set(cfg: Config, browser: Browser, args: list[str],
            session: "Session | None" = None) -> None:
    """/set — 设置页:分组菜单 → 单项菜单 → 改值。

    只是「另一条路」走到同样的设置项上;`/dpi` 这类单条命令照旧可用。
    """
    while True:
        print("\n=== 设置 ===")
        for idx, (group, _items) in enumerate(SETTINGS_GROUPS, start=1):
            print(f"  {idx}. {group}")
        preset_no = len(SETTINGS_GROUPS) + 1
        print(f"  {preset_no}. 预设")
        print("  0. 返回")
        print()
        raw = input(f"请选择分组 [0-{preset_no}]: ").strip()
        if not raw:
            print("[返回]")
            return
        if not raw.isdigit():
            print("  请输入编号。")
            continue
        idx = int(raw)
        if idx == 0:
            print("[返回]")
            return
        if idx == preset_no:
            cmd_preset(cfg, browser, args, session=session)
            return
        if not (1 <= idx <= len(SETTINGS_GROUPS)):
            print("  编号超出范围。")
            continue
        group, items = SETTINGS_GROUPS[idx - 1]
        if _set_group(cfg, browser, session, group, items):
            return


def _set_group(cfg: Config, browser: Browser, session: "Session | None",
               group: str, items: list[tuple[str, str]]) -> bool:
    """一个分组里的子菜单:选要改哪一项 → 改。返回 True 表示要退出设置页。"""
    while True:
        print(f"\n=== 设置 · {group} ===")
        for idx, (key, label) in enumerate(items, start=1):
            value = setting_current_value(cfg, key)
            print(f"  {idx}. {label:<12}{value}")
        print("  0. 返回")
        print()
        raw = input("请选择要修改的项: ").strip()
        if not raw:
            print("[返回]")
            return False
        if not raw.isdigit():
            print("  请输入编号。")
            continue
        idx = int(raw)
        if idx == 0:
            print("[返回]")
            return False
        if not (1 <= idx <= len(items)):
            print("  编号超出范围。")
            continue
        key, label = items[idx - 1]
        hint = SETTING_HINTS.get(key, "")
        print(f"\n[{label}] {hint}")
        _set_one(cfg, browser, session, key)
        # 改完回到分组菜单 —— 设置页要能连续改好几项


def _set_one(cfg: Config, browser: Browser, session: "Session | None",
             key: str) -> None:
    """改一个设置项(复用现有交互原语,与单条命令行为一致)。"""
    if key == "task":
        cmd_task(cfg, browser, [])
    elif key == "input":
        cmd_input(cfg, browser, [])
    elif key == "output":
        cmd_output(cfg, browser, [], session=session)
    elif key == "prefix":
        cfg.prefix = ask_text("--prefix 文件名前缀(留空则用原文件名)", cfg.prefix)
        print(f"[已设置] 前缀 → {cfg.prefix or '(用原文件名)'}")
    elif key == "dpi":
        cfg.dpi = ask_int("PDF 渲染分辨率 --dpi", cfg.dpi, minimum=1, maximum=1200)
        print(f"[已设置] DPI → {cfg.dpi}")
    elif key == "scale":
        cfg.scale = ask_float("--scale 额外放大倍数", cfg.scale,
                              minimum=0.1, maximum=8.0)
        print(f"[已设置] scale → {cfg.scale:g}")
    elif key == "max-side":
        cfg.max_side = ask_int("--max-side 最长边像素上限(0=不限制)", cfg.max_side,
                               minimum=0, maximum=16000)
        print(f"[已设置] max-side → {cfg.max_side}")
    elif key == "quality":
        cfg.quality = ask_int("--quality JPEG 质量(1-95)", cfg.quality,
                              minimum=1, maximum=95)
        print(f"[已设置] 质量 → {cfg.quality}")
    elif key == "preprocess":
        options = [f"{m} | {m} — {desc}" for m, desc in PREPROCESS_MODES.items()]
        print("\n--preprocess 预处理强度:")
        print("  binarize 最接近印刷体,enhance 最保守(默认)。")
        cfg.preprocess = ask_choice("请选择预处理模式:", options, current=cfg.preprocess)
        print(f"[已设置] 预处理 → {cfg.preprocess}")
    elif key == "prompt":
        modes = load_prompt_modes()
        options = [f"{m} | {m} — {PROMPT_HINTS.get(m, 'dots.mocr 提示模式')}"
                   for m in modes]
        cfg.prompt = ask_choice("请选择 prompt 模式:", options, current=cfg.prompt)
        print(f"[已设置] 提示模式 → {cfg.prompt}")
    elif key == "deskew":
        cfg.deskew = ask_toggle("自动纠偏(关掉会加 --no-deskew)",
                                current=cfg.deskew, true_word="纠偏开", false_word="纠偏关")
        print(f"[已设置] 纠偏 → {on_off(cfg.deskew, '开', '关')}")
    elif key == "trim":
        cfg.trim = ask_toggle("裁白边(关掉会加 --no-trim)",
                              current=cfg.trim, true_word="裁边开", false_word="裁边关")
        print(f"[已设置] 裁白边 → {on_off(cfg.trim, '开', '关')}")
    elif key == "staging":
        cfg.keep_staging = ask_toggle("保留预处理中间图(开=加 --keep-staging)",
                                       current=cfg.keep_staging,
                                       true_word="保留", false_word="不留")
        print(f"[已设置] 中间图 → {on_off(cfg.keep_staging, '保留', '不留')}")
    elif key == "gray":
        cfg.gray = ask_toggle("输出灰度图(开=加 --gray)", current=cfg.gray,
                              true_word="灰度", false_word="彩色")
        print(f"[已设置] 灰度 → {on_off(cfg.gray, '开', '关')}")
    elif key == "host":
        cfg.host = ask_host("模型服务地址 --ip", cfg.host)
        print(f"[已设置] 地址 → {cfg.host}")
    elif key == "port":
        cfg.port = ask_int("模型服务端口 --port", cfg.port, minimum=1, maximum=65535)
        print(f"[已设置] 端口 → {cfg.port}")
    elif key == "model":
        cfg.model = ask_model_name(cfg.host, cfg.port, cfg.model)
        print(f"[已设置] 模型 → {cfg.model}")
    elif key == "num-thread":
        cfg.num_thread = ask_int("--num-thread 并发页数", cfg.num_thread,
                                 minimum=1, maximum=64)
        print(f"[已设置] 并发页数 → {cfg.num_thread}")
    elif key == "start":
        cfg.start = ask_int("--start 起始页(1-based)", cfg.start,
                            minimum=1, maximum=100000)
        print(f"[已设置] 起始页 → {cfg.start}")
    elif key == "end":
        cfg.end = ask_int("--end 结束页(0=到末页)", cfg.end,
                          minimum=0, maximum=100000)
        print(f"[已设置] 结束页 → {cfg.end}")
    elif key == "preset":
        cmd_preset(cfg, browser, [], session=session)


# ── 预设(/preset)───────────────────────────────────────────────────────────
def apply_preset(cfg: Config, values: dict) -> list[tuple[str, object, object]]:
    """把预设的字段套到配置上,返回 [(字段, 旧值, 新值)]。"""
    changes: list[tuple[str, object, object]] = []
    names = set(Config.field_names())
    for name, new_value in values.items():
        if name not in names or name == "__desc__":
            continue
        old_value = getattr(cfg, name)
        if old_value == new_value:
            continue
        setattr(cfg, name, new_value)
        changes.append((name, old_value, new_value))
    return changes


def show_preset_changes(changes: list[tuple[str, object, object]]) -> None:
    """打印预设改了哪些字段。"""
    if not changes:
        print("[预设] 当前设置已经和预设一致,没有变化。")
        return
    print(f"[预设] 改了 {len(changes)} 项:")
    for name, old_value, new_value in changes:
        print(f"    {name:<12} {old_value} → {new_value}")


def cmd_preset(cfg: Config, browser: Browser, args: list[str],
               session: "Session | None" = None) -> None:
    """/preset — 预设菜单:内置预设 / 自定义 / 保存 / 删除。"""
    if session is None:
        print("[错误] 预设功能需要会话文件(用 --no-session 关掉时不可用)。")
        return

    while True:
        print("\n=== 预设 ===")
        options: list[tuple[str, str]] = []
        for name in PRESETS:
            options.append((name, f"{name} — {PRESETS[name][0]}"))
        for name in session.user_preset_names():
            options.append((name, f"{name} — {session.preset_desc(name)}"))
        options.append(("__custom__", "自定义(从文件加载)"))
        options.append(("__save__", "保存当前设置为预设"))
        options.append(("__delete__", "删除自定义预设"))
        options.append(("__back__", "返回"))

        for idx, (name, text) in enumerate(options, start=1):
            print(f"  {idx}. {text}")
        print()
        raw = input(f"请选择 [1-{len(options)}]: ").strip()
        if not raw:
            print("[返回]")
            return
        if not raw.isdigit():
            print("  请输入编号。")
            continue
        idx = int(raw)
        if not (1 <= idx <= len(options)):
            print("  编号超出范围。")
            continue
        name = options[idx - 1][0]

        if name == "__back__":
            print("[返回]")
            return
        if name == "__save__":
            _preset_save(cfg, session)
            continue
        if name == "__delete__":
            _preset_delete(session)
            continue
        if name == "__custom__":
            _preset_load_file(cfg, session)
            continue
        values = session.preset_values(name)
        changes = apply_preset(cfg, values)
        print(f"[已套用] 预设 {name}")
        show_preset_changes(changes)


def _preset_save(cfg: Config, session: Session) -> None:
    """把当前设置存成一个用户预设。"""
    name = ask_text("预设名称", "").strip()
    if not name:
        print("[取消]")
        return
    if name in PRESETS:
        print(f"[错误] '{name}' 是内置预设,不能覆盖。换个名字吧。")
        return
    values = cfg.as_dict()
    # 输入 / 输出目录跟具体文件走,预设不该带着走
    values.pop("input", None)
    desc = ask_text("预设说明(可留空)", "").strip()
    session.set_user_preset(name, values, desc)
    print(f"[已保存] 预设 '{name}'(下次启动还在)")


def _preset_delete(session: Session) -> None:
    """删掉一个用户预设。"""
    names = session.user_preset_names()
    if not names:
        print("[提示] 还没有自定义预设。")
        return
    options = [f"{n} | {n} — {session.preset_desc(n)}" for n in names]
    picked = ask_choice("请选择要删除的预设:", options, current=names[0])
    if session.delete_user_preset(picked):
        print(f"[已删除] 预设 '{picked}'")
    else:
        print("[提示] 内置预设不能删除。")


def _preset_load_file(cfg: Config, session: Session) -> None:
    """从 JSON 文件里读一个自定义预设。"""
    raw = input("预设文件路径 (空回车取消): ").strip()
    if not raw:
        print("[取消]")
        return
    path = expand_path(unescape_shell_path(raw))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[错误] 找不到文件: {path}")
        return
    except OSError as exc:
        print(f"[错误] 读不了 {path}: {exc}")
        return
    except json.JSONDecodeError as exc:
        print(f"[错误] JSON 格式错误: {exc}")
        return
    if not isinstance(data, dict):
        print("[错误] 预设文件应该是一个 JSON 对象。")
        return
    values = data.get("values") if isinstance(data.get("values"), dict) else data
    changes = apply_preset(cfg, values)
    print(f"[已加载] 预设文件 {path}")
    show_preset_changes(changes)


def cmd_reset(cfg: Config, browser: Browser, args: list[str]) -> None:
    """/reset — 全部恢复默认(要确认)。

    「默认」= 环境变量的默认值(不是写死的常量),所以 `OCR_DPI=300`
    起的面板, /reset 之后 DPI 仍然是 300。
    """
    if not ask_yes_no("确定要恢复默认设置吗?", default=False):
        print("[取消] 设置没变。")
        return
    fresh = Config.from_env()
    fresh.task = cfg.task
    fresh.apply_task_defaults(cfg.task)
    fresh.input = ""
    cfg.__dict__.update(fresh.__dict__)
    print("[已重置] 所有设置恢复默认(输入已清空)。")


def cmd_save(cfg: Config, browser: Browser, args: list[str],
             session: "Session | None" = None) -> None:
    """/save — 立刻把当前设置写回会话文件。"""
    if session is None or not session.enabled:
        print("[提示] 会话文件没启用(用了 --no-session?),没什么可保存的。")
        return
    if session.save(cfg, history=session.history):
        print(f"[已保存] {session.path}")
    else:
        print("[失败] 没写成功,看上面的警告。")


def cmd_reload(cfg: Config, browser: Browser, args: list[str],
               session: "Session | None" = None) -> None:
    """/reload — 丢弃当前改动,重新从会话文件载入。"""
    if session is None or not session.enabled:
        print("[提示] 会话文件没启用(用了 --no-session?),没什么可载入的。")
        return
    if not session.path.exists():
        print("[提示] 会话文件还不存在,保持当前设置。")
        return
    base = Config.from_env()
    fresh = session.load(base)
    cfg.__dict__.update(fresh.__dict__)
    print(f"[已载入] {session.path}")


def cmd_history(cfg: Config, browser: Browser, args: list[str],
                session: "Session | None" = None) -> None:
    """/history — 打印本次会话的命令历史。"""
    items = session.history if session is not None else []
    if not items:
        print("\n(还没有命令历史)")
        return
    print("\n=== 命令历史 ===")
    for idx, item in enumerate(items, start=1):
        print(f"  {idx:>3}. {item}")
    print()


def cmd_help(cfg: Config, browser: Browser, args: list[str]) -> None:
    """/help — 列出所有命令。"""
    print("\n=== 面板命令 ===")
    for name, (desc, usage) in COMMANDS.items():
        print(f"  /{name:<11}{desc:<26}{usage}")
    print("\n  提示:")
    print("    * 命令可以省略 `/`(输入 run 等价于 /run)。")
    print("    * 直接输入一个存在的路径 = 设为输入并立刻执行(流水线)。")
    print("    * /set 进设置页,/preset 套预设。")
    print("    * Ctrl-C 取消当前子提示并回到面板;Ctrl-D 退出。")
    print("    * ↑/↓ 翻历史,Ctrl-R 反向搜索(需要 readline)。")
    print("    * /print-argv(或 /run --dry-run)只打印 argv,不真的执行。")
    print()


def prepare_input(cfg: Config) -> bool:
    """确认输入已设置且存在,把修正后的路径写回 cfg。

    返回 False 表示输入不可用(已经打印了原因),调用方应当放弃本次操作。
    """
    if not cfg.input:
        print("[错误] 还没设置输入。")
        print("       用 /input 指定文件或文件夹(也可以直接敲一个存在的路径)。")
        return False
    target = resolve_input(Path(cfg.input))
    if not target.exists():
        print(f"[错误] 输入不存在: {cfg.input}")
        print("       用 /input 重新指定一个存在的路径。")
        return False
    cfg.input = str(target)
    return True


def ensure_output(cfg: Config, browser: Browser,
                  session: "Session | None" = None, create: bool = True) -> bool:
    """确保输出目录可用:没定过就问一次,定过了就直接用。

    返回 False 表示用户取消,调用方应当放弃本次执行。

    「定过没定过」看的是 session.output_fixed,不是 cfg.output 是否为空 ——
    cfg.output 一开始就有环境变量给的默认值(./note_md),如果拿它当判据,
    就永远处于「已定好」状态,「每次都问」这个模式就形同虚设。
    """
    fixed = session.output_fixed if session is not None else False

    if fixed and cfg.output:
        # 用户明确定过 → 直接用,目录没有就建一个
        target = expand_path(cfg.output)
        if create and not target.is_dir():
            try:
                target.mkdir(parents=True, exist_ok=True)
                print(f"[已创建] 输出目录 → {target}")
            except OSError as exc:
                print(f"[错误] 建不了输出目录 {target}: {exc}")
                return False
        cfg.output = str(target)
        return True

    # 从来没明确定过 → 问一次
    remembered = ""
    if session is not None and session.last_output:
        remembered = session.last_output
    default = remembered or cfg.output or cfg.default_output_for(cfg.task)
    print("\n[提示] 输出目录还没定 —— 这次输出到哪儿?")
    options = [
        f"default | 用这个目录({default})",
        "manual | 手动输入路径",
        "ask | 每次都问(这次先不跑)",
    ]
    action = ask_choice("请选择输出目录:", options, current="default")
    if action == "ask":
        print("[提示] 好,以后每次执行前都会问一次。")
        if session is not None:
            session.output_fixed = False
        return False
    if action == "manual":
        raw = input("请输入输出目录 (空回车取消): ").strip()
        if not raw:
            print("[取消]")
            return False
        cfg.output = str(expand_path(unescape_shell_path(raw)))
    else:
        cfg.output = default
    if session is not None:
        session.output_fixed = True
        session.last_output = cfg.output
    target = expand_path(cfg.output)
    if create:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"[错误] 建不了输出目录 {target}: {exc}")
            return False
    cfg.output = str(target)
    print(f"[输出] {cfg.output}")
    return True


def cmd_run(cfg: Config, browser: Browser, args: list[str],
            dry_run: bool = False, session: "Session | None" = None) -> None:
    """/run — 用当前状态执行(可加 --dry-run)。"""
    if any(a in ("--dry-run", "-n", "--preview") for a in args):
        dry_run = True
    if not prepare_input(cfg):
        return
    if not ensure_output(cfg, browser, session=session, create=not dry_run):
        return

    argv = build_full_argv(cfg)
    if dry_run:
        print_argv(argv, header="[dry-run] 将执行(未真正运行):")
        return
    run_argv(argv, dry_run=False)


def cmd_print_argv(cfg: Config, browser: Browser, args: list[str]) -> None:
    """/print-argv — 只打印当前配置对应的 argv,绝不执行。

    `/run --dry-run` 的别名;不需要模型服务也能验证整条链路。
    """
    if not prepare_input(cfg):
        return
    argv = build_full_argv(cfg)
    print_argv(argv, header="[dry-run] 将执行(未真正运行):")


def _run_pipeline(cfg: Config, browser: Browser,
                  session: "Session | None" = None, dry_run: bool = False) -> None:
    """流水线执行:裸路径设完输入后直接跑。

    和 /run 的区别:不再问「确认执行吗」—— 拖文件进来就是要跑。
    跑完回到面板,等下一个文件。
    """
    if not prepare_input(cfg):
        return
    if not ensure_output(cfg, browser, session=session, create=not dry_run):
        return
    argv = build_full_argv(cfg)
    if dry_run:
        print_argv(argv, header="[dry-run] 将执行(未真正运行):")
        return
    run_argv(argv, dry_run=False, confirm=False)


# ── 执行 / 动作 ─────────────────────────────────────────────────────────────
def skip_confirm() -> bool:
    """是否跳过「确认」直接执行(OCR_SHELL_YES=1)。"""
    return env_str("OCR_SHELL_YES", default="") not in ("", "0", "false", "no")


def preview_argv(argv: list[str]) -> None:
    """打印即将执行的完整 argv(带引号,空格安全,可直接复制)。"""
    print_argv(argv, header="\n[预览] 即将执行:")
    print(f"  共 {len(argv)} 个参数。")


def confirm_argv(argv: list[str]) -> bool:
    """预览 argv 并请用户确认。返回 True 表示可以执行。

    `OCR_SHELL_YES=1` 时跳过询问直接放行(「run without asking」模式)。
    """
    preview_argv(argv)
    if skip_confirm():
        print("  (OCR_SHELL_YES=1,跳过确认)")
        return True
    return ask_yes_no("\n确认执行上面这条命令吗?", default=True)


def run_argv(argv: list[str], dry_run: bool = False, confirm: bool = True) -> int:
    """执行(或只打印)argv,返回子进程退出码。

    dry_run=True 时只打印 argv,绝不执行 —— 这是没有模型服务时的验证入口。
    confirm=True 时先预览再询问确认。
    """
    if dry_run:
        print_argv(argv, header="[dry-run] 将执行(未真正运行):")
        return 0
    if confirm and not confirm_argv(argv):
        print("[取消] 已放弃执行。")
        return 0
    print_argv(argv, header="[运行] 正在执行:")
    try:
        import subprocess

        completed = subprocess.run(argv)
        return completed.returncode
    except FileNotFoundError as exc:
        sys.stderr.write(f"[错误] 找不到可执行文件: {exc}\n")
        return 127
    except KeyboardInterrupt:
        print("\n[中断] 已取消。")
        return 130


def action_preflight(dry_run: bool = False) -> int:
    """预检:依赖导入 + 模型服务连通性。"""
    print("\n=== 预检:依赖与模型服务 ===")
    rc = run_argv(build_argv("check_imports", []), dry_run=dry_run, confirm=False)
    if dry_run:
        return rc
    if rc != 0:
        print(f"[警告] check_imports 返回 {rc},依赖可能不完整。")

    host = env_str("OCR_HOST", "LMSTUDIO_IP", default="127.0.0.1")
    port = env_int("OCR_PORT", "LMSTUDIO_PORT", default=1234)
    model = env_str("OCR_MODEL", "LMSTUDIO_MODEL", default="dots.mocr")
    print()
    ok = probe_server(host, port, model)
    return 0 if ok else 1


def action_show_config() -> int:
    """打印当前配置:环境变量 + 各默认值。"""
    print("\n=== 当前配置 ===")
    print("\n[环境变量]")
    names = [
        "OCR_OUTPUT_DIR", "OCR_IMAGES_DIR", "OCR_HOST", "OCR_PORT", "OCR_MODEL",
        "OCR_DPI", "OCR_PREPROCESS", "OCR_SCALE", "OCR_MAX_SIDE", "OCR_PROMPT",
        "OCR_NUM_THREAD", "OCR_QUALITY", "OCR_SHELL_FORCE_TTY", "OCR_SHELL_YES",
        "LMSTUDIO_IP", "LMSTUDIO_PORT", "LMSTUDIO_MODEL", "OCR_VENV_PYTHON",
    ]
    any_env = False
    for name in names:
        value = os.environ.get(name)
        if value:
            print(f"  {name} = {value}")
            any_env = True
    if not any_env:
        print("  (没有设置任何 OCR_* 环境变量,全部用默认值)")

    print("\n[默认值]")
    defaults = [
        ("输入输出", f"输出目录 = {expand_path(env_str('OCR_OUTPUT_DIR', default='./note_md'))}"),
        ("服务端点", f"{env_str('OCR_HOST', 'LMSTUDIO_IP', default='127.0.0.1')}:"
                     f"{env_int('OCR_PORT', 'LMSTUDIO_PORT', default=1234)}"),
        ("模型名", env_str("OCR_MODEL", "LMSTUDIO_MODEL", default="dots.mocr")),
        ("DPI", env_int("OCR_DPI", default=150)),
        ("预处理", env_str("OCR_PREPROCESS", default="enhance")),
        ("scale", f"{env_float('OCR_SCALE', default=1.0):g}"),
        ("max-side", env_int("OCR_MAX_SIDE", default=1600)),
        ("prompt", env_str("OCR_PROMPT", default="prompt_layout_all_en")),
        ("num-thread", env_int("OCR_NUM_THREAD", default=1)),
        ("PDF 图片质量", env_int("OCR_QUALITY", default=80)),
    ]
    for label, value in defaults:
        print(f"  {label}: {value}")

    print("\n[可用 prompt 模式]")
    for mode in load_prompt_modes():
        print(f"  {mode:<24} {PROMPT_HINTS.get(mode, '')}")

    print("\n[脚本位置]")
    for name, path in SCRIPT_FILES.items():
        mark = "" if path.is_file() else "  ← 找不到!"
        print(f"  {name}: {path}{mark}")
    print(f"  python: {sys.executable}")
    print(f"  CWD: {Path.cwd()}")
    return 0


# ── 面板主循环 ──────────────────────────────────────────────────────────────
def make_session(path: Path | None = None, enabled: bool = True) -> Session:
    """造一个 Session。

    path=None → 用默认位置(环境变量 → XDG → ~/.config)。
    enabled=False → 不读不写(--no-session)。
    """
    if not enabled or path is None:
        return Session(path=None, enabled=False)
    return Session(path=path, enabled=True)


def setup_readline(history: list[str]) -> None:
    """把历史灌进 readline:↑/↓ 翻历史,Ctrl-R 反向搜索。

    没有 readline(精简 Python)就什么都不做 —— 不能因此崩掉。
    """
    if readline is None:
        return
    try:
        readline.clear_history()
        for item in history:
            readline.add_history(item)
    except Exception:
        pass


def push_history(history: list[str], text: str) -> None:
    """记一条命令(去重、限长)。"""
    if not text:
        return
    if history and history[-1] == text:
        return
    history.append(text)
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]
    if readline is not None:
        try:
            readline.add_history(text)
        except Exception:
            pass


def normalize_command(text: str) -> tuple[str, list[str]]:
    """把一行输入拆成 (命令名, 参数列表)。

    `/run --dry-run` → ("run", ["--dry-run"])
    `run`          → ("run", [])
    """
    parts = text.split()
    name = parts[0].lstrip("/").lower()
    return name, parts[1:]


def dispatch(cfg: Config, browser: Browser, line: str,
             dry_run: bool = False, session: "Session | None" = None) -> bool:
    """执行一条面板命令。返回 False 表示要退出面板。"""
    text = line.strip()
    if not text:
        return True

    name, args = normalize_command(text)

    # 退出
    if name in QUIT_WORDS:
        return False

    # 裸路径 → 设输入并立刻执行(流水线:拖文件进来就跑)
    if not text.startswith("/"):
        try:
            candidate = expand_path(unescape_shell_path(text))
        except Exception:
            candidate = Path(text)
        if candidate.exists():
            resolved = resolve_input(candidate)
            cfg.input = str(resolved)
            print(f"[已设置] 输入 → {resolved}")
            print("[流水线] 立即执行这次转换。")
            _run_pipeline(cfg, browser, session=session, dry_run=dry_run)
            return True

    handler = COMMANDS.get(name)
    if handler is None:
        print(f"[错误] 未知命令: {text}")
        print(f"       可用命令: {' '.join('/' + c for c in COMMANDS)}")
        print("       输入 /help 看全部命令。")
        if name.isdigit():
            print("       [提示] 面板模式用斜杠命令,例如 /input、/run。")
        return True

    if name == "task":
        cmd_task(cfg, browser, args)
    elif name == "input":
        cmd_input(cfg, browser, args)
    elif name == "output":
        cmd_output(cfg, browser, args, session=session)
    elif name == "dpi":
        cfg.dpi = ask_int("PDF 渲染分辨率 --dpi", cfg.dpi, minimum=1, maximum=1200)
        print(f"[已设置] DPI → {cfg.dpi}")
    elif name == "quality":
        cfg.quality = ask_int("--quality JPEG 质量(1-95)", cfg.quality,
                              minimum=1, maximum=95)
        print(f"[已设置] 质量 → {cfg.quality}")
    elif name == "start":
        cfg.start = ask_int("--start 起始页(1-based)", cfg.start,
                            minimum=1, maximum=100000)
        print(f"[已设置] 起始页 → {cfg.start}")
    elif name == "end":
        cfg.end = ask_int("--end 结束页(0=到末页)", cfg.end,
                          minimum=0, maximum=100000)
        print(f"[已设置] 结束页 → {cfg.end}")
    elif name == "max-side":
        cfg.max_side = ask_int("--max-side 最长边像素上限(0=不限制)", cfg.max_side,
                               minimum=0, maximum=16000)
        print(f"[已设置] max-side → {cfg.max_side}")
    elif name == "num-thread":
        cfg.num_thread = ask_int("--num-thread 并发页数", cfg.num_thread,
                                 minimum=1, maximum=64)
        print(f"[已设置] 并发页数 → {cfg.num_thread}")
    elif name == "scale":
        cfg.scale = ask_float("--scale 额外放大倍数", cfg.scale,
                              minimum=0.1, maximum=8.0)
        print(f"[已设置] scale → {cfg.scale:g}")
    elif name == "preprocess":
        options = [f"{m} | {m} — {desc}" for m, desc in PREPROCESS_MODES.items()]
        print("\n--preprocess 预处理强度:")
        print("  binarize 最接近印刷体,enhance 最保守(默认)。")
        cfg.preprocess = ask_choice("请选择预处理模式:", options, current=cfg.preprocess)
        print(f"[已设置] 预处理 → {cfg.preprocess}")
    elif name == "prompt":
        modes = load_prompt_modes()
        options = [f"{m} | {m} — {PROMPT_HINTS.get(m, 'dots.mocr 提示模式')}"
                   for m in modes]
        cfg.prompt = ask_choice("请选择 prompt 模式:", options, current=cfg.prompt)
        print(f"[已设置] 提示模式 → {cfg.prompt}")
    elif name == "deskew":
        cfg.deskew = ask_toggle("自动纠偏(关掉会加 --no-deskew)",
                                current=cfg.deskew, true_word="纠偏开", false_word="纠偏关")
        print(f"[已设置] 纠偏 → {on_off(cfg.deskew, '开', '关')}")
    elif name == "trim":
        cfg.trim = ask_toggle("裁白边(关掉会加 --no-trim)",
                              current=cfg.trim, true_word="裁边开", false_word="裁边关")
        print(f"[已设置] 裁白边 → {on_off(cfg.trim, '开', '关')}")
    elif name == "staging":
        cfg.keep_staging = ask_toggle("保留预处理中间图(开=加 --keep-staging)",
                                       current=cfg.keep_staging,
                                       true_word="保留", false_word="不留")
        print(f"[已设置] 中间图 → {on_off(cfg.keep_staging, '保留', '不留')}")
    elif name == "gray":
        cfg.gray = ask_toggle("输出灰度图(开=加 --gray)", current=cfg.gray,
                              true_word="灰度", false_word="彩色")
        print(f"[已设置] 灰度 → {on_off(cfg.gray, '开', '关')}")
    elif name == "prefix":
        cfg.prefix = ask_text("--prefix 文件名前缀(留空则用 PDF 文件名)", cfg.prefix)
        print(f"[已设置] 前缀 → {cfg.prefix or '(用 PDF 文件名)'}")
    elif name == "server":
        cmd_server(cfg, browser, args)
    elif name == "set":
        cmd_set(cfg, browser, args, session=session)
    elif name == "preset":
        cmd_preset(cfg, browser, args, session=session)
    elif name == "save":
        cmd_save(cfg, browser, args, session=session)
    elif name == "reload":
        cmd_reload(cfg, browser, args, session=session)
    elif name == "history":
        cmd_history(cfg, browser, args, session=session)
    elif name == "reset":
        cmd_reset(cfg, browser, args)
    elif name == "run":
        cmd_run(cfg, browser, args, dry_run=dry_run, session=session)
    elif name == "print-argv":
        cmd_print_argv(cfg, browser, args)
    elif name == "preflight":
        action_preflight()
    elif name == "config":
        action_show_config()
    elif name == "help":
        cmd_help(cfg, browser, args)
    return True


def panel_main(dry_run: bool = False, clear: bool = True,
               session: "Session | None" = None) -> int:
    """面板主循环:显示全部设置,接受斜杠命令。"""
    cfg = Config.from_env()
    if session is not None:
        cfg = session.load(cfg)
    browser = Browser()
    default_dry = dry_run
    history = list(session.history) if session is not None else []
    setup_readline(history)

    def save_and_leave(reason: str) -> int:
        """退出前把当前设置写回会话文件。"""
        if session is not None and session.enabled:
            if session.save(cfg, history=history):
                print(f"[已保存] 会话 → {session.path}")
            else:
                print("[警告] 会话没存上,看上面的提示。")
        print(reason)
        return 0

    render_panel(cfg, clear=clear, session=session, recent=history)
    while True:
        try:
            line = input("> ")
        except EOFError:
            return save_and_leave("\n[退出] 收到 EOF(Ctrl-D)。")
        except KeyboardInterrupt:
            # Ctrl-C 在主提示符上 → 直接退出(和 /quit 一样),设置自动保存。
            # 主提示符是「闲着没事」的状态,这时候按 Ctrl-C 的意图很明确
            # 就是想走;真要取消某个操作的话,那个子提示自己会吃到那个 Ctrl-C。
            print()
            return save_and_leave("\n[退出] Ctrl-C,已退出。")
        text = line.strip()
        if text:
            push_history(history, text)
            if session is not None:
                session.history = list(history)
        try:
            keep = dispatch(cfg, browser, line, dry_run=default_dry, session=session)
        except EOFError:
            return save_and_leave("\n[退出] 收到 EOF(Ctrl-D)。")
        except KeyboardInterrupt:
            # Ctrl-C 在子提示里 → 只取消这次操作,回到面板
            print("\n[提示] 已取消这次操作。")
            keep = True
        if not keep:
            return save_and_leave("再见。")
        render_panel(cfg, clear=clear, session=session, recent=history)


# ── 非交互入口 ──────────────────────────────────────────────────────────────
def exec_target(target: str, args: list[str], dry_run: bool) -> int:
    """--exec:直接转发给底层脚本。

    非交互模式没有菜单,也就没有「预览 + 确认」——
    用户已经用命令行把参数说清楚了,直接跑。
    """
    if target not in EXEC_TARGETS:
        sys.stderr.write(f"[错误] 未知的 --exec 目标: {target}\n")
        sys.stderr.write(f"       可用: {', '.join(sorted(EXEC_TARGETS))}\n")
        return 2
    # `--` 之后的一切都会原样透传给目标脚本,所以 `--dry-run` 写在那里
    # 不会被本脚本消费,只会被当成目标脚本的未知参数。提醒一下。
    if "--dry-run" in args and not dry_run:
        sys.stderr.write(
            "[提示] `--dry-run` 写在了 `--` 后面,会被原样传给目标脚本。\n"
            "       本脚本的 --dry-run 要写在 `--` 前面:\n"
            f"         ocr_shell.py --exec {target} --dry-run -- <参数...>\n"
        )
    argv = build_argv(target, args)
    return run_argv(argv, dry_run=dry_run, confirm=False)


def split_passthrough(argv: list[str]) -> tuple[list[str], list[str]]:
    """把 `--` 之后的参数切出来。

    argparse 自己不认 `--` 之后的内容,所以必须在喂给它之前先切掉。
    返回 (给 argparse 的部分, 透传的部分)。
    """
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1:]
    return list(argv), []


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ocr_shell",
        description="OCR 工具链的交互式外壳:面板式配置,或用 --exec 直接转发给底层脚本。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  ocr_shell.py                      # 进入交互式面板\n"
            "  ocr_shell.py --no-clear           # 面板不屏\n"
            "  ocr_shell.py --exec note_to_markdown -- note.jpg -o out/\n"
            "  ocr_shell.py --exec note_to_markdown --dry-run -- note.jpg -o out/\n"
            "  ocr_shell.py --exec pdf_to_images -- doc.pdf -o imgs/\n"
            "  ocr_shell.py --exec parser -- doc.pdf\n"
            "  ocr_shell.py --exec check_imports\n"
            "  ocr_shell.py --exec smoke_test -- --check-only\n"
            "  ocr_shell.py --list-prompts\n"
            "  ocr_shell.py --session /tmp/ocr-session.json   # 指定会话文件\n"
            "  ocr_shell.py --no-session                       # 不读不写会话文件\n"
            "\n"
            "面板里的命令: /task /input /output /dpi /quality /start /end\n"
            "              /preprocess /prompt /deskew /trim /staging /scale\n"
            "              /max-side /num-thread /gray /prefix /server\n"
            "              /set /preset /run /print-argv /save /reload\n"
            "              /history /reset /preflight /config /help /quit\n"
            "\n"
            "stdin 不是终端时不会进入交互面板(避免 CI 卡死),此时必须用 --exec。\n"
            "设 OCR_SHELL_FORCE_TTY=1 可以强制走交互面板(测试用)。\n"
        ),
    )
    parser.add_argument(
        "--exec",
        dest="exec_target",
        choices=sorted(EXEC_TARGETS),
        help="非交互模式:直接执行指定目标,`--` 之后的参数原样透传",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的 argv,不真的运行(--exec 下直接打印;面板里 /run 也不执行)",
    )
    parser.add_argument(
        "--list-prompts",
        action="store_true",
        help="打印 dots.mocr 支持的 prompt 模式名,一行一个",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="面板模式下不清屏(默认在终端里清屏,管道里自动不清)",
    )
    parser.add_argument(
        "--session",
        dest="session",
        metavar="PATH",
        default=None,
        help="会话文件路径(覆盖 OCR_SESSION_FILE / XDG_CONFIG_HOME / ~/.config 的默认位置)",
    )
    parser.add_argument(
        "--no-session",
        dest="no_session",
        action="store_true",
        help="不读也不写会话文件(每次都是全新默认设置)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    head, passthrough = split_passthrough(raw_argv)
    args = parse_args(head)

    if args.list_prompts:
        for mode in load_prompt_modes():
            print(mode)
        return 0

    if args.exec_target:
        return exec_target(args.exec_target, passthrough, args.dry_run)

    if not is_interactive():
        sys.stderr.write(
            "[错误] stdin 不是终端,已跳过交互面板(防止 CI 卡死)。\n"
            "       请用 --exec <目标> -- <参数...> 直接执行,例如:\n"
            "         python ocr/scripts/ocr_shell.py --exec note_to_markdown -- note.jpg -o out/\n"
            "       设 OCR_SHELL_FORCE_TTY=1 可强制进入交互模式。\n"
        )
        return 2

    # 会话文件:命令行 > 环境变量 > 默认位置;--no-session 完全关掉。
    #
    # OCR_SHELL_FORCE_TTY=1 表示「这个面板是被脚本驱动的」(测试 / 管道),
    # 这时候不应该继承用户交互会话里的状态 —— 否则一个残留的
    # ~/.config/ocr/session.json 会让脚本化跑出来的结果不可预测。
    # 除非用户明确指定了会话文件(OCR_SESSION_FILE 或 --session)。
    # OCR_NO_SESSION=1 是显式关掉会话(测试里用来保证可重复)。
    forced_tty = env_str("OCR_SHELL_FORCE_TTY", default="") not in ("", "0", "false", "no")
    no_session_env = env_str("OCR_NO_SESSION", default="") not in ("", "0", "false", "no")
    explicit_session = bool(args.session) or bool(env_str("OCR_SESSION_FILE", default=""))
    session_path: Path | None = None
    if not args.no_session:
        if args.session:
            session_path = expand_path(args.session)
        elif env_str("OCR_SESSION_FILE", default=""):
            session_path = default_session_path()
        elif forced_tty:
            session_path = None
        else:
            session_path = default_session_path()
    use_session = not args.no_session and session_path is not None
    if args.no_session or no_session_env:
        use_session = False
    elif forced_tty and not explicit_session:
        use_session = False

    try:
        # 交互模式下 --dry-run 也生效:/run 只打印 argv,不真的跑。
        return panel_main(dry_run=args.dry_run, clear=not args.no_clear,
                          session=make_session(session_path, enabled=use_session))
    except (KeyboardInterrupt, EOFError):
        print("\n[中断] 已取消。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
