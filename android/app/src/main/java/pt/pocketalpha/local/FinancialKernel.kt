package pt.pocketalpha.local

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode
import java.time.Instant
import kotlinx.serialization.Serializable

/** Bounded single-market, one-pending-order PAPER kernel. No provider or broker transport. */
object Decimal80 {
    val context = MathContext(80, RoundingMode.HALF_EVEN)
    fun read(value: String): BigDecimal {
        require(value.length <= 256)
        return BigDecimal(value).also { require(it.precision() <= 80 && it.scale() in -80..80) }
    }
    fun text(value: BigDecimal): String = value.stripTrailingZeros().toPlainString()
    fun add(a: BigDecimal, b: BigDecimal) = a.add(b, context)
    fun sub(a: BigDecimal, b: BigDecimal) = a.subtract(b, context)
    fun mul(a: BigDecimal, b: BigDecimal) = a.multiply(b, context)
    fun div(a: BigDecimal, b: BigDecimal) = a.divide(b, context)
}
private fun d(value: String) = Decimal80.read(value)
private fun BigDecimal.plus80(other: BigDecimal) = Decimal80.add(this, other)
private fun BigDecimal.minus80(other: BigDecimal) = Decimal80.sub(this, other)
private fun BigDecimal.times80(other: BigDecimal) = Decimal80.mul(this, other)
private fun BigDecimal.over80(other: BigDecimal) = Decimal80.div(this, other)

@Serializable data class LocalPolicy(
    val version: String, val fee: String, val spread: String, val slippage: String,
    val impact: String, val collar: String, val participation: String, val step: String,
    val minimumQuantity: String, val minimumNotional: String, val maximumOrder: String,
    val maximumExposure: String, val maximumDrawdown: String, val maximumDailyLoss: String,
    val maximumAge: Long, val maximumSpread: String, val lifetime: Long, val kill: Boolean,
) {
    fun validate() {
        require(version.isNotBlank() && version.length <= 128)
        listOf(fee, spread, step, minimumQuantity, minimumNotional, maximumOrder, maximumSpread)
            .forEach { require(d(it) > BigDecimal.ZERO) }
        listOf(slippage, impact).forEach { require(d(it) >= BigDecimal.ZERO) }
        listOf(participation, maximumExposure).forEach { require(d(it) > BigDecimal.ZERO && d(it) <= BigDecimal.ONE) }
        listOf(maximumDrawdown, maximumDailyLoss).forEach { require(d(it) > BigDecimal.ZERO && d(it) < BigDecimal.ONE) }
        require(d(collar) > BigDecimal.ZERO && d(collar) <= d("0.5"))
        require(d(fee) < d("10000"))
        require(d(spread).over80(d("2")).plus80(d(slippage)).plus80(d(impact)) < d("10000"))
        require(d(minimumQuantity).remainder(d(step)).compareTo(BigDecimal.ZERO) == 0)
        require(maximumAge in 0..2592000 && lifetime in 1..2592000)
    }
}
@Serializable data class PaperCommand(
    val id: String, val at: String, val kind: String,
    val side: String = "", val quantity: String = "0", val price: String = "0",
    val quoteClose: String = "", val barOpen: String = "", val volume: String = "0",
)
@Serializable data class LocalOrder(val id: String, val side: String, val remaining: String,
    val reference: String, val approvedAt: String)
@Serializable data class LocalBook(val cash: String, val quantity: String = "0", val basis: String = "0",
    val fees: String = "0", val realized: String = "0", val highWater: String,
    val dailyStart: String, val day: String, val at: String,
    val pending: LocalOrder? = null, val lastBarOpen: String? = null, val reason: String? = null, val halted: Boolean = false)

