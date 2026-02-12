import os
from typing import Dict, Optional


def upload_video_to_youtube(
    video_file: str,
    metadata: Dict,
    thumbnail_file: Optional[str] = None,
    subtitles_file: Optional[str] = None,
) -> Optional[str]:
    """Upload video to YouTube. Requires OAuth client secrets and API deps."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except Exception as exc:
        print(f"YouTube upload dependencies missing: {exc}")
        return None

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    client_secrets = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secret.json")
    token_file = os.getenv("YOUTUBE_TOKEN_FILE", "outputs/youtube_token.json")
    os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": metadata.get("title", "AI Video"),
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
            "categoryId": metadata.get("categoryId", "28"),
            "defaultLanguage": metadata.get("defaultLanguage", "en"),
        },
        "status": {
            "privacyStatus": metadata.get("privacyStatus", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response.get("id")
    if not video_id:
        return None

    if thumbnail_file and os.path.exists(thumbnail_file):
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_file)).execute()

    if subtitles_file and os.path.exists(subtitles_file):
        cap_body = {
            "snippet": {
                "videoId": video_id,
                "language": metadata.get("defaultLanguage", "en"),
                "name": "English",
                "isDraft": False,
            }
        }
        youtube.captions().insert(
            part="snippet",
            body=cap_body,
            media_body=MediaFileUpload(subtitles_file, mimetype="application/octet-stream"),
        ).execute()

    return f"https://www.youtube.com/watch?v={video_id}"
