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
    AlertCircle
} from 'lucide-react';

export default function TennisDashboard() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastRefreshed, setLastRefreshed] = useState(null);

    const fetchData = async () => {
        setLoading(true);
        try {
            const response = await fetch('/api/tennis-stats');
            if (!response.ok) throw new Error('Failed to fetch statistics');
            const result = await response.json();
            setData(result);
            setLastRefreshed(new Date());
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 60000); // Refresh every minute
        return () => clearInterval(interval);
    }, []);

    if (loading && !data) {
        return (
            <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: '#0f172a', color: '#f8fafc' }}>
                <RefreshCw style={{ animation: 'spin 1s linear infinite' }} />
                <span style={{ marginLeft: '12px', fontSize: '18px' }}>Loading Tennis Bot Stats...</span>
                <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
            </div>
        );
    }

    const formatCents = (cents) => `$${(cents / 100).toFixed(2)}`;

    return (
        <div style={{ minHeight: '100vh', background: '#0f172a', color: '#f8fafc', padding: '40px', fontFamily: '"Inter", sans-serif' }}>
            <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '40px' }}>
                <div>
                    <h1 style={{ fontSize: '32px', fontWeight: 'bold', margin: 0, background: 'linear-gradient(to right, #38bdf8, #818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                        Tennis Bot Dashboard
                    </h1>
                    <p style={{ color: '#94a3b8', marginTop: '8px' }}>Tracking live trades and performance</p>
                </div>
                <button
                    onClick={fetchData}
                    disabled={loading}
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        background: '#1e293b',
                        border: '1px solid #334155',
                        color: '#f8fafc',
                        padding: '10px 20px',
                        borderRadius: '12px',
                        cursor: 'pointer',
                        transition: 'all 0.2s'
                    }}
                >
                    <RefreshCw size={18} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
                    Refresh
                </button>
            </header>

            {error && (
                <div style={{ background: '#451a1a', border: '1px solid #7f1d1d', color: '#fecaca', padding: '16px', borderRadius: '12px', marginBottom: '32px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <AlertCircle size={20} />
                    {error}
                </div>
            )}

            {/* Stats Overview */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '24px', marginBottom: '40px' }}>
                <StatCard
                    icon={<Wallet color="#38bdf8" />}
                    title="Account Balance"
                    value={formatCents(data?.balance || 0)}
                    subValue="Real-time liquidity"
                />
                <StatCard
                    icon={data?.realizedPnL?.totalCents >= 0 ? <TrendingUp color="#4ade80" /> : <TrendingDown color="#f43f5e" />}
                    title="Realized P/L"
                    value={formatCents(data?.realizedPnL?.totalCents || 0)}
                    subValue={`${data?.realizedPnL?.wins || 0}W / ${data?.realizedPnL?.losses || 0}L (${data?.realizedPnL?.trades || 0} trades)`}
                    highlight={data?.realizedPnL?.totalCents >= 0 ? '#4ade80' : '#f43f5e'}
                />
                <StatCard
                    icon={<Activity color="#818cf8" />}
                    title="Resting Buy Orders"
                    value={data?.restingOrders?.length || 0}
                    subValue="Waiting to fill at 45¢"
                />
                <StatCard
                    icon={<Clock color="#94a3b8" />}
                    title="Last Updated"
                    value={lastRefreshed ? lastRefreshed.toLocaleTimeString() : '--:--'}
                    subValue="Auto-refreshing"
                />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
                {/* Resting Orders Table */}
                <section style={{ background: '#1e293b', padding: '24px', borderRadius: '20px', border: '1px solid #334155' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                        <Clock size={20} color="#38bdf8" />
                        <h2 style={{ fontSize: '20px', margin: 0 }}>Resting Buy Orders</h2>
                        <span style={{ marginLeft: 'auto', fontSize: '13px', color: '#64748b' }}>{data?.restingOrders?.length || 0} orders @ 45¢</span>
                    </div>
                    <div style={{ overflowX: 'auto', maxHeight: '400px', overflowY: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead style={{ position: 'sticky', top: 0, background: '#1e293b' }}>
                                <tr style={{ textAlign: 'left', borderBottom: '1px solid #334155', color: '#64748b', fontSize: '13px' }}>
                                    <th style={{ padding: '10px 12px' }}>Match</th>
                                    <th style={{ padding: '10px 12px' }}>Side</th>
                                    <th style={{ padding: '10px 12px' }}>Bid</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data?.restingOrders?.length > 0 ? (
                                    data.restingOrders.map((o, i) => {
                                        const parts = o.ticker.split('-');
                                        const matchPart = parts[1] || o.ticker;
                                        const playerCode = parts[2] || '';
                                        return (
                                            <tr key={i} style={{ borderBottom: i === data.restingOrders.length - 1 ? 'none' : '1px solid #1e293b' }}>
                                                <td style={{ padding: '10px 12px', fontSize: '13px', fontFamily: 'monospace', color: '#cbd5e1' }}>{matchPart}</td>
                                                <td style={{ padding: '10px 12px' }}>
                                                    <span style={{ padding: '3px 8px', borderRadius: '6px', fontSize: '12px', fontWeight: '600', background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8' }}>
                                                        YES {playerCode}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '10px 12px', color: '#4ade80', fontWeight: '600' }}>{formatCents(o.yes_price)}</td>
                                            </tr>
                                        );
                                    })
                                ) : (
                                    <tr><td colSpan="3" style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>No resting orders</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </section>

                {/* Recent Fills Table */}
                <section style={{ background: '#1e293b', padding: '24px', borderRadius: '20px', border: '1px solid #334155' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
                        <CheckCircle2 size={20} color="#4ade80" />
                        <h2 style={{ fontSize: '20px', margin: 0 }}>Recent Fills</h2>
                    </div>
                    <div style={{ overflowX: 'auto', maxHeight: '400px', overflowY: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead style={{ position: 'sticky', top: 0, background: '#1e293b' }}>
                                <tr style={{ textAlign: 'left', borderBottom: '1px solid #334155', color: '#64748b', fontSize: '13px' }}>
                                    <th style={{ padding: '10px 12px' }}>Match</th>
                                    <th style={{ padding: '10px 12px' }}>Action</th>
                                    <th style={{ padding: '10px 12px' }}>Price</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data?.recentFills?.length > 0 ? (
                                    data.recentFills.map((fill, i) => {
                                        const parts = fill.ticker.split('-');
                                        const matchPart = parts[1] || fill.ticker;
                                        return (
                                            <tr key={i} style={{ borderBottom: i === data.recentFills.length - 1 ? 'none' : '1px solid #1e293b' }}>
                                                <td style={{ padding: '10px 12px', fontSize: '13px', fontFamily: 'monospace', color: '#cbd5e1' }}>{matchPart}</td>
                                                <td style={{ padding: '10px 12px' }}>
                                                    <span style={{
                                                        padding: '3px 8px', borderRadius: '6px', fontSize: '12px', fontWeight: '600',
                                                        background: fill.action === 'buy' ? 'rgba(74, 222, 128, 0.1)' : 'rgba(244, 63, 94, 0.1)',
                                                        color: fill.action === 'buy' ? '#4ade80' : '#f43f5e'
                                                    }}>
                                                        {fill.action.toUpperCase()}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '10px 12px' }}>{formatCents(fill.yes_price)}</td>
                                            </tr>
                                        );
                                    })
                                ) : (
                                    <tr><td colSpan="3" style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>No recent fills</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </section>
            </div>
        </div>
    );
}

function StatCard({ icon, title, value, subValue, highlight }) {
    return (
        <div style={{ background: '#1e293b', padding: '24px', borderRadius: '20px', border: '1px solid #334155', transition: 'transform 0.2s', cursor: 'default' }}>
            <div style={{ marginBottom: '16px' }}>{icon}</div>
            <div style={{ color: '#94a3b8', fontSize: '14px', marginBottom: '4px' }}>{title}</div>
            <div style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '4px', color: highlight || '#f8fafc' }}>{value}</div>
            <div style={{ color: '#64748b', fontSize: '12px' }}>{subValue}</div>
        </div>
    );
}
