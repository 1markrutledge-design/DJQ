'use server';

import Redis from 'ioredis';

// --- STORAGE CONFIGURATION ---
const isKvEnabled = !!process.env.REDIS_URL;
const redis = isKvEnabled ? new Redis(process.env.REDIS_URL) : null;

// Error handling for Redis
if (redis) {
    redis.on('error', (err) => console.error('Redis Client Error', err));
}

// Initial data for cold starts
const initialSongs = require('../data/songs.json');
const initialVenues = require('../data/venues.json');
const initialUsers = require('../data/users.json');

// --- In-Memory Fallback (for local dev or if KV is missing) ---
if (!global.mockDb) {
    global.mockDb = {
        songs: initialSongs,
        venues: initialVenues,
        queues: {},
        users: initialUsers,
        stats: {}
    };
}
const mock = global.mockDb;

// --- Helper: KV Key Builders ---
const KEYS = {
    SONGS: 'djq:songs',
    VENUES: 'djq:venues',
    USERS: 'djq:users',
    QUEUE: (code) => `djq:queue:${code}`,
    STATS: (code) => `djq:stats:${code}`
};

// --- Songs ---
export async function getSongs() {
    if (isKvEnabled) {
        const data = await redis.get(KEYS.SONGS);
        return data ? JSON.parse(data) : initialSongs;
    }
    return mock.songs;
}

export async function addSong(song) {
    if (!song.id) song.id = Date.now().toString();
    if (isKvEnabled) {
        const songs = await getSongs();
        songs.push(song);
        await redis.set(KEYS.SONGS, JSON.stringify(songs));
    } else {
        mock.songs.push(song);
    }
    return song;
}

export async function deleteSong(id) {
    if (isKvEnabled) {
        const songs = await getSongs();
        const filtered = songs.filter(s => s.id !== id);
        await redis.set(KEYS.SONGS, JSON.stringify(filtered));
    } else {
        mock.songs = mock.songs.filter(s => s.id !== id);
    }
    return true;
}

// --- Venues ---
export async function getVenues() {
    if (isKvEnabled) {
        const data = await redis.get(KEYS.VENUES);
        return data ? JSON.parse(data) : initialVenues;
    }
    return mock.venues;
}

export async function saveVenue(venue) {
    if (isKvEnabled) {
        const venues = await getVenues();
        venues.push(venue);
        await redis.set(KEYS.VENUES, JSON.stringify(venues));
    } else {
        mock.venues.push(venue);
    }
    return venue;
}

export async function updateVenue(venue) {
    if (isKvEnabled) {
        const venues = await getVenues();
        const index = venues.findIndex(v => v.id === venue.id);
        if (index !== -1) {
            venues[index] = venue;
            await redis.set(KEYS.VENUES, JSON.stringify(venues));
        }
    } else {
        const index = mock.venues.findIndex(v => v.id === venue.id);
        if (index !== -1) mock.venues[index] = venue;
    }
    return venue;
}

export async function deleteVenue(venueId, venueCode) {
    if (isKvEnabled) {
        const venues = await getVenues();
        const filtered = venues.filter(v => v.id !== venueId);
        await redis.set(KEYS.VENUES, JSON.stringify(filtered));
        await redis.del(KEYS.QUEUE(venueCode));
        await redis.del(KEYS.STATS(venueCode));
    } else {
        mock.venues = mock.venues.filter(v => v.id !== venueId);
        delete mock.queues[venueCode];
    }
    return true;
}

// --- Queues ---
export async function getQueue(venueCode) {
    let queue = [];
    if (isKvEnabled) {
        const data = await redis.get(KEYS.QUEUE(venueCode));
        queue = data ? JSON.parse(data) : [];
    } else {
        queue = mock.queues[venueCode] || [];
    }

    // Sort: pending first, then by amount (highest first), then by timestamp
    return queue.sort((a, b) => {
        const statusA = a.status === 'pending' ? 0 : 1;
        const statusB = b.status === 'pending' ? 0 : 1;
        if (statusA !== statusB) return statusA - statusB;
        const amountA = a.amount || 0;
        const amountB = b.amount || 0;
        if (amountA !== amountB) return amountB - amountA;
        return a.timestamp - b.timestamp;
    });
}

export async function addToQueue(venueCode, request) {
    const queue = await getQueue(venueCode);
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;

    // Checks
    if (queue.some(q => q.song.id === request.song.id && q.status === 'pending')) {
        throw new Error("This song is already in the queue!");
    }
    if (queue.find(q => q.song.id === request.song.id && q.status === 'played' && q.playedAt && (now - q.playedAt) < oneHour)) {
        throw new Error("This song was played recently. Please wait.");
    }

    const newRequest = {
        id: Date.now().toString(),
        venueCode,
        ...request,
        status: 'pending',
        timestamp: Date.now(),
        nowPlayingStartTime: null,
        playDuration: 0,
        refunded: false,
        paymentIntentId: request.paymentIntentId || null,
        captured: false,
    };

    queue.push(newRequest);

    if (isKvEnabled) {
        await redis.set(KEYS.QUEUE(venueCode), JSON.stringify(queue));
    } else {
        mock.queues[venueCode] = queue;
    }

    await updateVenueStats(venueCode, 'created');
    return newRequest;
}

export async function markAsPlayed(venueCode, requestId) {
    const queue = await getQueue(venueCode);
    const index = queue.findIndex(req => req.id === requestId);
    if (index !== -1) {
        queue[index].status = 'played';
        queue[index].playedAt = Date.now();
        if (isKvEnabled) {
            await redis.set(KEYS.QUEUE(venueCode), JSON.stringify(queue));
        }
    }
    return true;
}

