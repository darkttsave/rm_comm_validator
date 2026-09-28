# RM Communication Validator

**实时 CAN/Serial 通信协议验证工具** — Validate RoboMaster communication protocols in real-time.

---

## 这个工具是干什么的？ What is this?

**RM Communication Validator** 是一个用于验证 RoboMaster 通信协议的工具。它可以：

- 接收 **CAN** 或 **Serial** 数据
- 按照选定的**协议**解析数据帧
- 检查字段范围、校验和、状态机等规则
- 在 Web 界面实时显示解析结果与验证状态
- 保存日志用于回放和 AI 辅助分析

---

## 核心概念 Core Concepts

### 1. Replay（回放模式）
从之前保存的日志文件（`.jsonl`）中回放数据，用于调试和分析历史问题。

### 2. Live（实时模式）
从真实的通信接口（CAN / Serial）读取实时数据并验证。

### 3. Simulator（模拟器）
模拟一个下位机/云台节点，为 Live 模式提供测试数据。  
当你选择 **RM Virtual Serial** 或 **RM Virtual CAN** 并点击 Start 时，Simulator 会自动启动。

### 4. 虚拟串口错误注入（Virtual Serial Error Injection）
在使用 **RM Virtual Serial** 时，可以选择错误注入模式来测试 Validator 的验证能力：

- **正常** - 发送完全正确的数据帧
- **非法 Mode** - 发送不合法的 mode 字段值
- **四元数异常** - 发送不满足归一化条件的四元数
- **CRC 错误** - 发送 CRC16 校验错误的数据帧

错误注入仅在选择 Virtual Serial Endpoint 时可用，用于测试协议验证器的正确性。

---

## 两种启动方式 Runtime Modes

### Normal Runtime（正常启动）

```bash
./start_web.sh
```

**含义**：
- 只启动 Validator Web
- **不启动**任何 Mock 节点
- 用于连接真实硬件

**用于场景**：
- 真实 Serial 设备（如实际云台）
- 真实 CAN 总线
- Replay 历史日志

**注意**：Normal Runtime 中 **不会显示** RM Virtual Serial / RM Virtual CAN 选项。

---

### Simulation Runtime（模拟启动）

```bash
./start_sim.sh
```

**含义**：
- 启动 Validator Web
- 允许使用 **RM Virtual Serial** 和 **RM Virtual CAN**
- 选择 Virtual Endpoint 并点击 Start 后，对应的 Mock 才会启动
- 点击 Stop 后，Mock 同时停止

**用于场景**：
- 没有真实电控板时测试协议
- 开发和调试新协议
- CI/CD 自动化测试

**注意**：启动 `start_sim.sh` 本身 **不会立即启动 Mock**，只有在 Web 中选择 Virtual Endpoint 并点击 Start 时才会启动。

---

## Live 模式的三个选择 Transport / Protocol / Endpoint

在 Live 模式中，你需要依次选择：

### 1. Transport（传输方式）
数据通过什么通信方式传输？

- **CAN** - SocketCAN (Linux)
- **Serial** - UART 串口

### 2. Protocol（协议）
收到的 bytes/frame 应该如何解释？

例如：
- **Tongji Sentry CAN** - CAN 协议，用于哨兵机器人
- **Tongji Gimbal Serial** - Serial 协议，用于云台通信

协议文件位于 `protocols/` 目录，可以在 Web 中随时切换（仅限 Idle 状态）。

### 3. Endpoint（端点）
数据实际从哪里来？

**CAN Transport 的 Endpoint：**
- **RM Virtual CAN** - 模拟设备（Simulation Runtime 中可用）
- **can0 / can1** - 物理 CAN 接口

**Serial Transport 的 Endpoint：**
- **RM Virtual Serial** - 模拟设备（Simulation Runtime 中可用）
- **/dev/ttyUSB0 / COM3** - 物理串口

---

## 快速开始 Quick Start

### 方式一：没有真实电控板（使用模拟器）

```bash
# 1. 启动 Simulation Runtime
./start_sim.sh

# 2. 浏览器自动打开（或手动访问 http://127.0.0.1:5000）

# 3. 在 Web 界面：
#    数据源 → Live
#    Transport → Serial（或 CAN）
#    Protocol → 选择协议
#    Endpoint → RM Virtual Serial（或 RM Virtual CAN）
#    点击 Start

# 4. 查看实时数据、验证结果
```

**预期效果**：
- Serial: 显示 `gimbal_to_vision` 消息，CRC16 和 QUAT_NORM 验证通过
- CAN: 显示 `quaternion` 和 `robot_state` 消息

### 方式二：有真实电控板

```bash
# 1. 启动 Normal Runtime
./start_web.sh

# 2. 浏览器自动打开

# 3. 在 Web 界面：
#    数据源 → Live
#    Transport → Serial（或 CAN）
#    Protocol → 选择协议
#    Endpoint → 选择物理设备（如 /dev/ttyUSB0 或 can0）
#    点击 Start

# 4. 查看实时数据
```

---

## 安装依赖 Installation

### Python 环境

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### Simulation Runtime 额外依赖

#### Serial 模拟器（RM Virtual Serial）

