package pt.pocketalpha.local

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode
import java.time.Instant

data class CausalClose(val close: String, val closedAt: String, val receivedAt: String)
data class LocalFeature(val status: String, val value: String?, val reason: String?)
/** Bounded causal SMA/EMA only; does not replace the complete technical-intelligence engine. */
object LocalIndicators {
    private val numericPolicy = MathContext(50, RoundingMode.HALF_EVEN)
    private fun add(a: BigDecimal, b: BigDecimal) = a.add(b, numericPolicy)
    private fun sub(a: BigDecimal, b: BigDecimal) = a.subtract(b, numericPolicy)
    private fun mul(a: BigDecimal, b: BigDecimal) = a.multiply(b, numericPolicy)
    private fun div(a: BigDecimal, b: BigDecimal) = a.divide(b, numericPolicy)
    fun calculate(history: List<CausalClose>, period: Int, kind: String, asOf: String): List<LocalFeature> {
        require(history.size <= 1000 && period in 2..500 && kind in setOf("SMA", "EMA"))
        val cutoff = Instant.parse(asOf)
        var last: Instant? = null
        val values = history.map {
            val closed = Instant.parse(it.closedAt); val received = Instant.parse(it.receivedAt)
            require(closed <= received && received <= cutoff && (last == null || closed > last))
            last = closed
            Decimal80.read(it.close).also { value -> require(value > BigDecimal.ZERO) }
        }
        var current: BigDecimal? = null
        val alpha = div(BigDecimal(2), BigDecimal(period + 1))
        return values.indices.map { index ->
            if (index + 1 < period) LocalFeature("WARMUP", null, "INSUFFICIENT_HISTORY") else {
                val mean = div(values.subList(index - period + 1, index + 1)
                    .fold(BigDecimal.ZERO) { sum, value -> add(sum, value) }, BigDecimal(period))
                current = if (kind == "SMA" || current == null) mean else add(requireNotNull(current),
                    mul(alpha, sub(values[index], requireNotNull(current))))
                LocalFeature("READY", Decimal80.text(requireNotNull(current)), null)
            }
        }
    }
}
