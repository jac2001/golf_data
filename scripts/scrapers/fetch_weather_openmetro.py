
#!/usr/bin/env python3
"""
Fetch weather data from Open-Meteo.

Usage:
  python3 scripts/scrapers/fetch_weather_openmeteo.py --lat 36.5686 --lon -121.9487
  python3 scripts/scrapers/fetch_weather_openmeteo.py --lat 36.5686 --lon -121.9487 --output /tmp/weather.json
"""

import argparse
import json
import requests
# ============================================================================                                        
  # WEATHER HELPERS                                                                                                     
  # ============================================================================                                        
                                                                                                                        
  # Course coordinates for weather lookup                                                                               
COURSE_COORDINATES = {
    "pebble beach": (36.5675, -121.9486),
    "torrey pines": (32.9005, -117.2516),
    "augusta national": (33.5021, -82.0232),
    "tpc scottsdale": (33.6417, -111.9083),
    "riviera": (34.0489, -118.5003),
    "bay hill": (28.4603, -81.5053),
    "tpc sawgrass": (30.1975, -81.3964),
    "harbour town": (32.1363, -80.8090),
    "quail hollow": (35.1089, -80.8519),
    "southern hills": (36.0631, -95.9408),
    "bethpage black": (40.7445, -73.4533),
    "valhalla": (38.2527, -85.4938),
    "pinehurst": (35.1894, -79.4694),
    "royal troon": (55.5436, -4.8492),
    "st andrews": (56.3433, -2.8019),
    # 2026 schedule additions
    "tpc san antonio": (29.5585, -98.6193),
    "innisbrook": (28.1531, -82.7338),           # Copperhead course, Zurich Classic area
    "tpc louisiana": (29.9421, -90.1710),        # Zurich Classic
    "pga national": (26.8373, -80.1169),         # Honda Classic
    "sedgefield": (36.0413, -79.8888),           # Wyndham Championship
    "muirfield village": (40.1037, -83.1418),    # Memorial Tournament
    "colonial": (32.7157, -97.3671),             # Charles Schwab / Colonial CC, Fort Worth
    "castle pines": (39.4631, -104.8760),        # BMW Championship alternate
    "oak hill": (43.1133, -77.5538),             # Rochester, NY
    "oakmont": (40.5195, -79.7986),              # USGA / PGA championship site
    "shinnecock": (40.8843, -72.4371),           # Shinnecock Hills
    "wilmington cc": (39.8102, -75.5171),        # BMW Championship
    "east lake": (33.7215, -84.3019),            # Tour Championship
    "kapalua": (20.9931, -156.6647),             # Sentry
    "waialae": (21.2769, -157.7559),             # Sony Open
    "shadow creek": (36.2272, -115.1908),        # CJ Cup
    "the grove xxiii": (34.2103, -118.6325),     # unofficial, Sherwood adj
    "century club": (32.9546, -117.0632),        # Farmers Insurance adj Torrey
    "muirhead": (56.3433, -2.8019),              # alias for st andrews
    "carnoustie": (56.5020, -2.6589),
    "royal st george": (51.3128, 1.3842),
    "hoylake": (53.3950, -3.1885),
    "royal birkdale": (53.6389, -3.0314),
}

def fetch_weather(lat: float, lon: float) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto"
    )
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()



def get_course_coordinates(course_name: str) -> tuple:                                                                
    """Get lat/lon for a course, or default to Pebble Beach."""                                                       
    if not course_name:                                                                                               
        return COURSE_COORDINATES["pebble beach"]                                                                     
                                                                                                                    
    course_lower = course_name.lower()                                                                                
    for key, coords in COURSE_COORDINATES.items():                                                                    
        if key in course_lower:                                                                                       
            return coords                                                                                             
                                                                                                                    
    # Default                                                                                                         
    return COURSE_COORDINATES["pebble beach"]                                                                         
    

def fetch_weather(lat: float, lon: float) -> dict:                                                                    
    """Fetch current weather from Open-Meteo API (free, no key needed)."""                                            
    try:                                                                                                              
        url = f"https://api.open-meteo.com/v1/forecast"                                                               
        params = {                                                                                                    
            "latitude": lat,                                                                                          
            "longitude": lon,                                                                                         
            "current_weather": "true",                                                                                
            "temperature_unit": "fahrenheit",                                                                         
            "windspeed_unit": "mph",                                                                                  
            "timezone": "America/Los_Angeles"                                                                         
        }                                                                                                             
        resp = requests.get(url, params=params, timeout=10)                                                           
        resp.raise_for_status()                                                                                       
        data = resp.json()                                                                                            
                                                                                                                    
        current = data.get("current_weather", {})                                                                     
                                                                                                                    
        # Weather code to description                                                                                 
        weather_codes = {                                                                                             
            0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",                                         
            45: "Foggy", 48: "Foggy", 51: "Light Drizzle", 53: "Drizzle",                                             
            55: "Heavy Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",                                      
            71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 80: "Rain Showers",                                       
            81: "Rain Showers", 82: "Heavy Showers", 95: "Thunderstorm"                                               
        }                                                                                                             
                                                                                                                    
        code = current.get("weathercode", 0)                                                                          
                                                                                                                    
        return {                                                                                                      
            "temp_f": round(current.get("temperature", 0)),                                                           
            "wind_mph": round(current.get("windspeed", 0)),                                                           
            "wind_dir": current.get("winddirection", 0),                                                              
            "conditions": weather_codes.get(code, "Unknown"),                                                         
            "code": code,                                                                                             
            "is_windy": current.get("windspeed", 0) > 15,                                                             
            "success": True                                                                                           
        }                                                                                                             
    except Exception as e:                                                                                            
        return {"success": False, "error": str(e)}                                                                    
                                                                                                                    
                    









def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch weather from Open-Meteo")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    data = fetch_weather(args.lat, args.lon)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(data, f, indent=2)
        print(f"✓ Saved weather → {args.output}")
    else:
        print(json.dumps(data, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

