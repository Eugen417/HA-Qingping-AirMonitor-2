import json
import logging
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components import mqtt
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, CONF_MAC

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    mac = entry.data[CONF_MAC]
    async_add_entities([
        QingpingBinarySensor(mac, "charging", "battery_charging"),
    ])

class QingpingBinarySensor(RestoreEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, mac, sensor_type, device_class):
        self._mac = mac
        self._sensor_type = sensor_type
        self._last_ts = 0
        self._attr_unique_id = f"qingping_cgs2_{mac}_{sensor_type}"
        self._attr_translation_key = sensor_type # МАГИЯ ПЕРЕВОДА
        self._attr_device_class = device_class

        formatted_mac = ":".join(mac[i:i+2] for i in range(0, len(mac), 2))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name="Qingping Air Monitor CGS2",
            manufacturer="Qingping",
            model="CGS2",
            connections={("mac", formatted_mac)},
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in ["on", "off"]:
            self._attr_is_on = (last_state.state == "on")

        topic_up = f"qingping/{self._mac}/up"

        async def message_received(msg):
            try:
                payload = json.loads(msg.payload)
                msg_type = str(payload.get("type"))
                
                if msg_type in ["12", "13", "17"] and "sensorData" in payload:
                    sensor_data_list = payload["sensorData"]
                    if not sensor_data_list:
                        return

                    # Безопасная функция для извлечения времени (как в sensor.py)
                    def get_ts(item):
                        ts = item.get("timestamp", 0)
                        if isinstance(ts, dict):
                            return ts.get("value", 0)
                        try:
                            return int(ts)
                        except (ValueError, TypeError):
                            return 0

                    # Строгая сортировка от новых к старым и выбор только самой свежей записи
                    sensor_data_list.sort(key=get_ts, reverse=True)
                    latest_data = sensor_data_list[0]
                    latest_ts = get_ts(latest_data)
                    if latest_ts > 0 and latest_ts < self._last_ts:
                        return
                    if latest_ts > self._last_ts:
                        self._last_ts = latest_ts
                    
                    bat_data = latest_data.get("battery", {})
                    status = bat_data.get("status")
                    level = bat_data.get("value")

                    if status is not None:
                        # По документации Qingping: 0 discharging, 1 charging, 2 fully charged
                        is_on = (status == 1 and (level is None or level < 100))
                        self._attr_is_on = is_on
                        self.async_write_ha_state()
                            
            except Exception as e:
                _LOGGER.error("MQTT Binary Error: %s", e)

        self.async_on_remove(
            await mqtt.async_subscribe(self.hass, topic_up, message_received)
        )
