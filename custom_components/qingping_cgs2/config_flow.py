import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_MAC, CONF_USE_HISTORY

class QingpingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Настройка интеграции через UI."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            # Очищаем MAC от двоеточий и переводим в верхний регистр
            mac = user_input[CONF_MAC].upper().replace(":", "")
            return self.async_create_entry(
                title=f"Air Monitor ({mac})", 
                data={CONF_MAC: mac},
                options={CONF_USE_HISTORY: False} # ПО УМОЛЧАНИЮ ВЫКЛЮЧЕНО
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
        return QingpingOptionsFlowHandler(config_entry)

class QingpingOptionsFlowHandler(config_entries.OptionsFlow):
    """Меню настроек после установки."""
    def __init__(self, config_entry):
        # В новых версиях HA config_entry является зарезервированным системным словом.
        # Поэтому мы сохраняем его под именем _config_entry, чтобы избежать конфликта.
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Берем текущее значение
        use_history = self._config_entry.options.get(CONF_USE_HISTORY, False)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_USE_HISTORY, default=use_history): bool,
            })
        )
