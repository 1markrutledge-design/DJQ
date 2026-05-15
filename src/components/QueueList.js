'use client';

import { DollarSign, Clock, Play, Check } from 'lucide-react';
import { useState, useEffect } from 'react';
import { startSongNowPlaying, markSongAsPlayed } from '@/app/actions';

export default function QueueList({ queue, onComplete, venueCode }) {
    const [nowPlayingId, setNowPlayingId] = useState(null);
    const [playStartTime, setPlayStartTime] = useState(null);
    const [elapsed, setElapsed] = useState(0);

    // Timer effect for counting seconds
    useEffect(() => {
        if (!nowPlayingId || !playStartTime) return;

        const interval = setInterval(() => {
            const seconds = Math.floor((Date.now() - playStartTime) / 1000);
            setElapsed(seconds);
        }, 100); // Update frequently for smooth timer

        return () => clearInterval(interval);
    }, [nowPlayingId, playStartTime]);

    const handleNowPlaying = async (requestId) => {
        const result = await startSongNowPlaying(venueCode, requestId);
        if (result.success) {
            setNowPlayingId(requestId);
            setPlayStartTime(Date.now());
            setElapsed(0);
        }
    };

    const handleMarkPlayed = async (requestId) => {
        const result = await markSongAsPlayed(venueCode, requestId);
        if (result.success) {
            setNowPlayingId(null);
            setPlayStartTime(null);
            setElapsed(0);
            if (onComplete) onComplete(requestId);
        } else if (result.error) {
            alert(result.error);
        }
    };

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    if (!queue || queue.length === 0) {
        return (
            <div style={{ textAlign: 'center', padding: '3rem', color: '#525252' }}>
                <p>No requests yet. The night is young!</p>
            </div>
        );
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {queue.map((req, index) => {
                const isNowPlaying = nowPlayingId === req.id;
                const canMarkPlayed = isNowPlaying && elapsed >= 60;
                const isRefunded = req.refunded || req.status === 'refunded';

                return (
                    <div
                        key={req.id}
                        className="card animate-fade-in"
                        style={{
                            borderLeft: isRefunded
                                ? '4px solid #ef4444'
                                : (req.amount || 0) > 0 ? '4px solid #fbbf24' : '4px solid #6d28d9',
                            background: isRefunded
                                ? 'linear-gradient(90deg, rgba(239,68,68,0.05) 0%, rgba(0,0,0,0) 100%)'
                                : (req.amount || 0) > 0
                                    ? 'linear-gradient(90deg, rgba(251,191,36,0.05) 0%, rgba(0,0,0,0) 100%)'
                                    : 'var(--card-bg)',
                            opacity: isRefunded ? 0.6 : 1
                        }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                {/* Index Number */}
                                <span style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#525252', width: '30px', textAlign: 'center' }}>
                                    {index + 1}
                                </span>

                                <div>
                                    <h3 style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>
                                        {req.song.title}
                                        {isRefunded && <span style={{ color: '#ef4444', fontSize: '0.8rem', marginLeft: '8px' }}>REFUNDED</span>}
                                    </h3>
                                    <p style={{ color: '#a3a3a3', fontSize: '0.9rem' }}>{req.song.artist}</p>

                                    {/* Tip Badge */}
                                    {(req.amount || 0) > 0 && (
                                        <div style={{
                                            marginTop: '4px',
                                            display: 'inline-flex', alignItems: 'center', gap: '4px',
                                            background: 'rgba(251, 191, 36, 0.1)', color: '#fbbf24',
                                            padding: '2px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 'bold'
                                        }}>
                                            <DollarSign size={14} />
                                            <span>${req.amount} Tip</span>
                                        </div>
                                    )}

                                    {/* Now Playing Timer */}
                                    {isNowPlaying && (
                                        <div style={{
                                            marginTop: '8px',
                                            display: 'inline-flex', alignItems: 'center', gap: '4px',
                                            background: canMarkPlayed ? 'rgba(34, 197, 94, 0.1)' : 'rgba(109, 40, 217, 0.1)',
                                            color: canMarkPlayed ? '#22c55e' : '#6d28d9',
                                            padding: '4px 12px', borderRadius: '999px', fontSize: '0.9rem', fontWeight: 'bold'
                                        }}>
                                            <Play size={12} fill="currentColor" />
                                            <span>Playing... {formatTime(elapsed)} / 1:00</span>
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem' }}>
                                {/* Time */}
                                <span style={{ fontSize: '0.8rem', color: '#525252', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <Clock size={12} /> {new Date(req.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>

                                { /* Action Buttons */}
                                {!isRefunded && (
                                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                                        {!isNowPlaying ? (
                                            <>
                                                <button
                                                    onClick={() => {
                                                        if (confirm('Decline this request and refund the user?')) {
                                                            import('@/app/actions').then(actions => actions.refundRequest(venueCode, req.id));
                                                            if (onComplete) onComplete(req.id);
                                                        }
                                                    }}
                                                    style={{
                                                        background: '#404040', border: 'none', color: '#a3a3a3',
                                                        padding: '6px 12px', borderRadius: '999px',
                                                        fontSize: '0.8rem', cursor: 'pointer', fontWeight: '600'
                                                    }}
                                                >
                                                    Decline
                                                </button>
                                                <button
                                                    onClick={() => handleNowPlaying(req.id)}
                                                    style={{
                                                        background: 'linear-gradient(135deg, #6d28d9 0%, #a855f7 100%)',
                                                        border: 'none',
                                                        color: 'white', padding: '6px 16px', borderRadius: '999px',
                                                        fontSize: '0.8rem', cursor: 'pointer', fontWeight: '600',
                                                        display: 'flex', alignItems: 'center', gap: '4px'
                                                    }}
                                                >
                                                    <Play size={12} fill="white" />
                                                    Play
                                                </button>
                                            </>
                                        ) : (
                                            <>
                                                <button
                                                    onClick={() => {
                                                        if (confirm('Skip this song and refund the user?')) {
                                                            import('@/app/actions').then(actions => actions.refundRequest(venueCode, req.id));
                                                            setNowPlayingId(null);
                                                            if (onComplete) onComplete(req.id);
                                                        }
                                                    }}
                                                    style={{
                                                        background: '#404040', border: 'none', color: '#ef4444',
                                                        padding: '6px 12px', borderRadius: '999px',
                                                        fontSize: '0.8rem', cursor: 'pointer', fontWeight: '600'
                                                    }}
                                                >
                                                    Skip/Refund
                                                </button>
                                                <button
                                                    onClick={() => handleMarkPlayed(req.id)}
                                                    disabled={!canMarkPlayed}
                                                    style={{
                                                        background: canMarkPlayed ? '#22c55e' : '#404040',
                                                        border: 'none',
                                                        color: 'white', padding: '6px 16px', borderRadius: '999px',
                                                        fontSize: '0.8rem', cursor: canMarkPlayed ? 'pointer' : 'not-allowed',
                                                        fontWeight: '600',
                                                        opacity: canMarkPlayed ? 1 : 0.5,
                                                        display: 'flex', alignItems: 'center', gap: '4px'
                                                    }}
                                                >
                                                    <Check size={12} />
                                                    {canMarkPlayed ? 'Played' : formatTime(60 - elapsed)}
                                                </button>
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
