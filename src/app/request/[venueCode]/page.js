'use client';

import { useState } from 'react';
import { submitSongRequest, fetchQueue, boostRequest, fetchPlayHistory, submitVerificationFeedback } from '../../actions';
import SongCard from '@/components/SongCard';
import PaymentModal from '@/components/PaymentModal';
import { Search, Home as HomeIcon } from 'lucide-react';

// Loading songs from Spotify API dynamically based on user search input
import { useEffect } from 'react';

export default function RequestPage({ params }) {
    const { venueCode } = params;
    const [songs, setSongs] = useState([]);
    const [query, setQuery] = useState('');
    const [selectedSong, setSelectedSong] = useState(null);
    const [notification, setNotification] = useState(null);

    // New State for Queue/Boost features
    const [queue, setQueue] = useState([]);
    const [viewMode, setViewMode] = useState('search'); // 'search' | 'queue' | 'history'
    const [boostTarget, setBoostTarget] = useState(null);
    const [playHistory, setPlayHistory] = useState([]);
    const [pendingVerifications, setPendingVerifications] = useState([]);

    useEffect(() => {
        loadQueue();
        loadPlayHistory();
        const interval = setInterval(() => {
            loadQueue();
            loadPlayHistory();
        }, 5000);
        return () => clearInterval(interval);
    }, [venueCode]);

    // Live Spotify Search Debounce effect
    useEffect(() => {
        const fetchSpotifySearch = async () => {
            if (!query.trim()) {
                setSongs([]);
                return;
            }
            try {
                const res = await fetch(`/api/spotify/search?q=${encodeURIComponent(query)}`);
                const data = await res.json();
                if (data.songs) {
                    setSongs(data.songs);
                }
            } catch (err) {
                console.error("Search error", err);
            }
        };

        const timer = setTimeout(() => {
            if (viewMode === 'search') {
                fetchSpotifySearch();
            }
        }, 500); // 500ms debounce

        return () => clearTimeout(timer);
    }, [query, viewMode]);

    async function loadQueue() {
        try {
            const q = await fetchQueue(venueCode);
            setQueue(q);
        } catch (e) {
            console.error("Failed to load queue", e);
        }
    }

    async function loadPlayHistory() {
        try {
            const res = await fetchPlayHistory(venueCode, 20);
            if (res.success) {
                setPlayHistory(res.history);
                // Find pendingverifications
                const pending = res.history.filter(h => h.verificationSent && h.guestConfirmed === null);
                setPendingVerifications(pending);
            }
        } catch (e) {
            console.error("Failed to load history", e);
        }
    }

    const handleVerification = async (requestId, confirmed) => {
        const res = await submitVerificationFeedback(venueCode, requestId, confirmed);
        if (res.success) {
            setNotification({ type: 'success', message: confirmed ? 'Thanks for confirming!' : 'Feedback received' });
            loadPlayHistory();
        }
        setTimeout(() => setNotification(null), 3000);
    };

    const filteredSongs = songs; // We now rely on the API for filtering

    const handlePaymentConfirm = async (paymentData) => {
        if (boostTarget) {
            // Handle Boost
            const res = await boostRequest(venueCode, boostTarget.id, paymentData.amount);
            if (res.success) {
                setBoostTarget(null);
                setNotification({ type: 'success', message: 'Boosted! 🚀' });
                loadQueue();
            } else {
                setNotification({ type: 'error', message: res.error });
            }
        } else {
            // Handle New Request
            const res = await submitSongRequest(venueCode, paymentData);
            if (res.success) {
                setSelectedSong(null);
                setNotification({ type: 'success', message: 'Request sent to DJ!' });
                loadQueue();
            } else {
                setNotification({ type: 'error', message: res.error || 'Failed to send request.' });
            }
        }
        setTimeout(() => setNotification(null), 3000);
    };

    return (
        <div className="container" style={{ paddingBottom: '100px' }}>
            {/* Header */}
            <div style={{ marginBottom: '1.5rem', paddingTop: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                <a href="/" style={{ position: 'absolute', left: 0, color: '#a3a3a3' }}>
                    <HomeIcon size={24} />
                </a>
                <div style={{ textAlign: 'center' }}>
                    <p style={{ fontSize: '0.9rem', color: '#a3a3a3', letterSpacing: '1px' }}>VENUE</p>
                    <h1 style={{ fontSize: '2.5rem', fontWeight: '900' }}>#{venueCode}</h1>
                </div>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', background: 'rgba(255,255,255,0.1)', padding: '4px', borderRadius: '12px', marginBottom: '1.5rem' }}>
                <button
                    onClick={() => setViewMode('search')}
                    style={{ flex: 1, padding: '8px', borderRadius: '8px', border: 'none', background: viewMode === 'search' ? 'white' : 'transparent', color: viewMode === 'search' ? 'black' : 'white', fontWeight: 'bold' }}
                >
                    Request Song
                </button>
                <button
                    onClick={() => setViewMode('queue')}
                    style={{ flex: 1, padding: '8px', borderRadius: '8px', border: 'none', background: viewMode === 'queue' ? 'white' : 'transparent', color: viewMode === 'queue' ? 'black' : 'white', fontWeight: 'bold' }}
                >
                    Live Queue
                </button>
                <button
                    onClick={() => setViewMode('history')}
                    style={{ flex: 1, padding: '8px', borderRadius: '8px', border: 'none', background: viewMode === 'history' ? 'white' : 'transparent', color: viewMode === 'history' ? 'black' : 'white', fontWeight: 'bold', position: 'relative' }}
                >
                    Play History
                    {pendingVerifications.length > 0 && (
                        <span style={{ position: 'absolute', top: '2px', right: '2px', background: '#ef4444', width: '8px', height: '8px', borderRadius: '50%' }} />
                    )}
                </button>
            </div>

            {viewMode === 'search' ? (
                <>
                    {/* Search */}
                    <div style={{ position: 'sticky', top: '1rem', zIndex: 10, marginBottom: '1.5rem' }}>
                        <div style={{ position: 'relative' }}>
                            <Search style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: '#a3a3a3' }} size={20} />
                            <input
                                className="input"
                                placeholder="Search songs or artists..."
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                style={{ paddingLeft: '3rem', background: 'rgba(23, 23, 23, 0.95)', backdropFilter: 'blur(10px)', border: '1px solid #404040' }}
                            />
                        </div>
                    </div>

                    {/* Song List */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        {filteredSongs.map(song => (
                            <SongCard key={song.id} song={song} onSelect={setSelectedSong} />
                        ))}
                        {filteredSongs.length === 0 && query && (
                            <p style={{ textAlign: 'center', color: '#525252', padding: '2rem' }}>No songs found. Try a different search.</p>
                        )}
                    </div>
                </>
            ) : viewMode === 'queue' ? (
                /* LIVE QUEUE VIEW */
                <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                    {queue.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '2rem', color: '#a3a3a3' }}>
                            <p>Queue is empty. Be the first!</p>
                            <button onClick={() => setViewMode('search')} className="btn btn-primary" style={{ marginTop: '1rem', width: 'auto' }}>Request Now</button>
                        </div>
                    ) : (
                        queue.map((req, i) => (
                            <div key={req.id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderLeft: (req.amount || 0) > 0 ? '4px solid #fbbf24' : '4px solid #404040' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                    <span style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#525252', width: '30px' }}>{i + 1}</span>
                                    <div>
                                        <h3 style={{ fontWeight: 'bold' }}>{req.song.title}</h3>
                                        <p style={{ fontSize: '0.9rem', color: '#a3a3a3' }}>{req.song.artist}</p>
                                        {(req.amount || 0) > 0 && <span style={{ fontSize: '0.8rem', color: '#fbbf24', fontWeight: 'bold' }}>${req.amount} Tip ✨</span>}
                                    </div>
                                </div>
                                <button
                                    onClick={() => setBoostTarget(req)}
                                    style={{ background: '#262626', border: '1px solid #404040', color: '#fbbf24', padding: '0.5rem 1rem', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' }}
                                >
                                    Boost 🚀
                                </button>
                            </div>
                        ))
                    )}
                </div>
            ) : viewMode === 'history' ? (
                /* PLAY HISTORY VIEW */
                <div className="animate-fade-in">
                    {/* Pending Verifications */}
                    {pendingVerifications.length > 0 && (
                        <div style={{ marginBottom: '1.5rem' }}>
                            <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', color: '#fbbf24' }}>Verification Needed</h3>
                            {pendingVerifications.map(req => (
                                <div key={req.id} className="card" style={{ borderLeft: '4px solid #fbbf24', marginBottom: '0.75rem' }}>
                                    <h4 style={{ fontWeight: 'bold', marginBottom: '0.25rem' }}>{req.song.title}</h4>
                                    <p style={{ fontSize: '0.9rem', color: '#a3a3a3', marginBottom: '1rem' }}>{req.song.artist}</p>
                                    <p style={{ fontSize: '0.9rem', marginBottom: '1rem', color: '#d4d4d4' }}>Did you hear this song played?</p>
                                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                                        <button
                                            onClick={() => handleVerification(req.id, true)}
                                            style={{ flex: 1, background: '#22c55e', color: 'white', border: 'none', padding: '0.5rem', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' }}
                                        >
                                            ✓ Yes
                                        </button>
                                        <button
                                            onClick={() => handleVerification(req.id, false)}
                                            style={{ flex: 1, background: '#ef4444', color: 'white', border: 'none', padding: '0.5rem', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' }}
                                        >
                                            ✗ No
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Recently Played</h3>
                    {playHistory.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '2rem', color: '#a3a3a3' }}>
                            <p>No songs played yet.</p>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {playHistory.map(req => (
                                <div key={req.id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div>
                                        <h4 style={{ fontWeight: 'bold' }}>{req.song.title}</h4>
                                        <p style={{ fontSize: '0.9rem', color: '#a3a3a3' }}>{req.song.artist}</p>
                                        {req.guestConfirmed === true && (
                                            <span style={{ fontSize: '0.8rem', color: '#22c55e' }}>✓ Verified</span>
                                        )}
                                    </div>
                                    <div style={{ textAlign: 'right' }}>
                                        <p style={{ fontSize: '0.8rem', color: '#525252' }}>
                                            {new Date(req.playedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            ) : null}

            {/* Payment Modal (Used for both New Request and Boost) */}
            {(selectedSong || boostTarget) && (
                <PaymentModal
                    song={selectedSong || boostTarget.song}
                    title={boostTarget ? `Boost "${boostTarget.song.title}"` : undefined}
                    onClose={() => { setSelectedSong(null); setBoostTarget(null); }}
                    onConfirm={handlePaymentConfirm}
                />
            )}

            {/* Notification Toast */}
            {notification && (
                <div className="animate-fade-in" style={{
                    position: 'fixed', bottom: '2rem', left: '50%', transform: 'translateX(-50%)',
                    background: notification.type === 'success' ? '#10b981' : '#ef4444',
                    color: 'white', padding: '1rem 2rem', borderRadius: '999px', fontWeight: 'bold',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.5)', zIndex: 100
                }}>
                    {notification.message}
                </div>
            )}
        </div>
    );
}
