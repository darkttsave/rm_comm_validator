// RM Communication Validator Web UI JavaScript

let updateInterval = null;
let isRunning = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadStatus();
    setupEventHandlers();
    startPeriodicUpdates();
});

// Setup event handlers
function setupEventHandlers() {
    document.getElementById('btn-demo').addEventListener('click', startDemo);
    document.getElementById('btn-replay').addEventListener('click', showReplayPanel);
    document.getElementById('btn-live').addEventListener('click', showLivePanel);
    document.getElementById('btn-stop').addEventListener('click', stopMonitoring);
    document.getElementById('chk-error-injection').addEventListener('change', toggleErrorInjection);
    document.getElementById('btn-start-replay').addEventListener('click', startReplay);
    document.getElementById('btn-start-live').addEventListener('click', startLive);
    document.getElementById('btn-refresh-interfaces').addEventListener('click', loadSocketCANInterfaces);
    document.getElementById('btn-start-live-serial').addEventListener('click', startLiveSerial);
    document.getElementById('btn-refresh-serial-ports').addEventListener('click', loadSerialPorts);
    document.getElementById('log-mode-select').addEventListener('change', setLogMode);
}

// Start periodic updates
function startPeriodicUpdates() {
    updateInterval = setInterval(updateAll, 500);
}

// Update all data
async function updateAll() {
    await updateStatus();
    await updateMessages();
    await updateRates();
    await updateEvents();
}

// Load initial status
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        // Update protocol name
        if (data.protocol) {
            const protocolName = data.protocol.split('/').pop().replace('.yaml', '');
            document.getElementById('protocol-name').textContent = `协议: ${protocolName}`;
        }

        // Store transport type globally
        window.transportType = data.transport_type || 'socketcan';

        // Load log files for replay
        loadLogFiles();

        // Load interfaces based on transport type
        if (window.transportType === 'serial') {
            await loadSerialPorts();
        } else {
            await loadSocketCANInterfaces();
        }
    } catch (error) {
        console.error('Failed to load status:', error);
    }
}

