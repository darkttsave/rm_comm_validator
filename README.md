# RM Communication Validator

RoboMaster 通信协议独立验证工具，支持 CAN 与串口（Serial）通信的实时解码、验证和监控。

---

## 快速模拟

三条命令，一键启动模拟通信链路、Mock 节点、Web UI、自动开始 Live 并打开浏览器。

### 串口

```bash
./start_serial_sim.sh
```

### CAN

```bash
./start_can_sim.sh
```

### 不知道选哪个

```bash
./start_sim.sh
```

脚本会自动完成：

1. 检查虚拟环境（`.venv`）与依赖
2. 创建模拟通信链路（串口对 / vcan0）
3. 启动 Mock 节点
4. 启动 Web UI
5. 自动开始 Live
6. 自动打开浏览器

执行后浏览器会直接显示实时模拟数据，无需任何手动配置。

> **首次使用**需要先初始化虚拟环境：
> ```bash
> python3 -m venv .venv
> .venv/bin/python -m pip install -r requirements.txt
> ```
> Serial 模拟还需要 `socat`（`sudo apt install socat`）。
> CAN 模拟需要 Linux + SocketCAN，创建 `vcan0` 时可能要求输入一次 sudo 密码。

---

## 说明

- **串口模拟**使用 `protocols/tongji_gimbal_serial.yaml`（同济参考协议，仅用于测试，非队内生产协议）
- **CAN 模拟**使用 `protocols/tongji_sentry.yaml`

详见下方「模拟链路说明」与「Advanced / 手动调试」。

---

## 模拟链路说明

### Serial 串口模拟

`./start_serial_sim.sh` 自动创建固定虚拟串口对：

- `/tmp/rmcv_mock` —— Mock 节点写入
- `/tmp/rmcv_validator` —— Validator 监听

数据流：

```
Mock Gimbal (normal, 10 Hz)
      │ 写 /tmp/rmcv_mock
      ▼
  socat PTY 对
      │
      ▼
/tmp/rmcv_validator
      │
      ▼
SerialTransport → SerialFramer → Decoder → Validator → Web
```

Web 中显示 `gimbal_to_vision` 消息卡片，校验项 `CRC16 PASS`、`QUAT_NORM PASS`。

### CAN 模拟

`./start_can_sim.sh` 自动确保 `vcan0` 存在并启动（需要时用 sudo），编译并运行 Mock EC Node。

数据流：

```
Mock EC Node (vcan0, normal)
      │
      ▼
   vcan0 (虚拟 CAN)
      │
      ▼
CANTransport → Decoder → Validator → Web
```

Web 中显示 `quaternion` 与 `robot_state` 消息卡片。

---

## 测试

```bash
# 运行全部测试（含 CAN regression 与 Serial 新增测试）
python -m pytest tests/ -v
```

---

## Advanced / 手动调试

以下内容供需要手动控制的高级用户参考，普通用户无需了解。

### 手动启动 Web UI

```bash
# 确保已激活虚拟环境：source .venv/bin/activate

# CAN 协议
python main.py web --protocol protocols/tongji_sentry.yaml --interface vcan0

# Serial 协议
python main.py web --protocol protocols/tongji_gimbal_serial.yaml
```

### 手动创建虚拟 CAN 接口

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

### 手动创建串口对（socat）

```bash
socat -d -d pty,raw,echo=0 pty,raw,echo=0
# 输出示例：
# ... N PTY is /dev/pts/3
# ... N PTY is /dev/pts/4
```

### 手动运行 Mock 节点

```bash
# Serial Mock（Tongji reference）
python tools/mock_serial_node/mock_gimbal.py /tmp/rmcv_mock --mode normal --rate 10

# CAN Mock（需先编译，见 tools/mock_ec_node/README.md）
./tools/mock_ec_node/build/mock_ec_node vcan0 normal
```

### Serial Mock 测试模式

```bash
# 正常模式
python tools/mock_serial_node/mock_gimbal.py /tmp/rmcv_mock --mode normal

# 无效模式枚举
python tools/mock_serial_node/mock_gimbal.py /tmp/rmcv_mock --mode invalid_mode

# 无效四元数（非归一化）
python tools/mock_serial_node/mock_gimbal.py /tmp/rmcv_mock --mode invalid_quaternion

# CRC 错误
python tools/mock_serial_node/mock_gimbal.py /tmp/rmcv_mock --mode bad_crc
```

