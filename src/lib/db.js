import { CosmosClient } from '@azure/cosmos';

let client;
let database;
let songsContainer;
let venuesContainer;
let requestsContainer;

// Initialize connection if env var is present
if (!process.env.COSMOS_CONNECTION_STRING) {
    console.warn("COSMOS_CONNECTION_STRING not set");
} else {
    client = new CosmosClient(process.env.COSMOS_CONNECTION_STRING);
    database = client.database('ClubQueueDB');
    songsContainer = database.container('songs');
    venuesContainer = database.container('venues');
    requestsContainer = database.container('requests');
}

// --- Helper for Queries ---
async function query(container, querySpec) {
    if (!container) throw new Error("Database not configured");
    const { resources } = await container.items.query(querySpec).fetchAll();
    return resources;
}

// --- Songs ---
export async function getSongs() {
    // Cosmos NoSQL query
    const q = {
        query: "SELECT * FROM c ORDER BY c.title ASC"
    };
    return await query(songsContainer, q);
}

export async function addSong(song) {
    if (!songsContainer) throw new Error("Database not configured");
    // Ensure ID
    if (!song.id) song.id = Date.now().toString();
    await songsContainer.items.create(song);
    return song;
}

export async function deleteSong(id) {
    if (!songsContainer) throw new Error("Database not configured");
    // Partition key is /id
    await songsContainer.item(id, id).delete();
    return true;
}

// --- Venues ---
export async function getVenues() {
    try {
        const q = { query: "SELECT * FROM c" };
        return await query(venuesContainer, q);
    } catch (e) {
        console.error("getVenues Error:", e);
        return [];
    }
}

export async function saveVenue(venue) {
    if (!venuesContainer) throw new Error("Database not configured");
    // Cosmos 'items.create'
    await venuesContainer.items.create(venue);
    return venue;
}

export async function updateVenue(venue) {
    if (!venuesContainer) throw new Error("Database not configured");
    // Upsert acts as update if ID/PartitionKey matches
    await venuesContainer.items.upsert(venue);
    return venue;
}

export async function deleteVenue(venueId, venueCode) {
    if (!venuesContainer) throw new Error("Database not configured");
    // Requires ID and Partition Key (Code)
    // If we only have ID, we'd need to query. But properly we should pass Code.
    await venuesContainer.item(venueId, venueCode).delete();
    return true;
}

// --- Queues ---
export async function getQueue(venueCode) {
    if (!requestsContainer) throw new Error("Database not configured");

    // 1. Get requests for venue
    // Note: Joins across containers are not supported in Cosmos NoSQL in a single query typically unless using specific features.
    // For simplicity/speed in this migration, we will fetch requests and join manually (since song data is small) OR store song data IN the request.
    // OPTIMIZATION: We will assume we fetch requests and if they have songId, we might need song details.
    // BUT, let's look at how we store requests. In `addToQueue`, we receive `request.song`. 
    // If we store the WHOLE song object in the request document, we don't need a join!
    // This is the NoSQL way.

    const q = {
        query: "SELECT * FROM c WHERE c.venueCode = @code AND c.status != 'deleted'",
        parameters: [{ name: "@code", value: venueCode }]
    };

    const requests = await query(requestsContainer, q);

    // Sort in JS: status=pending first, then Amount desc, then Time asc
    return requests.sort((a, b) => {
        // 1. Pending first (Played moves to bottom or stays depending on UI, usually filtered out)
        // If both pending or both played, continue
        const statusA = a.status === 'pending' ? 0 : 1;
        const statusB = b.status === 'pending' ? 0 : 1;
        if (statusA !== statusB) return statusA - statusB;

        // 2. Amount Descending (Highest Tip First)
        const amountA = a.amount || 0;
        const amountB = b.amount || 0;
        if (amountA !== amountB) return amountB - amountA;

        // 3. Time Ascending (First Come First Serve for ties)
        return a.timestamp - b.timestamp;
    });
}

