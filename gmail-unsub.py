import os
import base64
import re
import sys
import time
import argparse
import requests
from collections import defaultdict
from email.header import decode_header
from email.mime.text import MIMEText
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scope: Read metadata to find lists, Modify to send emails (trash/send)
REQUIRED_SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

class SubscriptionScanner:
    def __init__(self, service, dry_run=False):
        self.service = service
        self.dry_run = dry_run
        self.subscriptions = defaultdict(lambda: {
            'name': "Unknown",
            'count': 0,
            'mailto': None,
            'http': None,
            'post_command': None # For RFC 8058 One-Click
        })

    def decode_mime_header(self, header_value):
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
                            text_parts.append(bytes_content.decode('utf-8', errors='ignore'))
                    else:
                        text_parts.append(bytes_content.decode('utf-8', errors='ignore'))
                else:
                    text_parts.append(str(bytes_content))
            return "".join(text_parts)
        except Exception:
            return header_value

    def parse_sender(self, from_header):
        """Returns (Name, Email) tuple."""
        if not from_header:
            return ("Unknown", "unknown@example.com")
        
        # Match "Name <email@domain.com>" or just "email@domain.com"
        match = re.search(r'(.*?)\s*<(.*?)>', from_header)
        if match:
            name = match.group(1).strip().strip('"')
            email = match.group(2).strip()
        else:
            name = from_header
            email = from_header
        
        name = self.decode_mime_header(name)
        if not name: name = email
        return name, email

    def parse_list_unsubscribe(self, list_header, post_header):
        """
        Parses headers to find valid unsubscribe methods.
        RFC 2369: List-Unsubscribe
        RFC 8058: List-Unsubscribe-Post
        """
        mailto = None
        http = None
        one_click_url = None

        if not list_header:
            return None, None, None

        parts = list_header.split(',')
        for part in parts:
            clean = part.strip().strip('<>')
            if clean.startswith('mailto:'):
                mailto = clean
            elif clean.startswith('http'):
                http = clean # Traditional link

        # Check for RFC 8058 One-Click
        # Ensure the HTTP link matches the post requirement usually (List-Unsubscribe=One-Click)
        if post_header and "List-Unsubscribe=One-Click" in post_header and http:
            one_click_url = http

        return mailto, http, one_click_url

    def scan_inbox(self, max_results=500):
        print(f"Scanning last {max_results} emails...")
        
        try:
            results = self.service.users().messages().list(
                userId='me', maxResults=max_results, q='in:inbox'
            ).execute()
            messages = results.get('messages', [])
        except HttpError as e:
            print(f"API Error: {e}")
            return

        total = len(messages)
        for i, msg in enumerate(messages):
            if i % 20 == 0:
                sys.stdout.write(f"\rProcessing: {i}/{total}")
                sys.stdout.flush()

            try:
                # Get minimal metadata
                msg_detail = self.service.users().messages().get(
                    userId='me', id=msg['id'], format='metadata', 
                    metadataHeaders=['From', 'List-Unsubscribe', 'List-Unsubscribe-Post']
                ).execute()

                headers = {h['name'].lower(): h['value'] for h in msg_detail.get('payload', {}).get('headers', [])}
                
                list_unsub = headers.get('list-unsubscribe')
                if list_unsub:
                    sender_name, sender_email = self.parse_sender(headers.get('from'))
                    
                    self.subscriptions[sender_email]['name'] = sender_name
                    self.subscriptions[sender_email]['count'] += 1
                    
                    # Only parse methods if we haven't found them for this sender yet
                    if not self.subscriptions[sender_email]['mailto']:
                        post_val = headers.get('list-unsubscribe-post')
                        m, h, one_click = self.parse_list_unsubscribe(list_unsub, post_val)
                        
                        if m: self.subscriptions[sender_email]['mailto'] = m
                        if h: self.subscriptions[sender_email]['http'] = h
                        if one_click: self.subscriptions[sender_email]['post_command'] = one_click

            except Exception:
                continue
        
        print(f"\nScan complete. Found {len(self.subscriptions)} unique lists.")

    def execute_unsubscribe(self, sender_email):
        data = self.subscriptions[sender_email]
        
        if self.dry_run:
            print(f"[DRY RUN] Would unsubscribe from {data['name']} via {data['mailto'] or data['http']}")
            return True, "Simulated success"

        # Priority 1: RFC 8058 One-Click POST
        if data['post_command']:
            try:
                print("Attempting One-Click (POST)...", end=" ")
                # RFC 8058 requires POST request
                resp = requests.post(data['post_command'], data={'List-Unsubscribe': 'One-Click'}, timeout=10)
                if resp.status_code < 400:
                    return True, f"HTTP POST Success ({resp.status_code})"
            except Exception as e:
                print(f"POST failed: {e}")
        
        # Priority 2: Mailto
        if data['mailto']:
            return self._send_email_unsub(data['mailto'])
        
        # Priority 3: Manual Link (Cannot automate safely usually)
        if data['http']:
            return False, f"Manual link only: {data['http']}"

        return False, "No valid method found"

    def _send_email_unsub(self, mailto_link):
        try:
            content = mailto_link.replace('mailto:', '')
            if '?' in content:
                to_addr, query = content.split('?', 1)
            else:
                to_addr = content
                query = ""

            subject = "Unsubscribe"
            body = "Please unsubscribe me from this list."
            
            # Simple query parsing
            if 'subject=' in query.lower():
                for param in query.split('&'):
                    if param.lower().startswith('subject='):
                        subject = param.split('=', 1)[1].replace('%20', ' ').replace('+', ' ')
            
            message = MIMEText(body)
            message['to'] = to_addr
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            self.service.users().messages().send(userId='me', body={'raw': raw}).execute()
            return True, f"Email sent to {to_addr}"
        except Exception as e:
            return False, str(e)

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', REQUIRED_SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("Error: credentials.json missing.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', REQUIRED_SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def main():
    parser = argparse.ArgumentParser(description="Gmail Subscription Cleaner")
    parser.add_argument("--limit", type=int, default=500, help="Number of emails to scan (default: 500)")
    parser.add_argument("--threshold", type=int, default=3, help="Minimum emails from sender to show (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without sending requests")
    args = parser.parse_args()

    service = get_gmail_service()
    scanner = SubscriptionScanner(service, dry_run=args.dry_run)
    scanner.scan_inbox(max_results=args.limit)

    # Filter and Sort
    valid_subs = [
        (email, data) for email, data in scanner.subscriptions.items() 
        if data['count'] >= args.threshold and (data['mailto'] or data['http'])
    ]
    valid_subs.sort(key=lambda x: x[1]['count'], reverse=True)

    if not valid_subs:
        print(f"No active subscriptions found with > {args.threshold} emails.")
        return

    while True:
        print(f"\nFound {len(valid_subs)} Lists (Threshold: {args.threshold})")
        print(f"{'ID':<4} | {'Count':<5} | {'Auto':<5} | {'Sender'}")
        print("-" * 60)
        
        for idx, (email, data) in enumerate(valid_subs):
            is_auto = "YES" if (data['post_command'] or data['mailto']) else "NO"
            name = data['name'][:40]
            print(f"{idx:<4} | {data['count']:<5} | {is_auto:<5} | {name} <{email}>")

        print("-" * 60)
        print("Commands: [ID] Unsubscribe | [all] Unsubscribe All Auto | [q] Quit")
        
        choice = input("> ").strip().lower()
        if choice == 'q': break
        
        if choice == 'all':
            print("Batch processing...")
            for email, data in valid_subs:
                if data['post_command'] or data['mailto']:
                    print(f"Unsubscribing {data['name']}...", end=" ")
                    success, msg = scanner.execute_unsubscribe(email)
                    print(msg)
                    time.sleep(1) # Rate limit
            continue

        try:
            idx = int(choice)
            if 0 <= idx < len(valid_subs):
                email, data = valid_subs[idx]
                print(f"Selected: {data['name']}")
                if data['post_command'] or data['mailto']:
                    confirm = input("Confirm unsubscribe? (y/n): ")
                    if confirm.lower() == 'y':
                        s, m = scanner.execute_unsubscribe(email)
                        print(m)
                elif data['http']:
                    print(f"Manual Link: {data['http']}")
        except ValueError:
            pass

if __name__ == "__main__":
    main()