const { CosmosClient } = require('@azure/cosmos');
require('dotenv').config({ path: '.env.local' });

async function initDatabase() {
    if (!process.env.COSMOS_CONNECTION_STRING) {
        console.error("❌ COSMOS_CONNECTION_STRING not set in .env.local");
        process.exit(1);
    }

    const client = new CosmosClient(process.env.COSMOS_CONNECTION_STRING);

    try {
        console.log("🔄 Connecting to Cosmos DB...");
        const database = client.database('ClubQueueDB');

        // Verify database exists
        await database.read();
        console.log("✅ Database 'ClubQueueDB' found.");

        // Define all containers with their partition keys
        const containers = [
            { id: "songs", partitionKey: "/id" },
            { id: "venues", partitionKey: "/code" },
            { id: "requests", partitionKey: "/venueCode" },
            { id: "users", partitionKey: "/id" }
        ];

        // Create each container if it doesn't exist
        for (const containerDef of containers) {
            console.log(`🔄 Creating container '${containerDef.id}'...`);
            const { container } = await database.containers.createIfNotExists({
                id: containerDef.id,
                partitionKey: containerDef.partitionKey
            });
            console.log(`✅ Container '${containerDef.id}' ready (partition key: ${containerDef.partitionKey})`);
        }

        console.log("\n🎉 Database initialization complete!");
        console.log("All containers are ready to use.");

    } catch (err) {
        console.error("❌ Initialization Failed:", err.message);
        console.error(err);
        process.exit(1);
    }
}

initDatabase();
