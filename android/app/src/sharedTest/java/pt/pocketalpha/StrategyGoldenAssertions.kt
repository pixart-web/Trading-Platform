package pt.pocketalpha

import kotlinx.serialization.json.*
import org.junit.Assert.*
import pt.pocketalpha.local.*
import java.time.Instant

fun strategyInputFromFixture(row: JsonObject, definition: TrendDefinition): TrendInput {
    val input = row.getValue("input").jsonObject
    val memory = input.getValue("memory").jsonObject
    // The fixture projects Python memory fields; native definition binding is computed locally.
    return Json.decodeFromJsonElement(JsonObject(input + ("memory" to JsonObject(memory +
        ("definitionKey" to JsonPrimitive(definition.key()))))))
}

fun verifyStrategyGolden(text: String) {
    val root = Json.parseToJsonElement(text).jsonObject
    assertEquals("SYNTHETIC_ENGINEERING_FIXTURE",root.getValue("origin").jsonPrimitive.content)
    assertEquals("native-trend-review-oracle-1",root.getValue("schema").jsonPrimitive.content)
    assertEquals(27,root.getValue("cases").jsonArray.size)
    root.getValue("cases").jsonArray.forEach { value ->
        val row = value.jsonObject
        val definition = Json.decodeFromJsonElement<TrendDefinition>(row.getValue("definition"))
        val input = strategyInputFromFixture(row,definition)
        val actual = LocalTrendReview.evaluate(definition,input)
        assertTrue(actual.researchOnly)
        val fields = mapOf("action" to actual.action,"reason" to actual.reason,"directional" to actual.directional,
            "forecastId" to actual.forecastId,"referencePrice" to actual.referencePrice,"invalidationPrice" to actual.invalidationPrice,
            "trend" to actual.trend,"expectedReturn" to actual.expectedReturn)
        row.getValue("expected").jsonObject.forEach { (name, value) ->
            val expected = value.jsonPrimitive.contentOrNull
            val message = "${row.getValue("name").jsonPrimitive.content}: $name"
            if (name == "expiresAt") assertEquals(message,Instant.parse(expected),Instant.parse(actual.expiresAt))
            else if (name in setOf("referencePrice","invalidationPrice","trend","expectedReturn") && expected != null)
                assertEquals(message,0,Decimal80.read(expected).compareTo(Decimal80.read(requireNotNull(fields[name]))))
            else assertEquals(message,expected,fields[name])
        }
        assertEquals(definition.key(),actual.definitionKey)
        assertEquals(Instant.parse(input.asOf),Instant.parse(actual.at))
    }
    assertEquals(26,root.getValue("horizons").jsonArray.size)
    root.getValue("horizons").jsonArray.forEach { value ->
        val row = value.jsonObject
        assertEquals(Instant.parse(row.getValue("expected").jsonPrimitive.content),Instant.parse(ForecastHorizonClock.expiry(
            row.getValue("at").jsonPrimitive.content,row.getValue("horizon").jsonPrimitive.content)))
    }
}
