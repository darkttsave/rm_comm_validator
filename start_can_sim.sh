#!/usr/bin/env bash
# 一键 CAN 模拟：
#   确保 vcan0 -> 编译并启动 CAN Mock -> 启动 Web -> 自动 Live -> 打开浏览器
#
# 用户只需执行：./start_can_sim.sh
# 创建 vcan0 需要 sudo 时，系统会正常要求输入一次 sudo 密码。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tools/sim_common.sh"

echo "=== RM Communication Validator - CAN 模拟 ==="
echo ""

check_venv
check_curl

# 1. 检查 Linux
if [ "$(uname -s)" != "Linux" ]; then
    echo "[错误] CAN 模拟需要 Linux + SocketCAN 支持。"
    exit 1
fi

# 2. 检查 ip 命令
if ! command -v ip >/dev/null 2>&1; then
    echo "[错误] 缺少 ip 命令，请安装 iproute2："
    echo "  sudo apt install iproute2"
    echo ""
    exit 1
fi

# 3. 确保 vcan0 存在并处于 up 状态
echo "[1/4] 检查 vcan0 接口..."
if ip link show vcan0 >/dev/null 2>&1; then
    if ip link show vcan0 | grep -qE "state DOWN|state UNKNOWN"; then
        echo "      vcan0 已存在但未启动，正在启动..."
        sudo ip link set up vcan0
    else
        echo "      vcan0 已就绪。"
    fi
else
    echo "      vcan0 不存在，正在创建（需要 sudo 密码）..."
    sudo modprobe vcan
    sudo ip link add dev vcan0 type vcan
    sudo ip link set up vcan0
fi

# 4. 检查/编译 C++ Mock EC Node
MOCK_BIN="$ROOT_DIR/tools/mock_ec_node/build/mock_ec_node"
if [ ! -x "$MOCK_BIN" ]; then
    echo "[2/4] Mock EC Node 尚未构建，正在编译..."
    if ! command -v cmake >/dev/null 2>&1 || ! command -v g++ >/dev/null 2>&1; then
        echo "[错误] 缺少编译工具，请先安装："
        echo "  sudo apt install cmake g++"
        echo ""
        exit 1
    fi
    mkdir -p "$ROOT_DIR/logs"
    BUILD_LOG="$ROOT_DIR/logs/mock_ec_build.log"
    if ! ( cd "$ROOT_DIR/tools/mock_ec_node" && \
           cmake -S . -B build > "$BUILD_LOG" 2>&1 && \
           cmake --build build >> "$BUILD_LOG" 2>&1 ); then
        echo "[错误] Mock EC Node 编译失败。"
        echo "       详细日志：$BUILD_LOG"
        exit 1
    fi
    echo "      编译完成。"
fi

# 5. 启动 CAN Mock 与 Web
echo "[3/4] 启动 CAN Mock（mock_ec_node vcan0 normal）..."
launch_terminal "RM Validator - CAN Mock" \
    "'$MOCK_BIN' vcan0 normal"

echo "      启动 Web..."
launch_terminal "RM Validator - Web" \
    "cd '$ROOT_DIR' && '$PYTHON' main.py web --protocol protocols/tongji_sentry.yaml --host 127.0.0.1 --port 5000"

# 6. 等待 Web 就绪
echo "[4/4] 等待 Web 就绪..."
if ! wait_for_web; then
    echo "[错误] Web 服务未能启动，请查看 'RM Validator - Web' 终端输出。"
    exit 1
fi

# 7. 自动启动 CAN Live
echo "自动启动 CAN Live（interface=vcan0）..."
RESULT="$(start_can_live_api)"
echo "Live 启动结果：$RESULT"

# 8. 打开浏览器
open_browser

echo ""
echo "=== 完成 ==="
echo "浏览器已打开：$WEB_URL"
echo "如果页面尚未显示数据，请稍候几秒或刷新页面。"
echo "关闭方式：在各个终端窗口按 Ctrl+C。"
