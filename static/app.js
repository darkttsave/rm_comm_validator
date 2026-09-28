// RM Communication Validator Web UI JavaScript
// Unified workflow: 数据源 (Demo / Replay / Live) → 当前会话 → Start / Stop

const $ = (id) => document.getElementById(id);

let selectedSource = null;      // 'demo' | 'replay' | 'live'
let transportType = 'socketcan'; // 'socketcan' | 'serial'
let endpoints = [];             // unified endpoint list
let simulator = null;           // simulator status from /api/status
let session = null;             // session info from /api/status
let selectedEndpointDevice = null;

document.addEventListener('DOMContentLoaded', () => {
    loadInitial();
    setupHandlers();
    setInterval(updateAll, 500);
});

async function getJSON(url, options) {
    const response = await fetch(url, options);
    return response.json();
}

async function postJSON(url, body) {
    return getJSON(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {})
    });
}

function setupHandlers() {
    $('btn-src-demo').addEventListener('click', () => selectSource('demo'));
    $('btn-src-replay').addEventListener('click', () => selectSource('replay'));
    $('btn-src-live').addEventListener('click', () => selectSource('live'));
    $('btn-start').addEventListener('click', start);
    $('btn-stop').addEventListener('click', stop);
    $('btn-simulator-start').addEventListener('click', startSimulator);
    $('btn-simulator-stop').addEventListener('click', stopSimulator);
    $('btn-refresh-endpoints').addEventListener('click', loadEndpoints);
    $('btn-refresh-interfaces').addEventListener('click', loadSocketCANInterfaces);
    $('chk-error-injection').addEventListener('change', toggleErrorInjection);
    $('log-mode-select').addEventListener('change', setLogMode);
    $('endpoint-select').addEventListener('change', onEndpointChange);
}

// ---- initialization ----

async function loadInitial() {
    try {
        const st = await getJSON('/api/status');
        transportType = st.transport_type || 'socketcan';
        if (st.protocol) {
            const name = st.protocol.split('/').pop().replace('.yaml', '');
            $('protocol-name').textContent = `协议: ${name}`;
        }
        loadLogFiles();
        if (transportType === 'serial') {
            await loadEndpoints();
        } else {
            await loadSocketCANInterfaces();
        }
    } catch (e) {
        console.error('Failed to load initial status:', e);
    }
}

// ---- source selection ----

function selectSource(src) {
    selectedSource = src;
    ['demo', 'replay', 'live'].forEach(s => {
        $('btn-src-' + s).classList.toggle('active', s === src);
    });

    // Show the relevant config panel
    $('config-replay').hidden = (src !== 'replay');
    $('config-live').hidden = (src !== 'live');

    if (src === 'replay') {
        loadLogFiles();
    } else if (src === 'live') {
        if (transportType === 'serial') {
            $('config-live-serial').hidden = false;
            $('config-live-can').hidden = true;
            loadEndpoints();
        } else {
            $('config-live-serial').hidden = true;
            $('config-live-can').hidden = false;
            loadSocketCANInterfaces();
        }
    }

    updateSessionPreview();
}

function updateSessionPreview() {
    // Only update when idle (running state is driven by status polling).
    if (session && session.status === 'running') return;
    const label = selectedSource ? `已选择: ${selectedSource.toUpperCase()}` : '就绪';
    $('session-text').textContent = label;
}

// ---- start / stop ----

async function start() {
    if (!selectedSource) {
        alert('请先选择数据源 (Demo / Replay / Live)');
        return;
    }

    if (selectedSource === 'demo') {
        const r = await postJSON('/api/start_demo');
        if (!r.success) alert('启动 Demo 失败');
        return;
    }

    if (selectedSource === 'replay') {
        const path = $('replay-file-select').value;
        if (!path) { alert('请选择一个日志文件'); return; }
        const r = await postJSON('/api/start_replay', { path });
        if (!r.success) alert('启动 Replay 失败: ' + (r.error || '未知错误'));
        return;
    }

    if (selectedSource === 'live') {
        await startLive();
    }
}

