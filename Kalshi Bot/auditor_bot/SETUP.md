# Auditor Bot — Setup & Deployment Guide

## Step 1: Create the Azure Logic App (Email Relay)

This is how the Function sends email to Gmail. Azure blocks direct SMTP to Gmail,
so the Function POSTs to a Logic App, which uses the Gmail connector.

### 1.1 Create the Logic App

1. In the [Azure Portal](https://portal.azure.com), click **Create a resource**
2. Search for **Logic App** → Select **Logic App (Consumption)**
3. Settings:
   - **Subscription:** Same as your other bots
   - **Resource Group:** Same as your other bots (or create `djq-auditor-rg`)
   - **Logic App name:** `djq-auditor-email-relay`
   - **Region:** Same as your other bots
   - **Plan type:** Consumption (pay-per-use, ~$0 for 1 run/day)
4. Click **Review + Create** → **Create**

---

### 1.2 Design the Logic App Workflow

1. Go to your new Logic App → click **Logic app designer**
2. Click **Add a trigger** → search for **"When a HTTP request is received"**
3. In the trigger, paste this **Request Body JSON Schema** (so Azure parses the payload):

```json
{
  "type": "object",
  "properties": {
    "subject": { "type": "string" },
    "body":    { "type": "string" }
  },
  "required": ["subject", "body"]
}
```

4. Click **Save** — the trigger will generate an HTTP POST URL. **Copy this URL.**

---

### 1.3 Add the Gmail Action

1. Click **+ New step** after the trigger
2. Search **Gmail** → select **"Send email (V2)"**
3. Click **Sign in** — authorize your `1markrutledge@gmail.com` Google account
4. Fill in the action fields:
   - **To:** `1markrutledge@gmail.com`
   - **Subject:** Click inside the field → select **subject** from the dynamic content list
   - **Body:** Click inside the field → select **body** from the dynamic content list
5. Click **Save**

> The Logic App is now live. Test it by clicking **Run Trigger → Run** from the designer.

---

### 1.4 Copy the Trigger URL

In the **"When a HTTP request is received"** trigger box, click **"Copy"** next to the URL field.
This is your `LOGIC_APP_TRIGGER_URL`. It looks like:
```
https://prod-XX.eastus.logic.azure.com:443/workflows/.../triggers/manual/paths/invoke?api-version=...
```

---

## Step 2: Deploy the Azure Function App

### 2.1 Create the Function App in Azure

1. In Azure Portal → **Create a resource** → **Function App**
2. Settings:
   - **Subscription:** Same as other bots
   - **Resource Group:** Same group (or new `djq-auditor-rg`)
   - **Function App name:** `djq-auditor-bot` (must be globally unique)
   - **Runtime stack:** Python
   - **Version:** 3.11
   - **Region:** Same as other bots
   - **Plan type:** Consumption (Serverless)
   - **Operating System:** Linux
3. Click **Review + Create** → **Create**

---

### 2.2 Set Application Settings (Environment Variables)

In your new Function App → **Settings** → **Environment variables** → **+ Add** each:

| Name | Value |
|---|---|
| `KALSHI_API_KEY_ID` | Same value as in your other bot app settings |
| `KALSHI_PRIVATE_KEY_PEM` | Same value (the one-line PEM string) |
| `LOGIC_APP_TRIGGER_URL` | The URL you copied in Step 1.4 |
| `UNIT_SIZE` | `0.42` |

Click **Apply** → **Confirm** to save.

---

### 2.3 Deploy the Code

From your terminal, inside the `auditor_bot/` directory:

```bash
# Install Azure Functions Core Tools if not already installed
# brew tap azure/functions && brew install azure-functions-core-tools@4

cd "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/auditor_bot"

# Deploy directly to Azure
func azure functionapp publish djq-auditor-bot --python
```

Or zip-deploy via portal:
1. Zip the contents of `auditor_bot/` (not the folder itself, just the files inside)
2. In Azure Portal → your Function App → **Deployment** → **Advanced Tools (Kudu)** → **Zip Deploy**

---

## Step 3: Verify It Works

### 3.1 Manual Test Run

In Azure Portal → your Function App → **Functions** → **auditor_bot**:
1. Click **"Code + Test"**
2. Click **"Test/Run"** at the top → leave body empty → **Run**
3. Check **Logs** tab at the bottom for output — look for:
   ```
   AUDITOR BOT COMPLETED in X.Xs
   ```
4. Check your Gmail inbox for the report email

### 3.2 Verify the Schedule

The timer schedule `0 0 13 * * *` fires at **13:00 UTC** every day.

- **During EST (Nov–Mar):** 13:00 UTC = **8:00 AM ET** ✅
- **During EDT (Mar–Nov):** 13:00 UTC = **9:00 AM ET** (1hr late — acceptable, or change to `0 0 12 * * *` in summer)

To check the next scheduled run:
Azure Portal → Function App → **Functions** → **auditor_bot** → **Monitor** → **Invocations**

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `KeyError: KALSHI_PRIVATE_KEY_PEM` | Env var not set — check App Settings |
| Auth 401 from Kalshi | PEM format corrupted — ensure it's a single line with `\n` as literal `\n` |
| Logic App returns 400 | Check the HTTP trigger JSON schema matches the payload |
| Logic App returns 401 | Gmail token expired — re-authorize in Logic App designer |
| No email received | Check Gmail Spam folder; also check Logic App run history in portal |
