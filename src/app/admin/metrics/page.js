'use client';

import { useState, useEffect } from 'react';
import { fetchAdminData } from '../../actions';
import { DollarSign, Users, TrendingUp, Wallet } from 'lucide-react';

export default function MetricsPage() {
    const [data, setData] = useState(null);

    useEffect(() => {
        fetchAdminData().then(setData);
    }, []);

    if (!data) return <div className="p-8">Loading Metrics...</div>;

    const totalRevenue = data.totalRevenue || 0;
    const myCut = (totalRevenue * 0.70).toFixed(2);
    const activeVenues = data.venues.filter(v => v.status !== 'frozen').length;

    // Calculate total requests across all venues
    let totalRequests = 0;
    Object.values(data.queueStats).forEach(q => totalRequests += q.length);

    return (
        <div style={{ maxWidth: '1000px' }}>
            <h1 style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '2rem' }}>Growth Metrics</h1>

            {/* KPI Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '3rem' }}>
                {/* Revenue */}
                <div className="card" style={{ background: 'linear-gradient(135deg, #171717 0%, #262626 100%)', border: '1px solid #fbbf24' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <DollarSign size={18} color="#fbbf24" />
                        <span style={{ color: '#fbbf24', fontSize: '0.9rem', fontWeight: 'bold' }}>NET PROFIT</span>
                    </div>
                    <p style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'white' }}>${myCut}</p>
                </div>

                {/* Users */}
                <div className="card">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <Users size={18} color="#ec4899" />
                        <span style={{ color: '#a3a3a3', fontSize: '0.9rem' }}>ACTIVE VENUES</span>
                    </div>
                    <p style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'white' }}>{activeVenues}</p>
                    <p style={{ fontSize: '0.8rem', color: '#525252' }}>Total Registered: {data.venues.length}</p>
                </div>

                {/* Activity */}
                <div className="card">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <TrendingUp size={18} color="#22c55e" />
                        <span style={{ color: '#a3a3a3', fontSize: '0.9rem' }}>TOTAL REQUESTS</span>
                    </div>
                    <p style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'white' }}>{totalRequests}</p>
                </div>
            </div>

            {/* Withdraw Section */}
            <div className="card" style={{ padding: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', border: '1px dashed #525252' }}>
                <div>
                    <h2 style={{ fontSize: '1.2rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>Withdraw Earnings</h2>
                    <p style={{ color: '#a3a3a3', maxWidth: '400px' }}>
                        Transform your crypto-queue credits into fiat currency. Requires linking a bank account (Stripe Connect).
                    </p>
                </div>
                <button
                    disabled
                    className="btn"
                    style={{ background: '#262626', color: '#a3a3a3', cursor: 'not-allowed', display: 'flex', gap: '0.5rem', alignItems: 'center' }}
                >
                    <Wallet size={18} /> Withdraw (Coming Soon)
                </button>
            </div>

            <p style={{ marginTop: '1rem', fontSize: '0.8rem', color: '#525252', textAlign: 'center' }}>
                Analytics updated in real-time. Last sync: {new Date().toLocaleTimeString()}
            </p>
        </div>
    );
}
