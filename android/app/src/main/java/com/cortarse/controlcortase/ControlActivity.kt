package com.cortarse.controlcortase

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

    private lateinit var tvStatus: TextView
    private lateinit var btnDisconnect: Button
    private lateinit var tvLog: TextView
    private lateinit var seekBarSpeed: SeekBar
    private lateinit var tvSpeed: TextView

    // D-Pad Buttons
    private lateinit var btnForward: Button
    private lateinit var btnBackward: Button
    private lateinit var btnLeft: Button
    private lateinit var btnRight: Button
    private lateinit var btnStop: Button

    // Admin
    private lateinit var btnUpdate: Button
    private lateinit var btnRestart: Button
    private lateinit var rebootOverlay: View

    private var isUpdating = false
    private var updateLogBuilder = StringBuilder()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_control)

        initViews()
        setupListeners()

        updateLog("Control Activity Started")
        tvStatus.text = getString(R.string.status_connected)

        BluetoothManager.onConnectionFailed = {
            runOnUiThread {
                if (!rebootOverlay.isVisible) {
                    tvStatus.text = getString(R.string.status_disconnected)
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
        tvStatus = findViewById(R.id.tvStatus)
        btnDisconnect = findViewById(R.id.btnDisconnect)
        tvLog = findViewById(R.id.tvLog)
        seekBarSpeed = findViewById(R.id.seekBarSpeed)
        tvSpeed = findViewById(R.id.tvSpeed)

        btnForward = findViewById(R.id.btnForward)
        btnBackward = findViewById(R.id.btnBackward)
        btnLeft = findViewById(R.id.btnLeft)
        btnRight = findViewById(R.id.btnRight)
        btnStop = findViewById(R.id.btnStop)

        btnUpdate = findViewById(R.id.btnUpdate)
        btnRestart = findViewById(R.id.btnRestart)
        rebootOverlay = findViewById(R.id.rebootOverlay)
    }

    private fun setupListeners() {
        btnDisconnect.setOnClickListener {
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

        // Speed
        seekBarSpeed.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(
                seekBar: SeekBar?,
                progress: Int,
                fromUser: Boolean
            ) {
                tvSpeed.text = "Speed: $progress%"
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
                    tvStatus.text = getString(R.string.status_connected)
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
        BluetoothManager.close()
    }
}
