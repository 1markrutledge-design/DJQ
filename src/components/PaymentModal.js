'use client';

import { useState } from 'react';
import { CreditCard, Zap, Check } from 'lucide-react';

export default function PaymentModal({ song, title, onClose, onConfirm }) {
    const [processing, setProcessing] = useState(false);
    const [tipAmount, setTipAmount] = useState(3); // Default value

    const handlePay = async () => {
        setProcessing(true);
        // Simulate network delay for "Apple Pay" feel
        setTimeout(() => {
            onConfirm({
                song,
                queueType: 'Standard', // Deprecated in UI but kept for schema
                amount: tipAmount
            });
        }, 1500);
    };

    // Scroll Picker Logic: Simple approach using scroll-snap
    const amounts = [1, 2, 3, 4, 5];

    return (
        <div style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
            display: 'flex', alignItems: 'flex-end', justifyContent: 'center', zIndex: 50
        }}>
            <div className="animate-fade-in" style={{
                background: '#171717', width: '100%', maxWidth: '600px',
                borderTopLeftRadius: '20px', borderTopRightRadius: '20px',
                padding: '1.5rem', borderTop: '1px solid #262626'
            }}>

                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                    <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>{title || 'Confirm Request'}</h2>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#666', fontSize: '1.5rem' }}>&times;</button>
                </div>

                {/* Song Info */}
                <div style={{ marginBottom: '1.5rem', paddingBottom: '1rem', borderBottom: '1px solid #262626', textAlign: 'center' }}>
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '0.25rem' }}>{song.title}</h3>
                    <p style={{ color: '#a3a3a3' }}>{song.artist}</p>
                </div>

                {/* SCROLL PICKER */}
                <div style={{ marginBottom: '2rem', position: 'relative', height: '160px', overflow: 'hidden' }}>

                    {/* Selection Highlight / Lens */}
                    <div style={{
                        position: 'absolute', top: '50%', left: '0', right: '0', height: '50px',
                        transform: 'translateY(-50%)',
                        borderTop: '1px solid #404040', borderBottom: '1px solid #404040',
                        background: 'rgba(255,255,255,0.05)', pointerEvents: 'none'
                    }}></div>

                    {/* Scroll Container */}
                    <div
                        onScroll={(e) => {
                            // Calculate which item is centered
                            const itemHeight = 50;
                            const scrollTop = e.target.scrollTop;
                            const centerIndex = Math.round(scrollTop / itemHeight);
                            if (amounts[centerIndex]) {
                                setTipAmount(amounts[centerIndex]);
                            }
                        }}
                        style={{
                            height: '100%',
                            overflowY: 'scroll',
                            scrollSnapType: 'y mandatory',
                            paddingTop: '55px', // Buffer to center first item
                            paddingBottom: '55px', // Buffer to center last item
                        }}
                        className="no-scrollbar" // Add utility if needed or style scrollbar hidden
                    >
                        {amounts.map((amt) => (
                            <div
                                key={amt}
                                style={{
                                    height: '50px',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    scrollSnapAlign: 'center',
                                    fontSize: tipAmount === amt ? '2rem' : '1.5rem',
                                    fontWeight: tipAmount === amt ? 'bold' : 'normal',
                                    color: tipAmount === amt ? '#fbbf24' : '#525252',
                                    transition: 'all 0.2s ease'
                                }}
                            >
                                ${amt}.00
                            </div>
                        ))}
                    </div>
                </div>

                {/* Pay Button */}
                <button
                    onClick={handlePay}
                    disabled={processing}
                    className="btn"
                    style={{
                        background: 'black', color: 'white',
                        border: '1px solid #333',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
                        height: '56px', fontSize: '1.1rem'
                    }}
                >
                    {processing ? (
                        <span>Processing...</span>
                    ) : (
                        <>
                            <span style={{ fontWeight: '900', letterSpacing: '-0.5px' }}>Pay ${tipAmount}.00</span> with Pay
                        </>
                    )}
                </button>
                <p style={{ textAlign: 'center', fontSize: '0.75rem', color: '#525252', marginTop: '1rem' }}>
                    This is a secure mock payment. No real money will be charged.
                </p>
            </div>

            <style jsx>{`
                .no-scrollbar::-webkit-scrollbar {
                    display: none;
                }
                .no-scrollbar {
                    -ms-overflow-style: none;
                    scrollbar-width: none;
                }
            `}</style>
        </div>
    );
}
