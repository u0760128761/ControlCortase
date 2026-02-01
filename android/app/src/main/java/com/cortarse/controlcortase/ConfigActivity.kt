package com.cortarse.controlcortase

import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONArray
import org.json.JSONObject

class ConfigActivity : AppCompatActivity() {

    private lateinit var llDeviceContainer: LinearLayout
    private lateinit var btnAddDevice: Button
    private lateinit var btnSaveConfig: Button
    
    private var currentScanningCard: View? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_config)

        initViews()
        setupHeader()
        fetchCurrentConfig()
    }

    private fun initViews() {
        llDeviceContainer = findViewById(R.id.llDeviceContainer)
        btnAddDevice = findViewById(R.id.btnAddDevice)
        btnSaveConfig = findViewById(R.id.btnSaveConfig)

        btnAddDevice.setOnClickListener { showAddDeviceDialog() }
        btnSaveConfig.setOnClickListener { saveConfig() }
    }

    private fun setupHeader() {
        val header = findViewById<View>(R.id.layoutHeader)
        val tvStatus = header.findViewById<TextView>(R.id.headerTvStatus)
        val tvDeviceName = header.findViewById<TextView>(R.id.headerTvDeviceName)
        val tvDeviceAddress = header.findViewById<TextView>(R.id.headerTvDeviceAddress)
        
        tvStatus.text = getString(R.string.status_connected)
        BluetoothManager.lastDevice?.let { device ->
            tvDeviceName.visibility = View.VISIBLE
            tvDeviceAddress.visibility = View.VISIBLE
            tvDeviceName.text = getString(R.string.label_device_name, device.name ?: "Unknown")
            tvDeviceAddress.text = getString(R.string.label_device_address, device.address)
        }
        
        header.findViewById<View>(R.id.headerBtnLanguage).visibility = View.GONE
        header.findViewById<View>(R.id.headerBtnScan).visibility = View.GONE
        header.findViewById<View>(R.id.headerBtnAdmin).visibility = View.GONE
    }

    private fun fetchCurrentConfig() {
        BluetoothManager.sendCommand("GET_CONFIG")
        BluetoothManager.onDataReceived = { data ->
            runOnUiThread {
                try {
                    val json = JSONObject(data)
                    if (json.has("devices")) {
                        llDeviceContainer.removeAllViews()
                        val devices = json.getJSONArray("devices")
                        for (i in 0 until devices.length()) {
                            addDeviceToUI(devices.getJSONObject(i))
                        }
                    } else if (json.optString("status") == "success" && json.has("results")) {
                        // Scan result
                        val results = json.getJSONArray("results")
                        if (results.length() > 0) {
                            val first = results.getJSONObject(0)
                            currentScanningCard?.let { card ->
                                card.findViewById<EditText>(R.id.etPinTrig).setText(first.getInt("trigger").toString())
                                card.findViewById<EditText>(R.id.etPinEcho).setText(first.getInt("echo").toString())
                                Toast.makeText(this, "Scan complete!", Toast.LENGTH_SHORT).show()
                            }
                        } else {
                            Toast.makeText(this, "No sensors found", Toast.LENGTH_SHORT).show()
                        }
                    }
                } catch (e: Exception) {}
            }
        }
    }

    private fun addDeviceToUI(dev: JSONObject) {
        val inflater = LayoutInflater.from(this)
        val card = inflater.inflate(R.layout.item_device_config, llDeviceContainer, false)
        
        val etName = card.findViewById<EditText>(R.id.etDeviceName)
        val btnDelete = card.findViewById<ImageButton>(R.id.btnDeleteDevice)
        val pinsContainer = card.findViewById<LinearLayout>(R.id.llPinsContainer)
        val tvRole = card.findViewById<TextView>(R.id.tvRole)

        val id = dev.optString("id")
        val type = dev.optString("type")
        val name = dev.optString("name")
        val role = dev.optString("role")
        val pins = dev.optJSONObject("pins") ?: JSONObject()

        etName.setText(name)
        card.tag = dev // Store full metadata

        if (role.isNotEmpty()) {
            tvRole.text = "Role: $role"
            tvRole.visibility = View.VISIBLE
        }

        if (type == "motor") {
            val pinsView = inflater.inflate(R.layout.item_pins_motor, pinsContainer, true)
            pinsView.findViewById<EditText>(R.id.etPinFwd).setText(pins.optInt("forward").toString())
            pinsView.findViewById<EditText>(R.id.etPinBwd).setText(pins.optInt("backward").toString())
            pinsView.findViewById<EditText>(R.id.etPinSpd).setText(pins.optInt("enable").toString())
        } else if (type == "hcsr04") {
            val pinsView = inflater.inflate(R.layout.item_pins_hcsr04, pinsContainer, true)
            pinsView.findViewById<EditText>(R.id.etPinTrig).setText(pins.optInt("trigger").toString())
            pinsView.findViewById<EditText>(R.id.etPinEcho).setText(pins.optInt("echo").toString())
            
            pinsView.findViewById<Button>(R.id.btnScanSensor).setOnClickListener {
                currentScanningCard = card
                BluetoothManager.sendCommand("SCAN_CONFIG")
                Toast.makeText(this, "Scanning...", Toast.LENGTH_SHORT).show()
            }
        }

        btnDelete.setOnClickListener { llDeviceContainer.removeView(card) }
        llDeviceContainer.addView(card)
    }

    private fun showAddDeviceDialog() {
        val options = arrayOf("New Motor", "New HC-SR04 Sensor")
        AlertDialog.Builder(this)
            .setTitle("Add Peripheral")
            .setItems(options) { _, which ->
                val type = if (which == 0) "motor" else "hcsr04"
                val dev = JSONObject()
                dev.put("id", "dev_" + System.currentTimeMillis() % 10000)
                dev.put("type", type)
                dev.put("name", if (which == 0) "New Motor" else "New Sensor")
                dev.put("pins", JSONObject())
                addDeviceToUI(dev)
            }
            .show()
    }

    private fun saveConfig() {
        try {
            val devicesArr = JSONArray()
            for (i in 0 until llDeviceContainer.childCount) {
                val card = llDeviceContainer.getChildAt(i)
                val meta = card.tag as JSONObject
                
                val devJson = JSONObject()
                devJson.put("id", meta.getString("id"))
                devJson.put("type", meta.getString("type"))
                devJson.put("name", card.findViewById<EditText>(R.id.etDeviceName).text.toString())
                if (meta.has("role")) devJson.put("role", meta.getString("role"))

                val pins = JSONObject()
                if (devJson.getString("type") == "motor") {
                    val pContainer = card.findViewById<ViewGroup>(R.id.llPinsContainer)
                    pins.put("forward", pContainer.findViewById<EditText>(R.id.etPinFwd).text.toString().toInt())
                    pins.put("backward", pContainer.findViewById<EditText>(R.id.etPinBwd).text.toString().toInt())
                    pins.put("enable", pContainer.findViewById<EditText>(R.id.etPinSpd).text.toString().toInt())
                } else if (devJson.getString("type") == "hcsr04") {
                    val pContainer = card.findViewById<ViewGroup>(R.id.llPinsContainer)
                    pins.put("trigger", pContainer.findViewById<EditText>(R.id.etPinTrig).text.toString().toInt())
                    pins.put("echo", pContainer.findViewById<EditText>(R.id.etPinEcho).text.toString().toInt())
                }
                devJson.put("pins", pins)
                devicesArr.put(devJson)
            }

            val config = JSONObject()
            config.put("devices", devicesArr)

            BluetoothManager.sendCommand("SAVE_CONFIG:${config.toString()}")
            Toast.makeText(this, R.string.msg_config_saved, Toast.LENGTH_SHORT).show()
            finish()
        } catch (e: Exception) {
            Toast.makeText(this, "Check all fields are numbers", Toast.LENGTH_SHORT).show()
        }
    }
}
