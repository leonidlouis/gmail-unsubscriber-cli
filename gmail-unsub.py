import os
import base64
import re
import sys
from collections import defaultdict
from email.header import decode_header
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# The required scope for reading AND sending email
REQUIRED_SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def decode_mime_header(header_value):
    """
    Decodes MIME encoded headers (e.g., '=?utf-8?Q?Hello?=') into a readable string.
    """
    if not header_value:
        return "Unknown"
    try:
        decoded_parts = decode_header(header_value)
        text_parts = []
        for bytes_content, encoding in decoded_parts:
            if isinstance(bytes_content, bytes):
                if encoding:
                    try:
                        text_parts.append(bytes_content.decode(encoding))
                    except LookupError:
                        # Fallback for unknown encodings
                        text_parts.append(bytes_content.decode('utf-8', errors='ignore'))
                else:
                    text_parts.append(bytes_content.decode('utf-8', errors='ignore'))
            else:
                text_parts.append(str(bytes_content))
        return "".join(text_parts)
    except Exception:
        return header_value

def get_service():
    creds = None
    token_path = 'token.json'
    
    # Check if token exists and load it
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, REQUIRED_SCOPES)
        except Exception:
            print("Detected corrupt or incompatible token. Resetting...")
            creds = None

    # Verify credentials valid and have correct scopes
    if creds:
        # Check if current scopes match required scopes
        if set(creds.scopes) != set(REQUIRED_SCOPES):
            print("Scopes have changed. Re-authenticating...")
            creds = None
    
    # If not valid, log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                print("Token refresh failed. Re-authenticating...")
                if os.path.exists(token_path):
                    os.remove(token_path)
                creds = None
        
        if not creds:
            if not os.path.exists('credentials.json'):
                print("ERROR: 'credentials.json' not found.")
                print("Please download it from Google Cloud Console -> APIs & Services -> Credentials.")
                return None
            
            # Delete old token to ensure clean slate
            if os.path.exists(token_path):
                os.remove(token_path)

            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', REQUIRED_SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def get_header(headers, name):
    for header in headers:
        if header['name'].lower() == name.lower():
            return header['value']
    return None

def parse_list_unsubscribe(header_value):
    """
    Robustly parses the List-Unsubscribe header.
    Handles comma-separated values and angle brackets.
    Returns (mailto_link, http_link)
    """
    if not header_value:
        return None, None
    
    # Split by comma to handle multiple methods
    parts = header_value.split(',')
    
    mailto = None
    http = None
    
    for part in parts:
        part = part.strip()
        # Remove angle brackets
        clean_link = part.strip('<>')
        
        if clean_link.startswith('mailto:'):
            mailto = clean_link
        elif clean_link.startswith('http'):
            http = clean_link
            
    return mailto, http

