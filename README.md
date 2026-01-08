# Email Subscription Canceler

A professional-grade CLI tool that identifies and cancels newsletter subscriptions by parsing technical `List-Unsubscribe` headers in your Gmail inbox.

## Features
- **OAuth 2.0:** Secure authorization via official Google APIs.
- **Smart Detection:** Uses RFC 2369 headers to find legitimate subscriptions.
- **Auto-Unsubscribe:** Sends `mailto` requests automatically for supported lists.
- **High-Frequency Filtering:** Focuses on your most active senders first.

## Quick Start
1. **Initialize Environment:**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
2. **Activate & Run:**
   ```bash
   source .venv/bin/activate
   python gmail_scanner.py
   ```

## Configuration
Requires `credentials.json` in this folder (from Google Cloud Console).
- **Scan Depth:** Last 500 emails.
- **Display Filter:** Only shows senders appearing > 5 times.

## Interaction
- **[ID]:** Unsubscribe from a specific sender.
- **`all`:** Batch auto-unsubscribe from all supported lists.
- **`q`:** Quit.

## Security
- `credentials.json`: Your application's identity.
- `token.json`: Your active session. **Keep these private.**