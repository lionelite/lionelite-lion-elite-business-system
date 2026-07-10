import base64
import os
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


def get_credentials() -> Credentials:
    required = {
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
        "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET"),
        "GOOGLE_REFRESH_TOKEN": os.getenv("GOOGLE_REFRESH_TOKEN"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing Google OAuth settings: {', '.join(missing)}")

    return Credentials(
        token=None,
        refresh_token=required["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=required["GOOGLE_CLIENT_ID"],
        client_secret=required["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES,
    )


def gmail_service():
    return build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)


def calendar_service():
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)


def send_gmail(to: str, subject: str, body: str, reply_to_message_id: str | None = None) -> dict:
    message = EmailMessage()
    message["To"] = to
    message["From"] = os.getenv("GMAIL_FROM_ADDRESS", "me")
    message["Subject"] = subject
    message.set_content(body)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    payload = {"raw": raw}
    if reply_to_message_id:
        payload["threadId"] = reply_to_message_id

    return gmail_service().users().messages().send(userId="me", body=payload).execute()


def list_recent_replies(query: str = "in:inbox newer_than:2d", max_results: int = 50) -> list[dict]:
    service = gmail_service()
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = []
    for item in result.get("messages", []):
        messages.append(service.users().messages().get(userId="me", id=item["id"], format="metadata", metadataHeaders=["From", "Subject"]).execute())
    return messages


def create_calendar_event(summary: str, start_iso: str, end_iso: str, attendee_email: str | None = None, description: str | None = None) -> dict:
    event = {
        "summary": summary,
        "description": description or "",
        "start": {"dateTime": start_iso, "timeZone": "America/New_York"},
        "end": {"dateTime": end_iso, "timeZone": "America/New_York"},
    }
    if attendee_email:
        event["attendees"] = [{"email": attendee_email}]

    return calendar_service().events().insert(
        calendarId=os.getenv("GOOGLE_CALENDAR_ID", "primary"),
        body=event,
        sendUpdates="all" if attendee_email else "none",
    ).execute()
