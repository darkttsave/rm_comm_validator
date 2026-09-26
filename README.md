# RM 通信校验器

RoboMaster 通信协议独立验证工具，用于 CAN 通信的实时解码、验证和监控。

## 当前版本：V1.1

**核心功能**:
- **Web UI**: 浏览器界面，支持远程访问
- **Demo 模式**: 无需硬件即可演示
- **Replay 模式**: 回放历史日志
- **Live 模式**: SocketCAN 实时监控（Linux）
- **终端模式**: Rich 终端仪表板
- **完整日志**: JSONL 格式保留所有原始数据

---

## 快速开始

### Windows（Demo/Replay）

```powershell
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 3. 安装依赖
python -m pip install -r requirements.txt

# 4. 启动 Web UI
python main.py web

# 5. 浏览器访问 http://127.0.0.1:5000
# 点击 "Demo 模式" 查看效果
```

### Linux/NUC（Live CAN）

```bash
# 1. 安装 venv 支持（首次需要）
sudo apt install python3-venv

# 2. 创建虚拟环境
python3 -m venv .venv

# 3. 激活虚拟环境
source .venv/bin/activate

# 4. 安装依赖
python -m pip install -r requirements.txt

# 5. 配置 CAN 接口（系统层，在虚拟环境外执行）
sudo ip link set can0 type can bitrate 1000000
sudo ip link set up can0

# 6. 启动 Web UI（局域网可访问）
python main.py web --host 0.0.0.0 --port 5000

# 7. 浏览器访问 http://<NUC_IP>:5000
```

**虚拟环境说明**:
- ✅ **推荐每个项目使用独立 `.venv`**，避免依赖冲突
- ✅ VS Code 用户：选择项目的 `.venv` 作为 Python Interpreter
- ✅ 虚拟环境内：`python-can`, `Flask`, `PyYAML`, `rich` 等 Python 包
- ✅ 系统层：`sudo ip link`、SocketCAN 驱动、`can0` 配置（不在虚拟环境）
- ⚠️ 如已误装到全局环境，创建 `.venv` 后从此使用虚拟环境即可

**依赖清单** (`requirements.txt`):
```
python-can>=4.0.0    # SocketCAN（Linux 实时监控必需）
PyYAML>=6.0          # 协议解析（必需）
rich>=13.0.0         # 终端仪表板（可选）
Flask>=2.0.0         # Web UI（可选）
```

---

## 使用模式

### 模式 1: Web UI（推荐）

**启动**:
```bash
# 确保已激活虚拟环境：source .venv/bin/activate

# 本地访问
python main.py web

# 远程访问（NUC）
python main.py web --host 0.0.0.0 --port 5000
```

**访问**: `http://127.0.0.1:5000` 或 `http://<NUC_IP>:5000`

**功能**:
- **Demo**: 点击"Demo 模式"，无需硬件自动生成数据
- **Replay**: 选择 `logs/*.jsonl` 文件回放
- **Live**: Web UI 暂未接入 SocketCAN Live（请使用终端模式）

**界面**:
```
┌─────────────────────────────────────┐
│ 统计: 总帧/有效/无效/未知 + 帧率    │
├─────────────────────────────────────┤
│ 消息卡片（按类型分组）:             │
│   Quaternion (0x01)                 │
│   - 字段值 (x, y, z, w)             │
│   - 验证状态: ✓ PASS                │
│   - RAW HEX: 00 17 FF F1 ...  ← 原始数据
│                                     │
│   Robot State (0x110)               │
│   - 字段值 (bullet_speed, mode...)  │
│   - 验证状态: ✓ PASS                │
│   - RAW HEX: 0B 22 01 02 ...  ← 原始数据
├─────────────────────────────────────┤
│ 近期事件: 仅显示异常和警告          │
└─────────────────────────────────────┘
```

### 模式 2: 终端模式

**启动**:
```bash
# 确保已激活虚拟环境：source .venv/bin/activate
python main.py monitor --protocol protocols/tongji_sentry.yaml --interface can0
```

**适用场景**: SSH 直连调试，不需要浏览器

---

## 协议 YAML

协议文件位于 `protocols/` 目录，定义 CAN 消息的解码规则。

**示例** (`protocols/tongji_sentry.yaml`):
```yaml
transport:
  type: socketcan
  interface: can0

messages:
  - name: quaternion          # 消息名称
    direction: rx             # rx=接收, tx=发送
    id: "0x01"                # CAN ID
    dlc: 8                    # 数据长度
    
    fields:
      - name: w
        offset: 6             # 字节偏移
        type: int16           # 数据类型
        endian: big           # 字节序
        scale: 0.0001         # 解码值 = 原始值 × scale
      
      - name: mode
        offset: 2
        type: uint8
        enum:                 # 枚举值
          0: idle
          1: auto_aim
    
    validators:               # 自定义验证
      - type: quaternion_norm
        fields: [w, x, y, z]
        tolerance: 0.01
```

**支持的字段类型**: `uint8`, `int8`, `uint16`, `int16`, `uint32`, `int32`, `float32`

**自动验证**: CAN_ID, DLC, ENUM

