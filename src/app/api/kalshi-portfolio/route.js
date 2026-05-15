import { NextResponse } from 'next/server';
import crypto from 'crypto';

const KALSHI_BASE = 'https://api.elections.kalshi.com';

/**
 * Strategy Prefix Definitions
 */
const STRATEGIES = [
    { id: 'Strikeout Bot', prefix: 'KXMLBSO', color: '#3b82f6', icon: 'CircleDot' },
    { id: 'MLB Scattershot', prefix: 'KXMLBTOTAL', color: '#3b82f6', icon: 'CircleDot' },
    { id: 'MLB Scattershot', prefix: 'KXMLBTEAMTOTAL', color: '#3b82f6', icon: 'CircleDot' },
    { id: 'MLB Moneyline', prefix: 'KXMLBGAME', color: '#3b82f6', icon: 'CircleDot' },
    { id: 'MLB (Other)', prefix: 'KXMLB', color: '#3b82f6', icon: 'CircleDot' },
    { id: 'NBA Scattershot', prefix: 'KXNBA', color: '#f59e0b', icon: 'Trophy' },
    { id: 'Soccer Scattershot', prefix: 'KXEPL', color: '#10b981', icon: 'CircleDot' },
    { id: 'Soccer Scattershot', prefix: 'KXMLS', color: '#10b981', icon: 'CircleDot' },
    { id: 'Soccer Scattershot', prefix: 'KXSOCCER', color: '#10b981', icon: 'CircleDot' },
    { id: 'UFC Bot', prefix: 'KXUFC', color: '#f43f5e', icon: 'Swords' },
    { id: 'Climate Bot', prefix: 'KXHIGH', color: '#6366f1', icon: 'CloudSun' },
    { id: 'Climate Bot', prefix: 'KXLOW', color: '#6366f1', icon: 'CloudSun' },
    { id: 'Climate Bot', prefix: 'KXRAIN', color: '#6366f1', icon: 'CloudSun' },
    { id: 'Music Bot', prefix: 'KXSPOT', color: '#ec4899', icon: 'Music' },
    { id: 'Crypto Bot', prefix: 'KXBTC', color: '#8b5cf6', icon: 'Coins' },
    { id: 'Crypto Bot', prefix: 'KXETH', color: '#8b5cf6', icon: 'Coins' },
    { id: 'Crypto Bot', prefix: 'KXSOL', color: '#8b5cf6', icon: 'Coins' },
];

const TENNIS_CHAMPION = { id: 'Tennis Champion', color: '#10b981', icon: 'Trophy' };
const TENNIS_SCATTERSHOT = { id: 'Tennis Scattershot', color: '#10b981', icon: 'Trophy' };
const TENNIS_LATE_MOMENTUM = { id: 'Tennis Late Momentum', color: '#10b981', icon: 'Trophy' };
const TENNIS_OTHER = { id: 'Tennis (Other)', color: '#10b981', icon: 'Trophy' };

function getStrategy(ticker, clientOrderId = '', context = {}) {
    const upperTicker = ticker?.toUpperCase() || '';
    
    // 1. Special Case: Tennis Bot Variants (Ported from Auditor Bot)
    if (upperTicker.startsWith('KXATP') || upperTicker.startsWith('KXWTA') || upperTicker.startsWith('KXITF')) {
        const shares = context.shares || 0;
        const avgPrice = context.avgPrice || 0;
        
        if (shares === 2 || shares === 4) {
            return TENNIS_CHAMPION;
        } else if (shares === 1) {
            if (avgPrice >= 48 && avgPrice <= 56) return TENNIS_SCATTERSHOT;
            if (avgPrice >= 60 && avgPrice <= 88) return TENNIS_LATE_MOMENTUM;
            return TENNIS_OTHER;
        }
        return TENNIS_OTHER;
    }

    // 2. Check by CID prefix
    for (const s of STRATEGIES) {
        if (clientOrderId?.startsWith(s.prefix)) return s;
    }
    // 3. Fallback check by Ticker prefix
    for (const s of STRATEGIES) {
        if (upperTicker.startsWith(s.prefix)) return s;
    }
    return { id: 'OTHER', color: '#94a3b8', icon: 'HelpCircle' };
}

