import fs from 'fs/promises';
import path from 'path';

// Helper to get absolute path to data files
const getDataPath = (fileName) => path.join(process.cwd(), 'src', 'data', fileName);

export async function getSongs() {
    const filePath = getDataPath('songs.json');
    const data = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(data);
}

export async function getVenues() {
    const filePath = getDataPath('venues.json');
    try {
        const data = await fs.readFile(filePath, 'utf-8');
        return JSON.parse(data);
    } catch (error) {
        if (error.code === 'ENOENT') return [];
        throw error;
    }
}

export async function saveVenue(venue) {
    const venues = await getVenues();
    venues.push(venue);
    await fs.writeFile(getDataPath('venues.json'), JSON.stringify(venues, null, 2));
    return venue;
}

export async function getQueue(venueCode) {
    const filePath = getDataPath('queues.json');
    try {
        const data = await fs.readFile(filePath, 'utf-8');
        const queues = JSON.parse(data);
        return queues[venueCode] || [];
    } catch (error) {
        return [];
    }
}

export async function addToQueue(venueCode, request) {
    const filePath = getDataPath('queues.json');
    let queues = {};
    try {
        const data = await fs.readFile(filePath, 'utf-8');
        queues = JSON.parse(data);
    } catch (error) {
        // File might not exist yet
    }

    if (!queues[venueCode]) {
        queues[venueCode] = [];
    }

    const currentQueue = queues[venueCode];
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;

    // Check 1: Is song already pending?
    const isPending = currentQueue.some(q => q.song.id === request.song.id && q.status === 'pending');
    if (isPending) {
        throw new Error("This song is already in the queue!");
    }

    // Check 2: Was song played in the last hour?
    const recentlyPlayed = currentQueue.find(q =>
        q.song.id === request.song.id &&
        q.status === 'played' &&
        (now - q.timestamp) < oneHour
    );

    if (recentlyPlayed) {
        throw new Error("This song was played recently. Please wait before requesting it again.");
    }

    // Add timestamp and status
    const newRequest = {
        ...request,
        id: Date.now().toString(),
        timestamp: Date.now(),
        status: 'pending' // pending, played, skipped
    };

    queues[venueCode].push(newRequest);

    // Sort queue: Premium first, then by timestamp
    // We only want to sort PENDING items to the top for the display
    // But for storage we keep all. 
    // Actually, let's keep the existing sort logic but it might mix played/pending. 
    // Better to only sort pending items or rely on filtering in UI.
    // For safety, let's just append and let the UI filter.
    // WAIT: The previous logic sorted the whole array. If we keep 'played' items in valid 'queues[venueCode]', 
    // the UI QueueList needs to filter them out.
    // We will stick to the previous behavior of sorting, but simple sort might push played items around.
    // Let's just push and save. The UI MUST filter `status === 'pending'`.

    // Sort only pending items?
    // Let's sort everything but group pending first?
    // Simplified: Just sort by Premium/Standard for Pending, leave Played at bottom? 
    // For now, let's preserve the original sort which was good for Pending.
    // We will rely on UI to hide 'played'.

    queues[venueCode].sort((a, b) => {
        if (a.status !== 'pending' && b.status === 'pending') return 1;
        if (a.status === 'pending' && b.status !== 'pending') return -1;

        if (a.queueType === 'Premium' && b.queueType !== 'Premium') return -1;
        if (a.queueType !== 'Premium' && b.queueType === 'Premium') return 1;
        return a.timestamp - b.timestamp;
    });

    await fs.writeFile(filePath, JSON.stringify(queues, null, 2));
    return newRequest;
}

// Replaces removeFromQueue with status update to support history/cooldown
export async function removeFromQueue(venueCode, requestId) {
    return await markAsPlayed(venueCode, requestId);
}

export async function markAsPlayed(venueCode, requestId) {
    const filePath = getDataPath('queues.json');
    let queues = {};
    try {
        const data = await fs.readFile(filePath, 'utf-8');
        queues = JSON.parse(data);
    } catch (error) {
        return;
    }

    if (!queues[venueCode]) return;

    const requestIndex = queues[venueCode].findIndex(req => req.id === requestId);
    if (requestIndex !== -1) {
        queues[venueCode][requestIndex].status = 'played';
        queues[venueCode][requestIndex].timestamp = Date.now(); // Update timestamp to played time? 
        // No, cooldown should probably track when it was added or played? 
        // User asked: "played in the last hour". So we should technically update timestamp to NOW.
        // But that loses request time. Let's add 'playedAt'.
        queues[venueCode][requestIndex].playedAt = Date.now();
    }

    await fs.writeFile(filePath, JSON.stringify(queues, null, 2));
    return queues[venueCode];
}
