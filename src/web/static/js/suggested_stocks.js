/**
 * Suggested Stocks V2 - Triple Model View JavaScript
 * Handles loading and displaying predictions from all three models
 */

// Global state
let currentData = {};
let currentModelType = null;
let currentStrategy = null;
let currentSymbol = null;

// Load all data on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Suggested Stocks V2 loading...');
    loadTripleModelData();

    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', function() {
        loadTripleModelData();
    });
});

/**
 * Load data for all three models from API
 */
async function loadTripleModelData() {
    try {
        console.log('📡 Fetching triple model data...');

        const response = await fetch('/api/suggested-stocks/triple-model-view?limit=50');

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Failed to load data');
        }

        console.log('✅ Data loaded successfully:', result);

        // Store data globally
        currentData = result.data;

        // Update UI
        updateDateBadge(result.date);
        updateCounts(result.data);
        populateAllTables(result.data);

    } catch (error) {
        console.error('❌ Error loading data:', error);
        showError('Failed to load stock suggestions. Please try again.');
    }
}

/**
 * Update date badge
 */
function updateDateBadge(dateStr) {
    const badge = document.getElementById('data-date-badge');
    if (badge) {
        badge.textContent = `Data as of: ${dateStr}`;
    }
}

/**
 * Update stock counts in header cards
 */
function updateCounts(data) {
    // Traditional ML
    const tradCount = (data.traditional?.default_risk?.length || 0) +
                     (data.traditional?.high_risk?.length || 0);
    document.getElementById('trad-count').textContent = tradCount;

    // Raw LSTM
    const lstmCount = (data.raw_lstm?.default_risk?.length || 0) +
                     (data.raw_lstm?.high_risk?.length || 0);
    document.getElementById('lstm-count').textContent = lstmCount;

    // Kronos
    const kronosCount = (data.kronos?.default_risk?.length || 0) +
                       (data.kronos?.high_risk?.length || 0);
    document.getElementById('kronos-count').textContent = kronosCount;
}

/**
 * Populate all tables with data
 */
function populateAllTables(data) {
    // Traditional ML
    populateTable('traditional', 'default_risk', data.traditional?.default_risk || []);
    populateTable('traditional', 'high_risk', data.traditional?.high_risk || []);

    // Raw LSTM
    populateTable('raw_lstm', 'default_risk', data.raw_lstm?.default_risk || []);
    populateTable('raw_lstm', 'high_risk', data.raw_lstm?.high_risk || []);

    // Kronos
    populateTable('kronos', 'default_risk', data.kronos?.default_risk || []);
    populateTable('kronos', 'high_risk', data.kronos?.high_risk || []);
}

/**
 * Populate a specific table
 */
function populateTable(modelType, strategy, stocks) {
    // Map table IDs
    const tableIdMap = {
        'traditional': {
            'default_risk': 'traditional-default-table',
            'high_risk': 'traditional-high-table'
        },
        'raw_lstm': {
            'default_risk': 'lstm-default-table',
            'high_risk': 'lstm-high-table'
        },
        'kronos': {
            'default_risk': 'kronos-default-table',
            'high_risk': 'kronos-high-table'
        }
    };

    const badgeIdMap = {
        'traditional': {
            'default_risk': 'trad-default-badge',
            'high_risk': 'trad-high-badge'
        },
        'raw_lstm': {
            'default_risk': 'lstm-default-badge',
            'high_risk': 'lstm-high-badge'
        },
        'kronos': {
            'default_risk': 'kronos-default-badge',
            'high_risk': 'kronos-high-badge'
        }
    };

    const tableId = tableIdMap[modelType]?.[strategy];
    const badgeId = badgeIdMap[modelType]?.[strategy];

    if (!tableId) {
        console.error(`Table ID not found for ${modelType}/${strategy}`);
        return;
    }

    const tbody = document.querySelector(`#${tableId} tbody`);
    const badge = document.getElementById(badgeId);

    if (!tbody) {
        console.error(`Table body not found: ${tableId}`);
        return;
    }

    // Update badge
    if (badge) {
        badge.textContent = stocks.length;
    }

    // Clear existing rows
    tbody.innerHTML = '';

    // Add rows
    if (stocks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">No stocks available for this strategy</td></tr>';
        return;
    }

    stocks.forEach((stock, index) => {
        const row = createStockRow(stock, index + 1);
        tbody.appendChild(row);
    });

    console.log(`✅ Populated ${modelType}/${strategy}: ${stocks.length} stocks`);
}

/**
 * Create a table row for a stock
 */
