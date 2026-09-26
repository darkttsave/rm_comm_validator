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
    document.getElementById('btn-live').addEventListener('click', showLiveWarning);
    document.getElementById('btn-stop').addEventListener('click', stopMonitoring);
    document.getElementById('chk-error-injection').addEventListener('change', toggleErrorInjection);
    document.getElementById('btn-start-replay').addEventListener('click', startReplay);
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

        // Load log files for replay
        loadLogFiles();
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
        document.getElementById('btn-stop').disabled = !data.running;

        // Update error injection checkbox
        document.getElementById('chk-error-injection').checked = data.error_injection;

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
    header.innerHTML = `
        <span class="message-name">${name}</span>
        <span class="message-info">${data.can_id} DLC=${data.dlc}</span>
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

// Show live warning
function showLiveWarning() {
    alert('Live SocketCAN 监控需要 Linux 环境。\n\n当前 Windows 环境不支持。\n请使用 Demo 或 Replay 模式。');
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
