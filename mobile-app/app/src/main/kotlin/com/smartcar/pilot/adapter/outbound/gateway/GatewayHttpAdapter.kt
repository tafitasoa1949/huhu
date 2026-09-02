package com.smartcar.pilot.adapter.outbound.gateway

import com.smartcar.pilot.domain.model.CarAlreadyClaimedException
import com.smartcar.pilot.domain.model.CarSession
import com.smartcar.pilot.domain.model.CarSummary
import com.smartcar.pilot.domain.model.GatewayUnreachableException
import com.smartcar.pilot.domain.port.GatewayPort
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Implémentation REST du port [GatewayPort] — Phase 1 uniquement
 * (docs/mobile-protocol.md). N'est jamais utilisée après [claim] : la
 * Phase 2 passe par [com.smartcar.pilot.adapter.outbound.p2p], qui ne
 * connaît même pas cette classe.
 *
 * [configure] doit être appelé avant tout usage — l'adresse du Gateway est
 * saisie par le pilote sur l'écran de connexion, elle n'est pas connue à la
 * construction du conteneur de dépendances (voir `di.AppContainer`).
 */
class GatewayHttpAdapter(
    private val client: OkHttpClient = OkHttpClient(),
) : GatewayPort {

    @Volatile
    private var baseUrl: String? = null

    fun configure(host: String, port: Int) {
        baseUrl = "http://$host:$port"
    }

    override suspend fun listCars(): List<CarSummary> = withContext(Dispatchers.IO) {
        val request = Request.Builder().url("${requireBaseUrl()}/api/cars").build()
        runCatching {
            client.newCall(request).execute().use { response ->
                val body = response.body?.string().orEmpty()
                if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
                json.decodeFromString(ListSerializer(CarSummaryDto.serializer()), body).map { it.toDomain() }
            }
        }.getOrElse { throw GatewayUnreachableException(it) }
    }

    override suspend fun claim(carId: String): CarSession = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("${requireBaseUrl()}/api/cars/$carId/claim")
            .post(EMPTY_BODY)
            .build()
        val response = try {
            client.newCall(request).execute()
        } catch (e: IOException) {
            throw GatewayUnreachableException(e)
        }
        response.use {
            if (it.code == 409) throw CarAlreadyClaimedException(carId)
            val body = it.body?.string().orEmpty()
            if (!it.isSuccessful) throw GatewayUnreachableException(IOException("HTTP ${it.code}"))
            json.decodeFromString(ClaimResponseDto.serializer(), body).toDomain(claimedAtMs = System.currentTimeMillis())
        }
    }

    private fun requireBaseUrl(): String =
        baseUrl ?: error("GatewayHttpAdapter.configure(host, port) n'a pas été appelé avant usage")

    private companion object {
        val json = Json { ignoreUnknownKeys = true }
        val EMPTY_BODY = ByteArray(0).toRequestBody(null)
    }
}
