# Журнал изменений (CHANGELOG)

## [2026-01-29]

### Добавлено
- Установлена иконка приложения из пользовательского изображения (`uploaded_media_1769707147594.jpg`).
    - Созданы ресурсы: `ic_launcher_background.xml` (белый фон), `ic_launcher_foreground_scaled.xml` (масштабированное изображение), `ic_launcher.xml`, `ic_launcher_round.xml`.
- Исправлена ошибка AAPT `resource xml/data_extraction_rules not found`.
    - Созданы файлы `res/xml/data_extraction_rules.xml` и `res/xml/backup_rules.xml`.
- Исправлена ошибка AAPT `resource mipmap/ic_launcher not found`.
    - Создана директория `mipmap-anydpi-v26` и соответствующие XML файлы.
- Обновлена версия Java в `app/build.gradle`.
    - `sourceCompatibility`, `targetCompatibility` и `jvmTarget` обновлены до версии 17 (исправление предупреждений об устаревшей версии 8).
- Создана структура документации.
    - Директория `Docs/`.
    - Файл правил `Docs/RULES.md`.
    - Этот файл журнала `Docs/CHANGELOG.md`.
- Редизайн интерфейса (согласно плану).
    - Цветовая палитра: Gray-Brown (фон), Sand (плитки), Green (кнопки).
    - Обновлены макеты `activity_main.xml` и `activity_control.xml` (использованы `CardView`, увеличены размеры кнопок).
    - Создан макет элемента списка `item_device.xml`.
    - Обновлен `MainActivity.kt` для использования нового макета списка.
- Реализация многоязычности (Правила 5, 7, 8).
    - Добавлены ресурсы строк для Русского (`values-ru`) и Испанского (`values-es`).
    - В `activity_main.xml` добавлены кнопки переключения языка и документации.
    - В `MainActivity.kt` реализована логика переключения языка (EN -> RU -> ES) с перезапуском активити.
- Исправление ошибок.
    - Исправлен вылет приложения при нажатии "Scan Devices" (`ClassCastException` в `ArrayAdapter`). Явно указан `android.R.id.text1` для отображения текста в `item_device.xml`.
- Обновление UI.
    - Кнопки переключения языка и документации заменены на иконки.
    - Язык: Флаг страны текущего языка (США, Россия, Испания).
    - Документация: Иконка вопроса (?).
    - Созданы векторные ресурсы флагов и иконки помощи.
- Документация.
    - Создан файл `Docs/TROUBLESHOOTING.md` с инструкцией по исправлению ошибки `no advertisable device`.
    - Добавлены расширенные шаги диагностики (проверка флага `-C`, проверка прав доступа и manual SDP add).
