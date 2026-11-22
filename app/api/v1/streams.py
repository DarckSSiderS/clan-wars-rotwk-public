from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import requests
import os
from app.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.get("/twitch/{channel_name}")
async def check_twitch_stream(channel_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Проверить статус Twitch стрима"""
    try:
        # Используем Twitch API
        client_id = os.getenv("TWITCH_CLIENT_ID")
        client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            # Для демонстрации возвращаем случайный статус
            import random
            return {"is_live": random.choice([True, False]), "demo": True}
        
        # Получаем access token
        token_response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials"
            }
        )
        
        if token_response.status_code != 200:
            return {"is_live": False, "error": "Failed to get Twitch access token"}
        
        access_token = token_response.json()["access_token"]
        
        # Проверяем статус стрима
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}"
        }
        
        stream_response = requests.get(
            f"https://api.twitch.tv/helix/streams?user_login={channel_name}",
            headers=headers
        )
        
        if stream_response.status_code == 200:
            data = stream_response.json()
            is_live = len(data["data"]) > 0
            return {"is_live": is_live}
        else:
            return {"is_live": False, "error": "Failed to check stream status"}
            
    except Exception as e:
        return {"is_live": False, "error": str(e)}

@router.get("/youtube/{channel_id}")
async def check_youtube_stream(channel_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Проверить статус YouTube стрима"""
    try:
        # Используем YouTube Data API
        api_key = os.getenv("YOUTUBE_API_KEY")
        
        if not api_key:
            # Для демонстрации возвращаем случайный статус
            import random
            return {"is_live": random.choice([True, False]), "demo": True}
        
        # Сначала получаем ID канала, если передан username
        if not channel_id.startswith("UC"):
            # Это username, нужно получить channel ID
            search_response = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "q": channel_id,
                    "type": "channel",
                    "key": api_key
                }
            )
            
            if search_response.status_code == 200:
                data = search_response.json()
                if data["items"]:
                    channel_id = data["items"][0]["snippet"]["channelId"]
                else:
                    return {"is_live": False, "error": "Channel not found"}
            else:
                return {"is_live": False, "error": "Failed to search for channel"}
        
        # Проверяем активные стримы
        streams_response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "channelId": channel_id,
                "type": "video",
                "eventType": "live",
                "key": api_key
            }
        )
        
        if streams_response.status_code == 200:
            data = streams_response.json()
            is_live = len(data["items"]) > 0
            return {"is_live": is_live}
        else:
            return {"is_live": False, "error": "Failed to check stream status"}
            
    except Exception as e:
        return {"is_live": False, "error": str(e)} 