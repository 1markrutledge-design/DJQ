const REFRESH_INTERVAL = 15000; // 15 seconds
const charts = {};

async function updateDashboard() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        if (data.error) return;
        document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
        renderMarkets(data.markets);
    } catch (err) { console.error(err); }
}

function renderMarkets(markets) {
    const grid = document.getElementById('market-grid');
    const displayOrder = ["KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXHYPE15M", "KXDOGE15M", "KXBNB15M"];
    if (grid.querySelector('.loading')) grid.innerHTML = '';

    displayOrder.forEach(series => {
        const m = markets[series];
        if (!m) return;
        let card = document.getElementById(`card-${series}`);
        if (!card) {
            card = createCard(series, m.name);
            grid.appendChild(card);
        }
        updateCardData(series, m);
    });
}

function createCard(series, name) {
    const div = document.createElement('div');
    div.id = `card-${series}`;
    div.className = 'market-card';
    div.style.position = 'relative';
    div.innerHTML = `
        <span id="group-${series}" class="group-badge"></span>
        <div class="card-header">
            <div class="coin-info">
                <h2 id="title-${series}">${series.replace('KX', '').replace('15M', '')}</h2>
                <p>15m Cycles</p>
            </div>
            <div class="price-badges">
                <span class="badge bid" id="price-${series}">--¢</span>
            </div>
        </div>
        <div class="chart-container">
            <canvas id="chart-${series}"></canvas>
        </div>
        <div class="bible-stats">
            <div class="bible-header">
                <span>Strategy Bible</span>
                <span id="strat-type-${series}">--</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <div id="bible-winrate-${series}" style="font-size: 1.5rem; font-weight: 700; color: #fff;">--%</div>
                <div id="bible-trades-${series}" style="font-size: 0.7rem; color: var(--text-secondary);">0 Trades</div>
            </div>
            <p id="bible-desc-${series}" style="font-size: 0.65rem; color: var(--text-secondary); margin-top: 5px;"></p>
        </div>
    `;
    return div;
}

function updateCardData(series, data) {
    document.getElementById(`price-${series}`).textContent = `${data.current.price || 0}¢`;
    
    // Group & Bible Info
    const groupEl = document.getElementById(`group-${series}`);
    groupEl.textContent = data.group;
    groupEl.className = `group-badge group-${data.group.toLowerCase()}`;

    const total = data.bible.win + data.bible.loss;
    const wr = total > 0 ? Math.round((data.bible.win / total) * 100) : 0;
    
    document.getElementById(`bible-winrate-${series}`).textContent = `${wr}%`;
    document.getElementById(`bible-winrate-${series}`).style.color = wr >= 75 ? 'var(--win-color)' : '#fff';
    document.getElementById(`bible-trades-${series}`).textContent = `${total} Settlements`;
    
    const typeEl = document.getElementById(`strat-type-${series}`);
    const descEl = document.getElementById(`bible-desc-${series}`);
    
    if (data.group === "Momentum") {
        typeEl.textContent = "10m Squeeze (80+)";
        descEl.textContent = "Buy dominant side if 80+ at 10:00 mark. BTC/ETH follow trends.";
    } else {
        typeEl.textContent = "5m Reversion (20-)";
        descEl.textContent = "Buy cheap side if 20- at 10:00 mark. Altcoins rubber-band back.";
    }

    updateChart(series, data.history);
}

function updateChart(series, history) {
    const canvas = document.getElementById(`chart-${series}`);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const labels = history.map((_, i) => i);
    
    if (charts[series]) {
        charts[series].data.labels = labels;
        charts[series].data.datasets[0].data = history;
        charts[series].update('none');
    } else {
        charts[series] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    data: history,
                    borderColor: getCoinColor(series),
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: false },
                    y: { display: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', font: { size: 10 } } }
                }
            }
        });
    }
}

function getCoinColor(series) {
    const colors = { "KXBTC15M": "#F7931A", "KXETH15M": "#627EEA", "KXSOL15M": "#14F195", "KXXRP15M": "#23292F", "KXDOGE15M": "#C2A633", "KXBNB15M": "#F3BA2F", "KXHYPE15M": "#FF3366" };
    return colors[series] || "#3b82f6";
}

updateDashboard();
setInterval(updateDashboard, REFRESH_INTERVAL);
