import { NextResponse } from 'next/server';
import crypto from 'crypto';

const KALSHI_BASE = 'https://api.elections.kalshi.com';

function signRequest(method, path) {
    const apiKeyId = process.env.KALSHI_API_KEY_ID;
    let privateKeyPem = process.env.KALSHI_PRIVATE_KEY_PEM;

    if (!apiKeyId || !privateKeyPem) {
        throw new Error('Missing Kalshi API credentials');
    }

    // 1. Clean basic noise
    privateKeyPem = privateKeyPem.replace(/\\n/g, '\n').replace(/"/g, '').trim();

    // 2. Handle 'One-Line' corruption (missing newlines after headers)
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
        // 1. Get Balance
        const balanceData = await kalshiGet('/trade-api/v2/portfolio/balance');

        // Tennis series prefixes used by Kalshi
        const TENNIS_PREFIXES = ['KXATPMATCH', 'KXWTAMATCH', 'KXATPCHALLENGERMATCH', 'KXWTACHALLENGERMATCH', 'KXATP', 'KXWTA'];
        const isTennis = (ticker) => TENNIS_PREFIXES.some(p => ticker.toUpperCase().startsWith(p));

        // 2. Get All Tennis Fills & Settlements for P/L calculation
        const [fillsData, settlementsData] = await Promise.all([
            kalshiGet('/trade-api/v2/portfolio/fills', { limit: 1000 }),
            kalshiGet('/trade-api/v2/portfolio/settlements', { limit: 1000 })
        ]);

        const allTennisFills = (fillsData.fills || []).filter(f => isTennis(f.ticker));
        const allTennisSettlements = (settlementsData.settlements || []).filter(s => isTennis(s.ticker));
        const tennisFills = allTennisFills.slice(0, 50); // last 50 for display

        // Calculate realized P/L
        // We track buys at 45c as cost basis. 
        // Realization happens on ANY sell or ANY settlement.
        const COST_BASIS = 45;
        const buysByTicker = {};
        const realizedPnL = { totalCents: 0, wins: 0, losses: 0, trades: 0 };

        // Process all fills to build cost basis and realize sells
        const sortedFills = [...allTennisFills].sort((a, b) => new Date(a.created_time) - new Date(b.created_time));

        for (const fill of sortedFills) {
            const { ticker, action, yes_price, count = 1 } = fill;
            if (action === 'buy') {
                if (!buysByTicker[ticker]) buysByTicker[ticker] = [];
                for (let i = 0; i < count; i++) buysByTicker[ticker].push(yes_price);
            } else if (action === 'sell') {
                const buys = buysByTicker[ticker] || [];
                for (let i = 0; i < count; i++) {
                    const cost = buys.shift() ?? COST_BASIS;
                    const profit = yes_price - cost;
                    realizedPnL.totalCents += profit;
                    realizedPnL.trades++;
                    if (profit > 0) realizedPnL.wins++;
                    else realizedPnL.losses++;
                }
            }
        }

        // Process settlements as final realizations
        for (const settlement of allTennisSettlements) {
            const { ticker, revenue_cents = 0, yes_count = 0 } = settlement;
            // Settlement usually doesn't have a count in the same way, but 'value' is usually 100 for win
            // From audit, we saw revenue_cents was 0 for losses. 
            // In Kalshi v2, revenue_cents/revenue is the total payout.
            // If we have remaining buys in state, we realize them here.

            const buys = buysByTicker[ticker] || [];
            // If it's in settlements, it means the market resolved. 
            // Note: Kalshi settlements might show up even if you had 0 shares if you traded it before?
            // Actually, for the bot, if we have buys left, they are realized at settlement value.

            // However, settlements data often reflects the position at settlement.
            // Let's look at the audit again. 
            // Settlement: { ticker: "...", value: 100, yes_count: 0 ... }
            // Wait, if yes_count is 0 but it's a settlement, it might be that the shares were already sold?
            // If they were sold, they were already processed by the 'sell' logic above.
            // Only 'resting' positions at settlement time show up as revenue.

            // If the bot hasn't sold yet, the remaining buys in buysByTicker[ticker] 
            // should be realized at 'revenue_cents' per share? No, revenue_cents is total.
            // Actually, if a market settles, you get 100c if you won, 0c if you lost.

            // Better logic: Any shares left in buysByTicker[ticker] at the time of settlement 
            // are realized at the settlement value.
            const payoutPerShare = (settlement.market_result === 'yes') ? 100 : 0;

            // Kalshi v2 settlements are per-ticker.
            // We'll realize all remaining buys for this ticker.
            while (buys.length > 0) {
                const cost = buys.shift();
                const profit = payoutPerShare - cost;
                realizedPnL.totalCents += profit;
                realizedPnL.trades++;
                if (profit > 0) realizedPnL.wins++;
                else realizedPnL.losses++;
            }
        }

        // 3. Get Active Positions (filtered for Tennis)
        const positionsData = await kalshiGet('/trade-api/v2/portfolio/positions', { limit: 500 });
        const tennisPositions = (positionsData.positions || []).filter(p =>
            isTennis(p.ticker) && p.position !== 0
        );

        // 4. Get Resting Orders (pending fills — the bot's open 45¢ bids)
        const ordersData = await kalshiGet('/trade-api/v2/portfolio/orders', { status: 'resting', limit: 200 });
        const tennisRestingOrders = (ordersData.orders || []).filter(o => isTennis(o.ticker));

        return NextResponse.json({
            balance: balanceData.balance || 0,
            recentFills: tennisFills,
            activePositions: tennisPositions,
            restingOrders: tennisRestingOrders,
            realizedPnL,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        console.error('Tennis Stats API Error:', error);
        return NextResponse.json(
            { error: error.message || 'Failed to fetch tennis stats' },
            { status: 500 }
        );
    }
}
