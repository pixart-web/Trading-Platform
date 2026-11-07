package pt.pocketalpha

import org.junit.Test
import org.junit.Assert.*
import pt.pocketalpha.local.*
import kotlinx.serialization.json.*
import java.time.Instant

fun verifyLocalGolden(text: String) {
    val json = Json { encodeDefaults = true }
    val root = json.parseToJsonElement(text).jsonObject
    root.getValue("technical").jsonArray.forEach { item ->
        val row = item.jsonObject
        val history = row.getValue("history").jsonArray.map { bar ->
            val b = bar.jsonObject
            CausalClose(b.getValue("close").jsonPrimitive.content, b.getValue("closedAt").jsonPrimitive.content,
                b.getValue("receivedAt").jsonPrimitive.content)
        }
        val output = LocalIndicators.calculate(history, row.getValue("period").jsonPrimitive.int,
            row.getValue("kind").jsonPrimitive.content, row.getValue("asOf").jsonPrimitive.content)
        output.zip(row.getValue("expected").jsonArray).forEach { (actual, value) ->
            val expected = value.jsonObject
            assertEquals(expected.getValue("status").jsonPrimitive.content, actual.status)
            assertEquals(expected.getValue("reason").jsonPrimitive.contentOrNull, actual.reason)
            val amount = expected.getValue("value").jsonPrimitive.contentOrNull
            if (amount == null) assertNull(actual.value) else assertEquals(0, Decimal80.read(amount).compareTo(Decimal80.read(requireNotNull(actual.value))))
        }
    }
    root.getValue("decimals").jsonArray.forEach { value ->
        val row = value.jsonObject
        val left = Decimal80.read(row.getValue("left").jsonPrimitive.content)
        val right = Decimal80.read(row.getValue("right").jsonPrimitive.content)
        val result = if (row.getValue("operation").jsonPrimitive.content == "DIV") Decimal80.div(left, right) else Decimal80.add(left, right)
        assertEquals(0, Decimal80.read(row.getValue("expected").jsonPrimitive.content).compareTo(result))
    }
    val policy = json.decodeFromJsonElement<LocalPolicy>(root.getValue("policy"))
    val start = root.getValue("start").jsonPrimitive.content
    val engine = FinancialKernel(policy)
    var state = engine.genesis("1000", start)
    root.getValue("haltCases").jsonArray.forEach { value ->
        val row = value.jsonObject
        val book = state.copy(cash = row.getValue("cash").jsonPrimitive.content,
            highWater = row.getValue("highWater").jsonPrimitive.content,
            dailyStart = row.getValue("dailyStart").jsonPrimitive.content)
        assertEquals(row.getValue("reason").jsonPrimitive.contentOrNull, engine.riskHalt(book, Decimal80.read("100")))
    }
    root.getValue("risk").jsonArray.forEach { element ->
        val row = element.jsonObject
        var p = policy
        row.getValue("overrides").jsonObject.forEach { (key, value) ->
            p = when(key) {
                "kill_switch" -> p.copy(kill = value.jsonPrimitive.boolean)
                "maximum_order_notional" -> p.copy(maximumOrder = value.jsonPrimitive.content)
                "maximum_spread_bps" -> p.copy(maximumSpread = value.jsonPrimitive.content)
                "maximum_exposure_fraction" -> p.copy(maximumExposure = value.jsonPrimitive.content)
                else -> error("Unmapped oracle policy")
            }
        }
        val actual = FinancialKernel(p).admit(state, row.getValue("side").jsonPrimitive.content,
            row.getValue("quantity").jsonPrimitive.content, "100", start,
            Instant.parse(start).plusSeconds(row.getValue("age").jsonPrimitive.long).plusNanos(row.getValue("extraMicros").jsonPrimitive.long * 1000).toString())
        assertEquals(row.getValue("reason").jsonPrimitive.contentOrNull, actual)
    }
    root.getValue("commands").jsonArray.forEachIndexed { index, element ->
        state = engine.apply(state, json.decodeFromJsonElement<PaperCommand>(element))
        val expected = root.getValue("expected").jsonArray[index]
        if (expected != JsonNull) {
            val actual = mapOf("highWater" to state.highWater, "cash" to state.cash, "quantity" to state.quantity, "basis" to state.basis,
                "fees" to state.fees, "realized" to state.realized)
            expected.jsonObject.forEach { (key, value) ->
                assertEquals("exact $key after event $index", 0,
                    Decimal80.read(value.jsonPrimitive.content).compareTo(Decimal80.read(actual.getValue(key))))
            }
        }
    }
    assertEquals("0", state.quantity)
    assertEquals("0", state.basis)
    assertNull(state.pending)
}
