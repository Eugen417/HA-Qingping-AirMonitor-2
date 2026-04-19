import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_MAC

class QingpingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Настройка интеграции через UI."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            # Очищаем MAC от двоеточий и переводим в верхний регистр
            mac = user_input[CONF_MAC].upper().replace(":", "")
            return self.async_create_entry(title=f"Air Monitor ({mac})", data={CONF_MAC: mac})

        # Рисуем форму
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_MAC, default="582D34FFFFFF"): str,
            })
        )
