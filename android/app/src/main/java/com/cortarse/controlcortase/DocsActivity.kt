package com.cortarse.controlcortase

import android.content.Context
import android.os.Bundle
import android.widget.ImageButton
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.io.BufferedReader
import java.io.InputStreamReader

class DocsActivity : AppCompatActivity() {

    private lateinit var tvDocsContent: TextView
    private lateinit var btnBack: ImageButton

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_docs)

        tvDocsContent = findViewById(R.id.tvDocsContent)
        btnBack = findViewById(R.id.btnBack)

        btnBack.setOnClickListener { finish() }

        loadDocumentation()
    }

    private fun loadDocumentation() {
        val prefs = getSharedPreferences("Settings", Context.MODE_PRIVATE)
        val languageCode = prefs.getString("My_Lang", "en") ?: "en"

        // Выбираем файл в зависимости от языка
        // Файлы должны лежать в assets/docs/
        val fileName = when (languageCode) {
            "ru" -> "README_RU.md"
            "es" -> "README_ES.md"
            else -> "README_EN.md"
        }

        try {
            val inputStream = assets.open("docs/$fileName")
            val reader = BufferedReader(InputStreamReader(inputStream))
            val stringBuilder = java.lang.StringBuilder()
            var line: String?

            while (reader.readLine().also { line = it } != null) {
                stringBuilder.append(line).append('\n')
            }
            reader.close()
            tvDocsContent.text = stringBuilder.toString()
        } catch (e: Exception) {
            e.printStackTrace()
            tvDocsContent.text = "Error loading documentation / Ошибка загрузки документации: ${e.message}"
        }
    }
}
