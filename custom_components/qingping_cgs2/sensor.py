import json
import logging
from datetime import datetime, timezone
from homeassistant.components.mqtt import async_subscribe
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.sensor import (
    UNIT_CONVERTERS,
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, CONF_MAC, CONF_USE_HISTORY

_LOGGER = logging.getLogger(__name__)

SENSORS = {
    "temperature": {"class": SensorDeviceClass.TEMPERATURE, "unit": "°C", "icon": "mdi:thermometer"},
    "humidity": {"class": SensorDeviceClass.HUMIDITY, "unit": "%", "icon": "mdi:water-percent"},
    "co2": {"class": SensorDeviceClass.CO2, "unit": "ppm", "icon": "mdi:molecule-co2"},
    "noise": {"class": SensorDeviceClass.SOUND_PRESSURE, "unit": "dB", "icon": "mdi:volume-high"},
    "pm25": {"class": SensorDeviceClass.PM25, "unit": "µg/m³", "icon": "mdi:blur"},
    "pm10": {"class": SensorDeviceClass.PM10, "unit": "µg/m³", "icon": "mdi:blur-linear"},
    "tvoc_index": {"class": None, "unit": None, "icon": "mdi:air-filter"},
    "battery": {"class": SensorDeviceClass.BATTERY, "unit": "%", "cat": EntityCategory.DIAGNOSTIC},
    "power_mode": {
        "class": SensorDeviceClass.ENUM,
        "unit": None,
        "cat": EntityCategory.DIAGNOSTIC,
        "options": ["mains", "battery"],
        "icon": "mdi:power-plug",
    },
}

async def async_setup_entry(hass, entry, async_add_entities):
    mac = entry.data[CONF_MAC]
    use_history = entry.options.get(CONF_USE_HISTORY, False)
    
    entities = [QingpingSensor(mac, key, data, use_history) for key, data in SENSORS.items()]
    async_add_entities(entities)

class QingpingSensor(RestoreSensor):
    _attr_has_entity_name = True

    def __init__(self, mac, sensor_key, sensor_data, use_history):
        self._mac = mac
        self._sensor_key = sensor_key
        self._use_history = use_history
        self._attr_unique_id = f"qingping_cgs2_{mac}_{sensor_key}"
        self._attr_translation_key = sensor_key 
        
        self._attr_device_class = sensor_data.get("class")
        self._attr_native_unit_of_measurement = sensor_data.get("unit")
        if "icon" in sensor_data:
            self._attr_icon = sensor_data["icon"]
        if "options" in sensor_data:
            self._attr_options = sensor_data["options"]
        
        if sensor_key not in ["power_mode"]:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        
        if "cat" in sensor_data:
            self._attr_entity_category = sensor_data["cat"]

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
        last_state = await self.async_get_last_sensor_data()
        if last_state and last_state.native_value is not None:
            if self._sensor_key != "power_mode" or last_state.native_value in ("mains", "battery"):
                self._attr_native_value = last_state.native_value

        topic = f"qingping/{self._mac}/up"

        async def message_received(msg):
            try:
                payload = json.loads(msg.payload)
                msg_type = str(payload.get("type"))
                
                if msg_type not in ["12", "13", "17"]:
                    return
                    
                sensor_data_list = payload.get("sensorData")
                if not sensor_data_list:
                    return
                    
                def get_ts(item):
                    ts = item.get("timestamp", 0)
                    if isinstance(ts, dict):
                        return ts.get("value", 0)
                    try:
                        return int(ts)
                    except (ValueError, TypeError):
                        return 0

                def update_state(item):
                    if self._sensor_key == "power_mode":
                        status = item.get("battery", {}).get("status")
                        if status is not None:
                            self._attr_native_value = "mains" if status == 1 else "battery"
                            self.async_write_ha_state()
                        return

                    if self._sensor_key in item:
                        sensor_info = item[self._sensor_key]
                        if self._sensor_key == "battery" or sensor_info.get("status") == 0:
                            val = sensor_info.get("value")
                            if val is not None:
                                if self._sensor_key in ["temperature", "humidity"]:
                                    self._attr_native_value = round(float(val), 1)
                                else:
                                    self._attr_native_value = val
                                self.async_write_ha_state()

                if msg_type in ["12", "13"]:
                    # Реальное время: берем только самую свежую точку
                    sensor_data_list.sort(key=get_ts, reverse=True)
                    update_state(sensor_data_list[0])

                elif msg_type == "17":
                    if not self._use_history:
                        # ИСТОРИЯ ОТКЛЮЧЕНА: полностью игнорируем 17 пакет!
                        return
                        
                    # ИСТОРИЯ ВКЛЮЧЕНА: выгружаем ВСЕ пропущенные точки на график
                    # Сортируем от старых к новым, чтобы график зафиксировал все скачки
                    sensor_data_list.sort(key=get_ts, reverse=False)
                    for item in sensor_data_list:
                        update_state(item)
                        
                    # Сохраняем фоновый импорт в долгосрочную статистику HA
                    if self._sensor_key not in ["power_mode", "battery"]:
                        hourly_buckets = {}
                        for item in sensor_data_list:
                            if self._sensor_key in item:
                                val_info = item[self._sensor_key]
                                if val_info.get("status") == 0:
                                    val = val_info.get("value")
                                    ts_info = item.get("timestamp", {})
                                    ts = ts_info.get("value", 0) if isinstance(ts_info, dict) else int(item.get("timestamp", 0))
                                    
                                    if val is not None and ts > 0:
                                        hour_ts = ts - (ts % 3600)
                                        hourly_buckets.setdefault(hour_ts, []).append(float(val))
                        
                        if hourly_buckets:
                            statistics = []
                            for hour_ts in sorted(hourly_buckets):
                                values = hourly_buckets[hour_ts]
                                mean_val = sum(values) / len(values)
                                if self._sensor_key in ["temperature", "humidity"]:
                                    mean_val = round(mean_val, 1)
                                    
                                statistics.append(StatisticData(
                                    start=datetime.fromtimestamp(hour_ts, tz=timezone.utc),
                                    state=mean_val,
                                    mean=mean_val
                                ))
                            
                            unit_converter = UNIT_CONVERTERS.get(self._attr_device_class)
                            unit_class = (
                                unit_converter.UNIT_CLASS if unit_converter else None
                            )
                            metadata = StatisticMetaData(
                                has_mean=True,
                                mean_type=StatisticMeanType.ARITHMETIC,
                                has_sum=False,
                                name=f"Qingping CGS2 {self._sensor_key.upper()}",
                                source=DOMAIN,
                                statistic_id=f"{DOMAIN}:{self._mac.lower()}_{self._sensor_key}",
                                unit_class=unit_class,
                                unit_of_measurement=self._attr_native_unit_of_measurement,
                            )
                            try:
                                async_add_external_statistics(self.hass, metadata, statistics)
                            except Exception as err:
                                _LOGGER.error("Statistics import error: %s", err)

            except Exception as e:
                _LOGGER.error("MQTT CGS2 Error: %s", e)

        self.async_on_remove(
            await async_subscribe(self.hass, topic, message_received)
        )