### 日志

- 日志保存位置：`logs/`（JSONL 格式）
- 三档日志模式：不记录 / 仅异常（默认）/ 全部
- Serial 日志含 `port`、`length` 字段；CAN 日志含 `can_id`、`dlc` 字段
- 旧 CAN 日志（无 `transport` 字段）仍可正常回放

---

## 协议 YAML

协议文件位于 `protocols/` 目录。

### CAN 协议

`protocols/tongji_sentry.yaml`：

```yaml
transport:
  type: socketcan
  interface: can0

messages:
  - name: quaternion
    direction: rx
    id: "0x01"
    dlc: 8
    fields:
      - name: w
        offset: 6
        type: int16
        endian: big
        scale: 0.0001
```

### Serial 协议

`protocols/tongji_gimbal_serial.yaml`（参考协议）：

```yaml
transport:
  type: serial
  baudrate: 9600
  bytesize: 8
  parity: none
  stopbits: 1
  timeout_ms: 20
  header: "5350"   # 固定帧头（hex）

messages:
  - name: gimbal_to_vision
    direction: rx
    frame_length: 43
    fields:
      - name: mode
        offset: 2
        type: uint8
        enum:
          0: IDLE
          1: AUTO_AIM
    validators:
      - type: crc16
        fields: ['tongji_crc16', 'offset:41']
      - type: quaternion_norm
        fields: [q_w, q_x, q_y, q_z]
```

支持的字段类型：`uint8`, `int8`, `uint16`, `int16`, `uint32`, `int32`, `float32`

---

## 项目结构

```
rm_comm_validator/
├── start_sim.sh                # 一键模拟总入口
├── start_serial_sim.sh         # 一键串口模拟
├── start_can_sim.sh            # 一键 CAN 模拟
├── start_web.sh                # 手动启动 Web
├── main.py                     # 程序入口
├── protocol.py                 # 协议加载器（CAN + Serial）
├── decoder.py                  # 解码器/编码器
├── validator.py                # 验证器（CAN + Serial 校验）
├── can_transport.py            # SocketCAN 传输
├── serial_transport.py         # 串口传输
├── serial_framer.py            # 串口帧提取器
├── serial_utils.py             # 串口枚举
├── live_can_source.py          # CAN Live 数据源
├── live_serial_source.py       # Serial Live 数据源
├── crc_algorithms.py           # Tongji CRC16
├── recorder.py                 # JSONL 记录
├── dashboard.py                # 终端仪表板
├── demo_source.py              # Demo 数据源
├── replay_source.py            # Replay 数据源
├── web_app.py                  # Flask Web 应用
├── templates/                  # Web 模板
├── static/                     # CSS + JS
├── protocols/                  # 协议定义
│   ├── tongji_sentry.yaml      #   CAN 协议
│   └── tongji_gimbal_serial.yaml  # Serial 参考协议
├── tools/
│   ├── sim_common.sh           # 一键模拟共享辅助
│   └── mock_serial_node/       # Serial Mock 节点
├── tests/                      # 测试套件
├── docs/                       # 验收报告
├── logs/                       # 自动生成的日志
└── requirements.txt
```

**架构**：

```
CAN                 Serial
 │                    │
 ▼                    ▼
CANTransport      SerialTransport
                      │
                      ▼
                  SerialFramer
       │              │
       └──────┬───────┘
              ▼
         Decoder
              ↓
         Validator
              ↓
       Web / Logger
```

---

## 常见问题

### 1. 执行脚本提示找不到虚拟环境

先初始化：
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. 串口模拟提示缺少 socat

```bash
sudo apt install socat
```

### 3. CAN 模拟提示缺少编译工具

```bash
sudo apt install cmake g++
```

### 4. 浏览器没有显示数据

- 稍候几秒或刷新页面
- 查看各终端窗口输出（Mock / Web / Bridge）
- 确认 Mock 节点仍在运行

---

## 更多文档

- `docs/V1.1_验收报告.md` - V1.1 验收报告
- `docs/V1.2_Serial_Live_验收报告.md` - V1.2 Serial Live 验收报告
- `GitNote.txt` - Git 常用操作备忘
