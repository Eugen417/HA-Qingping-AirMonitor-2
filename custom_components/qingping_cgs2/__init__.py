from datetime import timedelta
import json
import logging
import time

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_MAC,
    CONF_REALTIME_INTERVAL,
    DEFAULT_REALTIME_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Запуск интеграции."""
    hass.data.setdefault(DOMAIN, {})

    mac = entry.data[CONF_MAC]
    realtime_interval = int(
        entry.options.get(CONF_REALTIME_INTERVAL, DEFAULT_REALTIME_INTERVAL)
    )
    topic_up = f"qingping/{mac}/up"
    topic_down = f"qingping/{mac}/down"

    entry_data = {
        "coordinator": type("DummyCoordinator", (), {"data": {}})(),
        "sw_version": None,
        "last_ack_id": None,
        "last_realtime_req": 0.0,
    }
    hass.data[DOMAIN][entry.entry_id] = entry_data

    async def send_realtime_command(_now=None):
        """Отправка команды 3.2 Set Realtime Data Reporting Interval (type 12)."""
        if realtime_interval <= 2:
            return
        payload = json.dumps({
            "type": "12",
            "up_itvl": str(realtime_interval),
            "duration": "3600",
        })
        try:
            await mqtt.async_publish(hass, topic_down, payload)
            entry_data["last_realtime_req"] = time.time()
        except Exception as err:
            _LOGGER.debug("Failed to publish realtime command for %s: %s", mac, err)

    async def handle_device_message(msg):
        """Обработка системных полей пакета: ACK Type 18, версия прошивки и продление Type 12."""
        try:
            payload = json.loads(msg.payload)
        except Exception:
            return

        msg_type = str(payload.get("type"))

        # 2.2 Device Reports Historical Data -> Server Response Type 18
        if msg_type == "17" and payload.get("need_ack") == 1:
            msg_id = payload.get("id", 0)
            ack_payload = json.dumps({
                "ack_id": msg_id,
                "code": 0,
                "desc": "",
                "timestamp": int(time.time()),
                "type": "18",
            })
            hass.async_create_task(mqtt.async_publish(hass, topic_down, ack_payload))

            # Если включен режим реального времени, а монитор прислал только фоновый пакет 17,
            # обновляем подписку на realtime (не чаще раза в 60 секунд)
            if realtime_interval > 2 and (time.time() - entry_data["last_realtime_req"]) > 60:
                hass.async_create_task(send_realtime_command())

        # Обновление версии прошивки (version) в карточке устройства Home Assistant
        version = payload.get("version")
        if version and version != entry_data.get("sw_version"):
            entry_data["sw_version"] = version
            dev_reg = dr.async_get(hass)
            device = dev_reg.async_get_device(identifiers={(DOMAIN, mac)})
            if device and device.sw_version != version:
                dev_reg.async_update_device(device.id, sw_version=str(version))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    unsub_mqtt = await mqtt.async_subscribe(hass, topic_up, handle_device_message)
    entry.async_on_unload(unsub_mqtt)

    if realtime_interval > 2:
        hass.async_create_task(send_realtime_command())
        entry.async_on_unload(
            async_track_time_interval(
                hass, send_realtime_command, timedelta(minutes=50)
            )
        )

    # Слушаем изменения настроек и применяем их
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Удаление интеграции."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Перезагрузка при изменении настроек."""
    await hass.config_entries.async_reload(entry.entry_id)