async function startLive() {
    if (transportType === 'serial') {
        const device = $('endpoint-select').value;
        if (!device) { alert('请选择一个 Endpoint'); return; }
        const ep = endpoints.find(e => e.device === device);
        const kind = ep ? ep.kind : 'physical';

        if (kind === 'virtual' && !(simulator && simulator.running)) {
            alert('虚拟串口尚未就绪，请先点击 "Start Simulator"');
            return;
        }

        const baudrate = parseInt($('serial-baudrate').value, 10);
        if (!baudrate || baudrate < 300 || baudrate > 115200) {
            alert('请输入有效的波特率 (300-115200)');
            return;
        }

        const r = await postJSON('/api/start_live_serial', {
            port: device,
            baudrate,
            label: ep ? ep.label : device
        });
        if (!r.success) {
            showLiveError(r);
        } else {
            hideLiveError();
        }
        return;
    }

    // SocketCAN
    const iface = $('live-interface-select').value;
    if (!iface) { alert('请选择一个 SocketCAN 接口'); return; }
    const r = await postJSON('/api/start_live', { interface: iface });
    if (!r.success) {
        alert('启动 Live 失败: ' + (r.error || '未知错误'));
    }
}

async function stop() {
    await postJSON('/api/stop');
    hideLiveError();
}

// ---- live error display ----

function showLiveError(r) {
    const box = $('live-error');
    let html = `<div class="status-error">✗ ${r.error || '连接失败'}</div>`;
    if (r.causes && r.causes.length) {
        html += '<div class="error-causes"><div class="error-causes-title">可能原因：</div><ul>';
        r.causes.forEach(c => { html += `<li>${c}</li>`; });
        html += '</ul></div>';
    }
    if (r.detail) {
        html += `<div class="error-detail">诊断信息：${r.detail}</div>`;
    }
    box.innerHTML = html;
    box.hidden = false;
}

function hideLiveError() {
    $('live-error').hidden = true;
    $('live-error').innerHTML = '';
}

// ---- endpoints (serial) ----

async function loadEndpoints() {
    try {
        const data = await getJSON('/api/serial_endpoints');
        endpoints = data.endpoints || [];
        const virtual = data.virtual || {};

        const select = $('endpoint-select');
        const prev = selectedEndpointDevice || select.value;
        select.innerHTML = '';

        // Group virtual vs physical
        const virtualEps = endpoints.filter(e => e.kind === 'virtual');
        const physicalEps = endpoints.filter(e => e.kind === 'physical');

        if (virtualEps.length) {
            const og = document.createElement('optgroup');
            og.label = '模拟设备';
            virtualEps.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.device;
                opt.textContent = e.available ? e.label : `${e.label} (不可用)`;
                opt.disabled = !e.available;
                og.appendChild(opt);
            });
            select.appendChild(og);
        }

        if (physicalEps.length) {
            const og = document.createElement('optgroup');
            og.label = '物理设备';
            physicalEps.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.device;
                opt.textContent = e.label;
                og.appendChild(opt);
            });
            select.appendChild(og);
        }

        if (!physicalEps.length) {
            const og = document.createElement('optgroup');
            og.label = '物理设备';
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = '未检测到物理串口';
            opt.disabled = true;
            og.appendChild(opt);
            select.appendChild(og);
        }

        if (prev && endpoints.some(e => e.device === prev)) {
            select.value = prev;
        } else {
            selectedEndpointDevice = select.value;
        }

        renderSimulatorControls(virtual);
    } catch (e) {
        console.error('Failed to load endpoints:', e);
    }
}

function onEndpointChange() {
    selectedEndpointDevice = $('endpoint-select').value;
    const ep = endpoints.find(e => e.device === selectedEndpointDevice);
    // Simulator panel visibility is controlled by transport type, not endpoint kind,
    // since virtual is always one of the options. Keep always visible for serial.
}

function renderSimulatorControls(virtual) {
    simulator = virtual;
    const statusEl = $('simulator-status');

    if (!virtual.socat_installed) {
        statusEl.className = 'status-warning';
        statusEl.textContent = 'Virtual Serial unavailable: socat is not installed. sudo apt install socat';
        $('btn-simulator-start').disabled = true;
        $('btn-simulator-stop').disabled = true;
        return;
    }

    $('btn-simulator-start').disabled = false;
    $('btn-simulator-stop').disabled = false;

    if (virtual.running) {
        statusEl.className = 'status-connected';
        statusEl.textContent = '● RM Virtual Serial Ready';
    } else if (virtual.status === 'starting') {
        statusEl.className = 'status-warning';
        statusEl.textContent = '● 启动中...';
    } else if (virtual.status === 'error') {
        statusEl.className = 'status-error';
        statusEl.textContent = `✗ ${virtual.error || '模拟器错误'}`;
    } else {
        statusEl.className = 'status-warning';
        statusEl.textContent = '○ 未运行';
    }
}