function createStockRow(stock, rank) {
    const tr = document.createElement('tr');

    // Clean symbol (remove NSE: prefix)
    const cleanSymbol = stock.symbol.replace('NSE:', '').replace('-EQ', '');

    // Format values
    const score = stock.selection_score ? stock.selection_score.toFixed(1) : '0.0';
    const target = stock.target_price ? `₹${stock.target_price.toFixed(2)}` : '-';
    const rec = stock.recommendation || 'HOLD';

    // Recommendation badge color
    const recColor = rec === 'BUY' ? 'success' : rec === 'SELL' ? 'danger' : 'secondary';

    tr.innerHTML = `
        <td>${rank}</td>
        <td><span class="badge bg-light text-dark">${cleanSymbol}</span></td>
        <td class="small">${stock.stock_name || cleanSymbol}</td>
        <td><span class="badge bg-primary">${score}</span></td>
        <td class="text-success fw-bold">${target}</td>
        <td><span class="badge bg-${recColor}">${rec}</span></td>
        <td>
            <button class="btn btn-sm btn-success" onclick="buyStock('${stock.symbol}')">
                <i class="bi bi-cart-plus"></i> Buy
            </button>
        </td>
    `;

    return tr;
}

/**
 * Buy a single stock
 */
function buyStock(symbol) {
    console.log(`🛒 Buying stock: ${symbol}`);

    // Store current selection
    currentSymbol = symbol;

    // Find stock details
    const stocks = currentData || [];
    const stock = stocks.find(s => s.symbol === symbol);

    if (!stock) {
        showError('Stock not found');
        return;
    }

    // Update modal
    document.getElementById('modal-stock-name').textContent = stock.stock_name || symbol;
    document.getElementById('modal-score').textContent = stock.selection_score ? `${stock.selection_score.toFixed(1)}` : 'N/A';
    document.getElementById('modal-target').textContent = stock.target_price ? `₹${stock.target_price.toFixed(2)}` : 'N/A';
    document.getElementById('order-quantity').value = 1;

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('buyOrderModal'));
    modal.show();
}

/**
 * Confirm single buy
 */
document.getElementById('confirm-buy-btn')?.addEventListener('click', async function() {
    const quantity = parseInt(document.getElementById('order-quantity').value) || 1;

    try {
        const stocks = currentData || [];
        const stock = stocks.find(s => s.symbol === currentSymbol);

        if (!stock) {
            throw new Error('Stock not found');
        }

        const response = await fetch('/api/mock-trading/order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentSymbol,
                quantity: quantity
            })
        });

        const result = await response.json();

        if (result.success) {
            showSuccess(`✅ Mock order placed for ${currentSymbol} (${quantity} shares)`);
            bootstrap.Modal.getInstance(document.getElementById('buyOrderModal')).hide();
        } else {
            throw new Error(result.error || 'Failed to place order');
        }

    } catch (error) {
        console.error('❌ Buy error:', error);
        showError(error.message);
    }
});

/**
 * Buy all stocks
 */
function buyAllStocks() {
    console.log(`🛒 Buying all stocks`);

    const stocks = currentData || [];

    if (stocks.length === 0) {
        showError('No stocks available');
        return;
    }

    // Update modal
    document.getElementById('bulk-total-stocks').textContent = stocks.length;
    document.getElementById('bulk-investment-amount').value = '';

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('bulkBuyModal'));
    modal.show();
}

/**
 * Confirm bulk buy
 */
document.getElementById('confirm-bulk-buy-btn')?.addEventListener('click', async function() {
    const investmentAmount = parseFloat(document.getElementById('bulk-investment-amount').value);

    if (!investmentAmount || investmentAmount < 1000) {
        showError('Please enter a valid investment amount (min ₹1000)');
        return;
    }

    try {
        const stocks = currentData || [];

        if (stocks.length === 0) {
            throw new Error('No stocks to buy');
        }

        // Calculate total selection score
        const totalScore = stocks.reduce((sum, s) => sum + (s.selection_score || 0), 0);

        // Place orders
        let successCount = 0;

        for (const stock of stocks) {
            // Allocate investment proportionally by selection score
            const allocation = (stock.selection_score / totalScore) * investmentAmount;
            const quantity = Math.floor(allocation / stock.current_price);

            if (quantity < 1) continue;

            const response = await fetch('/api/mock-trading/order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: stock.symbol,
                    quantity: quantity
                })
            });

            const result = await response.json();

            if (result.success) {
                successCount++;
            }
        }

        showSuccess(`✅ Placed ${successCount} mock orders successfully!`);
        bootstrap.Modal.getInstance(document.getElementById('bulkBuyModal')).hide();

    } catch (error) {
        console.error('❌ Bulk buy error:', error);
        showError(error.message);
    }
});

/**
 * Show success message
 */
function showSuccess(message) {
    alert(message); // TODO: Replace with toast notification
}

/**
 * Show error message
 */
function showError(message) {
    alert('❌ ' + message); // TODO: Replace with toast notification
}