function signRequest(method, path) {
    const apiKeyId = process.env.KALSHI_API_KEY_ID;
    let privateKeyPem = process.env.KALSHI_PRIVATE_KEY_PEM;

    if (!apiKeyId || !privateKeyPem) {
        throw new Error('Missing Kalshi API credentials');
    }

    privateKeyPem = privateKeyPem.replace(/\\n/g, '\n').replace(/"/g, '').trim();

    const header = '-----BEGIN RSA PRIVATE KEY-----';
    const footer = '-----END RSA PRIVATE KEY-----';

    if (privateKeyPem.includes(header) && !privateKeyPem.slice(header.length, header.length + 10).includes('\n')) {
        const content = privateKeyPem.replace(header, '').replace(footer, '').trim();
        privateKeyPem = `${header}\n${content}\n${footer}`;
    } else if (!privateKeyPem.includes(header) && privateKeyPem.includes('MIIE')) {
        privateKeyPem = `${header}\n${privateKeyPem}\n${footer}`;
    }

    const cleanPath = path.split('?')[0];
    const timestamp = Date.now().toString();
    const message = timestamp + method.toUpperCase() + cleanPath;

    const signature = crypto.sign(
        'sha256',
        Buffer.from(message),
        {
            key: privateKeyPem,
            padding: crypto.constants.RSA_PKCS1_PSS_PADDING,
            saltLength: crypto.constants.RSA_PSS_SALTLEN_MAX,
        }
    ).toString('base64');

    return {
        'KALSHI-ACCESS-KEY': apiKeyId,
        'KALSHI-ACCESS-SIGNATURE': signature,
        'KALSHI-ACCESS-TIMESTAMP': timestamp,
        'Content-Type': 'application/json',
    };
}

async function kalshiGet(path, params = null) {
    const url = new URL(KALSHI_BASE + path);
    if (params) {
        Object.keys(params).forEach(key => url.searchParams.append(key, params[key]));
    }

    const headers = signRequest('GET', path);
    const response = await fetch(url.toString(), {
        method: 'GET',
        headers,
        cache: 'no-store',
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Kalshi API error: ${response.status} - ${errorText}`);
    }

    return response.json();
}

export async function GET() {
    try {
        // 1. Fetch data concurrently
        const [balanceData, positionsData, fillsData, settlementsData] = await Promise.all([
            kalshiGet('/trade-api/v2/portfolio/balance'),
            kalshiGet('/trade-api/v2/portfolio/positions', { limit: 500 }),
            kalshiGet('/trade-api/v2/portfolio/fills', { limit: 1000 }),
            kalshiGet('/trade-api/v2/portfolio/settlements', { limit: 1000 })
        ]);

        const totalBalance = balanceData.balance || 0;
        const allPositions = positionsData.market_positions || [];
        const allFills = fillsData.fills || [];
        const allSettlements = settlementsData.settlements || [];

        // 2. Group Positions by Strategy
        const strategies = {};
        [...STRATEGIES, TENNIS_CHAMPION, TENNIS_SCATTERSHOT, TENNIS_LATE_MOMENTUM, TENNIS_OTHER].forEach(s => {
            if (!strategies[s.id]) {
                strategies[s.id] = { 
                    id: s.id, 
                    color: s.color, 
                    icon: s.icon,
                    positions: [], 
                    realizedPnL: 0,
                    activeInvestment: 0,
                    winCount: 0,
                    totalSettled: 0
                };
            }
        });
        strategies['OTHER'] = { id: 'OTHER', color: '#94a3b8', icon: 'HelpCircle', positions: [], realizedPnL: 0, activeInvestment: 0, winCount: 0, totalSettled: 0 };

        allPositions.forEach(pos => {
            const position = Math.abs(parseFloat(pos.position_fp || '0'));
            if (position === 0) return;
            
            // For active positions, we heuristic based on share count (avgPrice is harder to get here)
            const strat = getStrategy(pos.ticker, '', { shares: position });
            strategies[strat.id].positions.push(pos);
            
            // In Kalshi V2, market_exposure_dollars represents the current value at risk
            const exposure = parseFloat(pos.market_exposure_dollars || '0') * 100;
            strategies[strat.id].activeInvestment += exposure;
        });

        // 3. Calculate PnL from Fills & Settlements
        // We use a FIFO-ish approach per ticker
        const buysByTicker = {};

        // Sort fills chronologically
        const sortedFills = [...allFills].sort((a, b) => new Date(a.created_time) - new Date(b.created_time));

        for (const fill of sortedFills) {
            const { ticker, action, yes_price, count = 1, client_order_id } = fill;
            const strat = getStrategy(ticker, client_order_id, { shares: count, avgPrice: yes_price });

            if (action === 'buy') {
                if (!buysByTicker[ticker]) buysByTicker[ticker] = [];
                for (let i = 0; i < count; i++) buysByTicker[ticker].push(yes_price);
            } else if (action === 'sell') {
                const buys = buysByTicker[ticker] || [];
                for (let i = 0; i < count; i++) {
                    // If we can't find the buy, we assume a default cost (e.g. 50c) or use avg if we have some data
                    const cost = buys.shift() || 50; 
                    const profit = (yes_price || 0) - cost;
                    if (!isNaN(profit)) {
                        strategies[strat.id].realizedPnL += profit;
                        strategies[strat.id].totalSettled++;
                        if (profit > 0) strategies[strat.id].winCount++;
                    }
                }
            }
        }

        // Apply settlements using robust V2 fields
        const todayStr = new Date().toISOString().split('T')[0];
        
        allSettlements.forEach(settle => {
            const { 
                ticker, 
                settled_time, 
                value = 0, 
                yes_count_fp = '0', 
                no_count_fp = '0', 
                yes_total_cost_dollars = '0', 
                no_total_cost_dollars = '0', 
                fee_cost = '0' 
            } = settle;
            
            const yesCount = parseFloat(yes_count_fp || '0') || 0;
            const noCount = parseFloat(no_count_fp || '0') || 0;
            const shares = yesCount || noCount;
            
            const yesCostCents = Math.round(parseFloat(yes_total_cost_dollars || '0') * 100);
            const noCostCents = Math.round(parseFloat(no_total_cost_dollars || '0') * 100);
            const costCents = yesCostCents + noCostCents;
            const avgPrice = shares > 0 ? (costCents / shares) : 0;

            const strat = getStrategy(ticker, '', { shares, avgPrice });
            
            const isToday = settled_time.startsWith(todayStr);
            const fees = Math.round(parseFloat(fee_cost || '0') * 100);

            const payout = (value * yesCount) + ((100 - value) * noCount);
            const profit = payout - costCents - fees;

            if (!isNaN(profit)) {
                strategies[strat.id].totalSettled++;
                strategies[strat.id].realizedPnL += profit;
                if (profit > 0) strategies[strat.id].winCount++;
            }
        });

        // 4. Final aggregation
        const finalStrategies = Object.values(strategies).filter(s => {
            const hasData = s.positions.length > 0 || s.totalSettled > 0;
            const isRetired = s.id.includes('(Other)') || s.id === 'OTHER';
            return hasData && !isRetired;
        });

        console.log(`[DASHBOARD] Returning ${finalStrategies.length} active strategies. Filtered out: ${Object.keys(strategies).length - finalStrategies.length}`);

        const dashboardData = {
            totalBalance: totalBalance,
            totalActiveInvestment: (balanceData.portfolio_value !== undefined) ? balanceData.portfolio_value : Object.values(strategies).reduce((acc, s) => acc + s.activeInvestment, 0),
            totalRealizedPnL: Object.values(strategies).reduce((acc, s) => acc + s.realizedPnL, 0),
            strategies: finalStrategies,
            recentTrades: allFills.slice(0, 20).map(f => {
                const strat = getStrategy(f.ticker, f.client_order_id, { shares: f.count, avgPrice: f.yes_price });
                return {
                    ...f,
                    strategy: strat.id
                };
            }),
            timestamp: new Date().toISOString()
        };

        return NextResponse.json(dashboardData);
    } catch (error) {
        console.error('Unified Portfolio API Error:', error);
        return NextResponse.json(
            { error: error.message || 'Failed to fetch portfolio data' },
            { status: 500 }
        );
    }
}
