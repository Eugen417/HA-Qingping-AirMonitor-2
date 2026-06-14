from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN

# Оставляем только те платформы, файлы которых реально лежат в папке!
PLATFORMS = ["sensor", "binary_sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Запуск интеграции."""
    hass.data.setdefault(DOMAIN, {})
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": type("DummyCoordinator", (), {"data": {}})(),
    }
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Удаление интеграции."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
