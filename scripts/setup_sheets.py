"""
One-time Google Sheets setup verification script.
Run: python scripts/setup_sheets.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.sheets_service import sheets_service
from app.models.database import SessionLocal, engine
from app.models.models import Base, Sheet

print("\n╔══════════════════════════════════════════╗")
print("║   VoiceDesk — Google Sheets Setup        ║")
print("╚══════════════════════════════════════════╝\n")

# Ensure DB exists
Base.metadata.create_all(bind=engine)

# Try connecting
print(f"Credentials file: {settings.google_credentials_file}")
print(f"Spreadsheet name: {settings.google_spreadsheet_name}\n")

if sheets_service.connect():
    print("✓ Connected to Google Sheets successfully!\n")

    # Create default tabs
    db = SessionLocal()
    for name in settings.default_sheet_list:
        existing = db.query(Sheet).filter(Sheet.name == name).first()
        if not existing:
            sheet = Sheet(name=name, tab_name=name)
            db.add(sheet)
            db.commit()
        sheets_service.ensure_tab_exists(name)
        print(f"  ✓ Tab ready: '{name}'")

    db.close()
    print(f"\n✓ All done! Open your spreadsheet:")
    print(f"  https://docs.google.com/spreadsheets/")
    print(f"  (search for '{settings.google_spreadsheet_name}')\n")
else:
    print("✗ Could not connect to Google Sheets.")
    print("\nTroubleshooting:")
    print("  1. Make sure credentials.json exists at:")
    print(f"     {settings.google_credentials_file}")
    print("  2. Share your Google Spreadsheet with the service account email")
    print("     (found in credentials.json as 'client_email')")
    print("  3. Enable Google Sheets API + Google Drive API in your GCP project\n")
    sys.exit(1)
