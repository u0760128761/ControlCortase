package com.cortarse.controlcortase

import android.annotation.SuppressLint
import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.ListView
import android.widget.ProgressBar
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import java.util.ArrayList

class MainActivity : AppCompatActivity() {

    private lateinit var progressBar: ProgressBar
    private lateinit var deviceList: ListView
    private lateinit var deviceAdapter: ArrayAdapter<String>
    private lateinit var spinnerHistory: android.widget.Spinner
    private lateinit var historyAdapter: ArrayAdapter<String>
    private val devices = ArrayList<BluetoothDevice>()
    private val deviceNames = ArrayList<String>()
    private val historyNames = ArrayList<String>()
    private val historyAddresses = ArrayList<String>()

    private val bluetoothAdapter: BluetoothAdapter? by lazy {
        val manager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        manager.adapter
    }

    // Permission Launcher
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val granted = permissions.entries.all { it.value }
        if (granted) {
            scanDevices()
        } else {
            Toast.makeText(this, "Permissions required for Bluetooth", Toast.LENGTH_SHORT).show()
        }
    }

    private lateinit var btnLanguage: android.widget.ImageButton
    private lateinit var btnScanHeader: android.widget.ImageButton
    private lateinit var tvStatusHeader: android.widget.TextView
    private lateinit var containerStatusHeader: android.view.View

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        progressBar = findViewById(R.id.progressBar)
        deviceList = findViewById(R.id.deviceList)

        loadLocale()
        initHeader()
        initHistory()

        deviceAdapter = ArrayAdapter(this, R.layout.item_device, android.R.id.text1, deviceNames)
        deviceList.adapter = deviceAdapter


        deviceList.setOnItemClickListener { _, _, position, _ ->
            val device = devices[position]
            connectToDevice(device)
        }
    }

    private fun initHeader() {
        val header = findViewById<View>(R.id.layoutHeader)
        btnLanguage = header.findViewById(R.id.headerBtnLanguage)
        btnScanHeader = header.findViewById(R.id.headerBtnScan)
        tvStatusHeader = header.findViewById(R.id.headerTvStatus)
        containerStatusHeader = header.findViewById(R.id.headerContainerStatus)

        updateLanguageIcon()
        tvStatusHeader.text = getString(R.string.status_disconnected)

        btnLanguage.setOnClickListener { showLanguageMenu() }
        btnScanHeader.setOnClickListener { checkPermissionsAndScan() }
        containerStatusHeader.setOnClickListener {
            // Tapping "Disconnected" should connect to last device if available
            val prefs = getSharedPreferences("DeviceHistory", Context.MODE_PRIVATE)
            val lastAddress = prefs.getString("last_device", null)
            if (lastAddress != null) {
                val lastDevice = bluetoothAdapter?.getRemoteDevice(lastAddress)
                lastDevice?.let { connectToDevice(it) }
            } else if (historyAddresses.isNotEmpty()) {
                val lastAddressHistory = historyAddresses.last()
                val lastDevice = bluetoothAdapter?.getRemoteDevice(lastAddressHistory)
                lastDevice?.let { connectToDevice(it) }
            } else {
                Toast.makeText(this, "No saved devices to connect", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun initHistory() {
        spinnerHistory = findViewById(R.id.spinnerHistory)
        historyAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, historyNames)
        historyAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerHistory.adapter = historyAdapter

        loadHistory()

        spinnerHistory.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (position > 0) {
                    val address = historyAddresses[position - 1]
                    val device = bluetoothAdapter?.getRemoteDevice(address)
                    device?.let { connectToDevice(it) }
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
    }

    private fun loadHistory() {
        val prefs = getSharedPreferences("DeviceHistory", Context.MODE_PRIVATE)
        val historySet = prefs.getStringSet("devices", emptySet()) ?: emptySet()
        
        historyNames.clear()
        historyAddresses.clear()
        historyNames.add(getString(R.string.label_recent_devices)) // Default item
        
        historySet.forEach { entry ->
            val parts = entry.split("|")
            if (parts.size == 2) {
                historyNames.add("${parts[0]}\n${parts[1]}")
                historyAddresses.add(parts[1])
            }
        }
        historyAdapter.notifyDataSetChanged()
    }

    private fun saveToHistory(device: BluetoothDevice) {
        val prefs = getSharedPreferences("DeviceHistory", Context.MODE_PRIVATE)
        val historySet = prefs.getStringSet("devices", mutableSetOf())?.toMutableSet() ?: mutableSetOf()
        
        @SuppressLint("MissingPermission")
        val entry = "${device.name ?: "Unknown"}|${device.address}"
        historySet.add(entry)
        
        prefs.edit().putStringSet("devices", historySet)
            .putString("last_device", device.address)
            .apply()
        loadHistory()
    }

    private fun showLanguageMenu() {
        val popup = android.widget.PopupMenu(this, btnLanguage)
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
        btnLanguage.setImageResource(iconRes)
    }

    private fun setLocale(languageCode: String) {
        val prefs = getSharedPreferences("Settings", Context.MODE_PRIVATE)
        prefs.edit().putString("My_Lang", languageCode).apply()

        val locale = java.util.Locale(languageCode)
        java.util.Locale.setDefault(locale)
        val config = android.content.res.Configuration()
        config.setLocale(locale)
        baseContext.resources.updateConfiguration(config, baseContext.resources.displayMetrics)
        
        // Recreate activity to apply changes
        val intent = intent
        finish()
        startActivity(intent)
    }

    private fun loadLocale() {
        val prefs = getSharedPreferences("Settings", Context.MODE_PRIVATE)
        val language = prefs.getString("My_Lang", "") ?: ""
        if (language.isNotEmpty()) {
            val locale = java.util.Locale(language)
            java.util.Locale.setDefault(locale)
            val config = android.content.res.Configuration()
            config.setLocale(locale)
            baseContext.resources.updateConfiguration(config, baseContext.resources.displayMetrics)
        }
    }

    private fun checkPermissionsAndScan() {
        if (com.cortarse.controlcortase.BluetoothManager.isConnected()) {
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setMessage(R.string.msg_confirm_scan)
                .setPositiveButton(R.string.btn_yes) { _, _ ->
                    com.cortarse.controlcortase.BluetoothManager.close()
                    performScan()
                }
                .setNegativeButton(R.string.btn_no, null)
                .show()
        } else {
            performScan()
        }
    }

    private fun performScan() {
        val permissionsToRequest = mutableListOf<String>()
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(Manifest.permission.BLUETOOTH_SCAN)
            }
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(Manifest.permission.BLUETOOTH_CONNECT)
            }
        } else {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(Manifest.permission.ACCESS_FINE_LOCATION)
            }
        }

        if (permissionsToRequest.isNotEmpty()) {
            requestPermissionLauncher.launch(permissionsToRequest.toTypedArray())
        } else {
            scanDevices()
        }
    }

    private fun scanDevices() {
        if (bluetoothAdapter == null || !bluetoothAdapter!!.isEnabled) {
            Toast.makeText(this, "Enable Bluetooth first", Toast.LENGTH_SHORT).show()
            return
        }

        devices.clear()
        deviceNames.clear()
        deviceAdapter.notifyDataSetChanged()

        if (ActivityCompat.checkSelfPermission(
                this,
                Manifest.permission.BLUETOOTH_CONNECT
            ) != PackageManager.PERMISSION_GRANTED && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
        ) {
            return
        }

        // Add paired devices first
        val pairedDevices: Set<BluetoothDevice>? = bluetoothAdapter!!.bondedDevices
        pairedDevices?.forEach { device ->
            devices.add(device)
            deviceNames.add("${device.name} (Paired)\n${device.address}")
        }
        deviceAdapter.notifyDataSetChanged()
        
        Toast.makeText(this, "Showing Paired Devices", Toast.LENGTH_SHORT).show()
    }

    private fun connectToDevice(device: BluetoothDevice) {
        if (ActivityCompat.checkSelfPermission(
                this,
                Manifest.permission.BLUETOOTH_CONNECT
            ) != PackageManager.PERMISSION_GRANTED && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
        ) {
            return
        }

        progressBar.visibility = View.VISIBLE
        btnScanHeader.isEnabled = false

        Thread {
            val success = com.cortarse.controlcortase.BluetoothManager.connect(device)
            runOnUiThread {
                progressBar.visibility = View.GONE
                btnScanHeader.isEnabled = true
                if (success) {
                    saveToHistory(device)
                    Toast.makeText(this, "Connected to ${device.name}", Toast.LENGTH_SHORT).show()
                    val intent = Intent(this, ControlActivity::class.java)
                    startActivity(intent)
                } else {
                    Toast.makeText(this, "Connection Failed", Toast.LENGTH_SHORT).show()
                }
            }
        }.start()
    }
}
