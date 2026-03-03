#!/usr/bin/env python3
"""Test script to initiate an outbound call.

Usage:
    python scripts/test_call.py --phone "+966XXXXXXXXX" --name "خالد"
    python scripts/test_call.py --phone "+966XXXXXXXXX" --name "خالد" --base-url "http://localhost:8000"
"""

import argparse
import sys
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Test outbound call")
    parser.add_argument("--phone", required=True, help="Customer phone number (e.g., +966XXXXXXXXX)")
    parser.add_argument("--name", required=True, help="Customer name")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    url = f"{args.base_url}/api/calls/initiate"
    payload = {
        "customer_phone": args.phone,
        "customer_name": args.name,
        "context": {},
    }

    print(f"Initiating call to {args.name} ({args.phone})...")

    response = httpx.post(url, json=payload, timeout=30)

    if response.status_code == 200:
        data = response.json()
        print(f"Call initiated successfully!")
        print(f"  Call ID: {data['call_id']}")
        print(f"  Status: {data['status']}")
        print(f"  Twilio SID: {data.get('twilio_call_sid', 'N/A')}")
        print(f"\nTrack status: GET {args.base_url}/api/calls/{data['call_id']}/status")
        print(f"Get transcript: GET {args.base_url}/api/calls/{data['call_id']}/transcript")
    else:
        print(f"Error: {response.status_code}")
        print(response.json())


if __name__ == "__main__":
    main()
