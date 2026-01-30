package com.cortarse.controlcortase

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

    private lateinit var btnScan: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var deviceList: ListView
    private lateinit var deviceAdapter: ArrayAdapter<String>
    private val devices = ArrayList<BluetoothDevice>()
    private val deviceNames = ArrayList<String>()

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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        btnScan = findViewById(R.id.btnScan)
        progressBar = findViewById(R.id.progressBar)
        deviceList = findViewById(R.id.deviceList)
        btnLanguage = findViewById(R.id.btnLanguage)
        val btnDocs = findViewById<android.widget.ImageButton>(R.id.btnDocs)

        updateLanguageIcon()

        deviceAdapter = ArrayAdapter(this, R.layout.item_device, android.R.id.text1, deviceNames)
        deviceList.adapter = deviceAdapter

        btnScan.setOnClickListener {
            checkPermissionsAndScan()
        }
        
        btnLanguage.setOnClickListener {
            cycleLanguage()
        }

        btnDocs.setOnClickListener {
            // Placeholder for opening docs
            Toast.makeText(this, "Documentation coming soon", Toast.LENGTH_SHORT).show()
        }

        deviceList.setOnItemClickListener { _, _, position, _ ->
            val device = devices[position]
            connectToDevice(device)
        }
    }

    private fun cycleLanguage() {
        val currentLang = resources.configuration.locales.get(0).language
        val newLang = when (currentLang) {
            "en" -> "ru"
            "ru" -> "es"
            else -> "en"
        }
        setLocale(newLang)
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

    private fun checkPermissionsAndScan() {
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
        btnScan.isEnabled = false

        Thread {
            val success = com.cortarse.controlcortase.BluetoothManager.connect(device)
            runOnUiThread {
                progressBar.visibility = View.GONE
                btnScan.isEnabled = true
                if (success) {
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