def send_unsubscribe_email(service, mailto_link):
    """
    Sends an unsubscribe email based on the mailto link.
    """
    try:
        # Parse mailto:address?subject=...
        content = mailto_link.replace('mailto:', '')
        
        if '?' in content:
            to_addr, query = content.split('?', 1)
        else:
            to_addr = content
            query = ""

        subject = "Unsubscribe"
        body = "Please unsubscribe me from this list."
        
        # Extract subject manually to avoid urllib complexity issues
        if 'subject=' in query.lower():
            # Split query parameters
            params = query.split('&')
            for param in params:
                if param.lower().startswith('subject='):
                    subject = param.split('=', 1)[1]
                    # basic URL decode for spaces
                    subject = subject.replace('%20', ' ').replace('+', ' ')

        message = MIMEText(body)
        message['to'] = to_addr
        message['subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        return True, f"Unsubscribe email sent to {to_addr}"
    
    except Exception as e:
        return False, f"Failed: {str(e)}"

def interactive_unsubscribe(service, subscriptions):
    subs_list = list(subscriptions.items())
    subs_list.sort(key=lambda x: x[1]['count'], reverse=True)

    while True:
        print("\n" + "="*80)
        print(f"SUBSCRIPTION MANAGER - {len(subs_list)} Lists Found")
        print("="*80)
        print(f"{ 'ID':<4} | {'Freq':<5} | {'Auto?':<6} | {'Sender'}")
        print("-" * 80)
        
        for idx, (sender, data) in enumerate(subs_list):
            can_auto = "YES" if data['mailto'] else "NO"
            # Truncate sender if too long
            display_sender = (sender[:50] + '..') if len(sender) > 50 else sender
            print(f"{idx:<4} | {data['count']:<5} | {can_auto:<6} | {display_sender}")

        print("-" * 80)
        print("Commands: [ID] to unsubscribe | [all] to auto-unsub all possible | [q] to quit")
        choice = input("> ").strip().lower()

        if choice == 'q':
            break
        
        if choice == 'all':
            print("\nStarting batch unsubscribe...")
            count = 0
            for sender, data in subs_list:
                if data['mailto']:
                    print(f"[{sender}]:", end=" ")
                    success, msg = send_unsubscribe_email(service, data['mailto'])
                    print("Sent." if success else "Failed.")
                    if success: count += 1
            print(f"\nBatch complete. Sent {count} emails.")
            continue

        try:
            idx = int(choice)
            if 0 <= idx < len(subs_list):
                sender, data = subs_list[idx]
                print(f"\nTarget: {sender}")
                
                if data['mailto']:
                    print(f"Method: Auto-Email ({data['mailto']})")
                    confirm = input("Confirm send? (y/n): ").lower()
                    if confirm == 'y':
                        success, msg = send_unsubscribe_email(service, data['mailto'])
                        print(msg)
                elif data['http']:
                    print(f"Method: Manual Link")
                    print(f"Action: Please click the link below to unsubscribe:")
                    print(f"\n{data['http']}\n")
                else:
                    print("Error: No valid unsubscribe method parsed.")
            else:
                print("Invalid ID number.")
        except ValueError:
            print("Invalid input.")

def main():
    print("Initializing Gmail Scanner...")
    service = get_service()
    if not service:
        return

    LIMIT = 500
    print(f"Scanning last {LIMIT} emails for 'List-Unsubscribe' headers...")
    
    try:
        results = service.users().messages().list(userId='me', maxResults=LIMIT).execute()
        messages = results.get('messages', [])
    except HttpError as e:
        print(f"API Error: {e}")
        return

    if not messages:
        print("No messages found.")
        return

    subscriptions = defaultdict(lambda: {'count': 0, 'mailto': None, 'http': None})

    # Progress counter
    total = len(messages)
    
    for i, msg in enumerate(messages):
        # Update progress bar every 10 items or last item
        if i % 10 == 0 or i == total - 1:
            sys.stdout.write(f"\rScanning: {i+1}/{total}")
            sys.stdout.flush()
        
        try:
            # We use 'metadata' format which is much lighter/faster than 'full'
            msg_detail = service.users().messages().get(
                userId='me', 
                id=msg['id'], 
                format='metadata', 
                metadataHeaders=['From', 'List-Unsubscribe']
            ).execute()
            
            headers = msg_detail.get('payload', {}).get('headers', [])
            list_header = get_header(headers, 'List-Unsubscribe')
            
            if list_header:
                raw_sender = get_header(headers, 'From')
                
                # 1. Clean Sender Name
                clean_sender = "Unknown"
                if raw_sender:
                    # Extract name part before <email>
                    match = re.search(r'^(.*?)\s*<', raw_sender)
                    if match:
                        clean_sender = match.group(1).strip().replace('"', '')
                    else:
                        clean_sender = raw_sender
                    
                    # 2. Decode MIME (e.g. =?UTF-8?...)
                    clean_sender = decode_mime_header(clean_sender)

                subscriptions[clean_sender]['count'] += 1
                
                # 3. Parse Unsubscribe Link (if not already found for this sender)
                if not subscriptions[clean_sender]['mailto']:
                    mailto, http = parse_list_unsubscribe(list_header)
                    if mailto: subscriptions[clean_sender]['mailto'] = mailto
                    if http: subscriptions[clean_sender]['http'] = http

        except Exception:
            # Skip individual message errors to keep scanning
            continue

    print("\nScan complete.")
    
    # Filter for frequency > 5
    high_freq_subs = {k: v for k, v in subscriptions.items() if v['count'] > 5}
    
    if high_freq_subs:
        interactive_unsubscribe(service, high_freq_subs)
    else:
        print(f"No subscriptions with > 5 emails found (out of {len(subscriptions)} total detected).")

if __name__ == '__main__':
    main()
