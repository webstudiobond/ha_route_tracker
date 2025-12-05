"""The route integration."""
import logging
import os
import asyncio
import json
from datetime import datetime, timedelta
from aiofiles import open as aio_open
from typing import Any

from aiohttp import web
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.http import HomeAssistantView
from homeassistant.components import frontend
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import CONF_NAME, CONF_DEVICES
from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.http.view import HomeAssistantView as BaseHomeAssistantView

_LOGGER = logging.getLogger(__name__)

DOMAIN = "route"
SUPPORTED_DOMAINS = ["sensor"]

DEFAULT_NAME = "Route"
CONF_HLAT = "hlat"
CONF_HLON = "hlon"
CONF_HADDR = "haddr"
CONF_ACCESS_TOKEN = "access_token"
CONF_TIME_ZONE = "time_zone"
CONF_MINIMAL_DISTANCE = "minimal_distance"
CONF_NUMBER_OF_DAYS = "number_of_days"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    if DOMAIN in config:
        for conf in config.get(DOMAIN, []):
            await async_setup_route(hass, conf)
    return True


async def async_setup_route(hass: HomeAssistant, config: dict[str, Any]) -> None:
    base_path = os.path.dirname(__file__)
    resources_path = os.path.join(base_path, "resources")
    images_path = os.path.join(resources_path, "images")

    # local js/css
    hass.http.app.router.add_static(
        "/local/route/resources",
        resources_path,
        show_index=False
    )

    # local png
    if os.path.isdir(images_path):
        hass.http.app.router.add_static(
            "/local/route/resources/images",
            images_path,
            show_index=False
        )
    
    sensors_gps = SensorsGps(hass, config)
    hass.data.setdefault(DOMAIN, {})["sensors_gps"] = sensors_gps

    await sensors_gps.update()
    async_track_time_interval(hass, sensors_gps.async_update, timedelta(seconds=60))

    for platform in SUPPORTED_DOMAINS:
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, {DOMAIN: [config]}))

    route_view = Route(hass, config)
    await route_view.async_create_files()
    hass.http.register_view(route_view)
    
    # Register API endpoints
    config_api_view = RouteConfigAPI(hass, config)
    hass.http.register_view(config_api_view)
    
    # API to get fallback coordinates (only when there is no route data)
    home_location_api_view = RouteHomeLocationAPI(hass, config)
    hass.http.register_view(home_location_api_view)
    
    # Register API for history retrieval (secure proxying endpoint)
    history_api_view = RouteHistoryAPI(hass, config)
    hass.http.register_view(history_api_view)

    frontend.async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title="Routes",
        sidebar_icon="mdi:routes",
        frontend_url_path="myroute",  # <--- Было url_path, стало frontend_url_path
        config={"url": "/local/route"},
        require_admin=False,
    )


class SensorsGps:
    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self.config = config
        self.devices = config.get(CONF_DEVICES, [])
        self.hlat = config.get(CONF_HLAT, 50.0)
        self.hlon = config.get(CONF_HLON, 30.0)
        self.haddr = config.get(CONF_HADDR, "http://localhost:8123")
        self.access_token = config.get(CONF_ACCESS_TOKEN, "")
        self.time_zone = config.get(CONF_TIME_ZONE, "UTC")
        self.minimal_distance = config.get(CONF_MINIMAL_DISTANCE, 0.05)
        self.number_of_days = config.get(CONF_NUMBER_OF_DAYS, 7)
        self.states: dict[str, list[Any]] = {}

    async def update(self) -> None:
        self._get_device_trackers()

    async def async_update(self, now=None, **kwargs) -> None:
        await self.update()
        async_dispatcher_send(self.hass, DOMAIN)

    def _get_device_trackers(self) -> None:
        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for device in self.devices:
            if not isinstance(device, (list, tuple)) or len(device) < 2:
                continue
            device_entity = device[1]
            state = self.hass.states.get(device_entity)
            lat = state.attributes.get("latitude", 0) if state else 0
            lon = state.attributes.get("longitude", 0) if state else 0
            self.states[device_entity] = [time_now, lat, lon]


class RouteConfigAPI(BaseHomeAssistantView):
    """API endpoint для получения конфигурации route компонента."""
    url = "/api/route/config"
    name = "api:route:config"
    requires_auth = False  # Remove authorization requirement for iframe

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self.config = config

    async def get(self, request: web.Request) -> web.Response:
        """Returns the route configuration of the component in JSON format."""
        try:
            devices_var = []
            devices = self.config.get(CONF_DEVICES, [])
            
            for device in devices:
                if isinstance(device, (list, tuple)) and len(device) >= 2:
                    friendly_name, entity_id = device
                    entity_domain = entity_id.split(".")[0]
                    if entity_domain == "device_tracker":
                        virtual_entity_id = f"sensor.virtual_{entity_id.replace('.', '_')}"
                        devices_var.append([friendly_name, virtual_entity_id])
                    else:
                        devices_var.append([friendly_name, entity_id])
            
            config_data = {
                "devices": devices_var,
                "timeZone": self.config.get(CONF_TIME_ZONE, "UTC"),
                "minimalDistance": self.config.get(CONF_MINIMAL_DISTANCE, 0.05),
                "numberOfDays": self.config.get(CONF_NUMBER_OF_DAYS, 7)
            }
            
            # Headers to prevent API caching
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
            
            return web.json_response(config_data, headers=headers)
            
        except Exception as e:
            _LOGGER.error("Error getting route config: %s", e)
            return web.json_response(
                {"error": "Failed to get configuration"}, 
                status=500
            )


