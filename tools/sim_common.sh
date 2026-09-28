#!/usr/bin/env bash
# 共享辅助函数，供 start_serial_sim.sh / start_can_sim.sh 使用。
# 该文件不应单独执行。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"
WEB_HOST="127.0.0.1"
WEB_PORT="5000"
WEB_URL="http://$WEB_HOST:$WEB_PORT"

# 检查虚拟环境与关键依赖
check_venv() {
    if [ ! -x "$PYTHON" ]; then
        echo "[错误] 未找到虚拟环境 .venv"
        echo ""
        echo "请先执行初始化："
        echo "  python3 -m venv .venv"
        echo "  .venv/bin/python -m pip install -r requirements.txt"
        echo ""
        exit 1
    fi

    if ! "$PYTHON" -c "import serial" >/dev/null 2>&1; then
        echo "[错误] 缺少 pyserial，请安装："
        echo "  .venv/bin/python -m pip install pyserial"
        echo ""
        exit 1
    fi

    if ! "$PYTHON" -c "import flask" >/dev/null 2>&1; then
        echo "[错误] 缺少 Flask，请安装："
        echo "  .venv/bin/python -m pip install -r requirements.txt"
        echo ""
        exit 1
    fi
}

# 检查 curl（用于等待 Web 就绪与调用 API）
check_curl() {
    if ! command -v curl >/dev/null 2>&1; then
        echo "[错误] 缺少 curl，请安装："
        echo "  sudo apt install curl"
        echo ""
        exit 1
    fi
}

# 检测可用的图形终端模拟器（按优先级）
detect_terminal() {
    if command -v gnome-terminal >/dev/null 2>&1; then
        echo "gnome-terminal"
    elif command -v konsole >/dev/null 2>&1; then
        echo "konsole"
    elif command -v xterm >/dev/null 2>&1; then
        echo "xterm"
    else
        echo ""
    fi
}

# 在独立终端窗口启动命令；无图形终端时后台运行并打印日志位置
# 用法：launch_terminal <标题> <命令...>
launch_terminal() {
    local title="$1"; shift
    local cmd="$*"
    local term
    term="$(detect_terminal)"

    case "$term" in
        gnome-terminal)
            gnome-terminal --title="$title" -- bash -c "$cmd; exec bash" &
            ;;
        konsole)
            konsole --title "$title" -e bash -c "$cmd; exec bash" &
            ;;
        xterm)
            xterm -T "$title" -e bash -c "$cmd; exec bash" &
            ;;
        *)
            local safe_name
            safe_name="$(echo "$title" | tr ' ' '_' | tr -cd '[:alnum:]_-')"
            local logfile="$ROOT_DIR/logs/${safe_name}_$(date +%H%M%S).log"
            mkdir -p "$ROOT_DIR/logs"
            echo "[提示] 未检测到图形终端，改为后台运行：$title"
            echo "       日志文件：$logfile"
            nohup bash -c "$cmd" > "$logfile" 2>&1 &
            ;;
    esac
}

# 等待 Web 服务就绪（最多约 15 秒）
wait_for_web() {
    local attempt=1
    local max=60
    while [ "$attempt" -le "$max" ]; do
        if curl -fsS "$WEB_URL/api/status" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.25
        attempt=$((attempt + 1))
    done
    echo "[错误] Web 服务启动超时（$WEB_URL）"
    return 1
}

# 打开浏览器
open_browser() {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$WEB_URL" >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then
        open "$WEB_URL" >/dev/null 2>&1 &
    else
        echo "[提示] 请手动打开浏览器访问：$WEB_URL"
    fi
}

# 自动调用 API 启动 Serial Live
start_serial_live_api() {
    curl -sS -X POST "$WEB_URL/api/start_live_serial" \
        -H 'Content-Type: application/json' \
        -d '{"port": "/tmp/rmcv_validator", "baudrate": 9600}'
}

# 自动调用 API 启动 CAN Live
start_can_live_api() {
    curl -sS -X POST "$WEB_URL/api/start_live" \
        -H 'Content-Type: application/json' \
        -d '{"interface": "vcan0"}'
}
