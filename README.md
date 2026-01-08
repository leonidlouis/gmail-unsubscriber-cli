# Email Subscription Canceler

A CLI tool that identifies and cancels newsletter subscriptions by parsing technical `List-Unsubscribe` headers in your Gmail inbox.

## Features
- **OAuth 2.0:** Secure authorization via official Google APIs.
- **Smart Detection:** Uses RFC 2369 headers to find legitimate subscriptions.
- **Auto-Unsubscribe:** Sends `mailto` requests automatically for supported lists.
- **High-Frequency Filtering:** Focuses on your most active senders first.

## Installation & Setup

The `setup.sh` script automates the local environment configuration. Specifically, it:
1. Creates a Python virtual environment (`.venv`) to isolate dependencies.
2. Upgrades `pip` to the latest version.
3. Installs all required libraries defined in `requirements.txt`.

To run it:
```bash
chmod +x setup.sh
./setup.sh
```

## Google API Credentials (`credentials.json`)

To use this tool, you need to create a Google Cloud Project and enable the Gmail API.

1.  **Go to the Google Cloud Console:**
    Navigate to [console.cloud.google.com](https://console.cloud.google.com/).

2.  **Create a New Project:**
    Click the project dropdown in the top bar and select **"New Project"**. Give it a name (e.g., "Gmail Unsubscriber") and create it.

3.  **Enable the Gmail API:**
    - Go to **"APIs & Services" > "Library"**.
    - Search for **"Gmail API"**.
    - Click on it and select **"Enable"**.

4.  **Configure OAuth Consent Screen:**
    - Go to **"APIs & Services" > "OAuth consent screen"**.
    - Select **"External"** user type and click **Create**.
    - Fill in the required fields (App name, User support email, Developer contact information).
    - Click **"Save and Continue"**.
    - Under **Scopes**, click **"Add or Remove Scopes"**. Select `.../auth/gmail.modify` (or manually add `https://www.googleapis.com/auth/gmail.modify`).
    - Click **"Save and Continue"**.
    - Add your email as a **Test User** since the app is in "Testing" mode.

5.  **Create Credentials:**
    - Go to **"APIs & Services" > "Credentials"**.
    - Click **"Create Credentials"** and select **"OAuth client ID"**.
    - Application type: **"Desktop app"**.
    - Name: "Desktop Client" (or similar).
    - Click **"Create"**.

6.  **Download JSON:**
    - A popup will appear with your Client ID and Secret.
    - Click the **"Download JSON"** button.
    - Rename this file to `credentials.json` and place it in this project folder.

## Usage

1. **Activate Environment:**
   ```bash
   source .venv/bin/activate
   ```
2. **Run the Tool:**
   ```bash
   python gmail-unsub.py
   ```

## Configuration
- **Scan Depth:** Last 500 emails.
- **Display Filter:** Only shows senders appearing > 5 times.

## Interaction
- **[ID]:** Unsubscribe from a specific sender.
- **`all`:** Batch auto-unsubscribe from all supported lists.
- **`q`:** Quit.

## Security
- `credentials.json`: Your application's identity.
- `token.json`: Your active session. **Keep these private.**
