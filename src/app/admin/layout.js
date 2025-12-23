'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Store, BarChart3, Music, LogOut } from 'lucide-react';

export default function AdminLayout({ children }) {
    const [authed, setAuthed] = useState(false);
    const [password, setPassword] = useState('');
    const pathname = usePathname();

    // Persist session slightly better? Or just keep simple state.
    // For simplicity, we keep state. This means refresh = login again.
    // User requested "pages", so navigation is key. 
    // If we navigate, state triggers refresh IF layout unmounts? 
    // Layouts persis in Next.js! So state is preserved on navigation. Perfect.

    if (!authed) {
        return (
            <div className="container" style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div className="card" style={{ width: '100%', maxWidth: '400px', textAlign: 'center' }}>
                    <h1 style={{ marginBottom: '1rem', color: '#fbbf24' }}>Master Control</h1>
                    <form onSubmit={(e) => {
                        e.preventDefault();
                        if (password === 'Sleeper593!!') setAuthed(true);
                        else alert('Wrong password');
                    }}>
                        <input
                            type="password"
                            className="input"
                            placeholder="Enter Passcode"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            style={{ marginBottom: '1rem' }}
                        />
                        <button className="btn btn-primary">Login</button>
                    </form>
                </div>
            </div>
        );
    }

    const navItems = [
        { name: 'Dashboard', href: '/admin', icon: LayoutDashboard },
        { name: 'Venues', href: '/admin/venues', icon: Store },
        { name: 'Metrics', href: '/admin/metrics', icon: BarChart3 },
        { name: 'Song DB', href: '/admin/songs', icon: Music },
    ];

    return (
        <div style={{ display: 'flex', minHeight: '100vh', background: '#000' }}>
            {/* Sidebar */}
            <aside style={{ width: '250px', borderRight: '1px solid #262626', padding: '2rem', display: 'flex', flexDirection: 'column' }}>
                <Link href="/" style={{ textDecoration: 'none' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '2rem', color: '#fbbf24' }}>DJ Queue</h2>
                </Link>

                <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {navItems.map(item => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.name}
                                href={item.href}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.75rem',
                                    padding: '0.75rem 1rem',
                                    borderRadius: '8px',
                                    color: isActive ? '#fff' : '#a3a3a3',
                                    background: isActive ? '#262626' : 'transparent',
                                    fontWeight: isActive ? 'bold' : 'normal',
                                    transition: 'all 0.2s'
                                }}
                            >
                                <item.icon size={20} />
                                {item.name}
                            </Link>
                        );
                    })}
                </nav>

                <button
                    onClick={() => setAuthed(false)}
                    style={{
                        display: 'flex', alignItems: 'center', gap: '0.75rem',
                        padding: '0.75rem 1rem', background: 'none', border: 'none',
                        color: '#ef4444', cursor: 'pointer', marginTop: 'auto'
                    }}
                >
                    <LogOut size={20} /> Logout
                </button>
            </aside>

            {/* Main Content */}
            <main style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
                {children}
            </main>
        </div>
    );
}
