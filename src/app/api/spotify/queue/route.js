import { NextResponse } from 'next/server';
import { getVenues, updateVenue } from '@/lib/db';

async function refreshSpotifyToken(venue) {
    const clientId = process.env.SPOTIFY_CLIENT_ID;
    const clientSecret = process.env.SPOTIFY_CLIENT_SECRET;

    const tokenResponse = await fetch('https://accounts.spotify.com/api/token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString('base64')}`
        },
        body: new URLSearchParams({
            grant_type: 'refresh_token',
            refresh_token: venue.spotifyRefreshToken
        })
    });

    const data = await tokenResponse.json();
    if (data.access_token) {
        venue.spotifyAccessToken = data.access_token;
        if (data.refresh_token) {
            venue.spotifyRefreshToken = data.refresh_token;
        }
        venue.spotifyTokenExpiry = Date.now() + (data.expires_in * 1000);
        await updateVenue(venue);
        return venue.spotifyAccessToken;
    }
    return null;
}

export async function POST(request) {
    const { venueCode, spotifyUri } = await request.json();

    if (!venueCode || !spotifyUri) {
        return NextResponse.json({ error: 'Missing venueCode or spotifyUri' }, { status: 400 });
    }

    const venues = await getVenues();
    const venue = venues.find(v => v.code === venueCode);

    if (!venue || !venue.spotifyAccessToken) {
        return NextResponse.json({ error: 'Venue not connected to Spotify' }, { status: 403 });
    }

    let accessToken = venue.spotifyAccessToken;

    // Refresh if expired
    if (Date.now() > (venue.spotifyTokenExpiry - 60000)) {
        accessToken = await refreshSpotifyToken(venue);
        if (!accessToken) {
            return NextResponse.json({ error: 'Failed to refresh Spotify token' }, { status: 401 });
        }
    }

    // Add to Queue
    const queueResponse = await fetch(`https://api.spotify.com/v1/me/player/queue?uri=${encodeURIComponent(spotifyUri)}`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${accessToken}`
        }
    });

    if (queueResponse.ok || queueResponse.status === 204) {
        return NextResponse.json({ success: true });
    }

    const errorData = await queueResponse.json().catch(() => null);
    console.error("Spotify Queue Error:", errorData);

    if (queueResponse.status === 404) {
        return NextResponse.json({ error: 'No active Spotify playback found. Please open Spotify and play a song on your device first.' }, { status: 404 });
    }

    return NextResponse.json({ error: 'Failed to add to queue' }, { status: queueResponse.status });
}
