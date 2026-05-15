import { NextResponse } from 'next/server';
import { updateVenue, getVenues } from '@/lib/db';

export async function GET(request) {
    const { searchParams } = new URL(request.url);
    const code = searchParams.get('code');
    const venueCode = searchParams.get('state');

    if (!code || !venueCode) {
        return NextResponse.json({ error: 'Invalid callback parameters' }, { status: 400 });
    }

    const clientId = process.env.SPOTIFY_CLIENT_ID;
    const clientSecret = process.env.SPOTIFY_CLIENT_SECRET;

    const protocol = request.headers.get('x-forwarded-proto') || 'http';
    const host = request.headers.get('host');
    const redirectUri = `${protocol}://${host}/api/spotify/callback`;

    try {
        const tokenResponse = await fetch('https://accounts.spotify.com/api/token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString('base64')}`
            },
            body: new URLSearchParams({
                code,
                redirect_uri: redirectUri,
                grant_type: 'authorization_code'
            })
        });

        const data = await tokenResponse.json();

        if (data.error) {
            console.error("Spotify Auth Error:", data);
            return NextResponse.json({ error: data.error_description || data.error }, { status: 400 });
        }

        // Save tokens to DB
        const venues = await getVenues();
        const venue = venues.find(v => v.code === venueCode);

        if (venue) {
            venue.spotifyAccessToken = data.access_token;
            venue.spotifyRefreshToken = data.refresh_token;
            venue.spotifyTokenExpiry = Date.now() + (data.expires_in * 1000); // Expiry in ms
            await updateVenue(venue);
        }

        // Redirect back to dashboard
        return NextResponse.redirect(`${protocol}://${host}/dashboard/${venueCode}`);
    } catch (error) {
        console.error("Callback catch error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
