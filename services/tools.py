import json
import httpx
import psutil
import platform
from datetime import datetime

async def get_current_time() -> str:
    now = datetime.now()
    return json.dumps({"current_time": now.strftime("%H:%M:%S"), "current_date": now.strftime("%Y-%m-%d")})

async def get_weather(city: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://wttr.in/{city}?format=j1"
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                current = response.json()['current_condition'][0]
                return json.dumps({"city": city, "temperature_C": current['temp_C'], "condition": current['weatherDesc'][0]['value']})
            return json.dumps({"error": "Қала табылмады."})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def get_os_info() -> str:
    return json.dumps({"os": platform.system(), "python": platform.python_version()})

async def get_system_resources() -> str:
    return json.dumps({"cpu_%": psutil.cpu_percent(interval=0.5), "ram_%": psutil.virtual_memory().percent})

async def calculate_math(expression: str) -> str:
    try:
        if not all(c in "0123456789+-*/(). " for c in expression):
            return json.dumps({"error": "Рұқсат етілмеген символдар."})
        return json.dumps({"result": eval(expression)})
    except Exception as e:
        return json.dumps({"error": str(e)})

AI_TOOLS = [
    {"type": "function", "function": {"name": "get_current_time", "description": "Ағымдағы уақыт."}},
    {"type": "function", "function": {"name": "get_os_info", "description": "ОС ақпараты."}},
    {"type": "function", "function": {"name": "get_system_resources", "description": "Сервер ресурстары."}},
    {
        "type": "function",
        "function": {
            "name": "get_weather", "description": "Ауа райы.",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_math", "description": "Математикалық есептегіш.",
            "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}
        }
    }
]

FUNCTIONS_MAP = {
    "get_current_time": get_current_time,
    "get_weather": get_weather,
    "get_os_info": get_os_info,
    "get_system_resources": get_system_resources,
    "calculate_math": calculate_math
}