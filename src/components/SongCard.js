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
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', gap: '1rem' }}
            onClick={() => onSelect(song)}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flex: 1, overflow: 'hidden' }}>
                {song.albumArt ? (
                    <img src={song.albumArt} alt="Album Art" style={{ width: '50px', height: '50px', borderRadius: '4px', objectFit: 'cover', flexShrink: 0 }} />
                ) : (
                    <div style={{ width: '50px', height: '50px', borderRadius: '4px', background: '#404040', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <span style={{ color: '#a3a3a3', fontSize: '0.6rem', textAlign: 'center' }}>No Art</span>
                    </div>
                )}
                <div style={{ minWidth: 0 }}>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 'bold', marginBottom: '0.2rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{song.title}</h3>
                    <p style={{ color: '#a3a3a3', fontSize: '0.9rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{song.artist}</p>
                </div>
            </div>

            {song.genre && (
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
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
            )}
        </div>
    );
}
