"""
Google Sheets sync service using gspread.
Syncs SQLite → Google Sheets (one-way push).
"""
import json
from datetime import datetime
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logger import logger
from app.models.models import Sheet, Task, Meeting

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

TASK_HEADERS    = ["ID","Type","Title","Status","Due Date","Priority","Remarks","Created","Updated"]
MEETING_HEADERS = ["ID","Type","Title","Meeting Date","Participants","Location","Remarks","Renewal Date","Created"]


class SheetsService:
    def __init__(self):
        self._client: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None
        self._connected = False

    def connect(self) -> bool:
        creds_path = Path(settings.google_credentials_file)
        if not creds_path.exists():
            logger.warning(f"Google credentials not found at {creds_path}")
            return False
        try:
            creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
            self._client = gspread.authorize(creds)
            # Open or create spreadsheet
            try:
                self._spreadsheet = self._client.open(settings.google_spreadsheet_name)
                logger.info(f"Google Sheets opened: '{settings.google_spreadsheet_name}'")
            except gspread.SpreadsheetNotFound:
                self._spreadsheet = self._client.create(settings.google_spreadsheet_name)
                logger.info(f"Google Sheets created: '{settings.google_spreadsheet_name}'")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Google Sheets connection failed: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _get_or_create_tab(self, tab_name: str) -> gspread.Worksheet:
        """Get worksheet by name, create if missing."""
        try:
            return self._spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=20)
            logger.info(f"Created Sheets tab: '{tab_name}'")
            return ws

    def _ensure_headers(self, ws: gspread.Worksheet, headers: list[str]):
        first_row = ws.row_values(1)
        if first_row != headers:
            ws.update("A1", [headers])

    def _sheet_headers(self, sheet: Sheet) -> list[str]:
        if sheet.custom_columns and isinstance(sheet.custom_columns, list):
            return [str(h) for h in sheet.custom_columns if h is not None]
        return TASK_HEADERS

    def sync_sheet(self, db: Session, sheet: Sheet):
        """Push all tasks + meetings for one sheet to its Google Sheets tab."""
        if not self._connected:
            return
        tab_name = sheet.tab_name or sheet.name
        try:
            ws = self._get_or_create_tab(tab_name)
            headers = self._sheet_headers(sheet)
            self._ensure_headers(ws, headers)

            rows = []
            for t in sheet.tasks:
                rows.append([
                    t.id, "Task", t.title, t.status,
                    t.due_date.strftime("%Y-%m-%d %H:%M") if t.due_date else "",
                    t.priority,
                    t.remarks or "",
                    t.created_at.strftime("%Y-%m-%d %H:%M"),
                    t.updated_at.strftime("%Y-%m-%d %H:%M"),
                ])
            for m in sheet.meetings:
                rows.append([
                    m.id, "Meeting", m.title,
                    m.meeting_date.strftime("%Y-%m-%d %H:%M") if m.meeting_date else "",
                    m.participants or "",
                    m.location or "",
                    m.remarks or "",
                    m.renewal_date.strftime("%Y-%m-%d") if m.renewal_date else "",
                    m.created_at.strftime("%Y-%m-%d %H:%M"),
                ])

            # Clear data rows (keep header) then write fresh
            last_row = max(len(rows) + 1, 2)
            ws.batch_clear([f"A2:I{last_row + 50}"])
            if rows:
                ws.update("A2", rows)

            sheet.last_synced = datetime.utcnow()
            db.commit()
            logger.info(f"Synced sheet '{sheet.name}' → {len(rows)} rows")

        except Exception as e:
            logger.error(f"Sheets sync error for '{sheet.name}': {e}")

    def sync_all(self, db: Session):
        """Sync every sheet in the DB."""
        if not self._connected:
            logger.warning("Sheets sync skipped — not connected")
            return
        sheets = db.query(Sheet).all()
        for sheet in sheets:
            self.sync_sheet(db, sheet)

    def sync_all_background(self):
        """Sync every sheet in the DB in a background thread to prevent blocking the event loop."""
        import threading
        from app.models.database import SessionLocal

        if not self._connected:
            logger.warning("Sheets sync skipped — not connected")
            return

        def _run():
            db = SessionLocal()
            try:
                self.sync_all(db)
            except Exception as e:
                logger.error(f"Background sheets sync error: {e}")
            finally:
                db.close()

        # Run the blocking function in a separate daemon thread
        threading.Thread(target=_run, daemon=True).start()

    def ensure_tab_exists(self, tab_name: str):
        """Create tab in Google Sheets if it doesn't exist."""
        if self._connected:
            self._get_or_create_tab(tab_name)

    def ensure_tab_with_headers(self, sheet: Sheet):
        """Create or update a sheet tab with configured headers."""
        if self._connected:
            tab_name = sheet.tab_name or sheet.name
            ws = self._get_or_create_tab(tab_name)
            self._ensure_headers(ws, self._sheet_headers(sheet))


# Singleton
sheets_service = SheetsService()
