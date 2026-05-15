'use client';

import { useState, useEffect } from 'react';
import QueueList from '@/components/QueueList';
import { fetchQueue, removeSong, validateVenueLogin, checkForExpiredRequests } from '../../actions';

export default function DashboardPage({ params }) {
    const { venueCode } = params;
    const [queue, setQueue] = useState([]);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');

    const load = async () => {
        // Check for expired requests (auto-refund)
        await checkForExpiredRequests(venueCode);
        const data = await fetchQueue(venueCode);
        if (Array.isArray(data)) setQueue(data);
    };

    // Polling for real-time effect
    useEffect(() => {
        if (!isAuthenticated) return;

        load(); // Initial load
        const interval = setInterval(load, 5000); // Poll every 5s
        return () => clearInterval(interval);
    }, [venueCode, isAuthenticated]);

    const handleComplete = async (requestId) => {
        // Find request to get spotifyUri
        const req = queue.find(r => r.id === requestId);

        // Optimistic update
        setQueue(prev => prev.filter(r => r.id !== requestId));
        await removeSong(venueCode, requestId);

        // Add to Spotify Queue
        if (req && req.song && req.song.spotifyUri) {
            try {
                const res = await fetch('/api/spotify/queue', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        venueCode,
                        spotifyUri: req.song.spotifyUri
                    })
                });
                const data = await res.json();
                if (!res.ok) {
                    alert(`Failed to add to Spotify Queue: ${data.error || 'Unknown error'}`);
                }
            } catch (err) {
                console.error("Spotify Queue add error:", err);
            }
        }

        load(); // Re-fetch to be safe
    };

    const handleLogin = async (e) => {
        e.preventDefault();
        const res = await validateVenueLogin(venueCode, password);
        if (res.success) {
            setIsAuthenticated(true);
            setError('');
        } else {
            setError('Invalid Password');
        }
    };

    // LOGIN VIEW
    if (!isAuthenticated) {
        return (
            <div className="container" style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div className="card animate-fade-in" style={{ width: '100%', maxWidth: '400px', textAlign: 'center', padding: '2rem' }}>
                    <h1 style={{ marginBottom: '0.5rem', color: '#fbbf24' }}>Venue Login</h1>
                    <p style={{ color: '#a3a3a3', marginBottom: '1.5rem' }}>Enter password for {venueCode}</p>

                    <form onSubmit={handleLogin}>
                        <input
                            type="password"
                            className="input"
                            placeholder="Password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            style={{ marginBottom: '1rem' }}
                        />
                        {error && <p style={{ color: '#ef4444', marginBottom: '1rem' }}>{error}</p>}
                        <button type="submit" className="btn btn-primary">Enter Dashboard</button>
                    </form>
                    <a href="/" style={{ display: 'block', marginTop: '1.5rem', color: '#a3a3a3', textDecoration: 'none', fontSize: '0.9rem' }}>
                        &larr; Back to Home
                    </a>
                </div>
            </div>
        );
    }

    // DASHBOARD VIEW
    const totalRevenue = queue.reduce((acc, curr) => acc + (curr.amount || 0), 0);
    const myCut = (totalRevenue * 0.30).toFixed(2); // 30% to venue

    return (
        <div className="container" style={{ maxWidth: '800px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', marginBottom: '2rem', paddingTop: '1rem', borderBottom: '1px solid #262626', paddingBottom: '1rem' }}>
                <div>
                    <a href="/" style={{ fontSize: '0.9rem', color: '#a3a3a3', textDecoration: 'none' }}>&larr; Home</a>
                    <h1 style={{ fontSize: '2.5rem', fontWeight: '900', color: '#fbbf24', marginTop: '0.5rem' }}>#{venueCode}</h1>
                </div>
                <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem' }}>
                    <button onClick={() => setIsAuthenticated(false)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '0.9rem' }}>Log Out</button>
                    <div>
                        <p style={{ fontSize: '0.9rem', color: '#a3a3a3' }}>YOUR EARNINGS</p>
                        <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>${myCut}</div>
                    </div>
                </div>
            </div>

            {/* Spotify Connection Header */}
            <div style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'center' }}>
                <a
                    href={`/api/spotify/login?venueCode=${venueCode}`}
                    className="btn"
                    style={{
                        background: '#1DB954',
                        color: 'white',
                        padding: '0.75rem 1.5rem',
                        borderRadius: '99px',
                        textDecoration: 'none',
                        fontWeight: 'bold',
                        display: 'inline-block'
                    }}
                >
                    Connect to Spotify
                </a>
            </div>

            <div style={{ marginBottom: '1rem', display: 'flex', gap: '1rem' }}>
                <div style={{ background: '#262626', padding: '1rem', borderRadius: '12px', flex: 1 }}>
                    <p style={{ color: '#a3a3a3', fontSize: '0.8rem' }}>QUEUE LENGTH</p>
                    <p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{queue.length}</p>
                </div>
                <div style={{ background: '#262626', padding: '1rem', borderRadius: '12px', flex: 1 }}>
                    <p style={{ color: '#a3a3a3', fontSize: '0.8rem' }}>PREMIUM REQUESTS</p>
                    <p style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#fbbf24' }}>
                        {queue.filter(q => q.queueType === 'Premium').length}
                    </p>
                </div>
            </div>

            <h2 style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>Current Queue</h2>
            <QueueList queue={queue} onComplete={handleComplete} venueCode={venueCode} />
        </div>
    );
}
