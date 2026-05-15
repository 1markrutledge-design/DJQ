import { NextResponse } from 'next/server';

export async function GET(request) {
    const { searchParams } = new URL(request.url);
    const venueCode = searchParams.get('venueCode');

    if (!venueCode) {
        return NextResponse.json({ error: 'Venue code required' }, { status: 400 });
    }

    const clientId = process.env.SPOTIFY_CLIENT_ID;

    if (!clientId) {
        return NextResponse.json({ error: 'Spotify Client ID not configured in environment.' }, { status: 500 });
    }

    const protocol = request.headers.get('x-forwarded-proto') || 'http';
    const host = request.headers.get('host');
    const redirectUri = `${protocol}://${host}/api/spotify/callback`;

    const scopes = [
        'user-modify-playback-state',
        'user-read-playback-state',
        'user-read-currently-playing'
    ].join(' ');

    const state = venueCode;

    const authUrl = `https://accounts.spotify.com/authorize?` +
        `response_type=code` +
        `&client_id=${clientId}` +
        `&scope=${encodeURIComponent(scopes)}` +
        `&redirect_uri=${encodeURIComponent(redirectUri)}` +
        `&state=${state}`;

    return NextResponse.redirect(authUrl);
}