export async function removeFromQueue(venueCode, requestId) {
    return await markAsPlayed(venueCode, requestId);
}

export async function updateRequestAmount(venueCode, requestId, extraAmount) {
    const queue = await getQueue(venueCode);
    const index = queue.findIndex(req => req.id === requestId);
    if (index !== -1) {
        queue[index].amount = (queue[index].amount || 0) + parseFloat(extraAmount);
        if (isKvEnabled) {
            await redis.set(KEYS.QUEUE(venueCode), JSON.stringify(queue));
        }
        return queue[index];
    }
    return null;
}

export async function getAllQueues() {
    if (isKvEnabled) {
        // This is inefficient on KV but good for admin demo. 
        // Better: store a list of active venue codes.
        const venues = await getVenues();
        const all = {};
        for (const v of venues) {
            all[v.code] = await getQueue(v.code);
        }
        return all;
    }
    return mock.queues;
}

// --- Users ---
export async function createUser(userData) {
    const users = await getUsers();
    if (users.find(u => u.username === userData.username)) {
        throw new Error("Username already taken");
    }

    const newUser = { id: Date.now().toString(), ...userData, type: 'user' };
    if (isKvEnabled) {
        users.push(newUser);
        await redis.set(KEYS.USERS, JSON.stringify(users));
    } else {
        mock.users.push(newUser);
    }
    return newUser;
}

async function getUsers() {
    if (isKvEnabled) {
        const data = await redis.get(KEYS.USERS);
        return data ? JSON.parse(data) : initialUsers;
    }
    return mock.users;
}

export async function getUser(username) {
    const users = await getUsers();
    return users.find(u => u.username === username) || null;
}

// --- Accountability ---
export async function startNowPlaying(venueCode, requestId) {
    const queue = await getQueue(venueCode);
    const index = queue.findIndex(req => req.id === requestId);
    if (index !== -1) {
        queue[index].nowPlayingStartTime = Date.now();
        if (isKvEnabled) await redis.set(KEYS.QUEUE(venueCode), JSON.stringify(queue));
        return queue[index];
    }
    return null;
}

export async function markAsPlayedWithVerification(venueCode, requestId) {
    const queue = await getQueue(venueCode);
    const index = queue.findIndex(req => req.id === requestId);
    if (index === -1) return { success: false, error: 'Not found' };

    const request = queue[index];
    if (request.nowPlayingStartTime) {
        const duration = Math.floor((Date.now() - request.nowPlayingStartTime) / 1000);
        if (duration < 60) return { success: false, error: 'Must play for 1 min' };
        request.playDuration = duration;
    }

    request.status = 'played';
    request.playedAt = Date.now();
    if (Math.random() < 0.2) request.verificationSent = true;

    if (isKvEnabled) await redis.set(KEYS.QUEUE(venueCode), JSON.stringify(queue));
    await updateVenueStats(venueCode, 'played');
    return { success: true, request };
}

export async function checkExpiredRequests(venueCode) {
    const queue = await getQueue(venueCode);
    const now = Date.now();
    const timeout = 45 * 60 * 1000;
    const expired = [];

    queue.forEach(req => {
        if (req.status === 'pending' && !req.refunded && (now - req.timestamp) > timeout) {
            req.refunded = true;
            req.status = 'refunded';
            expired.push(req);
        }
    });

    if (expired.length > 0) {
        if (isKvEnabled) await redis.set(KEYS.QUEUE(venueCode), JSON.stringify(queue));
        await updateVenueStats(venueCode, 'refunded', expired.length);
    }
    return expired;
}

export async function submitGuestVerification(venueCode, requestId, confirmed) {
    const queue = await getQueue(venueCode);
    const index = queue.findIndex(req => req.id === requestId);
    if (index !== -1) {
        queue[index].guestConfirmed = confirmed;
        queue[index].guestConfirmedAt = Date.now();
        if (isKvEnabled) await redis.set(KEYS.QUEUE(venueCode), JSON.stringify(queue));
        await updateVenueStats(venueCode, confirmed ? 'verified_yes' : 'verified_no');
        return queue[index];
    }
    return null;
}

export async function getPlayHistory(venueCode, limit = 20) {
    const queue = await getQueue(venueCode);
    return queue.filter(q => q.status === 'played').sort((a, b) => b.playedAt - a.playedAt).slice(0, limit);
}

// --- Stats ---
export async function getVenueStats(venueCode) {
    if (isKvEnabled) {
        const data = await redis.get(KEYS.STATS(venueCode));
        return data ? JSON.parse(data) : {
            totalRequests: 0, playedRequests: 0, refundedRequests: 0,
            guestConfirmedPlayed: 0, guestDeniedPlayed: 0
        };
    }
    return mock.stats[venueCode] || { totalRequests: 0, playedRequests: 0, refundedRequests: 0 };
}

export async function updateVenueStats(venueCode, eventType, count = 1) {
    const stats = await getVenueStats(venueCode);
    switch (eventType) {
        case 'created': stats.totalRequests += count; break;
        case 'played': stats.playedRequests += count; break;
        case 'refunded': stats.refundedRequests += count; break;
        case 'verified_yes': stats.guestConfirmedPlayed += count; break;
        case 'verified_no': stats.guestDeniedPlayed += count; break;
    }
    if (isKvEnabled) {
        await redis.set(KEYS.STATS(venueCode), JSON.stringify(stats));
    } else {
        mock.stats[venueCode] = stats;
    }
    return stats;
}

export async function getAllVenueStats() {
    const venues = await getVenues();
    return Promise.all(venues.map(async (v) => ({
        venueCode: v.code,
        venueName: v.name,
        ...(await getVenueStats(v.code))
    })));
}
