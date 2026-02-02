package com.cortarse.controlcortase

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

/**
 * Data class representing a WiFi network
 */
data class WiFiNetwork(
    val ssid: String,
    val signal: Int,  // Signal strength in dBm (e.g., -50)
    val security: String,  // "Open", "WPA", "WPA2", etc.
    val isSaved: Boolean = false
) {
    fun getSignalStrengthText(): String {
        return when {
            signal >= -50 -> "Strong"
            signal >= -70 -> "Medium"
            else -> "Weak"
        }
    }
    
    fun getSignalStrengthColor(): Int {
        return when {
            signal >= -50 -> R.color.colorPrimary  // Green
            signal >= -70 -> R.color.colorSecondary  // Orange
            else -> R.color.colorError  // Red
        }
    }
}

/**
 * RecyclerView adapter for WiFi networks
 */
class WiFiNetworkAdapter(
    private var networks: List<WiFiNetwork>,
    private val onConnectClick: (WiFiNetwork) -> Unit,
    private val onLongClick: ((WiFiNetwork) -> Unit)? = null
) : RecyclerView.Adapter<WiFiNetworkAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val ivSignalStrength: ImageView = view.findViewById(R.id.ivSignalStrength)
        val tvSsid: TextView = view.findViewById(R.id.tvSsid)
        val tvSavedBadge: TextView = view.findViewById(R.id.tvSavedBadge)
        val tvSignalStrength: TextView = view.findViewById(R.id.tvSignalStrength)
        val tvSecurity: TextView = view.findViewById(R.id.tvSecurity)
        val btnConnect: Button = view.findViewById(R.id.btnConnect)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_wifi_network, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val network = networks[position]
        
        holder.tvSsid.text = network.ssid
        holder.tvSignalStrength.text = "Signal: ${network.getSignalStrengthText()}"
        holder.tvSecurity.text = " • ${network.security}"
        
        // Set signal strength icon color
        val color = holder.itemView.context.getColor(network.getSignalStrengthColor())
        holder.ivSignalStrength.setColorFilter(color)
        
        // Show/hide saved badge
        holder.tvSavedBadge.visibility = if (network.isSaved) View.VISIBLE else View.GONE
        
        // Update button text for saved networks
        holder.btnConnect.text = if (network.isSaved) {
            holder.itemView.context.getString(R.string.wifi_reconnect)
        } else {
            holder.itemView.context.getString(R.string.wifi_connect)
        }
        
        // Connect button click
        holder.btnConnect.setOnClickListener {
            onConnectClick(network)
        }
        
        // Long click for saved networks (to forget)
        if (network.isSaved && onLongClick != null) {
            holder.itemView.setOnLongClickListener {
                onLongClick.invoke(network)
                true
            }
        }
    }

    override fun getItemCount() = networks.size

    fun updateNetworks(newNetworks: List<WiFiNetwork>) {
        networks = newNetworks
        notifyDataSetChanged()
    }
}
