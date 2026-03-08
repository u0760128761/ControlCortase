# Устранение неполадок (Troubleshooting)

## Ошибка: `_bluetooth.error: no advertisable device`

Эта ошибка возникает на Raspberry Pi (Linux) при использовании библиотеки `pybluez`, если служба Bluetooth не запущена в режиме совместимости.

### Решение

Вам нужно включить "Compatibility Mode" для демона Bluetooth на вашем Raspberry Pi.

1.  **Откройте файл конфигурации службы Bluetooth:**
    ```bash
    sudo nano /etc/systemd/system/dbus-org.bluez.service
    ```
    *(Если файл пустой или не существует, попробуйте: `/lib/systemd/system/bluetooth.service`)*

2.  **Найдите строку, начинающуюся с `ExecStart`:**
    Обычно она выглядит так:
    ```ini
    ExecStart=/usr/lib/bluetooth/bluetoothd
    ```

3.  **Измените её, добавив флаг `-C`:**
    ```ini
    ExecStart=/usr/lib/bluetooth/bluetoothd -C
    ```

4.  **Сразу после этой строки добавьте команду для добавления профиля SP (Serial Port):**
    ```ini
    ExecStartPost=/usr/bin/sdptool add SP
    ```

5.  **Сохраните файл** (`Ctrl+O`, `Enter`) и **выдите** (`Ctrl+X`).

6.  **Перезагрузите службу Bluetooth:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```

7.  **Проверьте статус:**
    ```bash
    sudo systemctl status bluetooth
    ```
    Вы должны увидеть флаг `-C` в строке запуска.

8.  **Добавьте права пользователю (если еще не сделано):**
    ```bash
    sudo usermod -aG bluetooth $USER
    ```
    *(После этого нужно перезайти в систему или перезагрузить Pi)*.

### Если это не помогло (Расширенное решение)

Если ошибка сохраняется, выполните следующие шаги для диагностики:

1.  **Проверьте, что флаг `-C` действительно применился:**
    Выполните команду:
    ```bash
    ps aux | grep bluetoothd
    ```
    Вы должны увидеть строку, содержащую `/usr/lib/bluetooth/bluetoothd -C` (или `--compat`). Если флага нет, значит конфиг не применился или вы отредактировали не тот файл.

2.  **Проверьте права доступа к SDP:**
    Иногда проблема в правах доступа к сокету управления. Выполните:
    ```bash
    sudo chmod 777 /var/run/sdp
    ```
    Затем попробуйте запустить скрипт снова.

3.  **Вручную добавьте профиль SP:**
    Попробуйте выполнить команду вручную в терминале перед запуском скрипта:
    ```bash
    sudo sdptool add SP
    ```
    Если она выдает ошибку `Failed to connect to SDP server`, значит демон bluetooth всё еще не настроен правильно (см. пункт 1).

4.  **Убедитесь, что контроллер включен:**
    ```bash
    sudo hciconfig hci0 up
    sudo hciconfig hci0 piscan
    ```

### 5. Постоянное решение проблемы с правами (chmod)

Если команда `sudo chmod 777 /var/run/sdp` помогает, но проблема возвращается после перезагрузки, настройте автоматическое изменение прав:

1.  Откройте редактор конфигурации службы:
    ```bash
    sudo systemctl edit bluetooth
    ```
2.  Добавьте эти строки:
    ```ini
    [Service]
    ExecStartPost=/usr/bin/sdptool add SP
    ExecStartPost=/bin/chmod 666 /var/run/sdp
    ```
3.  Сохраните и перезагрузите:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```

### 6. Если "Unit bluetooth.service has a bad unit file setting"

Если после редактирования службы она перестала запускаться с ошибкой `bad unit file setting`:

1.  **Отмените изменения (Revert):**
    ```bash
    sudo systemctl revert bluetooth
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```
    Это удалит созданный файл `override.conf` и вернет службу к стандартным настройкам (но вам, возможно, придется заново добавить флаг `-C` в основной файл, если он тоже сбросился).

2.  **Простой способ автозапуска (вместо systemd):**
    Если `systemctl edit` вызывает ошибки, используйте `crontab` для установки прав при загрузке.
    
    Выполните:
    ```bash
    sudo crontab -e
    ```
    Добавьте в конец файла:
    ```bash
    @reboot sleep 10 && chmod 777 /var/run/sdp && sdptool add SP
    ```
    Это самый надежный и простой способ закрепить результат.
