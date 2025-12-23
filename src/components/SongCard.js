'use client';

/**
 * @param {Object} props
 * @param {Object} props.song - Song object {id, title, artist, genre}
 * @param {Function} props.onSelect - Callback when clicked
 */
export default function SongCard({ song, onSelect }) {
    return (
        <div
            className="card animate-fade-in"
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
            onClick={() => onSelect(song)}
        >
            <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 'bold', marginBottom: '0.2rem' }}>{song.title}</h3>
                <p style={{ color: '#a3a3a3', fontSize: '0.9rem' }}>{song.artist}</p>
            </div>
            <div style={{ textAlign: 'right' }}>
                <span style={{
                    fontSize: '0.75rem',
                    background: '#262626',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    color: '#d4d4d4'
                }}>
                    {song.genre}
                </span>
            </div>
        </div>
    );
}
