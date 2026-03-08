# Troubleshooting

## Error: `_bluetooth.error: no advertisable device`

This error occurs on Raspberry Pi (Linux) when using the `pybluez` library if the Bluetooth service is not running in compatibility mode.

### Solution

You need to enable "Compatibility Mode" for the Bluetooth daemon on your Raspberry Pi.

1.  **Open the Bluetooth service configuration file:**
    ```bash
    sudo nano /etc/systemd/system/dbus-org.bluez.service
    ```
    *(If the file is empty or missing, try: `/lib/systemd/system/bluetooth.service`)*

2.  **Find the line starting with `ExecStart`:**
    It usually looks like this:
    ```ini
    ExecStart=/usr/lib/bluetooth/bluetoothd
    ```

3.  **Modify it by adding the `-C` flag:**
    ```ini
    ExecStart=/usr/lib/bluetooth/bluetoothd -C
    ```

4.  **Right after this line, add the command to register the SP (Serial Port) profile:**
    ```ini
    ExecStartPost=/usr/bin/sdptool add SP
    ```

5.  **Save the file** (`Ctrl+O`, `Enter`) and **exit** (`Ctrl+X`).

6.  **Reload the Bluetooth service:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```

7.  **Check status:**
    ```bash
    sudo systemctl status bluetooth
    ```
    You should see the `-C` flag in the start command.

8.  **Add user permissions (if not done yet):**
    ```bash
    sudo usermod -aG bluetooth $USER
    ```
    *(You may need to log out and log back in, or reboot the Pi)*.

### If this didn't help (Advanced Solution)

If the error persists, follow these diagnostic steps:

    1.  **Verify that the `-C` flag was actually applied:**
        Run:
        ```bash
        ps aux | grep bluetoothd
        ```
        You should see a line containing `/usr/lib/bluetooth/bluetoothd -C` (or `--compat`). If not, the config wasn't applied or you edited the wrong file.

    2.  **Check SDP access permissions:**
        Sometimes the issue is permissions to the control socket. Run:
        ```bash
        sudo chmod 777 /var/run/sdp
        ```
        Then try running your script again.

    3.  **Manually add the SP profile:**
        Try running the command manually in the terminal before starting the script:
        ```bash
        sudo sdptool add SP
        ```
        If it outputs `Failed to connect to SDP server`, the bluetooth daemon is still not configured correctly (see step 1).

    4.  **Make sure the controller is up:**
        ```bash
        sudo hciconfig hci0 up
        sudo hciconfig hci0 piscan
        ```

### 5. Permanent solution for permissions (chmod)

If `sudo chmod 777 /var/run/sdp` helps but the problem returns after reboot, set up automatic permission changes:

1.  Open the service override editor:
    ```bash
    sudo systemctl edit bluetooth
    ```
2.  Add these lines:
    ```ini
    [Service]
    ExecStartPost=/usr/bin/sdptool add SP
    ExecStartPost=/bin/chmod 666 /var/run/sdp
    ```
3.  Save and restart:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```

### 6. If "Unit bluetooth.service has a bad unit file setting"

If the service fails to start after editing with `bad unit file setting`:

1.  **Revert changes:**
    ```bash
    sudo systemctl revert bluetooth
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
    ```
    This deletes the created `override.conf` and returns the service to defaults. You might need to re-add the `-C` flag to the main config.

2.  **Simple autostart alternative (instead of systemd):**
    If `systemctl edit` raises errors, use `crontab` to apply permissions on boot.
    
    Run:
    ```bash
    sudo crontab -e
    ```
    Append at the end:
    ```bash
    @reboot sleep 10 && chmod 777 /var/run/sdp && sdptool add SP
    ```
    This is the most reliable fallback method.