export async function addToQueue(venueCode, request) {
    // request: { song: {...}, queueType, amount, notes }
    if (!requestsContainer) throw new Error("Database not configured");

    // Check 1: Duplicate Pending (Query)
    const duplicateQ = {
        query: "SELECT * FROM c WHERE c.venueCode = @code AND c.song.id = @songId AND c.status = 'pending'",
        parameters: [
            { name: "@code", value: venueCode },
            { name: "@songId", value: request.song.id }
        ]
    };
    const dups = await query(requestsContainer, duplicateQ);
    if (dups.length > 0) throw new Error("This song is already in the queue!");

    // Check 2: Cooldown (1 Hour)
    const oneHourAgo = Date.now() - (60 * 60 * 1000);
    const cooldownQ = {
        query: "SELECT * FROM c WHERE c.venueCode = @code AND c.song.id = @songId AND c.status = 'played' AND c.playedAt > @time",
        parameters: [
            { name: "@code", value: venueCode },
            { name: "@songId", value: request.song.id },
            { name: "@time", value: oneHourAgo }
        ]
    };
    const recent = await query(requestsContainer, cooldownQ);
    if (recent.length > 0) throw new Error("This song was played recently. Please wait before requesting it again.");

    const newId = Date.now().toString();
    const now = Date.now();

    const newRequest = {
        id: newId,
        venueCode,
        userId: request.userId || null, // Optional tracking
        ...request, // Includes full song object, which is good for NoSQL
        status: 'pending',
        timestamp: now
    };

    await requestsContainer.items.create(newRequest);
    return newRequest;
}

export async function markAsPlayed(venueCode, requestId) {
    if (!requestsContainer) throw new Error("Database not configured");

    // In Cosmos, to update, we typically read then replace, or use Patch API.
    // Patch is more efficient.
    const item = requestsContainer.item(requestId, venueCode); // partition key assumed to be venueCode

    // Note: If partition key is NOT venueCode, this might fail. We should define venueCode as partition key.

    const { resource: existing } = await item.read();
    if (existing) {
        existing.status = 'played';
        existing.playedAt = Date.now();
        await item.replace(existing);
    }
    return true;
}

export async function updateRequestAmount(venueCode, requestId, extraAmount) {
    if (!requestsContainer) throw new Error("Database not configured");

    // In Cosmos, we need to read then replace/upsert
    const item = requestsContainer.item(requestId, venueCode);

    const { resource: existing } = await item.read();
    if (existing) {
        existing.amount = (existing.amount || 0) + parseFloat(extraAmount);

        // Removed: Upgrade to Premium logic. Sorting is now purely dynamic based on amount.

        await item.replace(existing);
        return existing;
    }
    throw new Error("Request not found");
}

export async function removeFromQueue(venueCode, requestId) {
    return markAsPlayed(venueCode, requestId);
}

export async function getAllQueues() {
    if (!requestsContainer) throw new Error("Database not configured");
    // Fetch ALL requests (Careful with cost, but fine for small app)
    const q = { query: "SELECT * FROM c" };
    const allRequests = await query(requestsContainer, q);

    // Group by venue
    const grouped = {};
    for (const req of allRequests) {
        if (!grouped[req.venueCode]) grouped[req.venueCode] = [];
        grouped[req.venueCode].push(req);
    }
    return grouped;
}

// --- Users ---
let usersContainer;
if (database) {
    usersContainer = database.container('users');
}

export async function createUser(userData) {
    // userData: { username, password, createdAt }
    if (!usersContainer) throw new Error("Database not configured");

    // Check if username exists
    const q = {
        query: "SELECT * FROM c WHERE c.username = @username",
        parameters: [{ name: "@username", value: userData.username }]
    };
    const existing = await query(usersContainer, q);
    if (existing.length > 0) throw new Error("Username already taken");

    const newUser = {
        id: Date.now().toString(), // partition key
        ...userData,
        type: 'user'
    };

    await usersContainer.items.create(newUser);
    return newUser;
}

export async function getUser(username) {
    if (!usersContainer) throw new Error("Database not configured");
    const q = {
        query: "SELECT * FROM c WHERE c.username = @username",
        parameters: [{ name: "@username", value: username }]
    };
    const users = await query(usersContainer, q);
    return users[0] || null;
}
