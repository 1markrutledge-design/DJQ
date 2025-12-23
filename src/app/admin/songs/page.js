'use client';

import { useState, useEffect } from 'react';
import { fetchSongs, createNewSong, deleteGlobalSong } from '../../actions';
import { ArrowLeft, Trash2, Plus, Music } from 'lucide-react';
import Link from 'next/link';

export default function SongManagerPage() {
    const [songs, setSongs] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadSongs();
    }, []);

    async function loadSongs() {
        setLoading(true);
        const res = await fetchSongs();
        setSongs(res);
        setLoading(false);
    }

    async function handleAdd(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        await createNewSong(formData);
        e.target.reset();
        loadSongs();
    }

    async function handleDelete(id) {
        if (!confirm('Are you sure you want to delete this song?')) return;
        setSongs(songs.filter(s => s.id !== id)); // Optimistic update
        await deleteGlobalSong(id);
        loadSongs();
    }

    return (
        <div className="container" style={{ maxWidth: '800px', paddingBottom: '4rem' }}>
            <header style={{ marginBottom: '2rem', paddingTop: '2rem', borderBottom: '1px solid #262626', paddingBottom: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <Link href="/admin" style={{ color: '#a3a3a3', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <ArrowLeft size={20} /> Back
                </Link>
                <div style={{ flex: 1 }}>
                    <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>Song Database</h1>
                    <p style={{ fontSize: '0.8rem', color: '#525252' }}>{songs.length} Tracks Loaded</p>
                </div>
            </header>

            {/* Add New Song */}
            <div className="card" style={{ marginBottom: '2rem', border: '1px solid #262626' }}>
                <h2 style={{ fontSize: '1rem', fontWeight: 'bold', marginBottom: '1rem', color: '#fbbf24', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Plus size={16} /> Add New Track
                </h2>
                <form onSubmit={handleAdd} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '0.5rem', alignItems: 'end' }}>
                    <div>
                        <label style={{ fontSize: '0.7rem', color: '#525252', display: 'block', marginBottom: '4px' }}>TITLE</label>
                        <input name="title" className="input" placeholder="e.g. Bohemian Rhapsody" required />
                    </div>
                    <div>
                        <label style={{ fontSize: '0.7rem', color: '#525252', display: 'block', marginBottom: '4px' }}>ARTIST</label>
                        <input name="artist" className="input" placeholder="e.g. Queen" required />
                    </div>
                    <div>
                        <label style={{ fontSize: '0.7rem', color: '#525252', display: 'block', marginBottom: '4px' }}>GENRE</label>
                        <select name="genre" className="input">
                            <option>Pop</option>
                            <option>Rock</option>
                            <option>Hip Hop</option>
                            <option>R&B</option>
                            <option>Country</option>
                            <option>Electronic</option>
                            <option>Jazz</option>
                        </select>
                    </div>
                    <button type="submit" className="btn btn-primary" style={{ height: '42px' }}>Add</button>
                </form>
            </div>

            {/* Song List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {loading ? <p>Loading...</p> : songs.map(song => (
                    <div key={song.id} className="card" style={{ padding: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ width: '40px', height: '40px', background: '#262626', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <Music size={18} color="#525252" />
                            </div>
                            <div>
                                <p style={{ fontWeight: 'bold' }}>{song.title}</p>
                                <p style={{ fontSize: '0.8rem', color: '#a3a3a3' }}>{song.artist} • <span style={{ color: '#525252' }}>{song.genre}</span></p>
                            </div>
                        </div>
                        <button
                            onClick={() => handleDelete(song.id)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.5rem', color: '#ef4444', opacity: 0.7 }}
                            title="Delete Song"
                        >
                            <Trash2 size={18} />
                        </button>
                    </div>
                ))}
            </div>
        </div>
    );
}
