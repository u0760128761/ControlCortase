package com.cortarse.controlcortase

import android.os.Bundle
import android.widget.Button
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_control)

        initViews()
        setupListeners()

        updateLog("Control Activity Started")
        tvStatus.text = getString(R.string.status_connected)

        BluetoothManager.onConnectionFailed = {
            runOnUiThread {
                tvStatus.text = getString(R.string.status_disconnected)
                updateLog("Error: Connection lost")
                finish() // Go back to scan screen
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
