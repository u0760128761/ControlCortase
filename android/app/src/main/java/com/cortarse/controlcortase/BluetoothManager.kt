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
    private val MY_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    private var socket: BluetoothSocket? = null
    private var outputStream: OutputStream? = null
    private var inputStream: InputStream? = null
    var lastDevice: BluetoothDevice? = null
    private var readThread: Thread? = null
    
    var onConnectionFailed: (() -> Unit)? = null
    var onDataReceived: ((String) -> Unit)? = null

    @SuppressLint("MissingPermission")
    fun connect(device: BluetoothDevice): Boolean {
        lastDevice = device
        return try {
            socket = device.createRfcommSocketToServiceRecord(MY_UUID)
            socket?.connect()
            outputStream = socket?.outputStream
            inputStream = socket?.inputStream
            startReading()
            true
        } catch (e: IOException) {
            e.printStackTrace()
            close()
            false
        }
    }

    fun reconnect(callback: (Boolean) -> Unit) {
        val device = lastDevice
        if (device == null) {
            callback(false)
            return
        }
        Thread {
            val success = connect(device)
            callback(success)
        }.start()
    }

    private fun startReading() {
        readThread?.interrupt()
        readThread = Thread {
            val buffer = ByteArray(1024)
            while (!Thread.currentThread().isInterrupted && socket?.isConnected == true) {
                try {
                    val bytes = inputStream?.read(buffer) ?: -1
                    if (bytes > 0) {
                        val message = String(buffer, 0, bytes)
                        onDataReceived?.invoke(message)
                    } else if (bytes == -1) {
                        break
                    }
                } catch (e: IOException) {
                    onConnectionFailed?.invoke()
                    break
                }
            }
        }.apply { start() }
    }

    fun sendCommand(command: String) {
        try {
            outputStream?.write((command + "\n").toByteArray())
        } catch (e: IOException) {
            e.printStackTrace()
            onConnectionFailed?.invoke()
            close()
        }
    }

    fun isConnected(): Boolean = socket?.isConnected == true

    fun close() {
        readThread?.interrupt()
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
        readThread = null
    }
}
