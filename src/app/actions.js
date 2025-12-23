'use server';

import { getVenues, saveVenue, addToQueue, getSongs, getQueue, removeFromQueue, getAllQueues, updateRequestAmount } from '@/lib/db';
import { redirect } from 'next/navigation';

export async function fetchQueue(venueCode) {
    const allRequests = await getQueue(venueCode);
    return allRequests.filter(req => req.status === 'pending');
}

export async function boostRequest(venueCode, requestId, amount) {
    try {
        await updateRequestAmount(venueCode, requestId, amount);
        return { success: true };
    } catch (e) {
        return { error: e.message };
    }
}

export async function fetchVenueStats(venueCode) {
    const allRequests = await getQueue(venueCode);
    const totalRevenue = allRequests.reduce((acc, req) => acc + (req.amount || 0), 0);
    return {
        totalRequests: allRequests.length,
        totalRevenue,
        pendingCount: allRequests.filter(r => r.status === 'pending').length
    };
}

export async function removeSong(venueCode, requestId) {
    await removeFromQueue(venueCode, requestId);
    return { success: true };
}

export async function createVenue(formData) {
    const name = formData.get('name');
    const password = formData.get('password');
    if (!name || !password) return { error: 'Name and Password required' };

    // Secret Admin Backdoor (Registration Mode)
    if (name === 'Admin6060!' && password === 'Sleeper593!!') {
        return { isHiddenRedirect: true };
    }

    // Generate code: Exact name, Uppercase, No Spaces
    const code = name.toUpperCase().replace(/\s/g, '');

    // CHECK IF EXISTS
    const venues = await getVenues();
    const existing = venues.find(v => v.code === code);

    if (existing) {
        return { error: `Venue name "${name}" is taken. Please choose another.` };
    }

    await saveVenue({
        id: Date.now().toString(),
        name,
        code,
        password, // In a real app, hash this!
        createdAt: Date.now()
    });

    return { success: true, code };
}

export async function validateVenue(formData) {
    const code = formData.get('code');

    // Secret Admin Backdoor
    if (code === 'Admin6060!') {
        // We cannot redirect from server action inside a client component easily if using 'preventDefault'.
        // Better to return a flag.
        return { isHiddenRedirect: true };
    }

    const venues = await getVenues();
    const venue = venues.find(v => v.code === code.toUpperCase());

    if (venue) {
        // Return success and details so client can store history before redirecting
        return { success: true, code: venue.code, name: venue.name };
    }

    return { error: 'Invalid Venue Code' };
}

export async function validateVenueLogin(venueCode, password) {
    const venues = await getVenues();
    const venue = venues.find(v => v.code === venueCode);

    if (venue && venue.password === password) {
        if (venue.status === 'frozen') return { error: 'Account Suspended' };
        return { success: true };
    }
    return { success: false };
}

export async function submitSongRequest(venueCode, requestData) {
    // requestData: { song, queueType, amount, notes }
    if (!venueCode || !requestData) return { error: 'Missing data' };

    try {
        await addToQueue(venueCode, requestData);
        return { success: true };
    } catch (error) {
        return { error: error.message };
    }
}

export async function fetchSongs() {
    return await getSongs();
}

export async function createNewSong(formData) {
    const title = formData.get('title');
    const artist = formData.get('artist');
    const genre = formData.get('genre') || 'Pop';

    if (!title || !artist) return { error: 'Title and Artist required' };

    await import('@/lib/db').then(db => db.addSong({
        id: Date.now().toString(),
        title,
        artist,
        genre,
        createdAt: Date.now()
    }));

    return { success: true };
}

export async function deleteGlobalSong(id) {
    await import('@/lib/db').then(db => db.deleteSong(id));
    return { success: true };
}

export async function fetchAdminData() {
    const venues = await getVenues();
    const allQueues = await getAllQueues(); // Need to import this

    let totalRevenue = 0;
    Object.values(allQueues).forEach(venueQueue => {
        venueQueue.forEach(req => {
            totalRevenue += (req.amount || 0);
        });
    });

    return {
        venues,
        totalRevenue,
        queueStats: allQueues
    };
}

export async function toggleVenueStatus(venueId, venueCode, currentStatus) {
    // currentStatus might be undefined (Active)
    const newStatus = (currentStatus === 'frozen') ? 'active' : 'frozen';

    // We need to fetch the full venue first to update it properly?
    // Or we rely on the UI passing the full object?
    // Better to fetch to be safe.
    const venues = await getVenues();
    const venue = venues.find(v => v.id === venueId);

    if (!venue) return { error: 'Venue not found' };

    venue.status = newStatus;

    await import('@/lib/db').then(db => db.updateVenue(venue));
    return { success: true, status: newStatus };
}

export async function destroyVenue(venueId, venueCode) {
    await import('@/lib/db').then(db => db.deleteVenue(venueId, venueCode));
    // Ideally we also delete all REQUESTS for this venue?
    // Yes, cleanup is good.
    // TODO: cleanup requests.
    return { success: true };
}

// --- User Auth ---

export async function registerUser(formData) {
    const username = formData.get('username');
    const password = formData.get('password');

    if (!username || !password) return { error: "Missing fields" };

    try {
        await import('@/lib/db').then(db => db.createUser({ username, password, createdAt: Date.now() }));
        return { success: true, username };
    } catch (e) {
        return { error: e.message };
    }
}

export async function login(formData) {
    const username = formData.get('username'); // Can be venue code OR username
    const password = formData.get('password');

    // 0. Check Admin Backdoor
    if (username === 'Admin6060!' && password === 'Sleeper593!!') {
        return { success: true, type: 'admin', redirect: '/admin' };
    }

    // 1. Check Venues (by Code)
    // NOTE: Venues login with CODE, Users with USERNAME.
    // We check Venues first assuming username input might be a venue code.
    const venueRes = await validateVenueLogin(username.toUpperCase(), password);
    if (venueRes.success) {
        return { success: true, type: 'venue', code: username.toUpperCase(), redirect: `/dashboard/${username.toUpperCase()}` };
    } else if (venueRes.error && venueRes.error !== 'Account Suspended') {
        // If specific error like suspended, return it.
        // If just failed, continue to check if it's a User.
    }

    // 2. Check Users
    try {
        const user = await import('@/lib/db').then(db => db.getUser(username));
        if (user && user.password === password) {
            return { success: true, type: 'user', username: user.username, redirect: `/user` };
        }
    } catch (e) {
        console.error("User login lookup failed", e);
    }

    return { error: "Your login info is wrong. Please try again." };
}
