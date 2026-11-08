package pt.pocketalpha.workspace

import pt.pocketalpha.core.Candle
import pt.pocketalpha.local.*
import java.time.Instant

/** Read-only research adapter. No forecast generation, orders or position ownership is invented. */
object StrategyReviewAdapter {
    fun review(candles: List<Candle>, market: String, quantity: String, asOf: String): TrendReview? {
        if (candles.isEmpty()) return null
        require(candles.size <= 1000 && candles.none { it.synthetic })
        require(candles.all { it.market_id == market && it.timeframe == "1h" && it.source == "coinbase-exchange-public" })
        val definition = TrendDefinition("native-trend-review-1",market,market.substringBeforeLast("-"),
            "coinbase-exchange-public","1h","4H","native-forecast-unavailable-1","technical-1.0.0",
            20,50,"0.001","0.001","0.10",7200)
        val closes = candles.map { CausalClose(it.close,it.close_time,it.received_at) }
        fun sma(period: Int) = LocalIndicators.calculate(closes,period,"SMA",asOf).lastOrNull()?.value
        val last = candles.last()
        val available = candles.maxOf { Instant.parse(it.received_at) }.toString()
        val technical = TrendTechnical(market,definition.source,"1h",definition.featureVersion,last.close_time,
            available,listOf(sma(20)),listOf(sma(50)))
        // Forecast projections are admitted only in isolated oracle tests at this stage.
        // Manual inventory has no strategy-owned stop/holding memory and must not be claimed as such.
        return LocalTrendReview.evaluate(definition,TrendInput(asOf,candles.map {
            TrendBar(it.market_id,it.source,it.timeframe,it.close,it.close_time,it.received_at)
        },technical,emptyList(),quantity,TrendMemory(definition.key())))
    }
}
