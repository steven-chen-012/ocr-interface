#!/usr/bin/env python3
"""
test_ocr_shell.py — ocr_shell.py 的冒烟测试(不需要模型服务器)。

覆盖两块:
  A. 非交互模式:`--exec` / `--dry-run` / `--list-prompts` / `--help`
  B. 面板模式:斜杠命令改设置、面板重绘、`/run --dry-run` 产出的 argv

面板模式用管道驱动(OCR_SHELL_FORCE_TTY=1),所有执行都走 --dry-run,
所以整个测试不需要模型服务、也不会真的跑 OCR。

运行:
    python ocr/scripts/test_ocr_shell.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "ocr_shell.py"


def run_shell(args: list[str], stdin: str = "", env_extra: dict | None = None,
              cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
        timeout=60,
    )


def run_panel(lines: list[str], cwd: Path | None = None,
             session_file: str | None = None) -> subprocess.CompletedProcess:
    """在面板模式里喂一串命令。

    session_file 用来隔离会话文件,免得测试污染用户真实的 ~/.config/ocr/。
    """
    env = {"OCR_SHELL_FORCE_TTY": "1"}
    if session_file:
        env["OCR_SESSION_FILE"] = session_file
    else:
        env["OCR_NO_SESSION"] = "1"
    return run_shell([], stdin="\n".join(lines) + "\n",
                     env_extra=env, cwd=cwd)


def argv_line(output: str, needle: str = "note_to_markdown.py") -> str:
    """从输出里取出真正要执行的 argv 那一行。

    注意:面板和提示语里也会出现 "--no-deskew" 这类字样(比如
    "/deskew 自动纠偏开关"),所以断言必须只看 argv 行,
    否则会把提示文案误判成参数。
    """
    for line in output.splitlines():
        if needle in line and "--" in line:
            return line
    return ""


def check(name: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not condition else ""))
    return condition


# ── A. 非交互模式 ────────────────────────────────────────────────────────────
def test_exec_mode() -> bool:
    print("\nA) 非交互 --exec 模式")
    passed = True

    cases = [
        ("note_to_markdown", ["note.jpg", "-o", "out/"], "note_to_markdown.py"),
        ("pdf_to_images", ["doc.pdf", "-o", "imgs/"], "pdf_to_images.py"),
        ("parser", ["doc.pdf"], "-m dots_mocr.parser"),
        ("check_imports", [], "check_imports.py"),
        ("smoke_test", [], "smoke_test.py"),
    ]
    for target, extra, needle in cases:
        r = run_shell(["--exec", target, "--dry-run", "--", *extra])
        out = r.stdout + r.stderr
        passed &= check(f"{target} 退出码 0", r.returncode == 0, f"got {r.returncode}")
        passed &= check(f"{target} argv 含 {needle}", needle in out)
        passed &= check(f"{target} 透传参数",
                        all(a in out for a in extra) if extra else True)

    r = run_shell(["--list-prompts"])
    modes = [m for m in r.stdout.split() if m.startswith("prompt_")]
    passed &= check("--list-prompts 退出码 0", r.returncode == 0)
    passed &= check("--list-prompts 列出模式", len(modes) >= 8, f"got {len(modes)}")
    passed &= check("--list-prompts 含 prompt_ocr", "prompt_ocr" in modes)

    r = run_shell(["--help"])
    passed &= check("--help 退出码 0", r.returncode == 0)

    # 非 TTY 时必须拒绝进面板,否则 CI 会挂住
    r = run_shell([], stdin="")
    passed &= check("非 TTY 退出码为 2", r.returncode == 2, f"got {r.returncode}")
    passed &= check("非 TTY 提示用 --exec", "--exec" in (r.stdout + r.stderr))
    return passed


# ── B. 面板模式 ──────────────────────────────────────────────────────────────
def test_panel() -> bool:
    print("\nB) 面板模式")
    passed = True

    with tempfile.TemporaryDirectory() as tmp:
        sample = Path(tmp) / "sample.pdf"
        sample.write_bytes(b"%PDF-1.4\n% test fixture\n")

        # 面板本身
        r = run_panel(["/quit"], cwd=Path(tmp))
        out = r.stdout + r.stderr
        passed &= check("画出面板", "OCR" in out and "╭" in out)
        passed &= check("面板列出任务", "note_to_markdown" in out)
        passed &= check("面板列出可用命令", "/input" in out and "/run" in out)
        passed &= check("/quit 干净退出", r.returncode == 0, f"got {r.returncode}")

        # 改一个数值,面板应重绘并反映新值
        r = run_panel(["/dpi", "300", "/quit"], cwd=Path(tmp))
        out = r.stdout + r.stderr
        passed &= check("/dpi 生效", "300" in out)
        passed &= check("/dpi 后重绘面板", out.count("╭") >= 2, f"panels={out.count('╭')}")

        # 设置输入 + 空跑,看 argv。
        # 先用 /output 固定输出目录 —— 否则第一次执行会问「输出到哪儿」,
        # 把后面的输入行吃掉了。
        r = run_panel(["/output", "2", "out_dir",
                       "/input", "1", "sample.pdf", "/run --dry-run", "/quit"],
                      cwd=Path(tmp))
        out = r.stdout + r.stderr
        cmd = argv_line(out)
        passed &= check("/run --dry-run 产出 argv", bool(cmd), out[-400:])
        passed &= check("argv 含输入路径", "sample.pdf" in cmd, cmd)
        passed &= check("argv 含 note_to_markdown", "note_to_markdown.py" in cmd, cmd)
        passed &= check("默认不带 --no-deskew", "--no-deskew" not in cmd, cmd)
        passed &= check("默认不带 --no-trim", "--no-trim" not in cmd, cmd)
        passed &= check("默认不带 --keep-staging", "--keep-staging" not in cmd, cmd)

        # 关掉纠偏 / 裁边 / 保留中间图 → 应出现对应开关
        r = run_panel(["/output", "2", "out_dir",
                       "/deskew", "n", "/trim", "n", "/staging", "y",
                       "/input", "1", "sample.pdf", "/run --dry-run", "/quit"],
                      cwd=Path(tmp))
        cmd = argv_line(r.stdout + r.stderr)
        passed &= check("关纠偏 → --no-deskew", "--no-deskew" in cmd, cmd)
        passed &= check("关裁边 → --no-trim", "--no-trim" in cmd, cmd)
        passed &= check("留中间图 → --keep-staging", "--keep-staging" in cmd, cmd)

        # 第一次执行时输出目录还没定 → 应该问一次(用裸路径触发流水线)
        r = run_panel(["sample.pdf", "1", "/quit"], cwd=Path(tmp))
        out = r.stdout + r.stderr
        passed &= check("输出未定时会问", "输出目录还没定" in out)

        # 预处理编号菜单
        r = run_panel(["/preprocess", "4", "/quit"], cwd=Path(tmp))
        out = r.stdout + r.stderr
        passed &= check("/preprocess 弹编号菜单", "请选择预处理模式" in out)
        passed &= check("/preprocess 选中 binarize", "binarize" in out)

        # 提示模式编号菜单
        r = run_panel(["/prompt", "3", "/quit"], cwd=Path(tmp))
        out = r.stdout + r.stderr
        passed &= check("/prompt 弹编号菜单", "prompt 模式" in out)
        passed &= check("/prompt 列出真实模式", "prompt_layout_all_en" in out)

        # 未知命令要给出提示
        r = run_panel(["/nope", "/quit"], cwd=Path(tmp))
        out = r.stdout + r.stderr
        passed &= check("未知命令有报错", "未知命令" in out)
        passed &= check("未知命令列出可用命令", "/input" in out.split("未知命令")[-1])

        # 空回车只重绘,不改状态
        r = run_panel(["", "/quit"], cwd=Path(tmp))
        passed &= check("空行重绘面板", r.stdout.count("╭") >= 2)

        # 裸路径 = 设置输入(并且按流水线语义立即执行)
        r = run_panel(["sample.pdf", "/quit"], cwd=Path(tmp))
        passed &= check("裸路径可设为输入", "sample.pdf" in (r.stdout + r.stderr))
        passed &= check("裸路径触发流水线执行", "流水线" in (r.stdout + r.stderr))

        # /server 子菜单 + 主机名校验
        r = run_panel(["/server", "1", "1", "/quit"], cwd=Path(tmp))
        passed &= check("/server 拒绝裸数字地址", "纯数字" in (r.stdout + r.stderr))

        # /help
        r = run_panel(["/help", "/quit"], cwd=Path(tmp))
        passed &= check("/help 有输出", len(r.stdout) > 0)

        # 没有输入时 /run 要拒绝
        r = run_panel(["/run", "/quit"], cwd=Path(tmp))
        passed &= check("无输入时 /run 拒绝", "输入" in (r.stdout + r.stderr))

        # /set 设置页
        r = run_panel(["/set", "/quit"], cwd=Path(tmp))
        out = r.stdout + r.stderr
        passed &= check("/set 打开设置页", "=== 设置 ===" in out)
        passed &= check("/set 有分组", "图片质量" in out and "预处理" in out)

        # /preset 菜单
        r = run_panel(["/preset", "/quit"], cwd=Path(tmp))
        out = r.stdout + r.stderr
        passed &= check("/preset 打开预设菜单", "=== 预设 ===" in out)
        passed &= check("/preset 列出内置预设", "handwriting" in out)

    return passed


# ── D. 会话持久化 ────────────────────────────────────────────────────────────
def test_session_persistence() -> bool:
    print("\nD) 会话持久化")
    passed = True

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sample = tmp_path / "sample.pdf"
        sample.write_bytes(b"%PDF-1.4\n% test fixture\n")
        session = tmp_path / "session.json"

        # 改 DPI 后退出 → 应自动保存
        r = run_panel(["/dpi", "300", "/quit"], cwd=tmp_path, session_file=str(session))
        passed &= check("退出时保存会话", session.is_file())
        if session.is_file():
            import json
            data = json.loads(session.read_text(encoding="utf-8"))
            passed &= check("会话文件是合法 JSON", isinstance(data, dict))
            passed &= check("会话文件记下 DPI=300",
                            data.get("config", {}).get("dpi") == 300,
                            str(data.get("config", {}).get("dpi")))

        # 重开 → DPI 应恢复
        r = run_panel(["/quit"], cwd=tmp_path, session_file=str(session))
        out = r.stdout + r.stderr
        passed &= check("重开后恢复 DPI=300", "300" in out)
        passed &= check("面板显示会话已载入", "已载入" in out)

        # --no-session 不读文件
        r = run_shell(["--no-session"], stdin="/quit\n",
                      env_extra={"OCR_SHELL_FORCE_TTY": "1"}, cwd=tmp_path)
        out = r.stdout + r.stderr
        passed &= check("--no-session 不载入", "未启用" in out)

        # --session 指定路径
        other = tmp_path / "other.json"
        r = run_shell(["--session", str(other)], stdin="/quit\n",
                      env_extra={"OCR_SHELL_FORCE_TTY": "1"}, cwd=tmp_path)
        passed &= check("--session 生效", str(other) in (r.stdout + r.stderr))

        # 坏掉的会话文件不能崩
        bad = tmp_path / "bad.json"
        bad.write_text("NOT VALID JSON {{{", encoding="utf-8")
        r = run_shell([], stdin="/quit\n",
                      env_extra={"OCR_SHELL_FORCE_TTY": "1",
                                 "OCR_SESSION_FILE": str(bad)}, cwd=tmp_path)
        out = r.stdout + r.stderr
        passed &= check("坏会话文件有警告", "警告" in out)
        passed &= check("坏会话文件不崩", r.returncode == 0, f"got {r.returncode}")

    return passed


def test_no_hardcoded_paths() -> bool:
    print("\nC) 源码硬编码检查")
    text = SCRIPT.read_text(encoding="utf-8")
    # 注意:这些模式不能直接写成字面量 —— CI 的 lint 作业会扫描所有 .py 文件,
    # 本文件自己反而会被判定为「含硬编码路径」。所以用拼接的方式构造。
    prefixes = ("/Us" + "ers/", "/ho" + "me/", "/mn" + "t/", "/op" + "t/", "/priv" + "ate/")
    bad = [p for p in prefixes if p in text]
    return check("无硬编码绝对路径", not bad, f"found {bad}")


# ── E. Ctrl-C 行为 ──────────────────────────────────────────────────────────
def test_ctrl_c() -> bool:
    print("\nD) Ctrl-C 行为")
    passed = True

    # 直接驱动 panel_main,注入 KeyboardInterrupt
    import builtins
    sys.path.insert(0, str(SCRIPT.parent))
    sys.path.insert(0, str(SCRIPT.parent.parent))
    import importlib
    shell = importlib.import_module("scripts.ocr_shell")

    def drive(responses):
        """responses: 依次给 input() 的返回值;None 表示抛 KeyboardInterrupt。"""
        seq = list(responses)
        def fake_input(prompt=""):
            r = seq.pop(0)
            if r is None:
                raise KeyboardInterrupt
            return r
        orig = builtins.input
        builtins.input = fake_input
        try:
            return shell.panel_main(dry_run=True, clear=False, session=None)
        finally:
            builtins.input = orig

    # 主提示符按 Ctrl-C → 退出
    rc = drive([None])
    passed &= check("主提示符 Ctrl-C 退出", rc == 0, f"got {rc}")

    # 子提示里按 Ctrl-C → 只取消这次操作,回到面板,然后 /quit 退出
    rc = drive(["/dpi", None, "/quit"])
    passed &= check("子提示 Ctrl-C 只取消操作", rc == 0, f"got {rc}")

    # Ctrl-D(EOF)→ 退出
    def fake_eof(prompt=""):
        raise EOFError
    orig = builtins.input
    builtins.input = fake_eof
    try:
        rc = shell.panel_main(dry_run=True, clear=False, session=None)
    finally:
        builtins.input = orig
    passed &= check("Ctrl-D 退出", rc == 0, f"got {rc}")

    return passed


def main() -> int:
    if not SCRIPT.is_file():
        print(f"[FAIL] 找不到 {SCRIPT}")
        return 1

    print("ocr_shell 冒烟测试")
    passed = True
    passed &= test_exec_mode()
    passed &= test_panel()
    passed &= test_session_persistence()
    passed &= test_ctrl_c()
    passed &= test_no_hardcoded_paths()

    print()
    if passed:
        print("全部通过 ✅")
        return 0
    print("有测试失败 ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())
