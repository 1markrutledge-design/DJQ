'use client';

import { DollarSign, Clock } from 'lucide-react';

export default function QueueList({ queue, onComplete }) {
    if (!queue || queue.length === 0) {
        return (
            <div style={{ textAlign: 'center', padding: '3rem', color: '#525252' }}>
                <p>No requests yet. The night is young!</p>
            </div>
        );
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {queue.map((req, index) => (
                <div
                    key={req.id}
                    className="card animate-fade-in"
                    style={{
                        // Highlight high value tips
                        borderLeft: (req.amount || 0) > 0 ? '4px solid #fbbf24' : '4px solid #6d28d9',
                        background: (req.amount || 0) > 0 ? 'linear-gradient(90deg, rgba(251,191,36,0.05) 0%, rgba(0,0,0,0) 100%)' : 'var(--card-bg)'
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            {/* Index Number */}
                            <span style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#525252', width: '30px', textAlign: 'center' }}>
                                {index + 1}
                            </span>

                            <div>
                                <h3 style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>{req.song.title}</h3>
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
                                        <span>{req.amount} Tip</span>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem' }}>
                            {/* Time */}
                            <span style={{ fontSize: '0.8rem', color: '#525252', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Clock size={12} /> {new Date(req.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>

                            {/* Mark as Played Button */}
                            <button
                                onClick={() => onComplete && onComplete(req.id)}
                                style={{
                                    background: '#262626', border: '1px solid #404040',
                                    color: '#d4d4d4', padding: '6px 16px', borderRadius: '999px',
                                    fontSize: '0.8rem', cursor: 'pointer', fontWeight: '600'
                                }}
                            >
                                Played
                            </button>
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}
