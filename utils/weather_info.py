import httpx

class WeatherForecastTool:
    def __init__(self, api_key:str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"

    async def get_current_weather(self, place:str):
        """Get current weather of a place"""
        try:
            url = f"{self.base_url}/weather"
            params = {
                "q": place,
                "appid": self.api_key,
            }
            async with httpx.AsyncClient(timeout=1.5) as client:
                response = await client.get(url, params=params)
                return response.json() if response.status_code == 200 else {}
        except Exception as e:
            return {}
    
    async def get_forecast_weather(self, place:str):
        """Get weather forecast of a place"""
        try:
            url = f"{self.base_url}/forecast"
            params = {
                "q": place,
                "appid": self.api_key,
                "cnt": 10,
                "units": "metric"
            }
            async with httpx.AsyncClient(timeout=1.5) as client:
                response = await client.get(url, params=params)
                return response.json() if response.status_code == 200 else {}
        except Exception as e:
            return {}