```bash
# Linux
sudo apt install socat

# macOS
brew install socat
```

#### CAN 模拟器（RM Virtual CAN）

```bash
# 1. 加载 vcan 内核模块
sudo modprobe vcan

# 2. 构建 Mock EC 节点
cd tools/mock_ec_node
./build.sh
```

**注意**：`start_sim.sh` 会自动检查这些依赖并给出提示，缺少某一个不会影响其他功能。

---

## 项目结构 Project Structure

```
rm_comm_validator/
├── protocols/              # 协议定义文件（YAML）
│   ├── tongji_sentry.yaml          # CAN 协议示例
│   └── tongji_gimbal_serial.yaml   # Serial 协议示例
├── web_app.py              # Flask Web 后端
├── protocol_registry.py    # 协议注册表（运行时切换）
├── serial_simulator.py     # Serial 模拟器（socat + mock_gimbal）
├── can_simulator.py        # CAN 模拟器（vcan0 + mock_ec_node）
├── decoder.py              # 协议解码器
├── validator.py            # 数据验证器
├── start_web.sh            # Normal Runtime 启动脚本
├── start_sim.sh            # Simulation Runtime 启动脚本
├── templates/              # Web UI HTML
├── static/                 # Web UI CSS/JS
└── tests/                  # 自动化测试
```

---

## 日志记录 Logging

在 Web 界面的「日志记录」选项中可以选择：

- **不记录** - 不保存日志
- **仅异常** - 只记录验证失败的帧（推荐）
- **全部** - 记录所有帧

日志保存在 `logs/` 目录，格式为 JSONL（每行一个 JSON 对象），可用于：
- Replay 回放
- Python 脚本分析
- AI 辅助诊断

---

## Advanced 高级用法

### 手动指定协议启动

```bash
# 指定默认协议 ID
python main.py web --protocol tongji_sentry

# 指定端口和 host
python main.py web --host 0.0.0.0 --port 8080 --simulation
```

### 虚拟 CAN 手动管理

```bash
# 创建 vcan0
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# 手动启动 Mock EC
./tools/mock_ec_node/build/mock_ec_node vcan0 --mode normal
```

### 虚拟串口手动管理

```bash
# 创建串口对
socat -d -d pty,raw,echo=0,link=/tmp/rmcv_mock pty,raw,echo=0,link=/tmp/rmcv_validator

# 手动启动 Mock Gimbal
python tools/mock_serial_node/mock_gimbal.py /tmp/rmcv_mock --mode normal --rate 10
```

### CLI 监控模式（Terminal UI）

```bash
# CAN 监控
python main.py monitor --protocol protocols/tongji_sentry.yaml --interface can0

# 使用 Rich Dashboard 显示实时数据
```

---

## 开发新协议 Developing New Protocols

1. 在 `protocols/` 目录创建新的 YAML 文件
2. 定义 `transport`、`messages`、`validations` 等
3. Web 界面会自动扫描并加载新协议
4. 无需重启 Web Server

示例：参考 `protocols/tongji_sentry.yaml` 和 `protocols/tongji_gimbal_serial.yaml`

---

## 常见问题 FAQ

### Q: 为什么 Live 按钮显示"不可用"？

**A**: CAN Live 需要 Linux + SocketCAN。如果在 Windows/macOS，只能使用 Demo/Replay/Serial。

### Q: RM Virtual Serial 不可用？

**A**: 
1. 确保运行的是 `start_sim.sh`（不是 `start_web.sh`）
2. 检查 socat 是否安装：`socat -V`
3. 查看 Web 界面顶部 Runtime badge 是否显示 "Simulation"

### Q: RM Virtual CAN 不可用？

**A**:
1. 运行 `start_sim.sh`（它会自动设置 vcan0）
2. 检查 Mock EC 是否已构建：`ls tools/mock_ec_node/build/mock_ec_node`
3. 如果缺失，运行：`cd tools/mock_ec_node && ./build.sh`

### Q: 运行中能否切换 Transport/Protocol？

**A**: 不能。必须先点击 Stop，然后才能切换 Transport/Protocol/Endpoint。

### Q: Demo 模式是用 CAN 还是 Serial？

**A**: Demo 是内置数据源，不依赖 Transport。它生成 CAN 语义的演示数据（quaternion / robot_state）。

### Q: 如何在 CI 中使用？

**A**: 
```bash
# 启动 Simulation Runtime
./start_sim.sh &
WEB_PID=$!

# 等待 Web 就绪
sleep 3

# 调用 API 启动 Live
curl -X POST http://127.0.0.1:5000/api/start_live_serial \
  -H "Content-Type: application/json" \
  -d '{"port": "/tmp/rmcv_validator", "baudrate": 9600, "label": "RM Virtual Serial", "kind": "virtual"}'

# 验证数据
# ...

# 清理
kill $WEB_PID
```

---

## 许可证 License

[Your License Here]

---

## 贡献 Contributing

欢迎提交 Issue 和 Pull Request！

开发流程：
1. Fork 仓库
2. 创建 feature 分支
3. 编写测试：`pytest tests/`
4. 提交 PR

---

**Created with ❤️ for RoboMaster**
