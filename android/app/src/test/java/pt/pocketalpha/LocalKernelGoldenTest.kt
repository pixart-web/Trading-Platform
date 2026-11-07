package pt.pocketalpha

import org.junit.Test
import org.junit.Assert.*
import pt.pocketalpha.local.*
import kotlinx.serialization.json.*
import java.time.Instant

class LocalKernelGoldenTest {
    @Test fun pythonRiskAndPartialRoundTripMatchExactly() {
        verifyLocalGolden(requireNotNull(javaClass.getResource("/local-kernel-golden.json")).readText())
    }
    @Test fun moneyRoundingIs80DigitHalfEvenAndInvalidValuesFail() {
        val one = Decimal80.read("1")
        assertEquals("0." + "3".repeat(80), Decimal80.text(Decimal80.div(one, Decimal80.read("3"))))
        assertThrows(IllegalArgumentException::class.java) { Decimal80.read("1e99999") }
    }
}

class LocalKernelSafetyTest {
    private val json = Json
    private fun root() = json.parseToJsonElement(requireNotNull(javaClass.getResource("/local-kernel-golden.json")).readText()).jsonObject
    @Test fun causalityReplayAndDayBoundariesFailClosed() {
        val r = root(); val policy = json.decodeFromJsonElement<LocalPolicy>(r.getValue("policy"))
        val engine = FinancialKernel(policy)
        val start = r.getValue("start").jsonPrimitive.content
        val initial = engine.genesis("1000", start)
        val commands = r.getValue("commands").jsonArray.map { json.decodeFromJsonElement<PaperCommand>(it) }
        val ordered = engine.apply(initial, commands.first())
        val partial = engine.apply(ordered, commands[1])
        assertThrows(IllegalArgumentException::class.java) { engine.apply(partial, commands[1].copy(id = "repeat")) }
        assertThrows(IllegalArgumentException::class.java) { engine.apply(initial, commands.first().copy(quoteClose = "2099-01-01T00:00:00Z")) }
        assertThrows(IllegalArgumentException::class.java) { engine.apply(ordered, commands[1].copy(at = "2099-01-01T00:00:00Z")) }
        val stale = engine.apply(ordered, commands[1].copy(at = Instant.parse(commands[1].at).plusSeconds(policy.maximumAge).plusNanos(1000).toString()))
        assertEquals("STALE_EXECUTION_DATA", stale.reason)
        assertNull(stale.pending)
        assertEquals("1000", stale.cash)
        val killed = engine.apply(ordered, PaperCommand("stop", start, "KILL"))
        assertNull(killed.pending)
        assertThrows(IllegalArgumentException::class.java) { engine.apply(killed, commands[1]) }
        val drawdown = initial.copy(highWater = "10000")
        assertEquals("DRAWDOWN_LIMIT", engine.admit(drawdown, "BUY", "1", "100", start, start))
    }
    @Test fun indicatorFutureInputAndUnsortedHistoryAreRejected() {
        val bars = listOf(CausalClose("100", "2025-01-01T01:00:00Z", "2025-01-01T02:00:00Z"))
        assertThrows(IllegalArgumentException::class.java) { LocalIndicators.calculate(bars, 3, "SMA", "2025-01-01T01:00:00Z") }
        assertThrows(IllegalArgumentException::class.java) { LocalIndicators.calculate(bars + bars, 3, "EMA", "2025-01-01T03:00:00Z") }
    }
}
