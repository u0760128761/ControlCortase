package com.cortarse.controlcortase

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONArray
import org.json.JSONObject

/**
 * Manages WiFi credentials storage using encrypted SharedPreferences
 */
object WiFiCredentialManager {
    
    private const val PREFS_NAME = "wifi_credentials"
    private const val KEY_NETWORKS = "saved_networks"
    
    private fun getEncryptedPrefs(context: Context): SharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
            
        return EncryptedSharedPreferences.create(
            context,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }
    
    /**
     * Save WiFi network credentials
     */
    fun saveNetwork(context: Context, ssid: String, password: String) {
        val prefs = getEncryptedPrefs(context)
        val networksJson = prefs.getString(KEY_NETWORKS, "[]") ?: "[]"
        val networks = JSONArray(networksJson)
        
        // Remove existing entry for this SSID if present
        val updatedNetworks = JSONArray()
        for (i in 0 until networks.length()) {
            val network = networks.getJSONObject(i)
            if (network.getString("ssid") != ssid) {
                updatedNetworks.put(network)
            }
        }
        
        // Add new entry
        val newNetwork = JSONObject()
        newNetwork.put("ssid", ssid)
        newNetwork.put("password", password)
        newNetwork.put("timestamp", System.currentTimeMillis())
        updatedNetworks.put(newNetwork)
        
        prefs.edit().putString(KEY_NETWORKS, updatedNetworks.toString()).apply()
    }
    
    /**
     * Get password for a saved network
     */
    fun getPassword(context: Context, ssid: String): String? {
        val prefs = getEncryptedPrefs(context)
        val networksJson = prefs.getString(KEY_NETWORKS, "[]") ?: "[]"
        val networks = JSONArray(networksJson)
        
        for (i in 0 until networks.length()) {
            val network = networks.getJSONObject(i)
            if (network.getString("ssid") == ssid) {
                return network.getString("password")
            }
        }
        return null
    }
    
    /**
     * Check if network is saved
     */
    fun isSaved(context: Context, ssid: String): Boolean {
        return getPassword(context, ssid) != null
    }
    
    /**
     * Get all saved network SSIDs
     */
    fun getSavedNetworks(context: Context): List<String> {
        val prefs = getEncryptedPrefs(context)
        val networksJson = prefs.getString(KEY_NETWORKS, "[]") ?: "[]"
        val networks = JSONArray(networksJson)
        
        val ssids = mutableListOf<String>()
        for (i in 0 until networks.length()) {
            val network = networks.getJSONObject(i)
            ssids.add(network.getString("ssid"))
        }
        return ssids
    }
    
    /**
     * Remove saved network
     */
    fun forgetNetwork(context: Context, ssid: String) {
        val prefs = getEncryptedPrefs(context)
        val networksJson = prefs.getString(KEY_NETWORKS, "[]") ?: "[]"
        val networks = JSONArray(networksJson)
        
        val updatedNetworks = JSONArray()
        for (i in 0 until networks.length()) {
            val network = networks.getJSONObject(i)
            if (network.getString("ssid") != ssid) {
                updatedNetworks.put(network)
            }
        }
        
        prefs.edit().putString(KEY_NETWORKS, updatedNetworks.toString()).apply()
    }
    
    /**
     * Clear all saved networks
     */
    fun clearAll(context: Context) {
        val prefs = getEncryptedPrefs(context)
        prefs.edit().clear().apply()
    }
}
