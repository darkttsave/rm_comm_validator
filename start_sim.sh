#!/usr/bin/env bash
# RM Communication Validator 一键模拟总入口

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "RM Communication Validator"
echo ""
echo "1) Serial 串口模拟"
echo "2) CAN 模拟"
echo "q) 退出"
echo ""
read -rp "请选择 [1/2/q]： " choice

case "$choice" in
    1)
        exec "$SCRIPT_DIR/start_serial_sim.sh"
        ;;
    2)
        exec "$SCRIPT_DIR/start_can_sim.sh"
        ;;
    q|Q)
        exit 0
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac
