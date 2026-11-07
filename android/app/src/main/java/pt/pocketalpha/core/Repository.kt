package pt.pocketalpha.core

import androidx.room.Room
import android.content.Context
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.net.URI
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

fun normalizeEndpoint(value: String): String {
    val uri = URI(value.trim())
    require(uri.scheme == "https" && !uri.host.isNullOrBlank()) { "Use an HTTPS API origin" }
    require(uri.userInfo == null && uri.rawQuery == null && uri.fragment == null)
    require(uri.path in listOf("", "/", "/mobile", "/mobile/")) { "Use the server origin or /mobile/" }
    require(uri.port == -1 || uri.port in 1..65535)
    return URI("https", null, uri.host, uri.port, "/mobile/", null, null).toASCIIString()
}
fun safeId(value: String): String {
    require(value.matches(Regex("[A-Za-z0-9_.:-]{1,128}"))) { "Invalid identifier" }
    return value
}
fun jsonBody(vararg entries: Pair<String, String>): JsonObject = buildJsonObject {
    entries.forEach { (key, value) -> put(key, value) }
}

@Singleton class Repository @Inject constructor(
    private val json: Json, private val vault: TokenVault, private val preferences: Preferences,
    private val database: PocketDatabase
) {
    private val invalidatedState = MutableStateFlow(false)
    val sessionInvalidated = invalidatedState.asStateFlow()
    private val lock = Mutex()
    private suspend fun invalidate() { vault.clear(); dao.clear(); invalidatedState.value = true }
    private var api: PocketApi? = null
    private var endpoint = ""
    private val dao get() = database.snapshots()
    private fun build(endpoint: String): PocketApi {
        val client = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS).callTimeout(30, TimeUnit.SECONDS)
            .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
            .addInterceptor { chain ->
                val request = chain.request().newBuilder()
                if (!chain.request().url.encodedPath.contains("/auth/login") &&
                    !chain.request().url.encodedPath.contains("/auth/refresh")) {
                    vault.access?.let { request.header("Authorization", "Bearer $it") }
                }
                val response = chain.proceed(request.build())
                val body = response.body
                if (body == null) response else {
                    val media = body.contentType()
                    val bytes = body.source().readByteArrayBounded(4 * 1024 * 1024)
                    body.close()
                    response.newBuilder().body(bytes.toResponseBody(media)).build()
                }
            }.build()
        return Retrofit.Builder().baseUrl(endpoint).client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build().create(PocketApi::class.java)
    }
    private suspend fun initialize(): PocketApi {
        if (api == null) {
            endpoint = normalizeEndpoint(preferences.endpoint())
            api = build(endpoint)
        }
        return requireNotNull(api)
    }
    private suspend fun rotate(client: PocketApi) {
        val stored = vault.read() ?: throw IOException("Sign in to your server")
        val tokens = try { client.refresh(RefreshRequest(stored.refresh_token)) }
            catch (failure: HttpException) { if (failure.code() == 401) invalidate(); throw failure }
        if (tokens.user_id != stored.user_id || tokens.session_id != stored.session_id) {
            invalidate(); throw IllegalArgumentException("Session identity mismatch")
        }
        vault.save(tokens)
    }
    suspend fun storedEndpoint(): String = preferences.endpoint()
    suspend fun resume(): Boolean = withContext(Dispatchers.IO) { lock.withLock {
        if (vault.read() == null) return@withLock false
        try { rotate(initialize()); true }
        catch (error: HttpException) {
            if (error.code() == 401) invalidate()
            false
        }
        catch (_: IllegalArgumentException) { vault.clear(); dao.clear(); false }
        catch (_: IOException) { vault.read() != null } // Only a still-valid stored session permits cached reads.
    } }
    suspend fun login(origin: String, username: String, password: String) = withContext(Dispatchers.IO) {
        lock.withLock {
            val normalized = normalizeEndpoint(origin)
            vault.clear(); dao.clear()
            endpoint = normalized; api = build(endpoint)
            val tokens = requireNotNull(api).login(LoginRequest(username.trim(), password, android.os.Build.MODEL.take(80)))
            preferences.saveEndpoint(normalized); vault.save(tokens); invalidatedState.value = false
        }
    }
    suspend fun logout(): Boolean = withContext(Dispatchers.IO) { lock.withLock {
        var revoked = false
        try { vault.read()?.let { stored -> authorized { it.revoke(stored.session_id) }; revoked = true } }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { /* Local logout still clears all credentials and snapshots. */ }
        vault.clear(); dao.clear(); api = null
        revoked
    } }
    private suspend fun <T> authorized(action: suspend (PocketApi) -> T): T {
        val client = initialize()
        if (vault.access == null) rotate(client)
        return try { action(client) } catch (error: HttpException) {
            if (error.code() != 401) throw error
            try { rotate(client); action(client) } catch (failure: HttpException) {
                if (failure.code() == 401) invalidate()
                throw failure
            }
        }
    }
    private fun message(error: Exception): String = when (error) {
        is HttpException -> when (error.code()) {
            401 -> "Session expired or revoked. Sign in again."
            403 -> "This operation is not authorized."
            404 -> "No server record exists for this selection."
            409 -> "The server revision changed. Refresh and review before resubmitting."
            422 -> "The server rejected these inputs. Review the required fields."
            429 -> "Rate limit reached. Wait before trying again."
            else -> "Server unavailable (${error.code()})."
        }
        is IOException -> "Connection unavailable. Check your HTTPS server and network."
        else -> "Response or input validation failed. No financial state was changed locally."
    }
    suspend fun read(key: String, cache: Boolean = true, fetch: suspend (PocketApi) -> JsonElement): Resource = withContext(Dispatchers.IO) {
        lock.withLock {
            val session = vault.read() ?: run { invalidate(); return@withLock Resource(error = "Sign in to your server") }
            val cacheKey = preferences.endpoint() + "|" + session.user_id + "|" + key
            try {
                val value = authorized(fetch)
                val payload = value.toString()
                if (cache && payload.length <= 1024 * 1024) {
                    dao.put(CachedSnapshot(cacheKey, payload, System.currentTimeMillis())); dao.prune()
                }
                Resource(value = value)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                // Permission failures/invalid payloads must never silently become cached success.
                val cached = if (cache && (error is IOException || (error is HttpException && error.code() >= 500))) dao.get(cacheKey) else null
                Resource(value = cached?.let { json.parseToJsonElement(it.payload) }, error = message(error), cachedAt = cached?.fetchedAt)
            }
        }
    }
    suspend fun mutate(action: suspend (PocketApi) -> Unit): String? = withContext(Dispatchers.IO) {
        lock.withLock {
            try { authorized(action); dao.clear(); null }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) { message(error) }
        }
    }
    fun encodeMarkets(value: List<Market>): JsonElement = json.encodeToJsonElement(value)
    fun encodeCandles(value: CandlePage): JsonElement = json.encodeToJsonElement(value)
    fun encodeWatchlists(value: List<Watchlist>): JsonElement = json.encodeToJsonElement(value)
    fun encodePortfolios(value: List<Portfolio>): JsonElement = json.encodeToJsonElement(value)
    fun markets(value: JsonElement): List<Market> = json.decodeFromJsonElement(value)
    fun watchlists(value: JsonElement): List<Watchlist> = json.decodeFromJsonElement(value)
    fun portfolios(value: JsonElement): List<Portfolio> = json.decodeFromJsonElement(value)
    fun candles(value: JsonElement): CandlePage = json.decodeFromJsonElement(value)
}

private fun okio.BufferedSource.readByteArrayBounded(limit: Long): ByteArray {
    val buffer = okio.Buffer()
    try {
        while (buffer.size <= limit) {
            if (read(buffer, minOf(8192, limit + 1 - buffer.size)) == -1L) return buffer.readByteArray()
        }
        throw IOException("Server response exceeds the bounded client limit")
    } finally { close() }
}

@Module @InstallIn(SingletonComponent::class) object CoreModule {
    @Provides @Singleton fun json(): Json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    @Provides @Singleton fun database(@ApplicationContext context: Context): PocketDatabase =
        Room.databaseBuilder(context, PocketDatabase::class.java, "snapshots.db").build()
}
