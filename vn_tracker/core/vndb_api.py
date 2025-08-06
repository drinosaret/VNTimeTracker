"""VNDB API integration for fetching visual novel data."""

import requests
import os
import urllib.parse
import json
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
        
        # Persistent VN data cache file
        self.vn_data_cache_file = os.path.join(image_cache_dir, "vn_data_cache.json")
        self.load_vn_data_cache()
    
    def load_vn_data_cache(self):
        """Load VN data from persistent cache file."""
        try:
            if os.path.exists(self.vn_data_cache_file):
                with open(self.vn_data_cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    self.vn_data.update(cached_data)
                    print(f"Loaded {len(cached_data)} VN entries from cache")
            else:
                print("No VN data cache file found")
        except Exception as e:
            print(f"Error loading VN data cache: {e}")
    
    def save_vn_data_cache(self):
        """Save VN data to persistent cache file."""
        try:
            with open(self.vn_data_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.vn_data, f, ensure_ascii=False, indent=2)
                print(f"Saved {len(self.vn_data)} VN entries to cache")
        except Exception as e:
            print(f"Error saving VN data cache: {e}")
    
    def search_vn(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """Search for visual novels and return list of VN data with IDs."""
        try:
            # Use search filter with higher limit to find exact matches
            payload = {
                "fields": "id, title, image{url}, description, released, rating, length_minutes, developers{name}",
                "sort": "searchrank",
                "results": min(limit * 2, 100)  # Get more results to find exact matches
            }
            if query.strip():
                payload["filters"] = ["search", "=", query.strip()]
            
            print(f"VNDB search request: {payload}")
            
            response = requests.post(
                VNDB_API_URL, 
                json=payload,
                headers={"Content-Type": "application/json"}, 
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            print(f"VNDB search response found {len(data.get('results', []))} results")
            
            # Store VN data for later use (by both title and ID)
            results = data.get("results", [])
            for item in results:
                # Store by title for backward compatibility
                self.vn_data[item["title"]] = item
                # Also store by ID for precise lookups
                if "id" in item:
                    self.vn_data[f"id:{item['id']}"] = item
            
            # Save to persistent cache
            if results:
                self.save_vn_data_cache()
            
            # Prioritize exact matches in results
            if query.strip():
                # Put exact matches first
                query_lower = query.strip().lower()
                exact_matches = [item for item in results if item["title"].lower() == query_lower]
                partial_matches = [item for item in results if item["title"].lower() != query_lower and query_lower in item["title"].lower()]
                other_matches = [item for item in results if item["title"].lower() != query_lower and query_lower not in item["title"].lower()]
                
                result_list = exact_matches + partial_matches + other_matches
                print(f"Prioritized results: exact={len(exact_matches)}, partial={len(partial_matches)}, other={len(other_matches)}")
                return result_list[:limit]
            else:
                return sorted(results, key=lambda x: x["title"])
            
        except Exception as e:
            print(f"VNDB API Search Error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_vn_data(self, title: str) -> Optional[Dict[str, Any]]:
        """Get stored VN data for a title."""
        return self.vn_data.get(title)
    
    def get_vn_data_by_id(self, vndb_id: str) -> Optional[Dict[str, Any]]:
        """Get stored VN data by VNDB ID."""
        return self.vn_data.get(f"id:{vndb_id}")
    
    def fetch_vn_by_id(self, vndb_id: str) -> Optional[Dict[str, Any]]:
        """Fetch VN data directly by VNDB ID."""
        try:
            payload = {
                "fields": "id, title, image{url}, description, released, rating, length_minutes, developers{name}",
                "filters": ["id", "=", vndb_id]
            }
            
            print(f"VNDB API fetch by ID request for '{vndb_id}': {payload}")
            
            response = requests.post(
                VNDB_API_URL, 
                json=payload,
                headers={"Content-Type": "application/json"}, 
                timeout=10
            )
            
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            if results:
                vn_data = results[0]  # Should be exactly one result for ID lookup
                # Store by both ID and title
                self.vn_data[f"id:{vndb_id}"] = vn_data
                self.vn_data[vn_data["title"]] = vn_data
                self.save_vn_data_cache()
                return vn_data
            else:
                print(f"No VN found with ID '{vndb_id}'")
                return None
                
        except Exception as e:
            print(f"VNDB API Error fetching by ID {vndb_id}: {e}")
            # Check cache for ID-based lookup
            cached_data = self.get_vn_data_by_id(vndb_id)
            if cached_data:
                print(f"Using cached data for ID '{vndb_id}' due to connection error")
                return cached_data
            import traceback
            traceback.print_exc()
            return None
    
    def refresh_vn_data(self, title: str) -> Optional[Dict[str, Any]]:
        """Force refresh VN data for a title, bypassing cache."""
        print(f"Force refreshing VN data for '{title}'")
        self.clear_vn_cache(title)
        return self.fetch_vn_details(title)
    
    def fetch_vn_details(self, title: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed VN information from VNDB by title."""
        # First check if we already have cached data
        if title in self.vn_data:
            print(f"Using cached data for '{title}'")
            return self.vn_data[title]
        
        try:
            # Search and look for exact title match in results
            payload = {
                "fields": "id, title, image{url}, description, released, rating, length_minutes, developers{name}",
                "filters": ["search", "=", title],
                "results": 20  # Get more results to find exact match
            }
            
            print(f"VNDB API detailed request for '{title}': {payload}")
            
            response = requests.post(
                VNDB_API_URL, 
                json=payload,
                headers={"Content-Type": "application/json"}, 
                timeout=10
            )
            
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            if results:
                # Look for exact title match first
                for result in results:
                    if result.get("title", "").lower() == title.lower():
                        print(f"Found exact match for '{title}': {result.get('title')} (ID: {result.get('id')})")
                        # Store by both title and ID
                        self.vn_data[title] = result
                        if "id" in result:
                            self.vn_data[f"id:{result['id']}"] = result
                        self.save_vn_data_cache()
                        return result
                
                # If no exact match, look for partial match
                for result in results:
                    result_title = result.get("title", "").lower()
                    if title.lower() in result_title or result_title in title.lower():
                        print(f"Found partial match for '{title}': {result.get('title')} (ID: {result.get('id')})")
                        # Store by both title and ID
                        self.vn_data[title] = result
                        if "id" in result:
                            self.vn_data[f"id:{result['id']}"] = result
                        self.save_vn_data_cache()
                        return result
                
                # If still no good match, return first result but warn
                print(f"Using first result for '{title}': {results[0].get('title')} (ID: {results[0].get('id')}) - may not be exact")
                vn_info = results[0]
                # Store by both title and ID
                self.vn_data[title] = vn_info
                if "id" in vn_info:
                    self.vn_data[f"id:{vn_info['id']}"] = vn_info
                self.save_vn_data_cache()
                return vn_info
            else:
                print(f"No results found for '{title}'")
                return None
            
        except Exception as e:
            print(f"VNDB API Error fetching details for {title}: {e}")
            # If we're offline or have connection issues, check cache one more time
            if title in self.vn_data:
                print(f"Using cached data for '{title}' due to connection error")
                return self.vn_data[title]
            import traceback
            traceback.print_exc()
            return None
    
    def get_cover_image(self, title: str) -> Optional[Any]:
        """Get cover image for a VN title."""
        if not title:
            return None
        
        # Check cache first (even if VN is not in vn_data)
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
                    image_data = f.read()  # Return raw bytes for PyQt5
                    # Cache in memory for future use
                    self.image_cache[image_path] = image_data
                    return image_data
            except Exception as e:
                print(f"Cache image loading error: {e}")
        
        # Try to fetch VN data if not available
        if title not in self.vn_data:
            print(f"VN data not found for '{title}', fetching...")
            vn_data = self.fetch_vn_details(title)
            if not vn_data:
                print(f"Could not fetch VN data for '{title}'")
                return None
        else:
            vn_data = self.vn_data[title]
        
        # Get image URL from VN data
        image_info = vn_data.get("image")
        if not image_info or not isinstance(image_info, dict):
            print(f"No image info found for '{title}': {image_info}")
            return None
            
        image_url = image_info.get("url")
        if not image_url:
            print(f"No image URL found for '{title}': {image_info}")
            return None
        
        # Download from URL
        try:
            print(f"Downloading image from: {image_url}")
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            img_data = response.content
            
            # Cache on disk
            with open(image_path, "wb") as f:
                f.write(img_data)
            
            # Cache in memory
            self.image_cache[image_path] = img_data
            
            print(f"Successfully downloaded and cached image for '{title}'")
            # Return raw bytes for PyQt5
            return img_data
            
        except Exception as e:
            print(f"Cover image fetch error for '{title}': {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def clear_cache(self) -> None:
        """Clear the image and VN data cache."""
        self.image_cache.clear()
        self.vn_data.clear()
        
        # Also clear persistent cache
        try:
            if os.path.exists(self.vn_data_cache_file):
                os.remove(self.vn_data_cache_file)
                print("Cleared persistent VN data cache")
        except Exception as e:
            print(f"Error clearing persistent cache: {e}")
        
        print("Cleared VN data and image cache")
    
    def clear_vn_cache(self, title: str) -> None:
        """Clear cached data for a specific VN title."""
        if title in self.vn_data:
            del self.vn_data[title]
            print(f"Cleared cached data for '{title}'")
            # Save updated cache
            self.save_vn_data_cache()
        
        # Also clear image cache for this title
        image_path = os.path.join(
            self.image_cache_dir, 
            f"{urllib.parse.quote(title, safe='')}.jpg"
        )
        if image_path in self.image_cache:
            del self.image_cache[image_path]
            print(f"Cleared cached image for '{title}'")
