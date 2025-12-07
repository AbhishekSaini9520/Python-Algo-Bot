// Trading Bot Dashboard - Main JavaScript

// ✅ WEBSOCKET CONNECTION
const socket = io('http://localhost:5000');

let botData = {
    status: "DISCONNECTED",
    account_balance: 10000,
    floating_pnl: 0,
    open_positions: 0,
    total_trades: 0,
    winning_trades: 0,
    losing_trades: 0,
    win_rate: 0,
    active_positions: [],
    recent_trades: [],
    config: {}
};

// ✅ CONNECTION EVENTS
socket.on('connect', () => {
    console.log('✅ Connected to backend');
    updateSystemStatus('✅ Connected to backend', 'success');
});

socket.on('disconnect', () => {
    console.log('❌ Disconnected from backend');
    updateSystemStatus('❌ Disconnected from backend', 'error');
});

socket.on('initial_data', (data) => {
    console.log('📊 Initial data received:', data);
    botData = data;
    renderDashboard();
    updateSystemStatus('✅ All systems connected', 'success');
});

socket.on('bot_update', (data) => {
    console.log('🔄 Update received:', data);
    botData = data;
    renderDashboard();
    updateLastUpdate();
});

socket.on('error', (error) => {
    console.error('❌ WebSocket error:', error);
    updateSystemStatus('❌ Connection error: ' + error, 'error');
});

// ✅ RENDER FUNCTIONS

function renderDashboard() {
    updateStatusBar();
    updatePerformanceMetrics();
    renderActivePositions();
    renderRecentTrades();
    renderConfiguration();
}

function updateStatusBar() {
    // Status
    document.getElementById('status-text').textContent = botData.status || 'OFFLINE';
    
    // Account Balance
    document.getElementById('account-balance').textContent = 
        '$' + formatNumber(botData.account_balance || 0);
    
    // Floating P&L
    const pnlElement = document.getElementById('floating-pnl');
    const pnl = botData.floating_pnl || 0;
    pnlElement.textContent = (pnl >= 0 ? '+' : '') + '$' + formatNumber(pnl);
    pnlElement.style.color = pnl >= 0 ? '#10b981' : '#ef4444';
    
    // Open Positions
    document.getElementById('open-positions').textContent = 
        botData.open_positions || 0;
    
    // Win Rate
    const winRateEl = document.getElementById('win-rate');
    winRateEl.textContent = (botData.win_rate || 0) + '%';
    winRateEl.style.color = (botData.win_rate || 0) >= 50 ? '#10b981' : '#ef4444';
    
    // Total Trades
    document.getElementById('total-trades').textContent = 
        botData.total_trades || 0;
}

function updatePerformanceMetrics() {
    document.getElementById('stat-total-trades').textContent = botData.total_trades || 0;
    document.getElementById('stat-win-rate').textContent = (botData.win_rate || 0) + '%';
    document.getElementById('stat-winning').textContent = botData.winning_trades || 0;
    document.getElementById('stat-losing').textContent = botData.losing_trades || 0;
    
    const floatingPnl = botData.floating_pnl || 0;
    const floatingEl = document.getElementById('stat-floating-pnl');
    floatingEl.textContent = (floatingPnl >= 0 ? '+' : '') + '$' + formatNumber(floatingPnl);
    floatingEl.style.color = floatingPnl >= 0 ? '#10b981' : '#ef4444';
    
    document.getElementById('stat-balance').textContent = 
        '$' + formatNumber(botData.account_balance || 0);
}

function renderActivePositions() {
    const container = document.getElementById('active-positions-container');
    const positions = botData.active_positions || [];
    
    if (positions.length === 0) {
        container.innerHTML = '<p style="color: #94a3b8; text-align: center; padding: 20px;">No active positions</p>';
        return;
    }
    
    container.innerHTML = positions.map(pos => `
        <div class="trade-item ${pos.type === 'SELL' ? 'sell' : ''}">
            <div class="trade-header">
                <span class="trade-type ${pos.type === 'BUY' ? 'buy' : 'sell'}">${pos.type}</span>
                <span class="trade-time">${pos.timestamp || 'N/A'}</span>
            </div>
            <div class="trade-details">
                <strong>${pos.instrument}</strong> | ${pos.timeframe}<br>
                Entry: $${formatNumber(pos.entry || 0)} | SL: $${formatNumber(pos.sl || 0)} | TP: $${formatNumber(pos.tp || 0)}<br>
                <div class="trade-pnl ${pos.pnl >= 0 ? 'profit' : 'loss'}">
                    ${pos.pnl >= 0 ? '+' : ''}$${formatNumber(pos.pnl || 0)} (${((pos.pnl / pos.entry) * 100).toFixed(2)}%)
                </div>
            </div>
            <div class="instrument-tag">${pos.instrument}</div>
            <div class="position-badge open">OPEN</div>
        </div>
    `).join('');
}

