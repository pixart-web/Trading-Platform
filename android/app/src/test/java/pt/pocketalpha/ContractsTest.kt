package pt.pocketalpha

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test
import pt.pocketalpha.core.*
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

class ContractsTest {
    private val json = Json { ignoreUnknownKeys = true }
    @Test fun endpointRejectsCredentialLeakAndCleartext() {
        listOf("http://example.test", "https://user:secret@example.test", // pragma: allowlist secret -- rejected credential-bearing URL fixture "https://example.test/?token=x",
            "https://example.test/#secret", "https://example.test/api/v1/", "file:///tmp/server").forEach {
            assertTrue("Must reject $it", runCatching { normalizeEndpoint(it) }.isFailure)
        }
        assertEquals("https://example.test/mobile/", normalizeEndpoint("https://example.test"))
        assertEquals("https://example.test:8443/mobile/", normalizeEndpoint("https://example.test:8443/mobile/"))
    }
    @Test fun financialDecimalsDoNotRoundThroughDouble() {
        assertEquals("9007199254740993.12", decimalLabel("9007199254740993.125"))
        assertEquals("—", decimalLabel("NaN"))
        assertEquals("—", decimalLabel(null))
    }
    @Test fun identifiersRejectTraversal() {
        listOf("../journal", "a/b", "http://venue", "x?token=a", "a#b").forEach {
            assertTrue(runCatching { safeId(it) }.isFailure)
        }
        assertEquals("coinbase:BTC-USD", safeId("coinbase:BTC-USD"))
    }
    @Test fun candleRejectsWrongIdentityAndImpossibleOHLC() {
        val candle = Candle("m", "1h", "2026-11-01T00:00:00Z", "2026-11-01T01:00:00Z",
            "100", "110", "90", "105", "2", "synthetic-test", "2026-11-01T01:00:01Z")
        candle.validate("m", "1h")
        assertTrue(runCatching { candle.validate("other", "1h") }.isFailure)
        assertTrue(runCatching { candle.copy(high = "95").validate("m", "1h") }.isFailure)
        assertTrue(runCatching { candle.copy(volume = "-1").validate("m", "1h") }.isFailure)
    }
    @Test fun unavailableAnalysisStillChecksSnapshotIdentity() {
        val value = json.parseToJsonElement("""{"market_id":"m","candle_timeframe":"1h","requested_as_of":"2026-11-01T00:00:00Z","status":"UNAVAILABLE"}""")
        validateAnalysis(value, "m", "1h", "2026-11-01T00:00:00Z")
        assertTrue(runCatching { validateAnalysis(value, "other", "1h", "2026-11-01T00:00:00Z") }.isFailure)
    }
    @Test fun typedMarketPaginationAndPermissionFailure() = runTest {
        MockWebServer().use { server ->
            val api = Retrofit.Builder().baseUrl(server.url("/mobile/"))
                .client(OkHttpClient.Builder().retryOnConnectionFailure(false).build())
                .addConverterFactory(json.asConverterFactory("application/json".toMediaType())).build().create(PocketApi::class.java)
            server.enqueue(MockResponse().setBody("""[{"market_id":"m","asset_id":"a","venue_id":"v","symbol":"BTC-USD","quote_currency":"USD"}]"""))
            assertEquals("m", api.markets("BTC", limit = 25, offset = 50).single().market_id)
            val request = server.takeRequest()
            assertEquals("/mobile/api/v1/markets?q=BTC&limit=25&offset=50", request.path)
            server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"expired"}"""))
            try { api.sessions(); fail("Must reject expired session") } catch (error: HttpException) { assertEquals(401, error.code()) }
        }
    }
    @Test fun smallAssetPricesRemainVisibleWithoutCurrencyRounding() {
        assertEquals("0.00000000123", priceLabel("0.0000000012300"))
        assertEquals("1.23E-9", axisPriceLabel("0.00000000123"))
        assertEquals("9007199254740993.12345", priceLabel("9007199254740993.12345"))
    }
}
