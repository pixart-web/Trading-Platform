package pt.pocketalpha

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import pt.pocketalpha.local.*
import java.time.Instant

class LocalStrategyReviewTest {
    private fun fixture() = requireNotNull(javaClass.getResource("/local-strategy-golden.json")).readText()
    @Test fun pythonStrategyDecisionsAndForecastHorizonsMatchExactly() { verifyStrategyGolden(fixture()) }
    @Test fun futureInputsDefinitionConflictsAndBoundsFailClosed() {
        val row = Json.parseToJsonElement(fixture()).jsonObject.getValue("cases").jsonArray.first().jsonObject
        val d = Json.decodeFromJsonElement<TrendDefinition>(row.getValue("definition"))
        val v = strategyInputFromFixture(row,d)
        assertThrows(IllegalArgumentException::class.java) { LocalTrendReview.evaluate(d,v.copy(memory = v.memory.copy(definitionKey = "0".repeat(64)))) }
        assertThrows(IllegalArgumentException::class.java) { LocalTrendReview.evaluate(d,v.copy(asOf = Instant.parse(v.asOf).minusNanos(1).toString())) }
        assertThrows(IllegalArgumentException::class.java) { LocalTrendReview.evaluate(d,v.copy(forecasts = listOf(v.forecasts.first().copy(generatedAt = "2099-01-01T00:00:00Z")))) }
        assertThrows(IllegalArgumentException::class.java) { LocalTrendReview.evaluate(d,v.copy(forecasts = listOf(v.forecasts.first().copy(expiresAt = v.asOf)))) }
        assertThrows(IllegalArgumentException::class.java) { LocalTrendReview.evaluate(d,v.copy(history = List(1001) { v.history.first() })) }
        assertThrows(IllegalArgumentException::class.java) { LocalTrendReview.evaluate(d,v.copy(history = v.history.asReversed())) }
        assertThrows(IllegalArgumentException::class.java) { LocalTrendReview.evaluate(d.copy(minimumTrend = "0"),v) }
        assertThrows(IllegalArgumentException::class.java) { LocalTrendReview.evaluate(d,v.copy(quantity = "2",memory = v.memory.copy(observedQuantity = "2",holdingUntil = v.asOf))) }
        assertThrows(IllegalArgumentException::class.java) { ForecastHorizonClock.expiry(v.asOf,"4h") }
        assertNotEquals(d.key(),d.copy(minimumReturn = "0.02").key())
    }
}
