'use client';

import { useState, useEffect } from 'react';
import { Home, LogOut } from 'lucide-react';

export default function UserDashboard() {
    const [username, setUsername] = useState('User');
    const [recentVenues, setRecentVenues] = useState([]);

    useEffect(() => {
        const user = localStorage.getItem('user_session');
        if (user) setUsername(user);

        const stored = localStorage.getItem('recent_venues');
        if (stored) {
            try { setRecentVenues(JSON.parse(stored)); } catch (e) { }
        }
    }, []);

    const handleLogout = () => {
        localStorage.removeItem('user_session');
        window.location.href = '/';
    };

    return (
        <div className="bg-home" style={{ minHeight: '100vh', padding: '1.5rem' }}>
            <div className="container">
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                    <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>Hello, {username} 👋</h1>
                    <button onClick={handleLogout} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>
                        <LogOut size={24} />
                    </button>
                </div>

                {/* Content */}
                <div className="card text-center" style={{ padding: '2rem', marginBottom: '2rem' }}>
                    <h2 style={{ fontSize: '2rem', fontWeight: '900', marginBottom: '0.5rem' }}>Ready to Party?</h2>
                    <p style={{ color: '#a3a3a3', marginBottom: '1.5rem' }}>Find a venue or use a code to join the queue.</p>

                    <a href="/" className="btn btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', textDecoration: 'none' }}>
                        <Home size={18} /> Join Venue
                    </a>
                </div>

                {/* Recent Venues (Shared with Guest logic for now) */}
                <h3 style={{ fontSize: '1rem', fontWeight: 'bold', color: '#a3a3a3', marginBottom: '1rem' }}>RECENT VENUES</h3>
                {recentVenues.length === 0 ? (
                    <p style={{ color: '#525252', textAlign: 'center' }}>No history yet.</p>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        {recentVenues.map(venue => (
                            <div
                                key={venue.code}
                                className="card"
                                style={{
                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                    padding: '1rem', cursor: 'pointer', border: '1px solid #404040',
                                    transition: 'all 0.2s'
                                }}
                                onClick={() => window.location.href = `/request/${venue.code}`}
                            >
                                <div style={{ textAlign: 'left' }}>
                                    <h4 style={{ fontWeight: 'bold', fontSize: '1.1rem' }}>{venue.name}</h4>
                                    <span style={{ fontSize: '0.8rem', color: '#a3a3a3', letterSpacing: '1px' }}>#{venue.code}</span>
                                </div>
                                <button
                                    style={{
                                        background: '#262626', color: 'white', border: 'none',
                                        padding: '8px 16px', borderRadius: '999px', fontSize: '0.9rem', fontWeight: '600'
                                    }}
                                >
                                    Join
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
