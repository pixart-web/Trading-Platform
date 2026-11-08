package pt.pocketalpha.local

import java.math.BigDecimal
import java.math.RoundingMode
import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import java.time.ZoneOffset
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/** Research decision projection only. No portfolio allocation, order, ledger or broker port. */
@Serializable data class TrendDefinition(
    val version: String, val market: String, val asset: String, val source: String,
    val timeframe: String, val horizon: String, val modelVersion: String, val featureVersion: String,
    val fastPeriod: Int, val slowPeriod: Int, val minimumTrend: String, val minimumReturn: String,
    val invalidation: String, val maximumAge: Long,
) {
    fun key(): String = MessageDigest.getInstance("SHA-256").digest(
        Json.encodeToString(this).toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    fun validate() {
        listOf(version,market,asset,source,modelVersion,featureVersion).forEach {
            require(it.matches(Regex("[A-Za-z0-9_.:-]{1,128}")))
        }
        require(featureVersion == "technical-1.0.0")
        require(timeframe in setOf("1m","5m","15m","30m","1h","4h","1d","1w"))
        ForecastHorizonClock.expiry("2025-01-01T00:00:00Z", horizon)
        require(fastPeriod in 2..499 && slowPeriod in 3..500 && fastPeriod < slowPeriod)
        listOf(minimumTrend,minimumReturn).forEach {
            val value = Decimal80.read(it)
            require(value > BigDecimal.ZERO && value <= BigDecimal.ONE && value.precision() <= 38 && value.scale() <= 24)
        }
        require(Decimal80.read(invalidation) > BigDecimal.ZERO && Decimal80.read(invalidation) < BigDecimal.ONE)
        require(Decimal80.read(invalidation).precision() <= 38 && Decimal80.read(invalidation).scale() <= 18)
        require(maximumAge in 0..2592000)
    }
}
@Serializable data class TrendBar(val market: String, val source: String, val timeframe: String,
    val close: String, val closedAt: String, val receivedAt: String)
@Serializable data class TrendTechnical(val market: String, val source: String, val timeframe: String,
    val featureVersion: String, val barClose: String, val availableAt: String,
    val fastValues: List<String?>, val slowValues: List<String?>)
/** Projection of validated upstream forecasts for mechanical research tests, not a forecast producer.
 * The operational adapter supplies no forecasts until the full native evidence contract is qualified. */
@Serializable data class TrendForecastProjection(val id: String, val market: String, val asset: String,
    val timeframe: String, val horizon: String, val modelVersion: String, val featureVersion: String,
    val status: String, val generatedAt: String, val expiresAt: String, val expectedReturn: String?)
@Serializable data class TrendMemory(val definitionKey: String, val observedQuantity: String = "0",
    val invalidationPrice: String? = null, val holdingUntil: String? = null)
@Serializable data class TrendInput(val asOf: String, val history: List<TrendBar>, val technical: TrendTechnical,
    val forecasts: List<TrendForecastProjection>, val quantity: String, val memory: TrendMemory)
@Serializable data class TrendReview(val action: String, val reason: String, val referencePrice: String?,
    val invalidationPrice: String?, val expiresAt: String, val directional: String?, val trend: String?,
    val expectedReturn: String?, val forecastId: String?, val at: String, val definitionKey: String) {
    val researchOnly: Boolean get() = true
}

/** Forecast horizons are separate from candle resolution; calendar months clamp in UTC. */
object ForecastHorizonClock {
    private val seconds = mapOf("1H" to 3600L,"4H" to 14400L,"8H" to 28800L,"12H" to 43200L,
        "24H" to 86400L,"2D" to 172800L,"3D" to 259200L,"7D" to 604800L,
        "14D" to 1209600L,"30D" to 2592000L,"90D" to 7776000L)
    fun expiry(at: String, horizon: String): String {
        val instant = Instant.parse(at)
        return if (horizon in seconds) instant.plusSeconds(seconds.getValue(horizon)).toString() else {
            require(horizon == "6M" || horizon == "12M")
            instant.atOffset(ZoneOffset.UTC).plusMonths(if (horizon == "6M") 6 else 12).toInstant().toString()
        }
    }
}

object LocalTrendReview {
    private fun amount(value: String) = Decimal80.read(value)
    fun evaluate(definition: TrendDefinition, input: TrendInput): TrendReview {
        definition.validate()
        // Snapshot caller-owned collections before evaluating. Results retain only immutable values.
        val bars = input.history.toList()
        val forecasts = input.forecasts.toList()
        val technical = input.technical.copy(fastValues = input.technical.fastValues.toList(), slowValues = input.technical.slowValues.toList())
        val asOf = Instant.parse(input.asOf)
        val memory = input.memory
        require(memory.definitionKey == definition.key()) { "Strategy memory definition mismatch" }
        require(bars.size <= 1000 && forecasts.size <= 64 && technical.fastValues.size <= 16 && technical.slowValues.size <= 16)
        require(amount(input.quantity).signum() >= 0 && amount(memory.observedQuantity).signum() >= 0)
        memory.invalidationPrice?.let { require(amount(it).signum() > 0) }
        memory.holdingUntil?.let(Instant::parse)
        require(Instant.parse(technical.availableAt) <= asOf) { "Future technical evidence" }
        require(Instant.parse(technical.barClose) <= Instant.parse(technical.availableAt))
        bars.forEach { bar ->
            require(amount(bar.close).signum() > 0)
            require(Instant.parse(bar.closedAt) <= Instant.parse(bar.receivedAt) && Instant.parse(bar.receivedAt) <= asOf) { "Future market evidence" }
        }
        require(bars.zipWithNext().all { (a,b) -> Instant.parse(a.closedAt) < Instant.parse(b.closedAt) })
        forecasts.forEach { forecast ->
            require(forecast.status in setOf("AVAILABLE","UNAVAILABLE"))
            require(Instant.parse(forecast.generatedAt) <= asOf && asOf < Instant.parse(forecast.expiresAt)) { "Unavailable forecast time" }
            require(Instant.parse(forecast.expiresAt) == Instant.parse(ForecastHorizonClock.expiry(forecast.generatedAt,forecast.horizon)))
            require((forecast.expectedReturn != null) == (forecast.status == "AVAILABLE"))
            forecast.expectedReturn?.let { require(amount(it) >= BigDecimal.ONE.negate()) }
        }
        var action = "NO_TRADE"
        var reason = "MISSING_EVIDENCE"
        var price: BigDecimal? = null
        var stop: BigDecimal? = null
        var directional: String? = null
        var trend: BigDecimal? = null
        var expected: BigDecimal? = null
        var forecastId: String? = null
        val valid = bars.isNotEmpty() && technical.market == definition.market && technical.source == definition.source &&
            technical.timeframe == definition.timeframe && technical.featureVersion == definition.featureVersion &&
            bars.last().let { last -> last.market == definition.market && last.source == definition.source && last.timeframe == definition.timeframe &&
                Instant.parse(last.closedAt) == Instant.parse(technical.barClose) &&
                Duration.between(Instant.parse(last.closedAt),asOf) <= Duration.ofSeconds(definition.maximumAge) } &&
            bars.all { it.market == definition.market && it.source == definition.source && it.timeframe == definition.timeframe }
        if (valid) {
            price = amount(bars.last().close)
            stop = if (amount(memory.observedQuantity).signum() > 0) memory.invalidationPrice?.let(::amount)
                else Decimal80.mul(price,Decimal80.sub(BigDecimal.ONE,amount(definition.invalidation)))
            if (amount(input.quantity).signum() > 0 && amount(memory.observedQuantity).signum() > 0) {
                if (memory.holdingUntil != null && asOf >= Instant.parse(memory.holdingUntil)) { action = "EXIT_LONG"; reason = "HORIZON_EXPIRED" }
                else if (stop != null && price <= stop) { action = "EXIT_LONG"; reason = "PRICE_INVALIDATION" }
            }
            val candidates = forecasts.filter { it.market == definition.market && it.asset == definition.asset &&
                it.timeframe == definition.timeframe && it.horizon == definition.horizon && it.modelVersion == definition.modelVersion &&
                it.featureVersion == definition.featureVersion && it.status == "AVAILABLE" }
            val latest = candidates.maxOfOrNull { Instant.parse(it.generatedAt) }
            val current = candidates.filter { Instant.parse(it.generatedAt) == latest }
            val fast = technical.fastValues.singleOrNull()?.let(::amount)
            val slow = technical.slowValues.singleOrNull()?.let(::amount)
            if (current.size == 1 && fast != null && slow != null && fast.signum() > 0 && slow.signum() > 0) {
                val forecast = current.single()
                forecastId = forecast.id
                trend = Decimal80.sub(Decimal80.div(fast,slow),BigDecimal.ONE).setScale(24,RoundingMode.HALF_EVEN)
                expected = amount(requireNotNull(forecast.expectedReturn)).setScale(24,RoundingMode.HALF_EVEN)
                val longCase = trend >= amount(definition.minimumTrend) && expected >= amount(definition.minimumReturn)
                val shortCase = trend <= amount(definition.minimumTrend).negate() && expected <= amount(definition.minimumReturn).negate()
                directional = when { longCase && !shortCase -> "LONG"; shortCase && !longCase -> "SHORT"; else -> "NO_TRADE" }
                if (action == "NO_TRADE") {
                    if (amount(input.quantity).signum() > 0) {
                        if (directional == "SHORT") { action = "EXIT_LONG"; reason = "TREND_INVALIDATION" } else reason = "HOLD_OR_NO_TRADE"
                    } else if (directional == "LONG") { action = "ENTER_LONG"; reason = "LONG_CASE_ONLY" }
                    else reason = when { longCase && shortCase -> "CONFLICTING_CASES"; shortCase -> "SHORT_CASE_ONLY"; else -> "NO_CASE_PASSED" }
                }
            }
        }
        require(action == "NO_TRADE" || (price != null && stop != null)) { "Action requires reference and invalidation evidence" }
        return TrendReview(action,reason,price?.let(Decimal80::text),stop?.let(Decimal80::text),
            ForecastHorizonClock.expiry(input.asOf,definition.horizon),directional,trend?.let(Decimal80::text),
            expected?.let(Decimal80::text),forecastId,asOf.toString(),definition.key())
    }
}
