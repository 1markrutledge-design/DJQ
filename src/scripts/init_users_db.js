const { CosmosClient } = require('@azure/cosmos');
require('dotenv').config({ path: '.env.local' });

async function initUsers() {
    if (!process.env.COSMOS_CONNECTION_STRING) {
        console.error("Please set COSMOS_CONNECTION_STRING environment variable.");
        process.exit(1);
    }

    const client = new CosmosClient(process.env.COSMOS_CONNECTION_STRING);

    try {
        console.log("Connecting to Cosmos DB...");
        const database = client.database('ClubQueueDB');

        // Check if DB exists (it should)
        await database.read();
        console.log("Database found.");

        // Create Users Container
        // Partition Key: /id (Unique User ID is good, or /username?)
        // Let's use /id as the primary key for partitioning.
        console.log("Creating 'users' container...");
        await database.containers.createIfNotExists({ id: "users", partitionKey: "/id" });
        console.log("Container 'users' created successfully.");

    } catch (err) {
        console.error("Initialization Failed:", err);
    }
}

initUsers();
