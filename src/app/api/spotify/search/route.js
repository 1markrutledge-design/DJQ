import { NextResponse } from 'next/server';

let globalAccessToken = null;
let globalTokenExpiry = null;

async function getClientAccessToken() {
    if (globalAccessToken && globalTokenExpiry && Date.now() < globalTokenExpiry) {
        return globalAccessToken;
    }

    const clientId = process.env.SPOTIFY_CLIENT_ID;
    const clientSecret = process.env.SPOTIFY_CLIENT_SECRET;

    if (!clientId || !clientSecret) {
        throw new Error('Spotify API credentials not configured.');
    }

    const response = await fetch('https://accounts.spotify.com/api/token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString('base64')}`
        },
        body: new URLSearchParams({
            grant_type: 'client_credentials'
        })
    });

    const data = await response.json();
    if (data.access_token) {
        globalAccessToken = data.access_token;
        globalTokenExpiry = Date.now() + (data.expires_in * 1000) - 60000;
        return globalAccessToken;
    }
    throw new Error('Could not get client access token');
}

export async function GET(request) {
    const { searchParams } = new URL(request.url);
    const query = searchParams.get('q');

    if (!query) {
        return NextResponse.json({ songs: [] });
    }

    try {
        const token = await getClientAccessToken();
        const searchResponse = await fetch(`https://api.spotify.com/v1/search?type=track&q=${encodeURIComponent(query)}&limit=15`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await searchResponse.json();

        if (data.tracks && data.tracks.items) {
            const songs = data.tracks.items.map(track => ({
                id: track.id,
                title: track.name,
                artist: track.artists.map(a => a.name).join(', '),
                albumArt: track.album.images.length > 0 ? track.album.images[0].url : null,
                spotifyUri: track.uri
            }));
            return NextResponse.json({ songs });
        }

        return NextResponse.json({ songs: [] });
    } catch (error) {
        console.error("Spotify Search Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
