require('dotenv').config({ path: '.env.local' });
const { CosmosClient } = require('@azure/cosmos');

async function listVenues() {
    if (!process.env.COSMOS_CONNECTION_STRING) {
        console.log("No Connection String found in .env.local");
        return;
    }
    const client = new CosmosClient(process.env.COSMOS_CONNECTION_STRING);
    const database = client.database('ClubQueueDB');
    const container = database.container('venues');

    try {
        const { resources } = await container.items.query("SELECT c.name, c.code FROM c").fetchAll();
        console.log("Registered Venues:");
        resources.forEach(v => console.log(`- Name: "${v.name}" | Code: "${v.code}"`));
    } catch (e) {
        console.error("Error fetching venues:", e.message);
    }
}

listVenues();
