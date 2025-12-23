'use client';

import { useState, useEffect } from 'react';
import { fetchAdminData, toggleVenueStatus, destroyVenue } from '../../actions';
import { Power, Trash2, Eye, ShieldAlert } from 'lucide-react';
import Link from 'next/link';

export default function VenuesManager() {
    const [venues, setVenues] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadData();
    }, []);

    async function loadData() {
        setLoading(true);
        const data = await fetchAdminData();
        setVenues(data.venues);
        setLoading(false);
    }

    async function handleFreeze(venue) {
        const action = venue.status === 'frozen' ? 'Unfreeze' : 'Freeze';
        if (!confirm(`${action} venue "${venue.name}"?`)) return;

        await toggleVenueStatus(venue.id, venue.code, venue.status);
        loadData();
    }

    async function handleDelete(venue) {
        const confirmStr = prompt(`Type DELETE to confirm deleting "${venue.name}" permanently.`);
        if (confirmStr !== 'DELETE') return;

        await destroyVenue(venue.id, venue.code);
        loadData();
    }

    if (loading) return <div className="p-8">Loading Venues...</div>;

    return (
        <div style={{ maxWidth: '1000px' }}>
            <h1 style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '2rem' }}>Venue Management</h1>

            <div style={{ display: 'grid', gap: '1rem' }}>
                {venues.length === 0 ? <p>No venues found.</p> : venues.map(venue => {
                    const isFrozen = venue.status === 'frozen';
                    return (
                        <div key={venue.id} className="card" style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            borderLeft: isFrozen ? '4px solid #ef4444' : '4px solid #22c55e',
                            opacity: isFrozen ? 0.7 : 1
                        }}>
                            <div>
                                <h3 style={{ fontSize: '1.2rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    {venue.name}
                                    {isFrozen && <span style={{ fontSize: '0.7rem', background: '#ef4444', padding: '2px 6px', borderRadius: '4px' }}>SUSPENDED</span>}
                                </h3>
                                <div style={{ display: 'flex', gap: '1rem', color: '#a3a3a3', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                                    <code>code: {venue.code}</code>
                                    <span>pass: {venue.password}</span>
                                </div>
                            </div>

                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <Link href={`/admin/venues/${venue.code}`}>
                                    <button className="btn" style={{ background: '#262626', padding: '0.5rem', display: 'flex', gap: '0.5rem' }}>
                                        <Eye size={18} /> View
                                    </button>
                                </Link>

                                <button
                                    onClick={() => handleFreeze(venue)}
                                    className="btn"
                                    style={{ background: isFrozen ? '#22c55e' : '#eab308', color: '#000', padding: '0.5rem', display: 'flex', gap: '0.5rem' }}
                                    title={isFrozen ? "Unfreeze" : "Freeze Login"}
                                >
                                    <Power size={18} /> {isFrozen ? "Activate" : "Freeze"}
                                </button>

                                <button
                                    onClick={() => handleDelete(venue)}
                                    className="btn"
                                    style={{ background: '#ef4444', padding: '0.5rem', display: 'flex', gap: '0.5rem' }}
                                    title="Delete Venue"
                                >
                                    <Trash2 size={18} />
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
