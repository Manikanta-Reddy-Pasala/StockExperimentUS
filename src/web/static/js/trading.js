/**
 * Trading.js - Shared utilities for v2 UI
 */
const Trading = {
    // ---- API wrapper ----
    async api(url, options = {}) {
        const defaults = {
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            credentials: 'same-origin'
        };
        if (options.body && typeof options.body === 'object') {
            options.body = JSON.stringify(options.body);
        }
        try {
            const resp = await fetch(url, { ...defaults, ...options });
            if (resp.status === 401) {
                window.location.href = '/login';
                return { success: false, error: 'Unauthorized' };
            }
            const data = await resp.json();
            if (!resp.ok && !data.error) data.error = `HTTP ${resp.status}`;
            return data;
        } catch (err) {
            console.error('API error:', err);
            return { success: false, error: err.message };
        }
    },

    // ---- Formatters ----
    formatINR(amount) {
        if (amount == null || isNaN(amount)) return '--';
        const abs = Math.abs(amount);
        const sign = amount < 0 ? '-' : '';
        if (abs >= 10000000) return sign + '\u20B9' + (abs / 10000000).toFixed(2) + ' Cr';
        if (abs >= 100000) return sign + '\u20B9' + (abs / 100000).toFixed(2) + ' L';
        return sign + '\u20B9' + abs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },

    formatPct(pct) {
        if (pct == null || isNaN(pct)) return '--';
        return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
    },

    formatPrice(price) {
        if (price == null || isNaN(price)) return '--';
        return '\u20B9' + Number(price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },

    // ---- P&L helpers ----
    pnlClass(value) {
        if (value == null || value === 0) return 'text-secondary';
        return value > 0 ? 'text-success' : 'text-danger';
    },

    pnlBg(value) {
        if (value == null || value === 0) return '';
        return value > 0 ? 'table-success' : 'table-danger';
    },

    // ---- Signal strength: EMA 200/400 crossover. Score 100=Entry1, 90=Entry2 ----
    getSignalStrength(stock) {
        const rec = (stock.recommendation || '').toUpperCase();
        const score = stock.selection_score || 0;
        const stage1 = score >= 100;

        if (rec === 'BUY')
            return stage1
                ? { label: 'STRONG BUY', cls: 'bg-success', icon: 'bi-arrow-up-circle-fill' }
                : { label: 'BUY', cls: 'bg-success bg-opacity-75', icon: 'bi-arrow-up-circle' };
        if (rec === 'SELL' || rec === 'SHORT')
            return stage1
                ? { label: 'STRONG SELL', cls: 'bg-danger', icon: 'bi-arrow-down-circle-fill' }
                : { label: 'SELL', cls: 'bg-danger bg-opacity-75', icon: 'bi-arrow-down-circle' };
        return { label: 'NEUTRAL', cls: 'bg-secondary', icon: 'bi-dash-circle' };
    },

    // ---- Trading actions ----
    async paperBuy(symbol, quantity) {
        return this.api('/api/mock-trading/order', {
            method: 'POST',
            body: { symbol, quantity: parseInt(quantity) }
        });
    },

    async liveBuy(symbol, quantity) {
        return this.api('/api/unified/orders/place', {
            method: 'POST',
            body: {
                symbol: `NSE:${symbol}-EQ`,
                qty: parseInt(quantity),
                type: 2, // market
                side: 1, // buy
                productType: 'CNC'
            }
        });
    },

    async closePosition(positionId) {
        return this.api(`/api/auto-trading/paper-trading/positions/${positionId}/close`, {
            method: 'POST'
        });
    },

    // ---- Chart.js equity curve helper ----
    createEquityChart(canvasId, labels, values, label = 'Portfolio Value') {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        const gradient = ctx.getContext('2d');
        const fill = gradient.createLinearGradient(0, 0, 0, 300);
        const isPositive = values.length > 0 && values[values.length - 1] >= values[0];
        if (isPositive) {
            fill.addColorStop(0, 'rgba(34, 197, 94, 0.3)');
            fill.addColorStop(1, 'rgba(34, 197, 94, 0.01)');
        } else {
            fill.addColorStop(0, 'rgba(248, 113, 113, 0.3)');
            fill.addColorStop(1, 'rgba(248, 113, 113, 0.01)');
        }

        return new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label,
                    data: values,
                    borderColor: isPositive ? '#22c55e' : '#f87171',
                    backgroundColor: fill,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    datalabels: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => Trading.formatINR(ctx.parsed.y)
                        }
                    }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8, font: { size: 11 } } },
                    y: {
                        grid: { color: 'rgba(0,0,0,0.05)' },
                        ticks: { callback: v => Trading.formatINR(v), font: { size: 11 } }
                    }
                },
                interaction: { intersect: false, mode: 'index' }
            }
        });
    },

    // ---- Monthly P&L bar chart ----
    createMonthlyPnlChart(canvasId, labels, values) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        const colors = values.map(v => v >= 0 ? '#22c55e' : '#f87171');
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Monthly P&L',
                    data: values,
                    backgroundColor: colors,
                    borderRadius: 6,
                    borderSkipped: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, datalabels: { display: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { callback: v => Trading.formatINR(v) } }
                }
            }
        });
    },

    // ---- Toast notifications ----
    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const icons = { success: 'bi-check-circle-fill', danger: 'bi-x-circle-fill', warning: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill' };
        const id = 'toast-' + Date.now();
        const html = `
            <div id="${id}" class="toast align-items-center text-bg-${type} border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body"><i class="bi ${icons[type] || icons.info} me-2"></i>${message}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>`;
        container.insertAdjacentHTML('beforeend', html);
        const el = document.getElementById(id);
        const bsToast = new bootstrap.Toast(el, { delay: 4000 });
        bsToast.show();
        el.addEventListener('hidden.bs.toast', () => el.remove());
    },

    // ---- Utility: days ago label ----
    daysAgoLabel(dateStr) {
        if (!dateStr) return '--';
        const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
        if (diff === 0) return 'Today';
        if (diff === 1) return '1 day';
        return diff + ' days';
    }
};
