#!/bin/bash
# OCR 交互式外壳 —— Finder 里双击本文件即可运行。
#
# 会打开一个菜单,让你自己挑:
#   · 输入(图片 / PDF / 文件夹)—— 浏览目录挑选,或手动输入任意路径
#   · 输出目录 —— 默认值、浏览挑选,或手动输入任意路径
#   · 全部参数 —— DPI、预处理强度、提示模式、服务器地址/端口/模型名……
#
# 本文件解析出的一切路径都基于自身位置(BASH_SOURCE),不写死任何目录。
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$BIN_DIR/ocr"

if [ ! -f "$LAUNCHER" ]; then
  echo "[错误] 找不到启动器: $LAUNCHER"
  echo "按回车关闭这个窗口。"
  read -r _ </dev/tty
  exit 1
fi
# 从 zip / 拷贝过来时可能丢了可执行位
[ -x "$LAUNCHER" ] || chmod +x "$LAUNCHER" 2>/dev/null || true

"$LAUNCHER"

rc=$?
echo
if [ "$rc" -ne 0 ]; then
  echo "[错误] 退出码 $rc"
fi
echo "按回车关闭这个窗口。"
read -r _ </dev/tty
