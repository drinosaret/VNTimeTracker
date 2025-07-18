"""VNDB API integration for fetching visual novel data."""

import requests
import os
import urllib.parse
from PIL import Image
from io import BytesIO
from typing import Dict, List, Optional, Any

VNDB_API_URL = "https://api.vndb.org/kana/vn"


class VNDBClient:
    """Client for interacting with VNDB API."""
    
    def __init__(self, image_cache_dir: str):
        self.image_cache_dir = image_cache_dir
        self.vn_data: Dict[str, Any] = {}
        self.image_cache: Dict[str, Any] = {}
        os.makedirs(image_cache_dir, exist_ok=True)
    
    def search_vn(self, query: str = "", limit: int = 50) -> List[str]:
        """Search for visual novels and return list of titles."""
        try:
            payload = {
                "fields": "title, image.url",
                "sort": "title",
                "results": limit
            }
            if query.strip():
                payload["filters"] = ["search", "=", query.strip()]
            
            response = requests.post(
                VNDB_API_URL, 
                json=payload,
                headers={"Content-Type": "application/json"}, 
                timeout=5  # Reduced timeout for faster UI response
            )
            response.raise_for_status()
            data = response.json()
            
            # Store VN data for later use
            self.vn_data = {item["title"]: item for item in data.get("results", [])}
            return sorted(self.vn_data.keys())
            
        except Exception as e:
            print(f"VNDB API Error: {e}, Query: {query}")
            return []
    
    def get_vn_data(self, title: str) -> Optional[Dict[str, Any]]:
        """Get stored VN data for a title."""
        return self.vn_data.get(title)
    
    def get_cover_image(self, title: str) -> Optional[Any]:
        """Get cover image for a VN title."""
        if not title or title not in self.vn_data:
            return None
        
        vn_data = self.vn_data[title]
        image_url = vn_data.get("image", {}).get("url")
        if not image_url:
            return None
        
        # Check cache first
        image_path = os.path.join(
            self.image_cache_dir, 
            f"{urllib.parse.quote(title, safe='')}.jpg"
        )
        
        if image_path in self.image_cache:
            return self.image_cache[image_path]
        
        # Load from disk cache if exists
        if os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    return f.read()  # Return raw bytes for PyQt5
            except Exception as e:
                print(f"Cache image loading error: {e}")
        
        # Download from URL
        try:
            response = requests.get(image_url, timeout=5)  # Reduced timeout for UI responsiveness
            response.raise_for_status()
            img_data = response.content
            
            # Cache on disk
            with open(image_path, "wb") as f:
                f.write(img_data)
            
            # Return raw bytes for PyQt5
            return img_data
            
        except Exception as e:
            print(f"Cover image fetch error: {e}")
            return None
    
    def clear_cache(self) -> None:
        """Clear the image cache."""
        self.image_cache.clear()