// Update status
async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        isRunning = data.running;

        // Update mode status
        let statusText = '就绪';
        if (data.running) {
            statusText = `运行中 - ${data.mode} 模式`;
        }
        document.getElementById('mode-status').textContent = statusText;

        // Update runtime
        const hours = Math.floor(data.runtime / 3600);
        const minutes = Math.floor((data.runtime % 3600) / 60);
        const seconds = data.runtime % 60;
        document.getElementById('runtime').textContent =
            `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;

        // Update statistics
        document.getElementById('stat-total').textContent = data.statistics.total;
        document.getElementById('stat-valid').textContent = data.statistics.valid;
        document.getElementById('stat-invalid').textContent = data.statistics.invalid;
        document.getElementById('stat-unknown').textContent = data.statistics.unknown;

        // Update buttons
        document.getElementById('btn-demo').disabled = data.running;
        document.getElementById('btn-replay').disabled = data.running;
        document.getElementById('btn-live').disabled = data.running;
        document.getElementById('btn-stop').disabled = !data.running;

        // Update log mode selector
        const logModeSelect = document.getElementById('log-mode-select');
        logModeSelect.disabled = data.running;
        logModeSelect.value = data.log_mode;

        // Update log status display
        updateLogStatus(data);

        // Update error injection checkbox
        document.getElementById('chk-error-injection').checked = data.error_injection;

        // Update Live mode status display
        if (data.mode === 'live') {
            const liveStatus = document.getElementById('live-status');
            if (data.connection_status === 'connected') {
                liveStatus.innerHTML = `<span class="status-connected">✓ 已连接到 ${data.interface}</span>`;
            } else if (data.connection_status === 'error') {
                liveStatus.innerHTML = `<span class="status-error">✗ 连接失败: ${data.last_error || '未知错误'}</span>`;
            }
        }

    } catch (error) {
        console.error('Failed to update status:', error);
    }
}

// Update messages
async function updateMessages() {
    try {
        const response = await fetch('/api/messages');
        const messages = await response.json();

        const container = document.getElementById('messages-container');

        if (Object.keys(messages).length === 0) {
            container.innerHTML = '<p class="no-data">等待数据...</p>';
            return;
        }

        container.innerHTML = '';

        for (const [msgName, msgData] of Object.entries(messages)) {
            const card = createMessageCard(msgName, msgData);
            container.appendChild(card);
        }

    } catch (error) {
        console.error('Failed to update messages:', error);
    }
}

// Create message card
function createMessageCard(name, data) {
    const card = document.createElement('div');
    card.className = `message-card ${data.all_passed ? 'valid' : 'invalid'}`;

    // Header
    const header = document.createElement('div');
    header.className = 'message-header';

    // Build info string based on available fields
    let infoStr = '';
    if (data.can_id) {
        infoStr = `${data.can_id} | DLC=${data.dlc}`;
    } else if (data.frame_length) {
        infoStr = `${name} | LEN=${data.frame_length}`;
    }

    header.innerHTML = `
        <span class="message-name">${name}</span>
        <span class="message-info">${infoStr}</span>
    `;
    card.appendChild(header);

    // Fields
    const fields = document.createElement('div');
    fields.className = 'message-fields';
    for (const [fieldName, fieldValue] of Object.entries(data.fields)) {
        const fieldItem = document.createElement('div');
        fieldItem.className = 'field-item';

        let displayValue = fieldValue;
        if (typeof fieldValue === 'number') {
            displayValue = fieldValue.toFixed(4);
        }

        fieldItem.innerHTML = `
            <span class="field-name">${fieldName}</span>
            <span class="field-value">${displayValue}</span>
        `;
        fields.appendChild(fieldItem);
    }
    card.appendChild(fields);

    // Validation
    const validation = document.createElement('div');
    validation.className = 'validation-section';
    validation.innerHTML = '<div class="validation-title">验证</div>';

    for (const v of data.validation) {
        const item = document.createElement('div');
        item.className = 'validation-item';
        const icon = v.passed ? '✓' : '✗';
        const iconClass = v.passed ? 'pass' : 'fail';
        item.innerHTML = `
            <span class="validation-icon ${iconClass}">${icon}</span>
            <span>${v.check}: ${v.message}</span>
        `;
        validation.appendChild(item);
    }
    card.appendChild(validation);

    // Raw data
    const raw = document.createElement('div');
    raw.className = 'raw-section';
    raw.innerHTML = `
        <div class="raw-title">RAW HEX</div>
        <div class="raw-data">${data.raw}</div>
    `;
    card.appendChild(raw);

    return card;
}

// Update rates
async function updateRates() {
    try {
        const response = await fetch('/api/rates');
        const rates = await response.json();

        const container = document.getElementById('rates-container');
        container.innerHTML = '';

        for (const [canId, rate] of Object.entries(rates)) {
            const item = document.createElement('div');
            item.className = 'rate-item';
            item.innerHTML = `
                <span class="rate-label">${canId}</span>
                <span class="rate-value">${rate} Hz</span>
            `;
            container.appendChild(item);
        }

    } catch (error) {
        console.error('Failed to update rates:', error);
    }
}

// Update events
async function updateEvents() {
    try {
        const response = await fetch('/api/events');
        const events = await response.json();

        const container = document.getElementById('events-container');

        if (events.length === 0) {
            container.innerHTML = '<p class="no-data">无事件</p>';
            return;
        }

        container.innerHTML = '';

        for (const event of events) {
            const item = document.createElement('div');
            item.className = 'event-item';
            item.textContent = event;
            container.appendChild(item);
        }

    } catch (error) {
        console.error('Failed to update events:', error);
    }
}

// Start demo mode
async function startDemo() {
    try {
        const response = await fetch('/api/start_demo', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await response.json();

        if (data.success) {
            hideReplayPanel();
        } else {
            alert('启动 Demo 模式失败');
        }
    } catch (error) {
        console.error('Failed to start demo:', error);
        alert('启动 Demo 模式失败: ' + error.message);
    }
}

// Show replay panel
function showReplayPanel() {
    loadLogFiles();
    document.getElementById('replay-section').style.display = 'block';
}

// Hide replay panel
function hideReplayPanel() {
    document.getElementById('replay-section').style.display = 'none';
}

// Load log files
async function loadLogFiles() {
    try {
        const response = await fetch('/api/list_logs');
        const logs = await response.json();

        const select = document.getElementById('replay-file-select');
        select.innerHTML = '<option value="">-- 选择日志文件 --</option>';

        for (const log of logs) {
            const option = document.createElement('option');
            option.value = log.path;
            option.textContent = `${log.name} (${formatBytes(log.size)})`;
            select.appendChild(option);
        }
    } catch (error) {
        console.error('Failed to load log files:', error);
    }
}

// Start replay
async function startReplay() {
    const select = document.getElementById('replay-file-select');
    const path = select.value;

    if (!path) {
        alert('请选择一个日志文件');
        return;
    }

    try {
        const response = await fetch('/api/start_replay', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path: path})
        });
        const data = await response.json();

        if (data.success) {
            hideReplayPanel();
        } else {
            alert('启动 Replay 失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        console.error('Failed to start replay:', error);
        alert('启动 Replay 失败: ' + error.message);
    }
}

// Stop monitoring
async function stopMonitoring() {
    try {
        const response = await fetch('/api/stop', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        await response.json();
        hideLivePanel();
        hideReplayPanel();
    } catch (error) {
        console.error('Failed to stop:', error);
    }
}

// Toggle error injection
async function toggleErrorInjection() {
    try {
        const response = await fetch('/api/toggle_error_injection', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        await response.json();
    } catch (error) {
        console.error('Failed to toggle error injection:', error);
    }
}

// Load SocketCAN interfaces
async function loadSocketCANInterfaces() {
    try {
        const response = await fetch('/api/socketcan_interfaces');
        const data = await response.json();

        const liveBtn = document.getElementById('btn-live');
        const select = document.getElementById('live-interface-select');

        if (data.platform !== 'linux') {
            liveBtn.disabled = true;
            liveBtn.title = '需要 Linux + SocketCAN';
            liveBtn.textContent = 'Live 模式 (不可用)';
            return;
        }

        if (data.interfaces.length === 0) {
            liveBtn.disabled = false;
            liveBtn.title = '点击查看详情';
            liveBtn.textContent = 'Live 模式 (无接口)';
            return;
        }

        // Enable Live button
        liveBtn.disabled = false;
        liveBtn.title = '启动 SocketCAN 实时监控';
        liveBtn.textContent = 'Live 模式';

        // Populate interface selector
        select.innerHTML = '';
        for (const iface of data.interfaces) {
            const option = document.createElement('option');
            option.value = iface;
            option.textContent = iface;
            if (iface === data.default) {
                option.selected = true;
            }
            select.appendChild(option);
        }

        // Show status if no interfaces
        const liveStatus = document.getElementById('live-status');
        if (data.interfaces.length === 0) {
            liveStatus.innerHTML = '<span class="status-warning">⚠ 无可用 SocketCAN 接口</span>';
        } else {
            liveStatus.innerHTML = '';
        }

    } catch (error) {
        console.error('Failed to load SocketCAN interfaces:', error);
    }
}

// Load serial ports
async function loadSerialPorts() {
    try {
        const response = await fetch('/api/serial_ports');
        const data = await response.json();

        const liveBtn = document.getElementById('btn-live');
        const select = document.getElementById('serial-port-select');

        // Enable Live button for Serial
        liveBtn.disabled = false;
        liveBtn.title = '启动串口实时监控';
        liveBtn.textContent = 'Live 模式';

        // Populate port selector
        select.innerHTML = '<option value="">-- 选择串口 --</option>';
        for (const portInfo of data.ports) {
            const option = document.createElement('option');
            option.value = portInfo.device;
            option.textContent = `${portInfo.device} - ${portInfo.description}`;
            select.appendChild(option);
        }

        // Show status if no ports
        const liveStatus = document.getElementById('live-serial-status');
        if (data.ports.length === 0) {
            liveStatus.innerHTML = '<span class="status-warning">⚠ 无可用串口</span>';
        } else {
            liveStatus.innerHTML = '';
        }

    } catch (error) {
        console.error('Failed to load serial ports:', error);
    }
}

// Start Live Serial mode
async function startLiveSerial() {
    const select = document.getElementById('serial-port-select');
    const port = select.value;
    const baudrateInput = document.getElementById('serial-baudrate');
    const baudrate = parseInt(baudrateInput.value);

    if (!port) {
        alert('请选择一个串口');
        return;
    }

    if (!baudrate || baudrate < 300 || baudrate > 115200) {
        alert('请输入有效的波特率 (300-115200)');
        return;
    }

    try {
        const response = await fetch('/api/start_live_serial', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({port: port, baudrate: baudrate})
        });
        const data = await response.json();

        if (data.success) {
            hideLivePanel();
        } else {
            alert('启动 Serial Live 模式失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        console.error('Failed to start live serial:', error);
        alert('启动 Serial Live 模式失败: ' + error.message);
    }
}

// Show Live panel
function showLivePanel() {
    hideReplayPanel();

    // Show appropriate panel based on transport type
    if (window.transportType === 'serial') {
        loadSerialPorts();
        document.getElementById('live-serial-section').style.display = 'block';
        document.getElementById('live-can-section').style.display = 'none';
    } else {
        loadSocketCANInterfaces();
        document.getElementById('live-can-section').style.display = 'block';
        document.getElementById('live-serial-section').style.display = 'none';
    }
}

// Hide Live panel
function hideLivePanel() {
    document.getElementById('live-can-section').style.display = 'none';
    document.getElementById('live-serial-section').style.display = 'none';
}

// Start Live mode
async function startLive() {
    const select = document.getElementById('live-interface-select');
    const interface = select.value;

    if (!interface) {
        alert('请选择一个 SocketCAN 接口');
        return;
    }

    try {
        const response = await fetch('/api/start_live', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({interface: interface})
        });
        const data = await response.json();

        if (data.success) {
            hideLivePanel();
        } else {
            alert('启动 Live 模式失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        console.error('Failed to start Live mode:', error);
        alert('启动 Live 模式失败: ' + error.message);
    }
}

// Helper functions
function pad(num) {
    return num.toString().padStart(2, '0');
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Update log status display
function updateLogStatus(data) {
    const logStatus = document.getElementById('log-status');
    if (!logStatus) return;

    if (!data.running) {
        logStatus.innerHTML = '';
        return;
    }

    let statusHtml = '<div class="log-status-info">';

    // Log mode
    const modeText = {
        'none': '不记录',
        'errors': '仅异常',
        'all': '全部'
    }[data.log_mode] || data.log_mode;

    statusHtml += `<span>模式: ${modeText}</span>`;

    // Recording status
    if (data.recording && data.log_file) {
        const fileName = data.log_file.split('/').pop().split('\\').pop();
        statusHtml += ` | <span class="status-recording">● 记录中: ${fileName}</span>`;
        statusHtml += ` | <span>已记录: ${data.recorded_frames} 帧</span>`;
    } else if (data.log_mode !== 'none') {
        statusHtml += ` | <span>未记录</span>`;
    }

    statusHtml += '</div>';
    logStatus.innerHTML = statusHtml;
}

// Set log mode
async function setLogMode() {
    const select = document.getElementById('log-mode-select');
    const mode = select.value;

    try {
        const response = await fetch('/api/set_log_mode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: mode})
        });
        const data = await response.json();

        if (!data.success) {
            alert('设置日志模式失败: ' + (data.error || '未知错误'));
            // Revert to previous value
            await updateStatus();
        }
    } catch (error) {
        console.error('Failed to set log mode:', error);
        alert('设置日志模式失败: ' + error.message);
    }
}
