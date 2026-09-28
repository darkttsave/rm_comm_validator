// RM Communication Validator Web UI JavaScript
// Unified Transport/Protocol/Endpoint workflow

const $ = (id) => document.getElementById(id);

let runtimeMode = 'normal';
let selectedSource = null;
let selectedTransport = null;
let selectedProtocol = null;
let selectedEndpoint = null;
let allProtocols = [];
let endpoints = [];
let running = false;

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
    $('transport-select').addEventListener('change', onTransportChange);
    $('protocol-select').addEventListener('change', onProtocolChange);
    $('endpoint-select').addEventListener('change', onEndpointChange);
    $('btn-refresh-endpoint').addEventListener('click', refreshEndpoints);
    $('chk-error-injection').addEventListener('change', toggleErrorInjection);
    $('log-mode-select').addEventListener('change', setLogMode);
}

// ---- initialization ----

async function loadInitial() {
    try {
        // Load runtime mode
        const rt = await getJSON('/api/runtime');
        runtimeMode = rt.mode;
        updateRuntimeBadge();

        // Load protocols
        const protocolsData = await getJSON('/api/protocols');
        allProtocols = protocolsData.protocols || [];

        // Get current status
        const st = await getJSON('/api/status');

        // Initialize transport selector
        const transports = [...new Set(allProtocols.map(p => p.transport))];
        const transportSelect = $('transport-select');
        transportSelect.innerHTML = '';
        for (const t of transports) {
            const opt = document.createElement('option');
            opt.value = t;
            opt.textContent = t === 'socketcan' ? 'CAN' : t === 'serial' ? 'Serial' : t;
            transportSelect.appendChild(opt);
        }

        // Set current transport from status
        if (st.transport_type) {
            selectedTransport = st.transport_type;
            transportSelect.value = st.transport_type;
            await onTransportChange();

            // Set current protocol
            if (st.protocol_id) {
                $('protocol-select').value = st.protocol_id;
                selectedProtocol = st.protocol_id;
                await onProtocolChange();
            }
        }

        loadLogFiles();
    } catch (e) {
        console.error('Failed to load initial data:', e);
    }
}

function updateRuntimeBadge() {
    const badge = $('runtime-badge');
    const modeEl = $('runtime-mode');
    if (runtimeMode === 'simulation') {
        badge.className = 'runtime-badge runtime-simulation';
        modeEl.textContent = 'Simulation';
    } else {
        badge.className = 'runtime-badge runtime-normal';
        modeEl.textContent = 'Normal';
    }
}

// ---- source selection ----

function selectSource(src) {
    if (running) return;
    selectedSource = src;
    ['demo', 'replay', 'live'].forEach(s => {
        $('btn-src-' + s).classList.toggle('active', s === src);
    });

    $('config-replay').hidden = (src !== 'replay');
    $('config-live').hidden = (src !== 'live');

    if (src === 'replay') {
        loadLogFiles();
    }
}

// ---- transport / protocol / endpoint ----

async function onTransportChange() {
    if (running) return;
    selectedTransport = $('transport-select').value;

    // Filter protocols by transport
    const protocols = allProtocols.filter(p => p.transport === selectedTransport);
    const protocolSelect = $('protocol-select');
    protocolSelect.innerHTML = '';

    if (protocols.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '-- No protocols available --';
        opt.disabled = true;
        protocolSelect.appendChild(opt);
        selectedProtocol = null;
        return;
    }

    for (const p of protocols) {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        protocolSelect.appendChild(opt);
    }

    // Auto-select first protocol
    selectedProtocol = protocols[0].id;
    protocolSelect.value = selectedProtocol;
    await onProtocolChange();
}

async function onProtocolChange() {
    if (running) return;
    selectedProtocol = $('protocol-select').value;

    if (!selectedProtocol) {
        $('endpoint-select').innerHTML = '<option value="">-- Select Protocol first --</option>';
        return;
    }

    // Load the protocol
    const result = await postJSON('/api/load_protocol', { protocol_id: selectedProtocol });
    if (!result.success) {
        alert('Failed to load protocol: ' + result.error);
        return;
    }

    // Update current transport
    selectedTransport = result.transport;

    // Show/hide baudrate for serial
    $('baudrate-row').hidden = (selectedTransport !== 'serial');

    // Load endpoints for this transport
    await refreshEndpoints();
}

