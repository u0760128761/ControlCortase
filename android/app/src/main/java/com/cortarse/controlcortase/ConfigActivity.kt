package com.cortarse.controlcortase

import android.content.Context
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject

class ConfigActivity : AppCompatActivity() {

    private lateinit var etM1Fwd: EditText
    private lateinit var etM1Bwd: EditText
    private lateinit var etM1En: EditText
    private lateinit var etM2Fwd: EditText
    private lateinit var etM2Bwd: EditText
    private lateinit var etM2En: EditText
    private lateinit var etSTrig: EditText
    private lateinit var etSEcho: EditText
    private lateinit var btnScanSensor: Button
    private lateinit var btnSaveConfig: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_config)

        initViews()
        setupHeader()
        fetchCurrentConfig()
    }

    private fun initViews() {
        etM1Fwd = findViewById(R.id.et_m1_fwd)
        etM1Bwd = findViewById(R.id.et_m1_bwd)
        etM1En = findViewById(R.id.et_m1_en)
        etM2Fwd = findViewById(R.id.et_m2_fwd)
        etM2Bwd = findViewById(R.id.et_m2_bwd)
        etM2En = findViewById(R.id.et_m2_en)
        etSTrig = findViewById(R.id.et_s_trig)
        etSEcho = findViewById(R.id.et_s_echo)
        btnScanSensor = findViewById(R.id.btnScanSensor)
        btnSaveConfig = findViewById(R.id.btnSaveConfig)

        btnScanSensor.setOnClickListener { scanSensor() }
        btnSaveConfig.setOnClickListener { saveConfig() }
    }

    private fun setupHeader() {
        val header = findViewById<View>(R.id.layoutHeader)
        val tvStatus = header.findViewById<android.widget.TextView>(R.id.headerTvStatus)
        val tvDeviceName = header.findViewById<android.widget.TextView>(R.id.headerTvDeviceName)
        val tvDeviceAddress = header.findViewById<android.widget.TextView>(R.id.headerTvDeviceAddress)
        
        tvStatus.text = getString(R.string.status_connected)
        BluetoothManager.lastDevice?.let { device ->
            tvDeviceName.visibility = View.VISIBLE
            tvDeviceAddress.visibility = View.VISIBLE
            tvDeviceName.text = getString(R.string.label_device_name, device.name ?: "Unknown")
            tvDeviceAddress.text = getString(R.string.label_device_address, device.address)
        }
        
        // Ensure header buttons are hidden or disabled
        header.findViewById<View>(R.id.headerBtnLanguage).visibility = View.GONE
        header.findViewById<View>(R.id.headerBtnScan).visibility = View.GONE
        header.findViewById<View>(R.id.headerBtnAdmin).visibility = View.GONE
    }

    private fun fetchCurrentConfig() {
        // Since we are using Bluetooth for commands, we can request config via JSON
        BluetoothManager.sendCommand("GET_CONFIG")
        
        // Setup listener for response
        BluetoothManager.onDataReceived = { data ->
            runOnUiThread {
                try {
                    val json = JSONObject(data)
                    if (json.has("motors")) {
                        val motors = json.getJSONObject("motors")
                        val m1 = motors.getJSONObject("left")
                        val m2 = motors.getJSONObject("right")
                        val s = json.getJSONObject("sensor")

                        etM1Fwd.setText(m1.getInt("forward").toString())
                        etM1Bwd.setText(m1.getInt("backward").toString())
                        etM1En.setText(m1.getInt("enable").toString())
                        
                        etM2Fwd.setText(m2.getInt("forward").toString())
                        etM2Bwd.setText(m2.getInt("backward").toString())
                        etM2En.setText(m2.getInt("enable").toString())

                        etSTrig.setText(s.getInt("trigger").toString())
                        etSEcho.setText(s.getInt("echo").toString())
                    }
                } catch (e: Exception) {
                    // Might be another data packet
                }
            }
        }
    }

    private fun scanSensor() {
        Toast.makeText(this, "Scanning...", Toast.LENGTH_SHORT).show()
        BluetoothManager.sendCommand("SCAN_CONFIG")
    }

    private fun saveConfig() {
        try {
            val config = JSONObject()
            val motors = JSONObject()
            val m1 = JSONObject()
            m1.put("forward", etM1Fwd.text.toString().toInt())
            m1.put("backward", etM1Bwd.text.toString().toInt())
            m1.put("enable", etM1En.text.toString().toInt())
            
            val m2 = JSONObject()
            m2.put("forward", etM2Fwd.text.toString().toInt())
            m2.put("backward", etM2Bwd.text.toString().toInt())
            m2.put("enable", etM2En.text.toString().toInt())
            
            motors.put("left", m1)
            motors.put("right", m2)
            
            val s = JSONObject()
            s.put("trigger", etSTrig.text.toString().toInt())
            s.put("echo", etSEcho.text.toString().toInt())
            
            config.put("motors", motors)
            config.put("sensor", s)

            BluetoothManager.sendCommand("SAVE_CONFIG:${config.toString()}")
            Toast.makeText(this, R.string.msg_config_saved, Toast.LENGTH_SHORT).show()
            finish()
        } catch (e: Exception) {
            Toast.makeText(this, "Check all fields are numbers", Toast.LENGTH_SHORT).show()
        }
    }
}