**添加自定义协议**:
1. 在 `protocols/` 创建 `.yaml` 文件
2. 参考 `tongji_sentry.yaml` 格式
3. 使用: `python main.py web --protocol protocols/your_protocol.yaml`

---

## 日志

### 自动记录

所有模式运行时自动生成 JSONL 日志：
```
logs/comm_YYYYMMDD_HHMMSS.jsonl
```

### 日志格式

每行一个 JSON 对象：
```json
{
  "timestamp": 1695707823.123456,
  "direction": "rx",
  "can_id": "0x110",
  "dlc": 8,
  "raw": "0B 22 01 02 04 E2 00 00",     ← 原始字节
  "message": "robot_state",
  "valid": true,
  "fields": {                            ← 解码后的值
    "bullet_speed": 28.5,
    "mode": 1
  },
  "validation": [...]                    ← 验证结果
}
```

### 查看日志

```bash
# 列出日志
ls -lh logs/*.jsonl

# 查看内容
less logs/comm_20260926_142530.jsonl

# 实时监控
tail -f logs/comm_20260926_142530.jsonl

# 使用 Replay 模式回放（确保已激活虚拟环境）
python main.py web
# 浏览器中点击 "Replay 模式"，选择文件
```

### 清理日志

```bash
# 删除 7 天前的日志
find logs/ -name "*.jsonl" -mtime +7 -delete
```

---

## 项目结构

```
rm_comm_validator/
├── main.py                    # 程序入口
├── protocol.py                # 协议加载器
├── decoder.py                 # 解码器/编码器
├── validator.py               # 验证器
├── can_transport.py           # SocketCAN 传输
├── recorder.py                # JSONL 记录
├── dashboard.py               # 终端仪表板
├── demo_source.py             # Demo 数据源（V1.1）
├── replay_source.py           # Replay 数据源（V1.1）
├── web_app.py                 # Flask Web 应用（V1.1）
├── templates/index.html       # Web 模板
├── static/                    # CSS + JS
├── protocols/                 # 协议定义
│   └── tongji_sentry.yaml
├── tests/                     # 测试套件
├── logs/                      # 自动生成的日志
└── requirements.txt
```

**架构**:
```
数据源 (Demo/Replay/Live) → Decoder → Validator
                                         ↓
                                  ┌──────┴──────┐
                                  ↓             ↓
                              Terminal        Web UI
                              Dashboard        ↓
                                  ↓         Recorder
                               Recorder
```

---

## 常见问题

### 1. 找不到 CAN 接口

**症状**: `Device "can0" does not exist`

**解决**:
```bash
# 检查硬件
lsusb
dmesg | grep -i can

# 加载驱动
sudo modprobe can
sudo modprobe can_raw
sudo modprobe gs_usb  # USB-CAN 适配器
```

### 2. 无法远程访问 Web UI

**检查**:
```bash
# 1. 确认启动参数正确（确保已激活虚拟环境）
python main.py web --host 0.0.0.0  # 不是 127.0.0.1

# 2. 检查防火墙
sudo ufw allow 5000/tcp

# 3. 验证端口监听
sudo netstat -tulnp | grep 5000

# 4. 测试连接
curl http://<NUC_IP>:5000
```

### 3. 没有数据显示

**排查**:
```bash
# 1. 验证 CAN 有流量
sudo apt install can-utils
candump can0

# 2. 检查比特率
ip -details link show can0 | grep bitrate

# 3. 验证协议文件（确保已激活虚拟环境）
python -c "import yaml; yaml.safe_load(open('protocols/tongji_sentry.yaml'))"
```

### 4. Demo 模式无数据

**确认**:
```bash
# 检查依赖安装（确保已激活虚拟环境）
python -m pip list | grep Flask

# 查看浏览器控制台错误（F12）
# 检查后端日志输出
```

---

## 测试

```bash
# 确保已激活虚拟环境：source .venv/bin/activate

# 运行所有测试
python tests/test_golden_vectors.py
python tests/test_validator.py
python tests/test_decoder.py
python tests/test_demo_source.py      # V1.1
python tests/test_replay_source.py    # V1.1
```

---

## Git 更新

从远端获取并切换到指定分支：

```bash
# 查看当前状态
git status
git branch --show-current

# 获取远端更新
git fetch origin

# 切换到目标分支
git switch <branch>

# 更新当前分支（仅快进合并）
git pull --ff-only
```

**注意**: `git pull` 只更新当前所在分支，不影响其他分支。

---

## 当前限制

**不支持**:
- ❌ UART/串口传输
- ❌ 实时发送功能（编码器已实现但无 CLI）
- ❌ CAN FD
- ❌ 数据图表可视化

**平台支持**:

| 平台 | Demo | Replay | Live CAN |
|------|------|--------|----------|
| Linux | ✅ | ✅ | ✅ |
| Windows | ✅ | ✅ | ❌ |
| macOS | ✅ | ✅ | ⚠️ 需驱动 |

---

## 更多文档

- `V1.1_验收报告.md` - 完整技术文档
- `项目现状报告.md` - 项目现状总结

## 许可证

独立开发工具，不属于 TongjiSuperPower 项目。
