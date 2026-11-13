# EWPE HP

[![Validate](https://github.com/keziksdmitrijs-byte/ewpe-hp/actions/workflows/validate.yml/badge.svg)](https://github.com/keziksdmitrijs-byte/ewpe-hp/actions/workflows/validate.yml)

Интеграция Home Assistant для тепловых насосов **GREE Versati** (воздух–вода) через облако **Gree+** (EWPE), то есть тем же путём, что и приложение Gree+. Modbus-адаптер и доступ к насосу по локальной сети не нужны.

*English below.*

> **Статус: первая версия, на реальном насосе ещё не проверена.** Протокол облака и параметры Versati взяты из открытых исследований (см. «Благодарности»). Интеграция проверена на модели облака, брокера и насоса. Если что-то не так на вашем насосе — откройте issue и приложите диагностику интеграции.

## Что умеет

| Сущность | Что делает | Параметр |
|---|---|---|
| Переключатель «Питание» | Включить / выключить насос | `Pow` |
| Выбор «Режим» | Отопление, горячая вода, охлаждение + ГВС, отопление + ГВС, охлаждение | `Mod` |
| Водонагреватель «Бак горячей воды» | Температура бака и её уставка | `WatBoxTem`, `WatBoxTemSet` |
| Числа | Уставки воды отопления (20–60 °C) и охлаждения (5–25 °C), уставки комнаты | `HeWatOutTemSet`, `CoWatOutTemSet`, `HeHomTemSet`, `CoHomTemSet` |
| Переключатели | Тихий режим, быстрый нагрев воды | `Quiet`, `FastHtWter` |
| Выборы | Приоритет при «отопление + ГВС» и «охлаждение + ГВС» | `HetHtWter`, `ColHtWter` |
| Датчики | Вода на выходе и входе, выход теплового насоса, бак, комната, код ошибки | `AllOutWatTem`, `AllInWatTem`, `HepOutWatTem`, `WatBoxTem`, `RmoHomTem`, `AllErr` |
| Двоичные датчики | ТЭН бака, электронагреватели 1 и 2, защита от замерзания, наличие ошибки | `WatBoxElcHeRunSta`, `ElcHe1RunSta`, `ElcHe2RunSta`, `AnFrzzRunSta`, `SyAnFroRunSta` |

**Кондиционеры GREE** из того же аккаунта Gree+ появляются как климатические устройства: выкл / авто / охлаждение / осушение / вентиляция / обогрев, температура 16–30 °C, скорость вентилятора (авто и пять ступеней), качание жалюзи, а также переключатели «Тихий режим», «Просушка (X-Fan)», «Свежий воздух», «Подсветка панели», «Турбо», «Ионизация». Насос это или кондиционер, интеграция определяет сама по первому ответу устройства.

Сущности создаются только для тех параметров, которые насос действительно сообщает; датчик, которого нет (например, комнатный — он показывает −30 °C), не появляется.

Насос опрашивается каждые 30 секунд. Изменения, о которых насос сообщает сам (через MQTT), видны сразу.

## Установка

1. HACS → Integrations → ⋮ → Custom repositories → `https://github.com/keziksdmitrijs-byte/ewpe-hp`, категория Integration.
2. Установите **EWPE HP** и перезапустите Home Assistant.
3. Настройки → Устройства и службы → Добавить интеграцию → **EWPE HP**.
4. Выберите регион (тот же, что в приложении Gree+; для Латвии — Европа), введите почту и пароль аккаунта Gree+.

Все насосы аккаунта появятся как устройства.

## Важно знать

- **Пароль не сохраняется.** Хранится только хеш, которым облако Gree+ проверяет вход. Если облако перестанет его принимать, Home Assistant попросит войти снова.
- **Смена режима.** Контроллер Versati меняет режим только при выключенном насосе. Если насос отказался, выключите его, смените режим и включите снова.
- **Уставка воды.** Насос принимает уставку воды, только когда управляет по температуре воды и погодозависимая кривая выключена. Иначе контроллер сам рассчитывает уставку и игнорирует запись.
- **Связь с облаком.** Модули Wi-Fi версии 3.2 и новее работают через MQTT-брокер Gree, старые — через свой шлюз в облаке. Интеграция выбирает путь по версии модуля и пробует другой, если насос не ответил. Сертификаты Gree выданы её собственным центром, поэтому, как и приложение, интеграция их не проверяет.
- Нужен интернет: без облака Gree+ насос недоступен.

## Благодарности

Протокол облака Gree+ описан в [luc10/gree-api-client](https://github.com/luc10/gree-api-client) и [davo22/homeassistant-gree-cloud](https://github.com/davo22/homeassistant-gree-cloud), параметры Versati — в [tomikaa87/gree-remote](https://github.com/tomikaa87/gree-remote) и [sarunasr/ha-gree-versati3](https://github.com/sarunasr/ha-gree-versati3). Код этой интеграции написан заново.

Проект не связан с GREE Electric Appliances и не одобрен ею. GREE, Versati и Gree+ — товарные знаки их владельцев.

---

## English

Home Assistant integration for **GREE Versati** air-to-water heat pumps through the **Gree+** (EWPE) cloud, the same way the Gree+ app reaches them: no Modbus adapter, no local network access to the unit.

> **Status: first release, not yet tried on a real unit.** The cloud protocol and the Versati parameters come from public research (see Credits); the integration is tested against a model of the cloud, its broker and the unit. If something is off on your unit, open an issue with the integration's diagnostics.

**Entities:** power, mode (heat, hot water, cool + hot water, heat + hot water, cool), the hot water tank as a water heater, heating (20–60 °C) and cooling (5–25 °C) water setpoints, room setpoints, quiet mode, fast hot water, heat/cool + hot water priority, water outlet / inlet / heat pump outlet / tank / room temperatures, error code, electric heaters and frost protection running. **GREE air conditioners** on the same Gree+ account show as climate entities (off / auto / cool / dry / fan / heat, 16–30 °C, auto and five fan speeds, swing) with quiet mode, X-fan, fresh air, panel light, turbo and health switches; whether a unit is a heat pump or an air conditioner is told by its first answer. Only parameters the unit reports get an entity. The unit is polled every 30 s; changes it reports itself over MQTT show at once.

**Install:** add `https://github.com/keziksdmitrijs-byte/ewpe-hp` to HACS as a custom integration repository, install **EWPE HP**, restart, then add the integration and sign in with your Gree+ region, email and password.

**Notes**
- The password is not stored, only the hash the Gree+ cloud signs in with.
- The Versati controller changes mode only while the unit is off.
- A water setpoint is taken only when the unit controls by water temperature with the weather curve off.
- Wi-Fi modules from protocol 3.2 on are reached over Gree's MQTT broker, older ones through their cloud gateway; the other way is tried when a unit stays silent. Gree's certificates come from its own CA and are not verified, as in the app.

**Credits:** the Gree+ cloud protocol from [luc10/gree-api-client](https://github.com/luc10/gree-api-client) and [davo22/homeassistant-gree-cloud](https://github.com/davo22/homeassistant-gree-cloud); Versati parameters from [tomikaa87/gree-remote](https://github.com/tomikaa87/gree-remote) and [sarunasr/ha-gree-versati3](https://github.com/sarunasr/ha-gree-versati3). This integration's code is written from scratch.

Not affiliated with or endorsed by GREE Electric Appliances. GREE, Versati and Gree+ are trademarks of their owners.

License: MIT.
