package com.cortarse.controlcortase

import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.textfield.TextInputEditText
import org.json.JSONObject

class WiFiActivity : AppCompatActivity() {

    private lateinit var tvCurrentSsid: TextView
    private lateinit var tvCurrentSignal: TextView
    private lateinit var btnDisconnect: Button
    private lateinit var btnScanNetworks: Button
    private lateinit var progressScanning: ProgressBar
    private lateinit var tvScanning: TextView
    private lateinit var tvAvailableNetworks: TextView
    private lateinit var rvAvailableNetworks: RecyclerView
    private lateinit var tvNoNetworks: TextView
    private lateinit var tvSavedNetworks: TextView
    private lateinit var rvSavedNetworks: RecyclerView
    private lateinit var tvDebugInfo: TextView

    private val availableNetworksAdapter: WiFiNetworkAdapter by lazy {
        WiFiNetworkAdapter(availableNetworks, ::onNetworkConnect)
    }
    private val savedNetworksAdapter: WiFiNetworkAdapter by lazy {
        WiFiNetworkAdapter(savedNetworks, ::onNetworkConnect, ::onNetworkLongClick)
    }
    
    private val availableNetworks = mutableListOf<WiFiNetwork>()
    private val savedNetworks = mutableListOf<WiFiNetwork>()
    
