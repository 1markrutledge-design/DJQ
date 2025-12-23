'use client';

import { useState, useEffect } from 'react';
import { fetchAdminData } from '../actions';
import { Users, DollarSign, Music } from 'lucide-react';
import Link from 'next/link';

export default function AdminPage() {
    const [data, setData] = useState(null);

    useEffect(() => {
        fetchAdminData().then(setData);
    }, []);

    if (!data) return <div className="text-center p-8">Loading Overview...</div>;

    const myCut = (data.totalRevenue * 0.70).toFixed(2);
    const venueCut = (data.totalRevenue * 0.30).toFixed(2);
    const totalRev = (data.totalRevenue || 0).toFixed(2);

    return (
        <div style={{ maxWidth: '1000px' }}>
            <h1 style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '2rem' }}>Dashboard Overview</h1>

            {/* Revenue Stats */}
            <h2 style={{ fontSize: '1.25rem', marginBottom: '1rem', color: '#a3a3a3' }}>REVENUE OVERVIEW</h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '3rem' }}>
                <div className="card" style={{ background: 'linear-gradient(135deg, #171717 0%, #262626 100%)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <DollarSign size={18} color="#fbbf24" />
                        <span style={{ color: '#a3a3a3', fontSize: '0.9rem' }}>MY EARNINGS (70%)</span>
                    </div>
                    <p style={{ fontSize: '2.5rem', fontWeight: 'bold', color: '#fbbf24' }}>${myCut}</p>
                    <p style={{ fontSize: '0.8rem', color: '#525252' }}>Total Processed: ${(data.totalRevenue || 0).toFixed(2)}</p>
                </div>
                <div className="card">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <Users size={18} color="#ec4899" />
                        <span style={{ color: '#a3a3a3', fontSize: '0.9rem' }}>VENUE PAYOUTS (30%)</span>
                    </div>
                    <p style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'white' }}>${venueCut}</p>
                </div>
            </div>

            {/* Venues */}
            <h2 style={{ fontSize: '1.25rem', marginBottom: '1rem', color: '#a3a3a3' }}>ACTIVE VENUES</h2>
            <div style={{ marginBottom: '3rem' }}>
                {data.venues.length === 0 ? (
                    <p style={{ color: '#525252' }}>No venues registered yet.</p>
                ) : (
                    data.venues.map(venue => {
                        const venueQueue = data.queueStats[venue.code] || [];
                        const revenue = venueQueue.reduce((acc, q) => acc + (q.amount || 0), 0);
                        return (
                            <div key={venue.code} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div>
                                    <h3 style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>{venue.name}</h3>
                                    <code style={{ background: '#262626', padding: '2px 6px', borderRadius: '4px', fontSize: '0.8rem', color: '#a3a3a3' }}>{venue.code}</code>
                                </div>
                                <div style={{ textAlign: 'right' }}>
                                    <p style={{ fontWeight: 'bold' }}>${(revenue * 0.30).toFixed(2)} Earned</p>
                                    <p style={{ fontSize: '0.8rem', color: '#525252' }}>{venueQueue.length} Requests</p>
                                </div>
                            </div>
                        )
                    })
                )}
            </div>

            {/* Song Management */}
            <h2 style={{ fontSize: '1.25rem', marginBottom: '1rem', color: '#a3a3a3' }}>DATABASE CONTROL</h2>
            <div className="card" style={{ cursor: 'pointer', textAlign: 'center', padding: '2rem', borderStyle: 'dashed' }}>
                <Music style={{ marginBottom: '0.5rem', color: '#6d28d9' }} />
                <p style={{ fontWeight: 'bold' }}>Manage Song Database</p>
                <p style={{ fontSize: '0.8rem', color: '#525252' }}>Add, Edit, or Remove global tracks.</p>
                <Link href="/admin/songs">
                    <button className="btn btn-primary" style={{ marginTop: '1rem', width: 'auto' }}>Open Editor</button>
                </Link>
            </div>

        </div>
    );
}