class FinancialKernel(private val policy: LocalPolicy) {
    init { policy.validate() }
    private fun validateBook(book: LocalBook) {
        listOf(book.cash, book.quantity, book.basis, book.fees).forEach { require(d(it) >= BigDecimal.ZERO) }
        require(d(book.highWater) > BigDecimal.ZERO && d(book.dailyStart) > BigDecimal.ZERO)
        d(book.realized)
        require(d(book.quantity).signum() != 0 || d(book.basis).signum() == 0)
    }
    fun genesis(capital: String, at: String): LocalBook {
        val initial = d(capital); require(initial > BigDecimal.ZERO && initial <= BigDecimal("1e30"))
        val time = Instant.parse(at)
        return LocalBook(cash = Decimal80.text(initial), highWater = Decimal80.text(initial),
            dailyStart = Decimal80.text(initial), day = time.toString().take(10), at = time.toString())
    }
    private fun reserve(price: BigDecimal): BigDecimal {
        val adverse = d(policy.spread).over80(d("2")).plus80(d(policy.slippage)).plus80(d(policy.impact)).over80(d("10000"))
        return price.times80(BigDecimal.ONE.plus80(d(policy.collar))).times80(BigDecimal.ONE.plus80(adverse))
            .times80(BigDecimal.ONE.plus80(d(policy.fee).over80(d("10000"))))
    }
    fun riskHalt(book: LocalBook, mark: BigDecimal): String? {
        require(mark > BigDecimal.ZERO && d(book.cash) >= BigDecimal.ZERO && d(book.quantity) >= BigDecimal.ZERO)
        val equity = d(book.cash).plus80(d(book.quantity).times80(mark))
        if (policy.kill || book.halted) return "KILL_SWITCH"
        if (equity <= BigDecimal.ZERO) return "BANKRUPTCY"
        if (d(book.highWater).minus80(equity).over80(d(book.highWater)) >= d(policy.maximumDrawdown)) return "DRAWDOWN_LIMIT"
        if (d(book.dailyStart).minus80(equity).over80(d(book.dailyStart)) >= d(policy.maximumDailyLoss)) return "DAILY_LOSS_LIMIT"
        return null
    }
    fun admit(book: LocalBook, side: String, quantity: String, price: String, quoteClose: String, at: String): String? {
        require(side in setOf("BUY", "SELL"))
        val now = Instant.parse(at); val close = Instant.parse(quoteClose)
        require(close <= now && now >= Instant.parse(book.at))
        val q = d(quantity); val mark = d(price); require(mark > BigDecimal.ZERO)
        val equity = d(book.cash).plus80(d(book.quantity).times80(mark))
        riskHalt(book, mark)?.let { return it }
        if (java.time.Duration.between(close, now).seconds > policy.maximumAge) return "STALE_DATA"
        if (d(policy.spread) > d(policy.maximumSpread)) return "SPREAD_LIMIT"
        if (book.pending != null) return "PENDING_ORDER_LIMIT"
        if (q < d(policy.minimumQuantity) || q.remainder(d(policy.step)).compareTo(BigDecimal.ZERO) != 0) return "INVALID_QUANTITY"
        if (q.times80(mark) < d(policy.minimumNotional)) return "MINIMUM_NOTIONAL"
        if (q.times80(reserve(mark)) > d(policy.maximumOrder)) return "ORDER_NOTIONAL_LIMIT"
        if (side == "BUY") {
            if (q.times80(reserve(mark)) > d(book.cash)) return "INSUFFICIENT_UNRESERVED_CASH"
            if (d(book.quantity).plus80(q).times80(mark.times80(BigDecimal.ONE.plus80(d(policy.collar)))) > equity.times80(d(policy.maximumExposure))) return "EXPOSURE_LIMIT"
        } else if (q > d(book.quantity)) return "SHORT_NOT_SUPPORTED"
        return null
    }
    fun apply(original: LocalBook, command: PaperCommand): LocalBook {
        validateBook(original)
        var book = original
        require(listOf(command.at, command.quoteClose, command.barOpen).all { it.length <= 64 })
        require(command.id.isNotBlank() && command.id.length <= 128)
        val now = Instant.parse(command.at); require(now >= Instant.parse(book.at))
        if (command.kind == "SUSPEND" || command.kind == "KILL")
            return book.copy(at = now.toString(), pending = null, reason = "OPERATOR_${command.kind}", halted = true)
        require(!book.halted) { "Explicit new experiment required after suspension/kill" }
        // No synthetic day rollover: daily counters require a separately qualified scheduler.
        require(now.toString().take(10) == book.day) { "DAY_BOUNDARY_REQUIRES_RECONCILIATION" }
        if (command.kind == "ORDER") {
            val reason = admit(book, command.side, command.quantity, command.price, command.quoteClose, command.at)
            return book.copy(at = now.toString(), reason = reason, pending = if (reason == null)
                LocalOrder(command.id, command.side, Decimal80.text(d(command.quantity)), command.price, command.at) else book.pending)
        }
        require(command.kind == "BAR")
        val close = Instant.parse(command.quoteClose); val open = Instant.parse(command.barOpen)
        require(open < close && close <= now && d(command.price) > BigDecimal.ZERO && d(command.volume) >= BigDecimal.ZERO)
        require(book.lastBarOpen == null || open > Instant.parse(book.lastBarOpen)) { "BAR_ALREADY_PROCESSED" }
        book = book.copy(lastBarOpen = open.toString())
        if (java.time.Duration.between(close, now).seconds > policy.maximumAge)
            return book.copy(at = now.toString(), pending = null, reason = "STALE_EXECUTION_DATA")
        val observedMark = d(command.price)
        book = book.copy(highWater = Decimal80.text(d(book.highWater).max(d(book.cash).plus80(d(book.quantity).times80(observedMark)))))
        riskHalt(book, observedMark)?.let { return book.copy(at = now.toString(), pending = null, reason = it, halted = true) }
        val order = book.pending ?: return book.copy(at = now.toString(), reason = "NO_PENDING_ORDER")
        val approved = Instant.parse(order.approvedAt)
        if (now >= approved.plusSeconds(policy.lifetime)) return book.copy(at = now.toString(), pending = null, reason = "ORDER_LIFETIME")
        if (open <= approved) return book.copy(at = now.toString(), reason = "NOT_CAUSALLY_ELIGIBLE")
        val mark = d(command.price); val reference = d(order.reference)
        if (mark < reference.times80(BigDecimal.ONE.minus80(d(policy.collar))) || mark > reference.times80(BigDecimal.ONE.plus80(d(policy.collar))))
            return book.copy(at = now.toString(), pending = null, reason = "PRICE_COLLAR")
        val rawCapacity = d(command.volume).times80(d(policy.participation))
        val capacity = rawCapacity.over80(d(policy.step)).setScale(0, RoundingMode.FLOOR).times80(d(policy.step))
        val q = d(order.remaining).min(capacity)
        if (q < d(policy.minimumQuantity) || q.times80(mark) < d(policy.minimumNotional)) return book.copy(at = now.toString(), reason = "NO_FILL_CAPACITY")
        val spread = mark.times80(d(policy.spread)).over80(d("20000"))
        val slippage = mark.times80(d(policy.slippage)).over80(d("10000"))
        val impact = mark.times80(d(policy.impact)).over80(d("10000")).times80(q.over80(d("2"))).over80(rawCapacity)
        val adverse = spread.plus80(slippage).plus80(impact)
        val fillPrice = if (order.side == "BUY") mark.plus80(adverse) else mark.minus80(adverse)
        val fee = fillPrice.times80(q).times80(d(policy.fee)).over80(d("10000"))
        var cash = d(book.cash); var qty = d(book.quantity); var basis = d(book.basis); var realized = d(book.realized)
        if (order.side == "BUY") {
            val debit = q.times80(fillPrice).plus80(fee)
            val nextEquity = cash.minus80(debit).plus80(qty.plus80(q).times80(mark))
            if (debit > cash || qty.plus80(d(order.remaining)).times80(mark) > nextEquity.times80(d(policy.maximumExposure)))
                return book.copy(at = now.toString(), pending = null, reason = "FILL_RISK_OR_CASH_LIMIT")
            cash = cash.minus80(debit); qty = qty.plus80(q); basis = basis.plus80(debit)
        } else {
            require(q <= qty)
            val allocated = if (q.compareTo(qty) == 0) basis else basis.times80(q).over80(qty)
            val proceeds = q.times80(fillPrice).minus80(fee)
            cash = cash.plus80(proceeds); qty = qty.minus80(q); basis = basis.minus80(allocated)
            realized = realized.plus80(proceeds.minus80(allocated))
        }
        val remaining = d(order.remaining).minus80(q)
        return book.copy(cash = Decimal80.text(cash), quantity = Decimal80.text(qty), basis = Decimal80.text(basis),
            realized = Decimal80.text(realized), fees = Decimal80.text(d(book.fees).plus80(fee)), at = now.toString(),
            highWater = Decimal80.text(d(book.highWater).max(cash.plus80(qty.times80(mark)))),
            pending = if (remaining.signum() == 0) null else order.copy(remaining = Decimal80.text(remaining)),
            reason = if (remaining.signum() == 0) "FILLED" else "PARTIALLY_FILLED").also { validateBook(it) }
    }
}
