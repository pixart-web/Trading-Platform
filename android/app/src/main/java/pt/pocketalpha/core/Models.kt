package pt.pocketalpha.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.*
import java.math.BigDecimal
import java.time.Instant

@Serializable data class LoginRequest(val username: String, val password: String, val device_name: String)
@Serializable data class RefreshRequest(val refresh_token: String)
@Serializable data class Tokens(
    val access_token: String, val refresh_token: String, val session_id: String,
    val user_id: String, val refresh_expires_at: String, val expires_in: Int = 300, val token_type: String = "Bearer"
)
@Serializable data class StoredSession(val refresh_token: String, val session_id: String, val user_id: String, val refresh_expires_at: String)
@Serializable data class Market(
    val market_id: String, val asset_id: String, val venue_id: String,
    val symbol: String, val quote_currency: String, val active: Boolean = true
)
@Serializable data class Candle(
    val market_id: String, val timeframe: String, val open_time: String, val close_time: String,
    val open: String, val high: String, val low: String, val close: String, val volume: String,
    val source: String, val received_at: String, val synthetic: Boolean = false
) {
    fun validate(market: String, frame: String) {
        require(market_id == market && timeframe == frame) { "Candle identity mismatch" }
        val values = listOf(open, high, low, close, volume).map { BigDecimal(it) }
        require(values.all { it.signum() >= 0 } && values.take(4).all { it.signum() > 0 })
        require(values[1] >= maxOf(values[0], values[3]) && values[2] <= minOf(values[0], values[3]))
        require(Instant.parse(close_time) > Instant.parse(open_time))
    }
}
@Serializable data class CandlePage(
    val candles: List<Candle>, val quality: JsonObject, val truncated: Boolean,
    val next_start: String? = null
)
@Serializable data class Watchlist(
    val watchlist_id: String, val name: String, val revision: Int, val created_at: String,
    val updated_at: String, val members: List<Member> = emptyList()
)
@Serializable data class Member(val member_id: String, val market_id: String, val asset_id: String,
                                val candle_timeframe: String, val added_at: String)
@Serializable data class Portfolio(val portfolio_id: String, val name: String, val base_currency: String,
                                    val revision: Int, val valuation_timeframe: String)

data class Resource(val value: JsonElement? = null, val loading: Boolean = false,
                    val error: String? = null, val cachedAt: Long? = null) {
    val offline: Boolean get() = cachedAt != null
}

val Timeframes = linkedMapOf("1m" to 60L, "5m" to 300L, "15m" to 900L, "30m" to 1800L,
    "1h" to 3600L, "4h" to 14400L, "1d" to 86400L, "1w" to 604800L)
val Horizons = listOf("1H", "4H", "8H", "12H", "24H", "2D", "3D", "7D", "14D", "30D", "90D", "6M", "12M")
fun JsonElement?.field(name: String): JsonElement? = (this as? JsonObject)?.get(name)?.takeUnless { it is JsonNull }
fun JsonElement?.text(name: String): String? = (field(name) as? JsonPrimitive)?.contentOrNull
fun JsonElement?.elements(): List<JsonElement> = (this as? JsonArray)?.toList() ?: emptyList()
fun decimalLabel(value: String?, digits: Int = 2): String = value?.let {
    runCatching { BigDecimal(it).setScale(digits, java.math.RoundingMode.HALF_EVEN).toPlainString() }.getOrNull()
} ?: "—"

fun validateAnalysis(value: JsonElement, market: String, frame: String, asOf: String) {
    require(value.text("market_id") == market && value.text("candle_timeframe") == frame)
    require(Instant.parse(value.text("requested_as_of")) == Instant.parse(asOf))
    if (value.text("status") == "UNAVAILABLE") return
    require(value.text("schema_version") == "analyze-response-1.0.0")
    val report = value.field("report") ?: error("Missing report")
    require(report.text("market_id") == market && report.text("candle_timeframe") == frame)
    require(Instant.parse(report.text("as_of")) == Instant.parse(asOf))
    val horizons = report.field("horizons").elements()
    require(horizons.map { it.text("horizon") } == Horizons)
    horizons.forEach { item ->
        listOf("forecast", "directional", "opportunity").forEach { name ->
            item.field(name)?.let { artifact ->
                require(artifact.text("market_id") == market && artifact.text("candle_timeframe") == frame)
                require(artifact.text("asset_id") == report.text("asset_id"))
                require(artifact.text("horizon") == item.text("horizon"))
            }
        }
        item.field("opportunity")?.let {
            require(it.text("analysis_id") == item.field("directional").text("analysis_id"))
            require(it.text("forecast_id") == item.field("forecast").text("forecast_id"))
        }
    }
}

fun validateScan(value: JsonElement, frame: String, horizon: String, asOf: String) {
    require(value.text("schema_version") == "scan-report-1.0.0")
    require(value.text("candle_timeframe") == frame && value.text("horizon") == horizon)
    require(Instant.parse(value.text("as_of")) == Instant.parse(asOf))
    val groups = value.field("groups").elements()
    val ranked = groups.flatMap { it.field("entries").elements() }
    val excluded = value.field("excluded").elements()
    val ids = ranked.map { it.field("market").text("market_id") } + excluded.map { it.field("market").text("market_id") }
    require(ids.size == value.text("universe_size")?.toInt() && ids.distinct().size == ids.size)
    require((ranked.isNotEmpty()) == (value.text("status") == "RESULTS"))
    groups.forEach { group -> group.field("entries").elements().forEachIndexed { index, entry ->
        val opportunity = entry.field("opportunity")
        require(entry.text("rank")?.toInt() == index + 1)
        require(opportunity.text("status") == "AVAILABLE" && opportunity.text("eligible") == "true")
        require(opportunity.text("market_id") == entry.field("market").text("market_id"))
        require(opportunity.text("policy_version") == group.text("policy_version"))
        require(opportunity.text("policy_hash") == group.text("policy_hash"))
        require(opportunity.text("horizon") == horizon && opportunity.text("candle_timeframe") == frame)
        require(Instant.parse(opportunity.text("as_of")) == Instant.parse(asOf))
    } }
}

fun priceLabel(value: String?): String = value?.toBigDecimalOrNull()?.stripTrailingZeros()?.toPlainString() ?: "—"
fun axisPriceLabel(value: String): String {
    val number = value.toBigDecimalOrNull()?.round(java.math.MathContext(6))?.stripTrailingZeros() ?: return "—"
    return number.toPlainString().takeIf { it.length <= 10 } ?: number.toEngineeringString()
}
