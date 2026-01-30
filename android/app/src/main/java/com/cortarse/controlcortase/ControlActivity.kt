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

    // Motor 1 Buttons
    private lateinit var btnM1Fwd: Button
    private lateinit var btnM1Back: Button
    private lateinit var btnM1Stop: Button

    // Motor 2 Buttons
    private lateinit var btnM2Fwd: Button
    private lateinit var btnM2Back: Button
    private lateinit var btnM2Stop: Button

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

        btnM1Fwd = findViewById(R.id.btnM1Fwd)
        btnM1Back = findViewById(R.id.btnM1Back)
        btnM1Stop = findViewById(R.id.btnM1Stop)

        btnM2Fwd = findViewById(R.id.btnM2Fwd)
        btnM2Back = findViewById(R.id.btnM2Back)
        btnM2Stop = findViewById(R.id.btnM2Stop)
    }

    private fun setupListeners() {
        btnDisconnect.setOnClickListener {
            BluetoothManager.close()
            finish()
        }

        // Motor 1
        btnM1Fwd.setOnClickListener { sendCommand("M1_FORWARD") }
        btnM1Back.setOnClickListener { sendCommand("M1_BACKWARD") }
        btnM1Stop.setOnClickListener { sendCommand("M1_STOP") }

        // Motor 2
        btnM2Fwd.setOnClickListener { sendCommand("M2_FORWARD") }
        btnM2Back.setOnClickListener { sendCommand("M2_BACKWARD") }
        btnM2Stop.setOnClickListener { sendCommand("M2_STOP") }

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
