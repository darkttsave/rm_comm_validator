# Mock EC Node

Linux 专用 C++ Mock 电控节点，用于通过 SocketCAN 测试 RM Communication Validator。

## 功能

模拟 RoboMaster 电控发送 CAN 消息：
- **CAN 0x01** (quaternion): 100 Hz
- **CAN 0x110** (robot_state): 20 Hz

数据布局严格遵循 `protocols/tongji_sentry.yaml`。

## 四种测试模式

### 1. normal（正常模式）
```bash
./mock_ec_node vcan0 normal
```
- 发送有效的四元数（围绕 Z 轴缓慢旋转）
- 发送有效的机器人状态（枚举值 0-4 循环）
- 用于验证 Validator 正常解码

### 2. invalid_enum（非法枚举）
```bash
./mock_ec_node vcan0 invalid_enum
```
- Quaternion 正常
- Robot state 的 `mode` 字段发送 `99`（不在 YAML 定义的 0-4 范围）
- 用于验证 Validator 的枚举校验

### 3. invalid_quaternion（非法四元数）
```bash
./mock_ec_node vcan0 invalid_quaternion
```
- 发送明显不归一化的四元数：`(0.9, 0.9, 0.9, 0.9)`，范数 ≈ 1.8
- Robot state 正常
- 用于验证 Validator 的四元数归一化校验

### 4. unknown_id（未知 CAN ID）
```bash
./mock_ec_node vcan0 unknown_id
```
- Quaternion 和 robot_state 正常
- 额外以 10 Hz 发送 **CAN 0x999**（未在协议中定义）
- 用于验证 Validator 如何处理未知消息

## Linux 测试流程

**注意**: 以下命令默认从仓库根目录执行。

### 前置条件
- Ubuntu 20.04+ 或其他支持 SocketCAN 的 Linux 发行版
- CMake 3.10+
- GCC/G++ 支持 C++17

### 步骤 1: 配置虚拟 CAN 接口
```bash
# 加载 vcan 内核模块
sudo modprobe vcan

# 创建虚拟 CAN 接口
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# 验证接口已创建
ip link show vcan0
```

### 步骤 2: 编译 Mock EC Node
```bash
cd tools/mock_ec_node

# 配置 CMake
cmake -S . -B build

# 编译
cmake --build build

# 验证可执行文件
ls -lh build/mock_ec_node
```

### 步骤 3: 启动 Validator（终端 1）
```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动监控（终端模式）
python main.py monitor \
  --protocol protocols/tongji_sentry.yaml \
  --interface vcan0
```

### 步骤 4: 启动 Mock Node（终端 2）
```bash
# 正常模式
./tools/mock_ec_node/build/mock_ec_node vcan0 normal

# 或其他测试模式
# ./tools/mock_ec_node/build/mock_ec_node vcan0 invalid_enum
# ./tools/mock_ec_node/build/mock_ec_node vcan0 invalid_quaternion
# ./tools/mock_ec_node/build/mock_ec_node vcan0 unknown_id
```

### 预期结果

**Normal 模式**:
- Validator 终端显示绿色 ✓ 校验通过
- Quaternion 的 `z` 和 `w` 字段缓慢变化
- Robot state 的 `mode` 字段从 `idle` → `auto_aim` → `small_buff` → `big_buff` → `outpost` 循环

**Invalid Enum 模式**:
- Quaternion 校验通过
- Robot state 显示 **红色警告**：`mode=99` 不在枚举范围

**Invalid Quaternion 模式**:
- Quaternion 显示 **红色警告**：归一化校验失败（norm ≈ 1.8）
- Robot state 正常

**Unknown ID 模式**:
- Quaternion 和 robot_state 正常
- Validator 日志中出现 **警告**：收到未知 CAN ID `0x999`

## 数据布局验证

Mock Node 严格遵循 `tongji_sentry.yaml` 定义：

### CAN 0x01 (Quaternion)
| Offset | Type   | Endian | Scale  | Field |
|--------|--------|--------|--------|-------|
| 0-1    | int16  | Big    | 0.0001 | x     |
| 2-3    | int16  | Big    | 0.0001 | y     |
| 4-5    | int16  | Big    | 0.0001 | z     |
| 6-7    | int16  | Big    | 0.0001 | w     |

### CAN 0x110 (Robot State)
| Offset | Type   | Endian | Scale  | Field        |
|--------|--------|--------|--------|--------------|
| 0-1    | int16  | Big    | 0.01   | bullet_speed |
| 2      | uint8  | -      | -      | mode (0-4)   |
| 3      | uint8  | -      | -      | shoot_mode   |
| 4-5    | int16  | Big    | 0.0001 | ft_angle     |
| 6-7    | -      | -      | -      | (unused)     |

## 停止 Mock Node

按 `Ctrl+C` 终止进程。

## 清理虚拟 CAN 接口
```bash
sudo ip link set down vcan0
sudo ip link delete vcan0
```

## 故障排除

### 编译错误："linux/can.h: No such file or directory"
```bash
# 安装 CAN 开发头文件
sudo apt install linux-headers-$(uname -r)
```

### 运行时错误："Interface vcan0 not found"
```bash
# 确保 vcan0 已创建并启动
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

### Validator 无数据
```bash
# 1. 检查 Mock Node 是否正常运行
ps aux | grep mock_ec_node

# 2. 使用 candump 验证 CAN 流量
sudo apt install can-utils
candump vcan0

# 3. 确认 Validator 监听的接口与 Mock Node 一致
```

## 注意事项

- **仅支持 Linux**：Mock Node 使用原生 SocketCAN API，无法在 Windows/macOS 运行
- **非生产代码**：仅用于测试，未实现完整电控逻辑
- **无双向通信**：当前版本不监听 CAN 0xFF 命令消息