function renderRecentTrades() {
    const container = document.getElementById('recent-trades-container');
    const trades = (botData.recent_trades || []).slice(0, 10);
    
    if (trades.length === 0) {
        container.innerHTML = '<p style="color: #94a3b8; text-align: center; padding: 20px;">No recent trades</p>';
        return;
    }
    
    container.innerHTML = trades.map(trade => `
        <div class="trade-item ${trade.type === 'SELL' ? 'sell' : ''}">
            <div class="trade-header">
                <span class="trade-type ${trade.type === 'BUY' ? 'buy' : 'sell'}">${trade.type}</span>
                <span class="trade-time">${trade.timestamp || 'N/A'} ${trade.status === 'CLOSED' ? '✅' : '⏳'}</span>
            </div>
            <div class="trade-details">
                ${trade.instrument} | ${trade.timeframe}<br>
                Entry: $${formatNumber(trade.entry || 0)} ${trade.status === 'CLOSED' ? `| Exit: $${formatNumber(trade.exit_price || 0)}` : ''}<br>
                <div class="trade-pnl ${trade.pnl >= 0 ? 'profit' : 'loss'}">
                    ${trade.pnl >= 0 ? '+' : ''}$${formatNumber(trade.pnl || 0)} (${((trade.pnl / trade.entry) * 100).toFixed(2)}%)
                </div>
            </div>
        </div>
    `).join('');
}

function renderConfiguration() {
    const container = document.getElementById('config-container');
    const config = botData.config || {};
    
    if (!config || Object.keys(config).length === 0) {
        container.innerHTML = '<p style="color: #94a3b8; grid-column: 1/-1;">Loading configuration...</p>';
        return;
    }
    
    container.innerHTML = `
        <div class="stat-box">
            <div class="stat-label">Max Lower Shadow</div>
            <div class="stat-value">${config.max_lower_shadow || 'N/A'}</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Min Upper Shadow</div>
            <div class="stat-value">${config.min_upper_shadow || 'N/A'}</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">BUY SL Multiplier</div>
            <div class="stat-value">${config.buy_sl_mult || 'N/A'}x ATR</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">BUY TP Multiplier</div>
            <div class="stat-value">${config.buy_tp_mult || 'N/A'}x ATR</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">SELL SL Multiplier</div>
            <div class="stat-value">${config.sell_sl_mult || 'N/A'}x ATR</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">SELL TP Multiplier</div>
            <div class="stat-value">${config.sell_tp_mult || 'N/A'}x ATR</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Instruments</div>
            <div class="stat-value" style="font-size: 0.9em;">${config.instruments || 'N/A'}</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Timeframes</div>
            <div class="stat-value" style="font-size: 0.9em;">${config.timeframes || 'N/A'}</div>
        </div>
    `;
}

function updateSystemStatus(message, type = 'info') {
    const statusEl = document.getElementById('system-status');
    const alertClass = type === 'success' ? 'alert-success' : 
                       type === 'error' ? 'alert-error' : 'alert-warning';
    
    statusEl.innerHTML = `
        <div class="alert ${alertClass}">
            ${message}
        </div>
    `;
}

function updateLastUpdate() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    document.getElementById('last-update').textContent = 
        `Last updated: ${timeString}`;
}

// ✅ UTILITY FUNCTIONS

function formatNumber(num) {
    return Math.abs(num).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function refreshPositions() {
    console.log('🔄 Refreshing positions...');
    socket.emit('request_update');
}

// ✅ INITIAL LOAD
console.log('🚀 Dashboard initialized');
console.log('📡 Connecting to WebSocket: http://localhost:5000');

// Request update on page load
setTimeout(() => {
    socket.emit('request_update');
}, 1000);

// Periodic update request (every 5 seconds)
setInterval(() => {
    if (socket.connected) {
        socket.emit('request_update');
    }
}, 5000);
