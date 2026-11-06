import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import (
    CONF_MAC,
    CONF_REALTIME_INTERVAL,
    CONF_USE_HISTORY,
    DEFAULT_REALTIME_INTERVAL,
    DOMAIN,
)

class QingpingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Настройка интеграции через UI."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            # Очищаем MAC от двоеточий/дефисов и переводим в верхний регистр
            mac = user_input[CONF_MAC].strip().upper().replace(":", "").replace("-", "")
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Air Monitor ({mac})", 
                data={CONF_MAC: mac},
                options={
                    CONF_USE_HISTORY: False,
                    CONF_REALTIME_INTERVAL: DEFAULT_REALTIME_INTERVAL,
                }
            )

        # Рисуем форму установки
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_MAC, default="582D34FFFFFF"): str,
            })
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return QingpingOptionsFlowHandler()

class QingpingOptionsFlowHandler(config_entries.OptionsFlow):
    """Меню настроек после установки."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        use_history = self.config_entry.options.get(CONF_USE_HISTORY, False)
        realtime_interval = self.config_entry.options.get(
            CONF_REALTIME_INTERVAL, DEFAULT_REALTIME_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_REALTIME_INTERVAL, default=realtime_interval
                ): vol.All(
                    vol.Coerce(int),
                    vol.Any(0, vol.Range(min=3, max=3600)),
                ),
                vol.Optional(CONF_USE_HISTORY, default=use_history): bool,
            })
        )
