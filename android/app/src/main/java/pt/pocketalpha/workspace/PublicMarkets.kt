package pt.pocketalpha.workspace

import android.content.Context
import androidx.room.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.time.Instant
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton
import dagger.hilt.android.qualifiers.ApplicationContext
import pt.pocketalpha.core.Candle
import pt.pocketalpha.local.Decimal80

@Serializable data class PublicMarket(val id: String, val step: String, val minimum: String)
@Entity(tableName = "public_history") data class HistoryRow(@PrimaryKey val market: String, val payload: String, val fetched: String)
@Dao interface HistoryDao {
    @Query("SELECT * FROM public_history WHERE market = :id") suspend fun get(id: String): HistoryRow?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun save(row: HistoryRow)
}
@Database(entities = [HistoryRow::class], version = 1, exportSchema = false)
abstract class PublicHistoryDatabase : RoomDatabase() { abstract fun history(): HistoryDao }

object CoinbaseParser {
    fun candles(body: String, market: String, received: Instant): List<Candle> {
        require(market.matches(Regex("[A-Z0-9]{2,16}-EUR")))
        val rows = Json.parseToJsonElement(body).jsonArray
        require(rows.size <= 1024) { "Provider response exceeds normalization budget" }
        val values = rows.map { element ->
            val r = element.jsonArray; require(r.size == 6)
            val opened = Instant.ofEpochSecond(r[0].jsonPrimitive.long)
            require(opened.epochSecond % 3600 == 0L)
            Candle(market, "1h", opened.toString(), opened.plusSeconds(3600).toString(),
                r[3].jsonPrimitive.content, r[2].jsonPrimitive.content, r[1].jsonPrimitive.content,
                r[4].jsonPrimitive.content, r[5].jsonPrimitive.content, "coinbase-exchange-public", received.toString()).also {
                listOf(it.open,it.high,it.low,it.close,it.volume).forEach(Decimal80::read)
                it.validate(market, "1h")
            }
        }.filter { Instant.parse(it.close_time) <= received }.sortedBy { Instant.parse(it.open_time) }
        require(values.map { it.open_time }.distinct().size == values.size)
        return values
    }
}
@Singleton class PublicMarkets @Inject constructor(@ApplicationContext context: Context) {
    private val http = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).callTimeout(20, TimeUnit.SECONDS).build()
    private val db = Room.databaseBuilder(context, PublicHistoryDatabase::class.java, "public-market-history.db").build()
    private val mutex = kotlinx.coroutines.sync.Mutex()
    private var nextRequest = 0L
    private suspend fun get(path: String): String = withContext(Dispatchers.IO) {
        mutex.lock()
        try {
            for (attempt in 0..2) {
                delay((nextRequest - System.currentTimeMillis()).coerceAtLeast(0))
                nextRequest = System.currentTimeMillis() + 1000
                http.newCall(Request.Builder().url("https://api.exchange.coinbase.com/$path").header("User-Agent", "PocketAlpha-Tablet/0.2").build()).execute().use { response ->
                    if (response.code == 429 || response.code in 500..599) {
                        if (attempt == 2) error("Provider unavailable (${response.code})")
                    } else {
                        check(response.isSuccessful) { "Provider HTTP ${response.code}" }
                        val stream = requireNotNull(response.body).byteStream()
                        val output = java.io.ByteArrayOutputStream()
                        val chunk = ByteArray(8192)
                        while (true) {
                            val count = stream.read(chunk)
                            if (count < 0) break
                            require(output.size() + count <= 2 * 1024 * 1024)
                            output.write(chunk, 0, count)
                        }
                        val bytes = output.toByteArray()
                        require(bytes.size <= 2 * 1024 * 1024)
                        return@withContext bytes.toString(Charsets.UTF_8)
                    }
                }
                delay(1000L shl attempt)
            }
            error("Provider unavailable")
        } finally { mutex.unlock() }
    }
    suspend fun discover(): List<PublicMarket> = Json.parseToJsonElement(get("products")).jsonArray.mapNotNull {
        val p = it.jsonObject
        val id = p["id"]?.jsonPrimitive?.content ?: return@mapNotNull null
        if (!id.matches(Regex("[A-Z0-9]{2,16}-EUR")) || p["status"]?.jsonPrimitive?.content != "online" || p["trading_disabled"]?.jsonPrimitive?.boolean == true) return@mapNotNull null
        PublicMarket(id, p["base_increment"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null, p["min_market_funds"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null).also {
            if (Decimal80.read(it.step).signum() <= 0 || Decimal80.read(it.minimum).signum() <= 0) return@mapNotNull null
        }
    }.sortedBy { it.id }
    suspend fun refresh(market: String): List<Candle> {
        require(market.matches(Regex("[A-Z0-9]{2,16}-EUR")))
        val end = Instant.ofEpochSecond(Instant.now().epochSecond / 3600 * 3600)
        val start = end.minusSeconds(240 * 3600)
        val values = CoinbaseParser.candles(get("products/$market/candles?granularity=3600&start=$start&end=$end"), market, Instant.now())
            .filter { Instant.parse(it.open_time) >= start && Instant.parse(it.close_time) <= end }
        require(values.zipWithNext().all { (a,b) -> Instant.parse(a.close_time) == Instant.parse(b.open_time) }) { "Missing native intervals: analysis unavailable" }
        require(values.isNotEmpty()) { "No complete provider candles" }
        db.history().save(HistoryRow(market, Json.encodeToString(values), Instant.now().toString()))
        return values
    }
    suspend fun cached(market: String): List<Candle> = db.history().get(market)?.let { Json.decodeFromString<List<Candle>>(it.payload) } ?: emptyList()
}
