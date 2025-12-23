const fs = require('fs');
const path = require('path');
const { Client } = require('pg');

// -- Load Local Data --
const getData = (file) => JSON.parse(fs.readFileSync(path.join(__dirname, '../data', file), 'utf-8'));

const songs = getData('songs.json');
const venues = getData('venues.json');
const queues = getData('queues.json');

async function migrate() {
    if (!process.env.DATABASE_URL) {
        console.error("Please set DATABASE_URL environment variable.");
        process.exit(1);
    }

    const client = new Client({
        connectionString: process.env.DATABASE_URL,
        ssl: { rejectUnauthorized: false }
    });

    try {
        await client.connect();
        console.log("Connected to Database...");

        // 1. Create Tables (Idempotent)
        console.log("Creating Tables...");
        await client.query(`
            CREATE TABLE IF NOT EXISTS songs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                genre TEXT,
                duration TEXT
            );

            CREATE TABLE IF NOT EXISTS venues (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                created_at BIGINT
            );

            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY,
                venue_code TEXT REFERENCES venues(code),
                song_id TEXT REFERENCES songs(id),
                queue_type TEXT,
                amount NUMERIC,
                notes TEXT,
                status TEXT DEFAULT 'pending',
                created_at BIGINT,
                played_at BIGINT
            );
        `);

        // 2. Migrate Songs
        console.log(`Migrating ${songs.length} Songs...`);
        for (const song of songs) {
            await client.query(
                `INSERT INTO songs (id, title, artist, genre, duration) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING`,
                [song.id, song.title, song.artist, song.genre, song.duration]
            );
        }

        // 3. Migrate Venues
        console.log(`Migrating ${venues.length} Venues...`);
        for (const venue of venues) {
            await client.query(
                `INSERT INTO venues (id, name, code, created_at) VALUES ($1, $2, $3, $4) ON CONFLICT (code) DO NOTHING`,
                [venue.id, venue.name, venue.code, venue.createdAt]
            );
        }

        // 4. Migrate Queues
        console.log("Migrating Queues...");
        for (const [venueCode, requests] of Object.entries(queues)) {
            for (const req of requests) {
                // Determine timestamps
                const playedAt = req.status === 'played' ? (req.playedAt || Date.now()) : null;

                await client.query(
                    `INSERT INTO requests (id, venue_code, song_id, queue_type, amount, notes, status, created_at, played_at) 
                     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) ON CONFLICT (id) DO NOTHING`,
                    [req.id, venueCode, req.song.id, req.queueType, req.amount, req.notes, req.status, req.timestamp, playedAt]
                );
            }
        }

        console.log("Migration Complete! 🚀");
    } catch (err) {
        console.error("Migration Failed:", err);
    } finally {
        await client.end();
    }
}

migrate();
