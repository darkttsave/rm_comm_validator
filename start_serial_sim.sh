#!/usr/bin/env bash
# 一键串口模拟：
#   创建虚拟串口对 -> 启动 Serial Mock -> 启动 Web -> 自动 Live -> 打开浏览器
#
# 用户只需执行：./start_serial_sim.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tools/sim_common.sh"

echo "=== RM Communication Validator - Serial 串口模拟 ==="
echo ""

check_venv
check_curl

# 1. 检查 socat
if ! command -v socat >/dev/null 2>&1; then
    echo "[错误] 未找到 socat，请先安装："
    echo "  sudo apt install socat"
    echo ""
    exit 1
fi

# 2. 清理旧的虚拟串口与残留进程
pkill -f "socat.*rmcv" 2>/dev/null || true
rm -f /tmp/rmcv_mock /tmp/rmcv_validator

# 3. 启动串口桥接（Serial Bridge）
echo "[1/4] 启动串口桥接（Serial Bridge）..."
launch_terminal "RM Validator - Serial Bridge" \
    "socat -d -d pty,raw,echo=0,link=/tmp/rmcv_mock pty,raw,echo=0,link=/tmp/rmcv_validator"

# 等待虚拟串口创建完成
for _ in $(seq 1 50); do
    if [ -e /tmp/rmcv_mock ] && [ -e /tmp/rmcv_validator ]; then
        break
    fi
    sleep 0.2
done
if [ ! -e /tmp/rmcv_mock ] || [ ! -e /tmp/rmcv_validator ]; then
    echo "[错误] 虚拟串口创建失败（/tmp/rmcv_mock 或 /tmp/rmcv_validator 未出现）"
    echo "       请查看 'RM Validator - Serial Bridge' 终端输出。"
    exit 1
fi

# 4. 启动 Serial Mock
echo "[2/4] 启动 Serial Mock（Tongji reference, normal, 10 Hz）..."
launch_terminal "RM Validator - Serial Mock" \
    "cd '$ROOT_DIR' && '$PYTHON' tools/mock_serial_node/mock_gimbal.py /tmp/rmcv_mock --mode normal --rate 10"

# 5. 启动 Web
echo "[3/4] 启动 Web..."
launch_terminal "RM Validator - Web" \
    "cd '$ROOT_DIR' && '$PYTHON' main.py web --protocol protocols/tongji_gimbal_serial.yaml --host 127.0.0.1 --port 5000"

# 6. 等待 Web 就绪
echo "[4/4] 等待 Web 就绪..."
if ! wait_for_web; then
    echo "[错误] Web 服务未能启动，请查看 'RM Validator - Web' 终端输出。"
    exit 1
fi

# 7. 自动启动 Serial Live
echo "自动启动 Serial Live（port=/tmp/rmcv_validator, baudrate=9600）..."
RESULT="$(start_serial_live_api)"
echo "Live 启动结果：$RESULT"

# 8. 打开浏览器
open_browser

echo ""
echo "=== 完成 ==="
echo "浏览器已打开：$WEB_URL"
echo "如果页面尚未显示数据，请稍候几秒或刷新页面。"
echo "关闭方式：在各个终端窗口按 Ctrl+C。"