class RouteHomeLocationAPI(BaseHomeAssistantView):
    """API endpoint для получения fallback координат (только когда нет данных маршрута)."""
    url = "/api/route/fallback-location"
    name = "api:route:fallback-location"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self.config = config

    async def get(self, request: web.Request) -> web.Response:
        """Возвращает fallback координаты только когда нет данных маршрута."""
        try:
            # Return coordinates only as fallback for empty routes
            location_data = {
                "latitude": self.config.get(CONF_HLAT, 50.0),
                "longitude": self.config.get(CONF_HLON, 30.0)
            }
            
            # Headers to prevent API caching
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
            
            return web.json_response(location_data, headers=headers)
            
        except Exception as e:
            _LOGGER.error("Error getting fallback location: %s", e)
            return web.json_response(
                {"error": "Failed to get fallback location"}, 
                status=500
            )


class RouteHistoryAPI(BaseHomeAssistantView):
    """API endpoint для получения истории устройств (проксирует запросы к History API)."""
    url = "/api/route/history"
    name = "api:route:history"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self.config = config

    async def get(self, request: web.Request) -> web.Response:
        """Proxies requests to the History API with internal authorization."""
        try:
            # Getting the query parameters
            date = request.query.get('date')
            entity_id = request.query.get('entity_id')
            
            if not date or not entity_id:
                return web.json_response(
                    {"error": "Missing required parameters: date, entity_id"}, 
                    status=400
                )
            
            # Making an internal HTTP request to the History API
            import aiohttp
            
            # Getting the access token from the configuration
            access_token = self.config.get(CONF_ACCESS_TOKEN, "")
            home_assistant_url = self.config.get(CONF_HADDR, "http://localhost:8123")
            
            if not access_token:
                return web.json_response(
                    {"error": "Access token not configured"}, 
                    status=503
                )
            
            # Generate URL for History API
            history_url = f"{home_assistant_url}/api/history/period/{date}?filter_entity_id={entity_id}"
            
            # Creating headers with authorization
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Making a request to the History API
            async with aiohttp.ClientSession() as session:
                async with session.get(history_url, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        return web.json_response(result)
                    else:
                        _LOGGER.error("History API error: %s", response.status)
                        return web.json_response(
                            {"error": f"History API error: {response.status}"}, 
                            status=response.status
                        )
            
        except Exception as e:
            _LOGGER.error("Error getting route history: %s", e)
            return web.json_response(
                {"error": f"Failed to get history: {str(e)}"}, 
                status=500
            )


class Route(BaseHomeAssistantView):
    url = "/local/route"
    name = "route"
    requires_auth = False  # Remove authorization for iframe

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self.config = config
        self._files_created = False

    async def async_create_files(self) -> None:
        """Check that the HTML file exists."""
        path_domain = self.hass.config.path(f"custom_components/{DOMAIN}")
        route_html_path = os.path.join(path_domain, "route.html")
        
        if not os.path.exists(route_html_path):
            _LOGGER.error("Route HTML file not found: %s", route_html_path)
            return
            
        self._files_created = True

    async def get(self, request: web.Request) -> web.Response:
        if not self._files_created:
            await self.async_create_files()
            
        path_domain = self.hass.config.path(f"custom_components/{DOMAIN}")
        route_html_path = os.path.join(path_domain, "route.html")
        
        if os.path.exists(route_html_path):
            async with aio_open(route_html_path, "r", encoding="utf-8") as file:
                content = await file.read()
            
            timestamp = str(int(datetime.now().timestamp()))
            
            content = content.replace(
                'href="/local/route/resources/leaflet.css"',
                f'href="/local/route/resources/leaflet.css?v={timestamp}"'
            )
            content = content.replace(
                'src="/local/route/resources/leaflet.js"',
                f'src="/local/route/resources/leaflet.js?v={timestamp}"'
            )
            content = content.replace(
                'src="/local/route/resources/leaflet.polylineDecorator.js"',
                f'src="/local/route/resources/leaflet.polylineDecorator.js?v={timestamp}"'
            )
            
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Last-Modified': datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT'),
                'ETag': f'"{timestamp}"'
            }
            
            return web.Response(
                text=content, 
                content_type="text/html",
                headers=headers
            )
            
        return web.Response(text="Route page not found", status=404)
