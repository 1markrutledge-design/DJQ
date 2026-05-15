'use client';

import React, { useState, useEffect } from 'react';
import {
    TrendingUp,
    TrendingDown,
    Wallet,
    Activity,
    History,
    RefreshCw,
    Clock,
    CheckCircle2,
    AlertCircle,
    CircleDot,
    Swords,
    CloudSun,
    Trophy,
    HelpCircle,
    ChevronRight,
    ArrowUpRight,
    ArrowDownRight
} from 'lucide-react';

const ICON_MAP = {
    CircleDot: <CircleDot size={20} />,
    Swords: <Swords size={20} />,
    CloudSun: <CloudSun size={20} />,
    Trophy: <Trophy size={20} />,
    HelpCircle: <HelpCircle size={20} />
};

const THEME = {
    bg: '#0a0f1d',
    surface: '#111827',
    surfaceHeader: '#1e293b',
    border: '#33415533',
    text: '#f8fafc',
    textMuted: '#94a3b8',
    textDim: '#64748b',
    indigo: '#818cf8',
    emerald: '#10b981',
    rose: '#f43f5e',
    purple: '#a855f7'
};

export default function KalshiPortfolio() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastRefreshed, setLastRefreshed] = useState(null);

    const fetchData = async () => {
        setLoading(true);
        try {
            const response = await fetch('/api/kalshi-portfolio');
            if (!response.ok) throw new Error('Failed to fetch portfolio data');
            const result = await response.json();
            setData(result);
            setLastRefreshed(new Date());
            setError(null);
        } catch (err) {
            console.error('Dashboard Fetch Error:', err);
            setError(`Error: ${err.message}. Check your console for details.`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 60000);
        return () => clearInterval(interval);
    }, []);

    if (loading && !data) {
        return (
            <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: THEME.bg, color: THEME.text }}>
                <RefreshCw style={{ animation: 'spin 1s linear infinite', color: THEME.indigo }} size={32} />
                <span style={{ marginLeft: '16px', fontSize: '20px', fontWeight: '500' }}>Loading Unified Portfolio...</span>
                <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
            </div>
        );
    }

    const formatCurrency = (cents) => `$${(cents / 100).toFixed(2)}`;
    const formatPercent = (val) => `${val.toFixed(1)}%`;

    return (
        <div style={{ minHeight: '100vh', background: THEME.bg, color: THEME.text, padding: '40px md:80px', fontFamily: '"Inter", sans-serif' }}>
            {/* Header */}
            <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '48px', flexWrap: 'wrap', gap: '24px' }}>
                <div>
                    <h1 style={{ fontSize: '36px', fontWeight: '800', margin: 0, background: 'linear-gradient(to right, #818cf8, #c084fc, #f472b6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                        Kalshi Bot Dashboard (V2)
                    </h1>
                    <p style={{ color: THEME.textMuted, marginTop: '8px', fontSize: '18px' }}>Unified performance across all trading strategies.</p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div style={{ textAlign: 'right' }}>
                        <p style={{ fontSize: '12px', color: THEME.textDim, fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Last Updated</p>
                        <p style={{ fontSize: '14px', color: '#cbd5e1', fontFamily: 'monospace' }}>{lastRefreshed?.toLocaleTimeString() || '--:--'}</p>
                    </div>
                    <button
                        onClick={fetchData}
                        disabled={loading}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '8px', background: '#1e293b', border: '1px solid #334155', color: THEME.text,
                            padding: '12px 24px', borderRadius: '16px', cursor: 'pointer', transition: 'all 0.2s', fontWeight: '600', fontSize: '14px',
                            opacity: loading ? 0.5 : 1
                        }}
                    >
                        <RefreshCw size={18} style={{ animation: loading ? 'spin 1s linear infinite' : 'none', color: THEME.indigo }} />
                        Refresh
                    </button>
                </div>
            </header>

            {error && (
                <div style={{ background: 'rgba(69, 26, 26, 0.5)', border: '1px solid rgba(127, 29, 29, 0.5)', color: '#fecaca', padding: '16px', borderRadius: '16px', marginBottom: '32px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <AlertCircle size={20} color={THEME.rose} />
                    <span style={{ fontWeight: '500' }}>{error}</span>
                </div>
            )}

            {/* Total Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px', marginBottom: '48px' }}>
                <MainStatCard
                    icon={<Wallet color={THEME.indigo} />}
                    title="Account Balance"
                    value={formatCurrency(data?.totalBalance || 0)}
                    subValue="Live Liquidity"
                />
                <StatMetricCard
                    icon={<Activity color={THEME.purple} />}
                    title="Active Stakes"
                    value={formatCurrency(data?.totalActiveInvestment || 0)}
                    subValue="Currently in play"
                />
                <StatMetricCard
                    icon={(data?.totalRealizedPnL || 0) >= 0 ? <TrendingUp color={THEME.emerald} /> : <TrendingDown color={THEME.rose} />}
                    title="Realized PnL"
                    value={formatCurrency(data?.totalRealizedPnL || 0)}
                    subValue="Day Total"
                    color={(data?.totalRealizedPnL || 0) >= 0 ? THEME.emerald : THEME.rose}
                />
            </div>

            {/* Strategies Grid */}
            <h2 style={{ fontSize: '24px', fontWeight: '700', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <Swords color={THEME.indigo} size={24} />
                Live Strategies
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '32px', marginBottom: '64px' }}>
                {data?.strategies?.map((strat, i) => (
                    <StrategyCard key={i} strat={strat} formatCurrency={formatCurrency} formatPercent={formatPercent} />
                ))}
            </div>

            {/* Recent Trades Section */}
            <section style={{ background: 'rgba(17, 24, 39, 0.4)', border: '1px solid rgba(51, 65, 85, 0.3)', borderRadius: '24px', padding: '32px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '32px' }}>
                    <History size={24} color={THEME.indigo} />
                    <h2 style={{ fontSize: '24px', fontWeight: '700', margin: 0 }}>Recent Trade History</h2>
                </div>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                        <thead>
                            <tr style={{ color: THEME.textDim, fontSize: '12px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                                <th style={{ padding: '0 16px 16px 16px', borderBottom: '1px solid #1e293b' }}>Strategy</th>
                                <th style={{ padding: '0 16px 16px 16px', borderBottom: '1px solid #1e293b' }}>Market</th>
                                <th style={{ padding: '0 16px 16px 16px', borderBottom: '1px solid #1e293b' }}>Side</th>
                                <th style={{ padding: '0 16px 16px 16px', borderBottom: '1px solid #1e293b' }}>Action</th>
                                <th style={{ padding: '0 16px 16px 16px', borderBottom: '1px solid #1e293b' }}>Price</th>
                                <th style={{ padding: '0 16px 16px 16px', borderBottom: '1px solid #1e293b' }}>Time</th>
                            </tr>
                        </thead>
                        <tbody style={{ fontSize: '14px' }}>
                            {data?.recentTrades?.map((trade, i) => (
                                <tr key={i} style={{ borderBottom: '1px solid #1e293b' }}>
                                    <td style={{ padding: '20px 16px' }}>
                                        <span style={{ padding: '4px 12px', background: 'rgba(129, 140, 248, 0.1)', color: THEME.indigo, borderRadius: '8px', fontSize: '12px', fontWeight: '700' }}>
                                            {trade.strategy}
                                        </span>
                                    </td>
                                    <td style={{ padding: '20px 16px' }}>
                                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                                            <span style={{ fontWeight: '500', color: '#f1f5f9' }}>{trade.ticker}</span>
                                            <span style={{ fontSize: '10px', color: THEME.textDim, fontFamily: 'monospace', marginTop: '4px' }}>{trade.order_id}</span>
                                        </div>
                                    </td>
                                    <td style={{ padding: '20px 16px' }}>
                                        <span style={{ fontWeight: '700', color: THEME.indigo, textTransform: 'uppercase' }}>{trade.side}</span>
                                    </td>
                                    <td style={{ padding: '20px 16px' }}>
                                        <span style={{
                                            padding: '4px 12px', borderRadius: '999px', fontSize: '12px', fontWeight: '700',
                                            background: trade.action === 'buy' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
                                            color: trade.action === 'buy' ? THEME.emerald : THEME.rose
                                        }}>
                                            {trade.action.toUpperCase()}
                                        </span>
                                    </td>
                                    <td style={{ padding: '20px 16px', fontWeight: '700', fontFamily: 'monospace' }}>{trade.yes_price}¢</td>
                                    <td style={{ padding: '20px 16px', color: THEME.textDim, fontFamily: 'monospace' }}>
                                        {new Date(trade.created_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>
        </div>
    );
}

function MainStatCard({ icon, title, value, subValue }) {
    return (
        <div style={{ background: 'rgba(17, 24, 39, 0.6)', borderRadius: '32px', padding: '32px', border: '1px solid rgba(51, 65, 85, 0.2)', position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '24px' }}>
                <div style={{ padding: '12px', background: 'rgba(129, 140, 248, 0.1)', borderRadius: '16px' }}>{icon}</div>
                <ArrowUpRight size={20} color={THEME.textDim} />
            </div>
            <p style={{ color: THEME.textMuted, fontSize: '14px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{title}</p>
            <h3 style={{ fontSize: '40px', fontWeight: '800', margin: '8px 0', color: THEME.text }}>{value}</h3>
            <p style={{ color: THEME.textDim, fontSize: '12px', fontWeight: '500' }}>{subValue}</p>
        </div>
    );
}

function StatMetricCard({ icon, title, value, subValue, color }) {
    return (
        <div style={{ background: 'rgba(17, 24, 39, 0.6)', borderRadius: '32px', padding: '32px', border: '1px solid rgba(51, 65, 85, 0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '24px' }}>
                <div style={{ padding: '12px', background: '#1e293b', borderRadius: '16px' }}>{icon}</div>
                <Activity size={20} color={THEME.textDim} style={{ opacity: 0.2 }} />
            </div>
            <p style={{ color: THEME.textMuted, fontSize: '14px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{title}</p>
            <h3 style={{ fontSize: '40px', fontWeight: '800', margin: '8px 0', color: color || THEME.text }}>{value}</h3>
            <p style={{ color: THEME.textDim, fontSize: '12px', fontWeight: '500' }}>{subValue}</p>
        </div>
    );
}

function StrategyCard({ strat, formatCurrency, formatPercent }) {
    const winRate = strat.totalSettled > 0 ? (strat.winCount / strat.totalSettled) * 100 : 0;
    
    return (
        <div style={{ background: 'rgba(17, 24, 39, 0.4)', border: '1px solid rgba(51, 65, 85, 0.3)', borderRadius: '24px', overflow: 'hidden' }}>
            <div style={{ padding: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(30, 41, 59, 0.5)', borderBottom: '1px solid rgba(51, 65, 85, 0.3)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div style={{ padding: '10px', borderRadius: '12px', background: `${strat.color}20`, color: strat.color }}>
                        {ICON_MAP[strat.icon] || <HelpCircle size={20} />}
                    </div>
                    <div>
                        <h3 style={{ fontSize: '20px', fontWeight: '700', margin: 0 }}>{strat.id} Strategy</h3>
                        <p style={{ fontSize: '12px', color: THEME.textMuted, fontWeight: '500', textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: '4px' }}>Currently Managing</p>
                    </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <p style={{ fontSize: '10px', color: THEME.textDim, fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Win Rate</p>
                    <p style={{ fontSize: '20px', fontWeight: '900', color: winRate >= 50 ? THEME.emerald : THEME.rose, margin: '4px 0 0 0' }}>{formatPercent(winRate)}</p>
                </div>
            </div>
            <div style={{ padding: '24px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
                <div>
                    <label style={{ fontSize: '10px', color: THEME.textDim, fontWeight: '900', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Active Position</label>
                    <p style={{ fontSize: '24px', fontWeight: '900', margin: '8px 0 4px 0' }}>{formatCurrency(strat.activeInvestment)}</p>
                    <p style={{ fontSize: '12px', color: THEME.textDim }}>{strat.positions.length} Open Markets</p>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <label style={{ fontSize: '10px', color: THEME.textDim, fontWeight: '900', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Realized PnL</label>
                    <p style={{ fontSize: '24px', fontWeight: '900', margin: '8px 0 4px 0', color: strat.realizedPnL >= 0 ? THEME.emerald : THEME.rose }}>
                        {strat.realizedPnL >= 0 ? '+' : ''}{formatCurrency(strat.realizedPnL)}
                    </p>
                    <p style={{ fontSize: '12px', color: THEME.textDim }}>{strat.totalSettled} Settled Trades</p>
                </div>
            </div>
            {strat.positions.length > 0 && (
                <div style={{ padding: '0 24px 24px 24px' }}>
                    <label style={{ fontSize: '10px', color: THEME.textDim, fontWeight: '900', textTransform: 'uppercase', letterSpacing: '0.1em', display: 'block', marginBottom: '12px' }}>Markets</label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {strat.positions.slice(0, 3).map((p, j) => (
                            <div key={j} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(10, 15, 29, 0.4)', padding: '12px', borderRadius: '12px', border: '1px solid rgba(51, 65, 85, 0.1)' }}>
                                <span style={{ fontSize: '12px', fontFamily: 'monospace', color: '#cbd5e1', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginRight: '16px' }}>{p.ticker}</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
                                    <span style={{ fontSize: '10px', fontWeight: '700', color: THEME.textDim }}>{p.position} Shares</span>
                                    <ChevronRight size={14} color="#334155" />
                                </div>
                            </div>
                        ))}
                        {strat.positions.length > 3 && (
                            <p style={{ fontSize: '10px', color: THEME.textDim, textAlign: 'center', marginTop: '8px', fontWeight: '700' }}>+ {strat.positions.length - 3} more markets</p>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
