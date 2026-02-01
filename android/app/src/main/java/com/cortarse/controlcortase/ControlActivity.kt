package com.cortarse.controlcortase

import android.content.Context
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ControlActivity : AppCompatActivity() {

    private lateinit var tvLog: TextView
    private lateinit var seekBarSpeed: SeekBar
    private lateinit var tvSpeed: TextView
    private lateinit var tvDeviceName: TextView
    private lateinit var tvDeviceAddress: TextView
    private lateinit var btnLanguageHeader: android.widget.ImageButton
    private lateinit var btnScanHeader: android.widget.ImageButton
    private lateinit var tvStatusHeader: android.widget.TextView
    private lateinit var containerStatusHeader: android.view.View

    // D-Pad Buttons
    private lateinit var btnForward: Button
    private lateinit var btnBackward: Button
    private lateinit var btnLeft: Button
    private lateinit var btnRight: Button
    private lateinit var btnStop: Button

    // Admin
    private lateinit var btnUpdate: Button
    private lateinit var btnRestart: Button
    private lateinit var btnDisconnect: Button
    private lateinit var rebootOverlay: View

    private var isUpdating = false
    private var isChangingLanguage = false
    private var updateLogBuilder = StringBuilder()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_control)

        initViews()
        setupListeners()

        updateLog("Control Activity Started")
        tvStatusHeader.text = getString(R.string.status_connected)

        BluetoothManager.onConnectionFailed = {
            runOnUiThread {
                if (!rebootOverlay.isVisible) {
                    tvStatusHeader.text = getString(R.string.status_disconnected)
                    updateLanguageIcon() // Ensure header reflects state
                    updateLog("Error: Connection lost")
                    finish()
                }
            }
        }

        // Handle incoming data (logs during update)
        BluetoothManager.onDataReceived = { data ->
            runOnUiThread {
                if (isUpdating) {
                    updateLogBuilder.append(data)
                    updateLog(data.trim())
                    if (data.contains("DONE")) {
                        isUpdating = false
                        updateLog("Update finished")
                    }
                } else if (data.contains("RESTARTING")) {
                    showRebootOverlay()
                }
            }
        }
    }

    private fun initViews() {
        val header = findViewById<View>(R.id.layoutHeader)
        tvStatusHeader = header.findViewById(R.id.headerTvStatus)
        tvDeviceName = header.findViewById(R.id.headerTvDeviceName)
        tvDeviceAddress = header.findViewById(R.id.headerTvDeviceAddress)
        btnLanguageHeader = header.findViewById(R.id.headerBtnLanguage)
        btnScanHeader = header.findViewById(R.id.headerBtnScan)
        containerStatusHeader = header.findViewById(R.id.headerContainerStatus)

        tvLog = findViewById(R.id.tvLog)
        seekBarSpeed = findViewById(R.id.seekBarSpeed)
        tvSpeed = findViewById(R.id.tvSpeed)
        tvSpeed.text = getString(R.string.label_speed, seekBarSpeed.progress)
        updateLanguageIcon()
 
        BluetoothManager.lastDevice?.let { device ->
            tvDeviceName.visibility = View.VISIBLE
            tvDeviceAddress.visibility = View.VISIBLE
            tvDeviceName.text = getString(R.string.label_device_name, device.name ?: "Unknown")
            tvDeviceAddress.text = getString(R.string.label_device_address, device.address)
        }

        btnForward = findViewById(R.id.btnForward)
        btnBackward = findViewById(R.id.btnBackward)
        btnLeft = findViewById(R.id.btnLeft)
        btnRight = findViewById(R.id.btnRight)
        btnStop = findViewById(R.id.btnStop)

        btnUpdate = findViewById(R.id.btnUpdate)
        btnRestart = findViewById(R.id.btnRestart)
        btnDisconnect = findViewById(R.id.btnDisconnect)
        rebootOverlay = findViewById(R.id.rebootOverlay)
    }

    private fun setupListeners() {
        btnLanguageHeader.setOnClickListener { showLanguageMenu() }
        btnScanHeader.setOnClickListener {
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setMessage(R.string.msg_confirm_scan)
                .setPositiveButton(R.string.btn_yes) { _, _ ->
                    BluetoothManager.close()
                    finish()
                }
                .setNegativeButton(R.string.btn_no, null)
                .show()
        }
        containerStatusHeader.setOnClickListener {
            // Tapping "Connected" should disconnect
            BluetoothManager.close()
            finish()
        }

        // D-Pad
        btnForward.setOnClickListener { sendCommand("FORWARD") }
        btnBackward.setOnClickListener { sendCommand("BACKWARD") }
        btnLeft.setOnClickListener { sendCommand("LEFT") }
        btnRight.setOnClickListener { sendCommand("RIGHT") }
        btnStop.setOnClickListener { sendCommand("STOP") }

        // Admin
        btnUpdate.setOnClickListener {
            isUpdating = true
            updateLogBuilder.setLength(0)
            updateLog("Starting deployment...")
            sendCommand("UPDATE")
        }

        btnRestart.setOnClickListener {
            AlertDialog.Builder(this)
                .setTitle(R.string.btn_restart)
                .setMessage(R.string.confirm_restart)
                .setPositiveButton("OK") { _, _ ->
                    sendCommand("RESTART")
                }
                .setNegativeButton("Cancel", null)
                .show()
        }
        
        btnDisconnect.setOnClickListener {
            BluetoothManager.close()
            finish()
        }

        // Speed
        seekBarSpeed.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(
                seekBar: SeekBar?,
                progress: Int,
                fromUser: Boolean
            ) {
                tvSpeed.text = getString(R.string.label_speed, progress)
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}

            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                seekBar?.let {
                    // Map 0-100 to 0-255
                    val pwmValue = (it.progress * 255) / 100
                    sendCommand("SPEED:$pwmValue")
                }
            }
        })
    }

    private fun showRebootOverlay() {
        rebootOverlay.visibility = View.VISIBLE
        updateLog("Rebooting... Auto-reconnect in 20s")
        
        // Wait for system to go down and come up
        Handler(Looper.getMainLooper()).postDelayed({
            startAutoReconnectLoop()
        }, 20000)
    }

    private fun startAutoReconnectLoop() {
        updateLog("Attempting to reconnect...")
        BluetoothManager.reconnect { success ->
            runOnUiThread {
                if (success) {
                    rebootOverlay.visibility = View.GONE
                    updateLog("Reconnected successfully")
                    tvStatusHeader.text = getString(R.string.status_connected)
                } else {
                    // Retry every 5 seconds
                    Handler(Looper.getMainLooper()).postDelayed({
                        startAutoReconnectLoop()
                    }, 5000)
                }
            }
        }
    }

    private fun sendCommand(cmd: String) {
        BluetoothManager.sendCommand(cmd)
        updateLog("Sent: $cmd")
    }

    private fun updateLog(msg: String) {
        val time = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        val currentText = tvLog.text.toString()
        val newText = "[$time] $msg\n$currentText"
        tvLog.text = newText
    }

    override fun onDestroy() {
        super.onDestroy()
        if (!isChangingLanguage) {
            BluetoothManager.close()
        }
    }

    private fun showLanguageMenu() {
        val popup = android.widget.PopupMenu(this, btnLanguageHeader)
        popup.menu.add(0, 0, 0, getString(R.string.lang_en)).setIcon(R.drawable.ic_flag_us)
        popup.menu.add(0, 1, 1, getString(R.string.lang_ru)).setIcon(R.drawable.ic_flag_ru)
        popup.menu.add(0, 2, 2, getString(R.string.lang_es)).setIcon(R.drawable.ic_flag_es)
        
        popup.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                0 -> setLocale("en")
                1 -> setLocale("ru")
                2 -> setLocale("es")
            }
            true
        }
        popup.show()
    }

    private fun updateLanguageIcon() {
        val currentLang = resources.configuration.locales.get(0).language
        val iconRes = when (currentLang) {
            "ru" -> R.drawable.ic_flag_ru
            "es" -> R.drawable.ic_flag_es
            else -> R.drawable.ic_flag_us
        }
        btnLanguageHeader.setImageResource(iconRes)
    }

    private fun setLocale(languageCode: String) {
        val prefs = getSharedPreferences("Settings", Context.MODE_PRIVATE)
        prefs.edit().putString("My_Lang", languageCode).apply()

        val locale = java.util.Locale(languageCode)
        java.util.Locale.setDefault(locale)
        val config = android.content.res.Configuration()
        config.setLocale(locale)
        baseContext.resources.updateConfiguration(config, baseContext.resources.displayMetrics)
        
        isChangingLanguage = true
        val intent = intent
        finish()
        startActivity(intent)
    }
}
