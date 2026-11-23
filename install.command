#!/bin/bash
# macOS：安装已构建的解环工坊合并版
set -e

BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
SRC="$(cd "$(dirname "$0")" && pwd)"
ZIP="$SRC/dist/ring-workshop/ua_game_kit-0.3.15.zip"

if [ ! -f "$ZIP" ]; then
    printf '%s\n' '未找到合并版安装包。请使用合并版 ZIP，或按 README 从源码构建。' >&2
    exit 1
fi

"$BLENDER" -b --command extension install-file -r user_default "$ZIP"

printf '%s\n' '请在 Blender 偏好设置中停用旧搭建器和旧买量工坊，再启用「解环工坊」。'
echo ""
read -n 1 -s -r -p "按任意键关闭..."