async function startSimulator() {
    $('simulator-status').className = 'status-warning';
    $('simulator-status').textContent = '● 启动中...';
    const r = await postJSON('/api/simulator/start');
    if (!r.success) {
        $('simulator-status').className = 'status-error';
        $('simulator-status').textContent = '✗ ' + (r.error || '启动失败');
    }
    await loadEndpoints();
}

async function stopSimulator() {
    await postJSON('/api/simulator/stop');
    await loadEndpoints();
}

// ---- SocketCAN interfaces ----

async function loadSocketCANInterfaces() {
    try {
        const data = await getJSON('/api/socketcan_interfaces');
        const select = $('live-interface-select');
        select.innerHTML = '';
        (data.interfaces || []).forEach(iface => {
            const opt = document.createElement('option');
            opt.value = iface;
            opt.textContent = iface;
            if (iface === data.default) opt.selected = true;
            select.appendChild(opt);
        });

        const status = $('live-status');
        if (!(data.interfaces || []).length) {
            status.innerHTML = '<span class="status-warning">⚠ 无可用 SocketCAN 接口</span>';
        } else {
            status.innerHTML = '';
        }
    } catch (e) {
        console.error('Failed to load SocketCAN interfaces:', e);
    }
}

// ---- periodic status ----

async function updateAll() {
    await updateStatus();
    await updateMessages();
    await updateRates();
    await updateEvents();
}

async function updateStatus() {
    try {
        const st = await getJSON('/api/status');
        session = st.session || {};
        const running = st.running;

        // runtime
        $('runtime').textContent = formatRuntime(st.runtime);

        // statistics
        $('stat-total').textContent = st.statistics.total;
        $('stat-valid').textContent = st.statistics.valid;
        $('stat-invalid').textContent = st.statistics.invalid;
        $('stat-unknown').textContent = st.statistics.unknown;

        renderSession(st);

        // buttons
        $('btn-start').disabled = running;
        $('btn-stop').disabled = !running;
        ['demo', 'replay', 'live'].forEach(s => { $('btn-src-' + s).disabled = running; });
        $('log-mode-select').disabled = running;
        $('log-mode-select').value = st.log_mode;

        // error injection checkbox (Demo only, but keep synced)
        $('chk-error-injection').checked = st.error_injection;

        updateLogStatus(st);

        // simulator + endpoints (serial transport)
        if (transportType === 'serial' && st.simulator) {
            simulator = st.simulator;
            renderSimulatorControls(st.simulator);
        }
    } catch (e) {
        console.error('Failed to update status:', e);
    }
}

function renderSession(st) {
    const s = st.session || {};
    const textEl = $('session-text');
    const statusEl = $('session-status');

    if (st.running) {
        let text = '';
        if (s.mode === 'demo') text = 'Demo';
        else if (s.mode === 'replay') text = 'Replay';
        else if (s.mode === 'live') {
            if (transportType === 'serial') {
                text = `Live / ${s.endpoint_label || s.endpoint || ''} / ${s.baudrate || ''}`;
            } else {
                text = `Live / SocketCAN / ${s.interface || ''}`;
            }
        }
        textEl.textContent = text;
        statusEl.textContent = '● Running';
        statusEl.className = 'session-status-running';
    } else if (s.status === 'error' && s.last_error) {
        textEl.textContent = s.last_error;
        statusEl.textContent = '● Error';
        statusEl.className = 'session-status-error';
    } else {
        textEl.textContent = selectedSource ? `已选择: ${selectedSource.toUpperCase()}` : '就绪';
        statusEl.textContent = '● Idle';
        statusEl.className = 'session-status-idle';
    }
}

// ---- messages ----

async function updateMessages() {
    try {
        const messages = await getJSON('/api/messages');
        const container = $('messages-container');
        if (Object.keys(messages).length === 0) {
            container.innerHTML = '<p class="no-data">等待数据...</p>';
            return;
        }
        container.innerHTML = '';
        for (const [name, data] of Object.entries(messages)) {
            container.appendChild(createMessageCard(name, data));
        }
    } catch (e) {
        console.error('Failed to update messages:', e);
    }
}

