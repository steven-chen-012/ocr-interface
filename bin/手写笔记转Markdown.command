#!/bin/bash
# 手写笔记转 Markdown —— Finder 里双击本文件即可运行。
# 也可以把图片 / PDF 直接拖到本文件上。
#
# 本文件解析出的一切路径都基于自身位置(BASH_SOURCE),不写死任何目录:
#   <包目录>/bin/手写笔记转Markdown.command
#     ├─ ./nmd                       ← 启动器(负责找解释器)
#     └─ ../scripts/note_to_markdown.py  ← 真正的转换程序
#
# 输出目录优先级:
#   1. $OCR_OUTPUT_DIR
#   2. 当前工作目录下的 note_md/
#   3. 输入文件所在目录下的 note_md/
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$BIN_DIR/.." && pwd)"
NMD="$BIN_DIR/nmd"

if [ ! -f "$NMD" ]; then
  echo "[错误] 找不到启动器: $NMD"
  echo "按回车关闭这个窗口。"
  read -r _ </dev/tty
  exit 1
fi
# 从 zip / 拷贝过来时可能丢了可执行位
[ -x "$NMD" ] || chmod +x "$NMD" 2>/dev/null || true

# macOS 终端把带空格的路径插入成 `扫描文稿\ 2.pdf`,需要还原转义。
unescape() {
  printf '%s' "$1" | sed -e 's/\\\( \)/\1/g' -e "s/\\\\'/'/g" -e 's/\\"/"/g'
}

if [ "$#" -gt 0 ]; then
  # Finder 里把文件拖到本图标上:路径已经是真实路径,不用还原
  TARGET="$1"
else
  echo "请把要转换的手写照片或 PDF 拖进这个终端窗口，然后回车："
  read -r TARGET
  TARGET="$(unescape "$TARGET")"
fi

TARGET="${TARGET%"${TARGET##*[![:space:]]}"}"   # 去掉首尾空白

if [ -z "$TARGET" ] || [ ! -e "$TARGET" ]; then
  echo "[错误] 找不到文件: ${TARGET:-（空）}"
  echo
  echo "按回车关闭这个窗口。"
  read -r _ </dev/tty
  exit 1
fi

# 输出目录:环境变量 > CWD/note_md > 输入文件旁边/note_md(全部相对运行位置)
if [ -n "${OCR_OUTPUT_DIR:-}" ]; then
  OUT="$OCR_OUTPUT_DIR"
elif [ -n "${PWD:-}" ]; then
  OUT="$PWD/note_md"
else
  OUT="$(cd "$(dirname "$TARGET")" && pwd)/note_md"
fi

if "$NMD" "$TARGET" -o "$OUT"; then
  echo
  echo "===== 产物在: $OUT ====="
  ls -1 "$OUT"
else
  rc=$?
  echo
  echo "[错误] 转换失败(退出码 $rc)"
  echo "提示:如果报缺依赖,先在 $PKG_DIR 下建 venv 并 pip install -r requirements.txt"
fi

echo
echo "按回车关闭这个窗口。"
read -r _ </dev/tty