    private var statusCheckAttempts = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_wifi)

        initViews()
        setupHeader()
        setupRecyclerViews()
        loadSavedNetworks()
        
        // Delay status check to ensure Bluetooth is ready
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            checkCurrentConnection()
        }, 500)
    }

    private fun initViews() {
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

        tvCurrentSsid = findViewById(R.id.tvCurrentSsid)
        tvCurrentSignal = findViewById(R.id.tvCurrentSignal)
        btnDisconnect = findViewById(R.id.btnDisconnect)
        btnScanNetworks = findViewById(R.id.btnScanNetworks)
        progressScanning = findViewById(R.id.progressScanning)
        tvScanning = findViewById(R.id.tvScanning)
        tvAvailableNetworks = findViewById(R.id.tvAvailableNetworks)
        rvAvailableNetworks = findViewById(R.id.rvAvailableNetworks)
        tvNoNetworks = findViewById(R.id.tvNoNetworks)
        tvSavedNetworks = findViewById(R.id.tvSavedNetworks)
        rvSavedNetworks = findViewById(R.id.rvSavedNetworks)
        tvDebugInfo = findViewById(R.id.tvDebugInfo)

        btnScanNetworks.setOnClickListener { scanNetworks() }
        btnDisconnect.setOnClickListener { disconnectWiFi() }
        
        // Test button to verify Bluetooth communication
        findViewById<Button>(R.id.btnTestConnection).setOnClickListener {
            tvDebugInfo.text = "Debug: Testing BT with GET_CONFIG command..."
            BluetoothManager.onDataReceived = { data ->
                runOnUiThread {
                    tvDebugInfo.text = "Debug: BT works! Received: ${data.take(100)}..."
                    // Now try WIFI_STATUS again
                    android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                        statusCheckAttempts = 0
                        checkCurrentConnection()
                    }, 1000)
                }
            }
            BluetoothManager.sendCommand("GET_CONFIG")
        }
    }

    private fun setupHeader() {
        // Header is already set up in initViews
    }

    private fun setupRecyclerViews() {
        // Available networks
        rvAvailableNetworks.layoutManager = LinearLayoutManager(this)
        rvAvailableNetworks.adapter = availableNetworksAdapter

        // Saved networks
        rvSavedNetworks.layoutManager = LinearLayoutManager(this)
        rvSavedNetworks.adapter = savedNetworksAdapter
    }

    private fun loadSavedNetworks() {
        val savedSsids = WiFiCredentialManager.getSavedNetworks(this)
        savedNetworks.clear()
        savedSsids.forEach { ssid ->
            savedNetworks.add(WiFiNetwork(ssid, 0, "Saved", true))
        }
        savedNetworksAdapter.updateNetworks(savedNetworks)
        
        tvSavedNetworks.visibility = if (savedNetworks.isNotEmpty()) View.VISIBLE else View.GONE
        rvSavedNetworks.visibility = if (savedNetworks.isNotEmpty()) View.VISIBLE else View.GONE
    }

    private fun checkCurrentConnection() {
        statusCheckAttempts++
        tvDebugInfo.text = "Debug: Sending WIFI_STATUS command (attempt $statusCheckAttempts)..."
        
        val startTime = System.currentTimeMillis()
        var responseReceived = false
        
        BluetoothManager.onDataReceived = { data ->
            if (!responseReceived) {
                responseReceived = true
                val elapsed = System.currentTimeMillis() - startTime
                runOnUiThread {
                    tvDebugInfo.text = "Debug: Response received in ${elapsed}ms\nData: $data"
                    
                    try {
                        android.util.Log.d("WiFiActivity", "Received WiFi status: $data")
                        val json = JSONObject(data.trim())
                        
                        if (json.has("connected")) {
                            if (json.getBoolean("connected")) {
                                val ssid = json.optString("ssid", "Unknown")
                                val signal = json.optInt("signal", 0)
                                tvCurrentSsid.text = getString(R.string.wifi_connected_to, ssid)
                                tvCurrentSignal.text = getString(R.string.wifi_signal_strength, "$signal dBm")
                                tvCurrentSignal.visibility = View.VISIBLE
                                btnDisconnect.visibility = View.VISIBLE
                                tvDebugInfo.text = "Debug: Connected to $ssid (${signal}dBm)"
                            } else {
                                tvCurrentSsid.text = getString(R.string.wifi_not_connected)
                                tvCurrentSignal.visibility = View.GONE
                                btnDisconnect.visibility = View.GONE
                                tvDebugInfo.text = "Debug: Not connected (server response: connected=false)"
                            }
                        } else {
                            android.util.Log.w("WiFiActivity", "No 'connected' field in response")
                            tvCurrentSsid.text = getString(R.string.wifi_not_connected)
                            tvCurrentSignal.visibility = View.GONE
                            btnDisconnect.visibility = View.GONE
                            tvDebugInfo.text = "Debug: Invalid response - no 'connected' field\n$data"
                        }
                    } catch (e: Exception) {
                        android.util.Log.e("WiFiActivity", "Error parsing WiFi status: ${e.message}", e)
                        tvCurrentSsid.text = getString(R.string.wifi_not_connected)
                        tvCurrentSignal.visibility = View.GONE
                        btnDisconnect.visibility = View.GONE
                        tvDebugInfo.text = "Debug: Parse error: ${e.message}\nData: $data"
                    }
                }
            }
        }
        
        BluetoothManager.sendCommand("WIFI_STATUS")
        
        // Timeout after 5 seconds
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            if (!responseReceived) {
                tvDebugInfo.text = "Debug: No response after 5s. Retrying..."
                if (statusCheckAttempts < 3) {
                    checkCurrentConnection()
                } else {
                    tvDebugInfo.text = "Debug: Failed after 3 attempts. Check Bluetooth connection."
                    tvCurrentSsid.text = getString(R.string.wifi_not_connected)
                    tvCurrentSignal.visibility = View.GONE
                    btnDisconnect.visibility = View.GONE
                }
            }
        }, 5000)
    }

    private fun scanNetworks() {
        progressScanning.visibility = View.VISIBLE
        tvScanning.visibility = View.VISIBLE
        btnScanNetworks.isEnabled = false
        
        BluetoothManager.sendCommand("WIFI_SCAN")
        BluetoothManager.onDataReceived = { data ->
            runOnUiThread {
                try {
                    val json = JSONObject(data.trim())
                    if (json.has("networks")) {
                        val networksArray = json.getJSONArray("networks")
                        availableNetworks.clear()
                        
                        for (i in 0 until networksArray.length()) {
                            val network = networksArray.getJSONObject(i)
                            val ssid = network.getString("ssid")
                            val signal = network.getInt("signal")
                            val security = network.getString("security")
                            val isSaved = WiFiCredentialManager.isSaved(this, ssid)
                            
                            availableNetworks.add(WiFiNetwork(ssid, signal, security, isSaved))
                        }
                        
                        // Sort by signal strength
                        availableNetworks.sortByDescending { it.signal }
                        availableNetworksAdapter.updateNetworks(availableNetworks)
                        
                        tvAvailableNetworks.visibility = View.VISIBLE
                        rvAvailableNetworks.visibility = View.VISIBLE
                        tvNoNetworks.visibility = if (availableNetworks.isEmpty()) View.VISIBLE else View.GONE
                    }
                } catch (e: Exception) {
                    android.util.Log.e("WiFiActivity", "Error parsing scan results: ${e.message}")
                    Toast.makeText(this, "Scan failed: ${e.message}", Toast.LENGTH_SHORT).show()
                } finally {
                    progressScanning.visibility = View.GONE
                    tvScanning.visibility = View.GONE
                    btnScanNetworks.isEnabled = true
                }
            }
        }
    }

    private fun onNetworkConnect(network: WiFiNetwork) {
        if (network.isSaved) {
            // Connect with saved password
            val password = WiFiCredentialManager.getPassword(this, network.ssid)
            if (password != null) {
                connectToNetwork(network.ssid, password)
            }
        } else {
            // Show password dialog
            showPasswordDialog(network)
        }
    }

    private fun onNetworkLongClick(network: WiFiNetwork) {
        AlertDialog.Builder(this)
            .setTitle(R.string.wifi_forget_network)
            .setMessage(getString(R.string.wifi_forget_network_confirm, network.ssid))
            .setPositiveButton(R.string.btn_yes) { _, _ ->
                WiFiCredentialManager.forgetNetwork(this, network.ssid)
                loadSavedNetworks()
                Toast.makeText(this, getString(R.string.wifi_network_forgotten, network.ssid), Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton(R.string.btn_no, null)
            .show()
    }

    private fun showPasswordDialog(network: WiFiNetwork) {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_wifi_password, null)
        val tvDialogSsid = dialogView.findViewById<TextView>(R.id.tvDialogSsid)
        val etPassword = dialogView.findViewById<TextInputEditText>(R.id.etPassword)
        val cbRememberNetwork = dialogView.findViewById<CheckBox>(R.id.cbRememberNetwork)
        
        tvDialogSsid.text = network.ssid
        
        val dialog = AlertDialog.Builder(this)
            .setView(dialogView)
            .create()
        
        dialogView.findViewById<Button>(R.id.btnCancel).setOnClickListener {
            dialog.dismiss()
        }
        
        dialogView.findViewById<Button>(R.id.btnConnect).setOnClickListener {
            val password = etPassword.text.toString()
            if (password.isEmpty()) {
                Toast.makeText(this, R.string.wifi_password_required, Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            
            if (cbRememberNetwork.isChecked) {
                WiFiCredentialManager.saveNetwork(this, network.ssid, password)
                loadSavedNetworks()
            }
            
            connectToNetwork(network.ssid, password)
            dialog.dismiss()
        }
        
        dialog.show()
    }

    private fun connectToNetwork(ssid: String, password: String) {
        val json = JSONObject()
        json.put("ssid", ssid)
        json.put("password", password)
        
        Toast.makeText(this, getString(R.string.wifi_connecting, ssid), Toast.LENGTH_SHORT).show()
        
        BluetoothManager.sendCommand("WIFI_CONNECT:${json.toString()}")
        BluetoothManager.onDataReceived = { data ->
            runOnUiThread {
                try {
                    val response = JSONObject(data.trim())
                    if (response.optString("status") == "connected") {
                        Toast.makeText(this, getString(R.string.wifi_connected_to, ssid), Toast.LENGTH_LONG).show()
                        checkCurrentConnection()
                    } else {
                        val error = response.optString("error", "Unknown error")
                        Toast.makeText(this, getString(R.string.wifi_connection_failed) + ": $error", Toast.LENGTH_LONG).show()
                    }
                } catch (e: Exception) {
                    android.util.Log.e("WiFiActivity", "Error parsing connection response: ${e.message}")
                }
            }
        }
    }

    private fun disconnectWiFi() {
        AlertDialog.Builder(this)
            .setTitle(R.string.wifi_disconnect)
            .setMessage(R.string.wifi_disconnect_confirm)
            .setPositiveButton(R.string.btn_yes) { _, _ ->
                BluetoothManager.sendCommand("WIFI_DISCONNECT")
                BluetoothManager.onDataReceived = { data ->
                    runOnUiThread {
                        try {
                            val response = JSONObject(data.trim())
                            if (response.optString("status") == "disconnected") {
                                Toast.makeText(this, R.string.wifi_disconnected, Toast.LENGTH_SHORT).show()
                                checkCurrentConnection()
                            }
                        } catch (e: Exception) {
                            android.util.Log.e("WiFiActivity", "Error parsing disconnect response: ${e.message}")
                        }
                    }
                }
            }
            .setNegativeButton(R.string.btn_no, null)
            .show()
    }
}
