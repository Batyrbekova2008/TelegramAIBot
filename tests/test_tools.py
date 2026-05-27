import json
import pytest
from unittest.mock import AsyncMock, MagicMock


# ── get_current_time ──────────────────────────────────────────────────────────

async def test_get_current_time_returns_valid_json():
    from services.tools import get_current_time
    result = await get_current_time()
    data = json.loads(result)
    assert "current_time" in data
    assert "current_date" in data


async def test_get_current_time_time_format():
    from services.tools import get_current_time
    data = json.loads(await get_current_time())
    h, m, s = data["current_time"].split(":")
    assert all(part.isdigit() for part in (h, m, s))


async def test_get_current_time_date_format():
    from services.tools import get_current_time
    data = json.loads(await get_current_time())
    parts = data["current_date"].split("-")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


# ── calculate_math ────────────────────────────────────────────────────────────

async def test_calculate_math_addition():
    from services.tools import calculate_math
    assert json.loads(await calculate_math("2 + 3"))["result"] == 5


async def test_calculate_math_parentheses():
    from services.tools import calculate_math
    assert json.loads(await calculate_math("(10 + 5) * 2"))["result"] == 30


async def test_calculate_math_float_division():
    from services.tools import calculate_math
    result = json.loads(await calculate_math("10 / 4"))["result"]
    assert abs(result - 2.5) < 1e-9


async def test_calculate_math_rejects_letters():
    from services.tools import calculate_math
    data = json.loads(await calculate_math("x + 1"))
    assert "error" in data


async def test_calculate_math_rejects_import():
    from services.tools import calculate_math
    data = json.loads(await calculate_math("__import__('os').system('id')"))
    assert "error" in data


async def test_calculate_math_handles_division_by_zero():
    from services.tools import calculate_math
    data = json.loads(await calculate_math("1 / 0"))
    assert "error" in data


# ── get_os_info ───────────────────────────────────────────────────────────────

async def test_get_os_info_has_required_fields():
    from services.tools import get_os_info
    data = json.loads(await get_os_info())
    assert "os" in data and isinstance(data["os"], str) and data["os"]
    assert "python" in data and isinstance(data["python"], str)


# ── get_system_resources ──────────────────────────────────────────────────────

async def test_get_system_resources_has_cpu_and_ram():
    from services.tools import get_system_resources
    data = json.loads(await get_system_resources())
    assert "cpu_%" in data and "ram_%" in data


async def test_get_system_resources_values_in_range():
    from services.tools import get_system_resources
    data = json.loads(await get_system_resources())
    assert 0 <= data["cpu_%"] <= 100
    assert 0 <= data["ram_%"] <= 100


# ── get_weather (mocked httpx) ────────────────────────────────────────────────

def _make_mock_client(status_code: int, json_body: dict | None = None):
    """Return an async context manager mock for httpx.AsyncClient."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    if json_body is not None:
        mock_response.json.return_value = json_body
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


async def test_get_weather_success(mocker):
    from services.tools import get_weather
    payload = {"current_condition": [{"temp_C": "22", "weatherDesc": [{"value": "Sunny"}]}]}
    mocker.patch("httpx.AsyncClient", return_value=_make_mock_client(200, payload))

    data = json.loads(await get_weather("Almaty"))
    assert data["city"] == "Almaty"
    assert data["temperature_C"] == "22"
    assert data["condition"] == "Sunny"


async def test_get_weather_city_not_found(mocker):
    from services.tools import get_weather
    mocker.patch("httpx.AsyncClient", return_value=_make_mock_client(404))

    data = json.loads(await get_weather("UnknownCity"))
    assert "error" in data


async def test_get_weather_network_error(mocker):
    from services.tools import get_weather
    import httpx
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
    mocker.patch("httpx.AsyncClient", return_value=mock_client)

    data = json.loads(await get_weather("Nowhere"))
    assert "error" in data