async function refreshEndpoints() {
    if (!selectedTransport) return;

    const apiUrl = selectedTransport === 'serial' ? '/api/serial_endpoints' : '/api/can_endpoints';
    const data = await getJSON(apiUrl);
    endpoints = data.endpoints || [];

    const select = $('endpoint-select');
    select.innerHTML = '';

    if (endpoints.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '-- No endpoints available --';
        opt.disabled = true;
        select.appendChild(opt);
        return;
    }

    // Group virtual vs physical
    const virtualEps = endpoints.filter(e => e.kind === 'virtual');
    const physicalEps = endpoints.filter(e => e.kind === 'physical');

    if (virtualEps.length > 0) {
        const og = document.createElement('optgroup');
        og.label = '模拟设备';
        for (const e of virtualEps) {
            const opt = document.createElement('option');
            const key = e.interface || e.device;
            opt.value = key;
            opt.textContent = e.available ? e.label : `${e.label} (不可用)`;
            opt.disabled = !e.available;
            opt.dataset.kind = e.kind;
            opt.dataset.label = e.label;
            og.appendChild(opt);
        }
        select.appendChild(og);
    }

    if (physicalEps.length > 0) {
        const og = document.createElement('optgroup');
        og.label = '物理设备';
        for (const e of physicalEps) {
            const opt = document.createElement('option');
            const key = e.interface || e.device;
            opt.value = key;
            opt.textContent = e.label;
            opt.dataset.kind = e.kind;
            opt.dataset.label = e.label;
            og.appendChild(opt);
        }
        select.appendChild(og);
    }

    // Auto-select first available endpoint
    const firstAvailable = endpoints.find(e => e.available);
    if (firstAvailable) {
        const key = firstAvailable.interface || firstAvailable.device;
        select.value = key;
        selectedEndpoint = key;
    }
}

function onEndpointChange() {
    selectedEndpoint = $('endpoint-select').value;
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
    if (!selectedTransport || !selectedProtocol || !selectedEndpoint) {
        alert('请选择 Transport / Protocol / Endpoint');
        return;
    }

    const select = $('endpoint-select');
    const selectedOpt = select.options[select.selectedIndex];
    const kind = selectedOpt ? selectedOpt.dataset.kind : 'physical';
    const label = selectedOpt ? selectedOpt.dataset.label : selectedEndpoint;

    let result;
    if (selectedTransport === 'serial') {
        const baudrate = parseInt($('serial-baudrate').value, 10);
        if (!baudrate || baudrate < 300 || baudrate > 115200) {
            alert('请输入有效的波特率 (300-115200)');
            return;
        }
        result = await postJSON('/api/start_live_serial', {
            port: selectedEndpoint,
            baudrate,
            label,
            kind
        });
    } else {
        result = await postJSON('/api/start_live', {
            interface: selectedEndpoint,
            label,
            kind
        });
    }

    if (!result.success) {
        showLiveError(result);
    } else {
        hideLiveError();
    }
}

async function stop() {
    await postJSON('/api/stop');
    hideLiveError();
}

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
        running = st.running;

        // Runtime
        $('runtime-display').textContent = formatRuntime(st.runtime);

        // Statistics
        $('stat-total').textContent = st.statistics.total;
        $('stat-valid').textContent = st.statistics.valid;
        $('stat-invalid').textContent = st.statistics.invalid;
        $('stat-unknown').textContent = st.statistics.unknown;

        renderSession(st);

        // Lock controls when running
        $('btn-start').disabled = running;
        $('btn-stop').disabled = !running;
        ['demo', 'replay', 'live'].forEach(s => { $('btn-src-' + s).disabled = running; });
        $('transport-select').disabled = running;
        $('protocol-select').disabled = running;
        $('endpoint-select').disabled = running;
        $('btn-refresh-endpoint').disabled = running;
        $('serial-baudrate').disabled = running;
        $('log-mode-select').disabled = running;
        $('log-mode-select').value = st.log_mode;

        $('chk-error-injection').checked = st.error_injection;

        updateLogStatus(st);
    } catch (e) {
        console.error('Failed to update status:', e);
    }
}

function renderSession(st) {
    const s = st.session || {};
    const textEl = $('session-text');
    const statusEl = $('session-status');
    const backendEl = $('session-backend');

    if (running) {
        let text = '';
        if (s.mode === 'demo') {
            text = 'Demo';
        } else if (s.mode === 'replay') {
            text = 'Replay';
        } else if (s.mode === 'live') {
            const transport = s.transport === 'socketcan' ? 'CAN' : 'Serial';
            const protocol = s.protocol || '';
            const endpoint = s.endpoint_label || s.endpoint || '';
            const baudrate = s.baudrate ? ` @ ${s.baudrate}` : '';
            text = `Live / ${transport} / ${protocol} / ${endpoint}${baudrate}`;
        }
        textEl.textContent = text;
        statusEl.textContent = '● Running';
        statusEl.className = 'session-status-running';

        // Show backend status for virtual endpoints
        if (s.endpoint_kind === 'virtual') {
            const serialSim = st.serial_simulator || {};
            const canSim = st.can_simulator || {};
            let backend = '';
            if (s.transport === 'serial' && serialSim.running) {
                backend = '● Mock Gimbal running';
            } else if (s.transport === 'socketcan' && canSim.running) {
                backend = '● Mock EC running';
            }
            if (backend) {
                backendEl.textContent = backend;
                backendEl.hidden = false;
            } else {
                backendEl.hidden = true;
            }
        } else {
            backendEl.hidden = true;
        }
    } else if (s.status === 'error' && s.last_error) {
        textEl.textContent = s.last_error;
        statusEl.textContent = '● Error';
        statusEl.className = 'session-status-error';
        backendEl.hidden = true;
    } else {
        textEl.textContent = selectedSource ? `已选择: ${selectedSource.toUpperCase()}` : '就绪 Ready';
        statusEl.textContent = '● Idle';
        statusEl.className = 'session-status-idle';
        backendEl.hidden = true;
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
