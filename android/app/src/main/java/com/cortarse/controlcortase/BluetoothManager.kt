package com.cortarse.controlcortase

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.os.Handler
import android.os.Looper
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.util.UUID

object BluetoothManager {
    private val MY_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB") // Standard SPP UUID
    private var socket: BluetoothSocket? = null
    private var outputStream: OutputStream? = null
    private var inputStream: InputStream? = null
    
    // Callback for connection status
    var onConnectionFailed: (() -> Unit)? = null

    // Connect to a device
    // SuppressSuppressLint because permission checks should be done in Activity before calling this
    @SuppressLint("MissingPermission")
    fun connect(device: BluetoothDevice): Boolean {
        return try {
            socket = device.createRfcommSocketToServiceRecord(MY_UUID)
            socket?.connect()
            outputStream = socket?.outputStream
            inputStream = socket?.inputStream
            true
        } catch (e: IOException) {
            e.printStackTrace()
            close()
            false
        }
    }

    // Send command
    fun sendCommand(command: String) {
        try {
            outputStream?.write((command + "\n").toByteArray())
        } catch (e: IOException) {
            e.printStackTrace()
            onConnectionFailed?.invoke()
            close()
        }
    }

    // Check if connected
    fun isConnected(): Boolean {
        return socket?.isConnected == true
    }

    // Close connection
    fun close() {
        try {
            outputStream?.close()
            inputStream?.close()
            socket?.close()
        } catch (e: IOException) {
            e.printStackTrace()
        }
        socket = null
        outputStream = null
        inputStream = null
    }
}
