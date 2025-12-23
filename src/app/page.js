'use client';

import { createVenue, validateVenue, login, registerUser } from './actions';
import { useState, useEffect } from 'react';

export default function Home() {
    const [authMode, setAuthMode] = useState('guest'); // 'guest' | 'login' | 'signup' | 'partner_register'
    const [newVenueCode, setNewVenueCode] = useState(null);

    const [recentVenues, setRecentVenues] = useState([]);

    useEffect(() => {
        // Auto-redirect if logged in
        const session = localStorage.getItem('user_session');
        if (session) {
            window.location.href = '/user';
            return;
        }

        const stored = localStorage.getItem('recent_venues');
        if (stored) {
            try {
                setRecentVenues(JSON.parse(stored));
            } catch (e) {
                console.error("Failed to parse recent venues");
            }
        }
    }, []);

    const addToRecent = (code, name) => {
        const newEntry = { code, name, timestamp: Date.now() };
        // Filter out existing to avoid duplicates, keep top 3
        const updated = [newEntry, ...recentVenues.filter(v => v.code !== code)].slice(0, 3);
        setRecentVenues(updated);
        localStorage.setItem('recent_venues', JSON.stringify(updated));
    };

    return (
        <div className="bg-home" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
            <main className="container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>

                <div className="animate-fade-in" style={{ width: '100%', maxWidth: '400px', textAlign: 'center' }}>
                    <h1 style={{
                        fontSize: '3rem', fontWeight: '900', letterSpacing: '-2px', marginBottom: '0.5rem',
                        background: 'linear-gradient(to right, #6d28d9, #ec4899)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent'
                    }}>
                        DJ Queue
                    </h1>
                    <p style={{ color: '#a3a3a3', marginBottom: '2rem' }}>The premium request experience.</p>

                    {/* Main Toggle: Guest vs Member */}
                    <div style={{ background: '#262626', padding: '4px', borderRadius: '12px', display: 'flex', marginBottom: '2rem' }}>
                        <button
                            onClick={() => setAuthMode('guest')}
                            style={{
                                flex: 1, padding: '10px', borderRadius: '8px', border: 'none', fontWeight: '600',
                                background: authMode === 'guest' ? '#404040' : 'transparent', color: authMode === 'guest' ? 'white' : '#a3a3a3', cursor: 'pointer', transition: 'all 0.2s'
                            }}
                        >
                            Guest
                        </button>
                        <button
                            onClick={() => setAuthMode('login')}
                            style={{
                                flex: 1, padding: '10px', borderRadius: '8px', border: 'none', fontWeight: '600',
                                background: (authMode === 'login' || authMode === 'signup') ? '#404040' : 'transparent', color: (authMode === 'login' || authMode === 'signup') ? 'white' : '#a3a3a3', cursor: 'pointer', transition: 'all 0.2s'
                            }}
                        >
                            Log In
                        </button>
                    </div>

                    {/* --- GUEST MODE --- */}
                    {authMode === 'guest' && (
                        <>
                            <form
                                onSubmit={async (e) => {
                                    e.preventDefault();
                                    const formData = new FormData(e.target);
                                    const res = await validateVenue(formData);
                                    if (res?.isHiddenRedirect) {
                                        window.location.href = '/admin';
                                        return;
                                    }
                                    if (res?.error) {
                                        alert(res.error);
                                    } else if (res?.success) {
                                        addToRecent(res.code, res.name);
                                        window.location.href = `/request/${res.code}`;
                                    }
                                }}
                                className="animate-fade-in card"
                                style={{ padding: '2rem', marginBottom: '2rem' }}
                            >
                                <h2 style={{ marginBottom: '1.5rem', fontSize: '1.25rem' }}>Enter Venue Code</h2>
                                <input
                                    name="code"
                                    className="input"
                                    placeholder="e.g. SPACE24"
                                    style={{ textAlign: 'center', fontSize: '1.5rem', letterSpacing: '2px', textTransform: 'uppercase', marginBottom: '1.5rem' }}
                                    required
                                />
                                <button type="submit" className="btn btn-primary">Join Party</button>
                            </form>

                            {/* RECENT VENUES */}
                            {recentVenues.length > 0 && (
                                <div className="animate-fade-in">
                                    <h3 style={{
                                        fontSize: '0.9rem', fontWeight: 'bold', color: '#737373',
                                        textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '1rem',
                                        textAlign: 'left'
                                    }}>
                                        Recent Venues
                                    </h3>
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
                                </div>
                            )}
                        </>
                    )}

                    {/* --- LOGIN MODE --- */}
                    {authMode === 'login' && (
                        <div className="animate-fade-in card" style={{ padding: '2rem' }}>
                            <form action={async (formData) => {
                                const res = await login(formData);
                                if (res.success) {
                                    // Make sure we save user session locally if needed, for recent venues etc.
                                    if (res.type === 'user') {
                                        localStorage.setItem('user_session', res.username);
                                    }
                                    window.location.href = res.redirect;
                                } else {
                                    alert(res.error);
                                }
                            }}>
                                <h2 style={{ marginBottom: '1.5rem', fontSize: '1.25rem' }}>Welcome Back</h2>
                                <input name="username" className="input" placeholder="Username or Venue Code" style={{ marginBottom: '1rem' }} required />
                                <input name="password" type="password" className="input" placeholder="Password" style={{ marginBottom: '1rem' }} required />
                                <button type="submit" className="btn btn-primary" style={{ marginBottom: '1rem' }}>Log In</button>
                            </form>

                            <div style={{ borderTop: '1px solid #404040', paddingTop: '1rem', marginTop: '0.5rem' }}>
                                <p style={{ fontSize: '0.9rem', color: '#a3a3a3', marginBottom: '0.5rem' }}>New here?</p>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    <button onClick={() => setAuthMode('signup')} style={{ flex: 1, background: 'none', border: '1px solid #404040', color: 'white', padding: '8px', borderRadius: '8px', cursor: 'pointer' }}>Sign Up</button>
                                    <button onClick={() => setAuthMode('partner_register')} style={{ flex: 1, background: 'none', border: '1px solid #404040', color: '#fbbf24', padding: '8px', borderRadius: '8px', cursor: 'pointer' }}>Create Venue</button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* --- SIGNUP MODE --- */}
                    {authMode === 'signup' && (
                        <div className="animate-fade-in card" style={{ padding: '2rem' }}>
                            <form action={async (formData) => {
                                const res = await registerUser(formData);
                                if (res.success) {
                                    // Auto login
                                    const loginRes = await login(formData);
                                    if (loginRes.success && loginRes.type === 'user') {
                                        localStorage.setItem('user_session', loginRes.username);
                                        window.location.href = loginRes.redirect;
                                    } else {
                                        setAuthMode('login');
                                    }
                                } else {
                                    alert(res.error);
                                }
                            }}>
                                <h2 style={{ marginBottom: '1.5rem', fontSize: '1.25rem' }}>Create Account</h2>
                                <input name="username" className="input" placeholder="Choose Username" style={{ marginBottom: '1rem' }} required />
                                <input name="password" type="password" className="input" placeholder="Choose Password" style={{ marginBottom: '1rem' }} required />
                                <button type="submit" className="btn btn-primary" style={{ marginBottom: '1rem' }}>Sign Up</button>
                                <p style={{ fontSize: '0.9rem', color: '#a3a3a3', cursor: 'pointer', textAlign: 'center' }} onClick={() => setAuthMode('login')}>
                                    Already have an account? Log In
                                </p>
                            </form>
                        </div>
                    )}

                    {/* --- VENUE REGISTER MODE --- */}
                    {authMode === 'partner_register' && (
                        <div className="animate-fade-in card" style={{ padding: '2rem' }}>
                            {newVenueCode ? (
                                <div>
                                    <h2 style={{ color: '#fbbf24', marginBottom: '1rem' }}>Venue Created!</h2>
                                    <p style={{ color: '#a3a3a3' }}>Your Code:</p>
                                    <div style={{ fontSize: '2.5rem', fontWeight: 'bold', margin: '1rem 0', letterSpacing: '2px' }}>{newVenueCode}</div>
                                    <p style={{ fontSize: '0.9rem', color: '#525252' }}>Use this code to login to your dashboard.</p>
                                    <a href={`/dashboard/${newVenueCode}`} className="btn btn-premium" style={{ marginTop: '1rem', textDecoration: 'none' }}>Go to Dashboard</a>
                                    <button
                                        onClick={() => { setNewVenueCode(null); setAuthMode('login'); }}
                                        style={{ display: 'block', margin: '1rem auto 0', background: 'none', border: 'none', color: '#a3a3a3', cursor: 'pointer', fontSize: '0.9rem' }}
                                    >
                                        Close
                                    </button>
                                </div>
                            ) : (
                                <form action={async (formData) => {
                                    const res = await createVenue(formData);
                                    if (res?.isHiddenRedirect) { window.location.href = '/admin'; return; }
                                    if (res.error) {
                                        alert(res.error);
                                    } else if (res.success) {
                                        setNewVenueCode(res.code);
                                    }
                                }}>
                                    <h2 style={{ marginBottom: '1.5rem', fontSize: '1.25rem' }}>Register Venue</h2>
                                    <input name="name" className="input" placeholder="Venue Name" style={{ marginBottom: '1rem' }} required />
                                    <input name="password" type="password" className="input" placeholder="Set Password" style={{ marginBottom: '1rem' }} required />
                                    <button type="submit" className="btn btn-primary" style={{ marginBottom: '1rem' }}>Create Code</button>
                                    <p style={{ fontSize: '0.9rem', color: '#a3a3a3', cursor: 'pointer', textAlign: 'center' }} onClick={() => setAuthMode('login')}>
                                        Back to Login
                                    </p>
                                </form>
                            )}
                        </div>
                    )}

                </div>
            </main>
        </div>
    );
}
