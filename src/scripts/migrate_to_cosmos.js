const fs = require('fs');
const path = require('path');
const { CosmosClient } = require('@azure/cosmos');

// -- Load Local Data --
const getData = (file) => JSON.parse(fs.readFileSync(path.join(__dirname, '../data', file), 'utf-8'));

const songs = getData('songs.json');
const venues = getData('venues.json');
const queues = getData('queues.json');

async function migrate() {
    if (!process.env.COSMOS_CONNECTION_STRING) {
        console.error("Please set COSMOS_CONNECTION_STRING environment variable.");
        process.exit(1);
    }

    const client = new CosmosClient(process.env.COSMOS_CONNECTION_STRING);

    try {
        console.log("Connecting to Cosmos DB...");

        // 1. Create Database
        const { database } = await client.databases.createIfNotExists({ id: "ClubQueueDB" });
        console.log("Database 'ClubQueueDB' ready.");

        // 2. Create Containers
        // Songs: Partition Key /genre (or /id) - let's use /genre for grouping or /id for simple lookup. 
        // Actually /id is fine for reference data.
        const { container: songsContainer } = await database.containers.createIfNotExists({ id: "songs", partitionKey: "/id" });

        // Venues: Partition Key /code (since we query by code often? or /id). 
        // /code is unique, so valid.
        const { container: venuesContainer } = await database.containers.createIfNotExists({ id: "venues", partitionKey: "/code" });

        // Requests: Partition Key /venueCode (Essential for tenancy).
        const { container: requestsContainer } = await database.containers.createIfNotExists({ id: "requests", partitionKey: "/venueCode" });

        console.log("Containers ready.");

        // 3. Migrate Songs
        console.log(`Migrating ${songs.length} Songs...`);
        for (const song of songs) {
            // Upsert (Create or Replace)
            await songsContainer.items.upsert(song);
        }

        // 4. Migrate Venues
        console.log(`Migrating ${venues.length} Venues...`);
        for (const venue of venues) {
            await venuesContainer.items.upsert(venue);
        }

        // 5. Migrate Queues
        // Map dictionary { venueCode: [requests] } to flat list of Request documents
        let totalRequests = 0;
        console.log("Migrating Queues...");
        for (const [venueCode, requests] of Object.entries(queues)) {
            for (const req of requests) {
                // Ensure request has venueCode (primary partition key)
                const doc = {
                    ...req,
                    venueCode: venueCode,
                    // Ensure status/timestamps are preserved
                    status: req.status || 'pending'
                };
                await requestsContainer.items.upsert(doc);
                totalRequests++;
            }
        }
        console.log(`Migrated ${totalRequests} Requests.`);

        console.log("Migration Complete! 🚀");

    } catch (err) {
        console.error("Migration Failed:", err);
    }
}

migrate();