function createMessageCard(name, data) {
    const card = document.createElement('div');
    card.className = `message-card ${data.all_passed ? 'valid' : 'invalid'}`;

    const header = document.createElement('div');
    header.className = 'message-header';
    let infoStr = '';
    if (data.can_id) infoStr = `${data.can_id} | DLC=${data.dlc}`;
    else if (data.frame_length) infoStr = `${name} | LEN=${data.frame_length}`;
    header.innerHTML = `<span class="message-name">${name}</span><span class="message-info">${infoStr}</span>`;
    card.appendChild(header);

    const fields = document.createElement('div');
    fields.className = 'message-fields';
    for (const [fieldName, fieldValue] of Object.entries(data.fields)) {
        const item = document.createElement('div');
        item.className = 'field-item';
        let display = fieldValue;
        if (typeof fieldValue === 'number') display = fieldValue.toFixed(4);
        item.innerHTML = `<span class="field-name">${fieldName}</span><span class="field-value">${display}</span>`;
        fields.appendChild(item);
    }
    card.appendChild(fields);

    const validation = document.createElement('div');
    validation.className = 'validation-section';
    validation.innerHTML = '<div class="validation-title">验证</div>';
    for (const v of data.validation) {
        const item = document.createElement('div');
        item.className = 'validation-item';
        const icon = v.passed ? '✓' : '✗';
        const cls = v.passed ? 'pass' : 'fail';
        item.innerHTML = `<span class="validation-icon ${cls}">${icon}</span><span>${v.check}: ${v.message}</span>`;
        validation.appendChild(item);
    }
    card.appendChild(validation);

    const raw = document.createElement('div');
    raw.className = 'raw-section';
    raw.innerHTML = `<div class="raw-title">RAW HEX</div><div class="raw-data">${data.raw}</div>`;
    card.appendChild(raw);

    return card;
}

// ---- rates / events ----

async function updateRates() {
    try {
        const rates = await getJSON('/api/rates');
        const container = $('rates-container');
        container.innerHTML = '';
        for (const [k, rate] of Object.entries(rates)) {
            const item = document.createElement('div');
            item.className = 'rate-item';
            item.innerHTML = `<span class="rate-label">${k}</span><span class="rate-value">${rate} Hz</span>`;
            container.appendChild(item);
        }
    } catch (e) {
        console.error('Failed to update rates:', e);
    }
}

async function updateEvents() {
    try {
        const events = await getJSON('/api/events');
        const container = $('events-container');
        if (!events.length) {
            container.innerHTML = '<p class="no-data">无事件</p>';
            return;
        }
        container.innerHTML = '';
        for (const ev of events) {
            const item = document.createElement('div');
            item.className = 'event-item';
            item.textContent = ev;
            container.appendChild(item);
        }
    } catch (e) {
        console.error('Failed to update events:', e);
    }
}

// ---- log files ----

async function loadLogFiles() {
    try {
        const logs = await getJSON('/api/list_logs');
        const select = $('replay-file-select');
        select.innerHTML = '<option value="">-- 选择日志文件 --</option>';
        for (const log of logs) {
            const opt = document.createElement('option');
            opt.value = log.path;
            opt.textContent = `${log.name} (${formatBytes(log.size)})`;
            select.appendChild(opt);
        }
    } catch (e) {
        console.error('Failed to load log files:', e);
    }
}

// ---- misc controls ----

async function toggleErrorInjection() {
    await postJSON('/api/toggle_error_injection');
}

async function setLogMode() {
    const mode = $('log-mode-select').value;
    const r = await postJSON('/api/set_log_mode', { mode });
    if (!r.success) {
        alert('设置日志模式失败: ' + (r.error || '未知错误'));
        await updateStatus();
    }
}

function updateLogStatus(st) {
    const el = $('log-status');
    if (!st.running) { el.innerHTML = ''; return; }
    const modeText = { none: '不记录', errors: '仅异常', all: '全部' }[st.log_mode] || st.log_mode;
    let html = `<div class="log-status-info"><span>模式: ${modeText}</span>`;
    if (st.recording && st.log_file) {
        const name = st.log_file.split('/').pop().split('\\').pop();
        html += ` | <span class="status-recording">● 记录中: ${name}</span>`;
        html += ` | <span>已记录: ${st.recorded_frames} 帧</span>`;
    } else if (st.log_mode !== 'none') {
        html += ` | <span>未记录</span>`;
    }
    html += '</div>';
    el.innerHTML = html;
}

// ---- helpers ----

function pad(n) { return n.toString().padStart(2, '0'); }

function formatRuntime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
