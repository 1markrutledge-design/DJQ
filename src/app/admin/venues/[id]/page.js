'use client';

import { useState, useEffect } from 'react';
import { fetchQueue } from '../../../actions';
import { ArrowLeft, Clock } from 'lucide-react';
import Link from 'next/link';

export default function AdminVenueView({ params }) {
    const { id: venueCode } = params; // route is [id] but effectively using code
    const [queue, setQueue] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchQueue(venueCode).then(res => {
            setQueue(res);
            setLoading(false);
        });
    }, [venueCode]);

    if (loading) return <div className="p-8">Loading Queue...</div>;

    const revenue = queue.reduce((acc, req) => acc + (req.amount || 0), 0);

    return (
        <div style={{ maxWidth: '800px' }}>
            <Link href="/admin/venues" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#a3a3a3', marginBottom: '2rem' }}>
                <ArrowLeft size={18} /> Back to Venues
            </Link>

            <header style={{ marginBottom: '2rem', borderBottom: '1px solid #262626', paddingBottom: '1rem' }}>
                <h1 style={{ fontSize: '2rem', fontWeight: 'bold' }}>{venueCode} Live Queue</h1>
                <p style={{ color: '#fbbf24', fontSize: '1.2rem' }}>Current Revenue: ${revenue.toFixed(2)}</p>
                <p style={{ color: '#a3a3a3' }}>{queue.length} Songs Pending</p>
            </header>

            <div style={{ display: 'grid', gap: '1rem' }}>
                {queue.length === 0 ? <p>Queue is empty.</p> : queue.map(req => (
                    <div key={req.id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <h3 style={{ fontWeight: 'bold' }}>{req.song.title}</h3>
                            <p style={{ fontSize: '0.9rem', color: '#a3a3a3' }}>{req.song.artist}</p>
                            {req.queueType === 'Premium' && (
                                <span style={{ fontSize: '0.7rem', background: '#fbbf24', color: 'black', padding: '2px 6px', borderRadius: '4px', marginTop: '4px', display: 'inline-block' }}>
                                    ${req.amount} TIP
                                </span>
                            )}
                        </div>
                        <div style={{ textAlign: 'right', fontSize: '0.8rem', color: '#525252' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Clock size={14} />
                                {new Date(req.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
