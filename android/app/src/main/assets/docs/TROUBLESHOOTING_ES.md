# Solución de Problemas (Troubleshooting)

## Error: `_bluetooth.error: no advertisable device`

Este error ocurre en Raspberry Pi (Linux) al usar la biblioteca `pybluez` si el servicio Bluetooth no se ejecuta en modo de compatibilidad.

### Solución

Es necesario habilitar el "Modo de compatibilidad" (Compatibility Mode) para el demonio Bluetooth en tu Raspberry Pi.

1.  **Abre el archivo de configuración del servicio Bluetooth:**
    ```bash
    sudo nano /etc/systemd/system/dbus-org.bluez.service
    ```
    *(Si el archivo está vacío o no existe, intenta: `/lib/systemd/system/bluetooth.service`)*

2.  **Busca la línea que comienza con `ExecStart`:**
    Generalmente se ve así:
    ```ini
    ExecStart=/usr/lib/bluetooth/bluetoothd
    ```

3.  **Modifícala agregando la bandera `-C`:**
    ```ini
    ExecStart=/usr/lib/bluetooth/bluetoothd -C
    ```

4.  **Inmediatamente después de esta línea, agrega el comando para registrar el perfil SP (Serial Port):**
    ```ini
    ExecStartPost=/usr/bin/sdptool add SP
    ```

5.  **Guarda el archivo** (`Ctrl+O`, `Enter`) y **sal** (`Ctrl+X`).

6.  **Recarga el servicio Bluetooth:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```

7.  **Comprueba el estado:**
    ```bash
    sudo systemctl status bluetooth
    ```
    Deberías ver la bandera `-C` en el comando de ejecución.

8.  **Añade permisos de usuario (si aún no se ha hecho):**
    ```bash
    sudo usermod -aG bluetooth $USER
    ```
    *(Después de esto, puede que necesites cerrar sesión y volver a entrar, o reiniciar la Pi)*.

### Si esto no ayudó (Solución Avanzada)

Si el error persiste, sigue estos pasos de diagnóstico:

    1.  **Verifica que la bandera `-C` se haya aplicado realmente:**
        Ejecuta:
        ```bash
        ps aux | grep bluetoothd
        ```
        Deberías ver una línea que contenga `/usr/lib/bluetooth/bluetoothd -C` (o `--compat`). Si no aparece, la configuración no se aplicó o se editó el archivo incorrecto.

    2.  **Comprueba los permisos de acceso de SDP:**
        A veces el problema son los permisos del socket de control. Ejecuta:
        ```bash
        sudo chmod 777 /var/run/sdp
        ```
        Luego intenta ejecutar tu script nuevamente.

    3.  **Añade manualmente el perfil SP:**
        Intenta ejecutar el comando manualmente en el terminal antes de iniciar el script:
        ```bash
        sudo sdptool add SP
        ```
        Si devuelve `Failed to connect to SDP server`, el demonio bluetooth aún no está configurado correctamente (ver paso 1).

    4.  **Asegúrate de que el controlador esté activo:**
        ```bash
        sudo hciconfig hci0 up
        sudo hciconfig hci0 piscan
        ```

### 5. Solución permanente para permisos (chmod)

Si `sudo chmod 777 /var/run/sdp` ayuda pero el problema regresa tras reiniciar, configura los cambios automáticos de permisos:

1.  Abre el editor del servicio:
    ```bash
    sudo systemctl edit bluetooth
    ```
2.  Añade estas líneas:
    ```ini
    [Service]
    ExecStartPost=/usr/bin/sdptool add SP
    ExecStartPost=/bin/chmod 666 /var/run/sdp
    ```
3.  Guarda y reinicia:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```

### 6. Si aparece "Unit bluetooth.service has a bad unit file setting"

Si el servicio falla al iniciar tras editarlo con el mensaje `bad unit file setting`:

1.  **Revierte los cambios:**
    ```bash
    sudo systemctl revert bluetooth
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```
    Esto borra el archivo `override.conf` creado y devuelve el servicio a los valores predeterminados. Puede que necesites volver a añadir la bandera `-C` al archivo principal.

2.  **Alternativa simple de inicio automático (en lugar de systemd):**
    Si `systemctl edit` causa errores, usa `crontab` para aplicar los permisos al arranque.
    
    Ejecuta:
    ```bash
    sudo crontab -e
    ```
    Añade al final:
    ```bash
    @reboot sleep 10 && chmod 777 /var/run/sdp && sdptool add SP
    ```
    Este es el método de respaldo más seguro.
