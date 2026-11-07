package pt.pocketalpha.core

import kotlinx.serialization.json.JsonElement
import retrofit2.http.*

interface PocketApi {
    @POST("api/v1/auth/login") suspend fun login(@Body body: LoginRequest): Tokens
    @POST("api/v1/auth/refresh") suspend fun refresh(@Body body: RefreshRequest): Tokens
    @POST("api/v1/auth/step-up") suspend fun stepUp(@Body body: kotlinx.serialization.json.JsonObject)
    @GET("api/v1/auth/sessions") suspend fun sessions(): JsonElement
    @DELETE("api/v1/auth/sessions/{id}") suspend fun revoke(@Path("id") id: String)
    @GET("api/v1/markets") suspend fun markets(@Query("q") query: String, @Query("limit") limit: Int = 50,
                                              @Query("offset") offset: Int = 0): List<Market>
    @GET("api/v1/markets/{id}/candles/latest") suspend fun latestCandle(@Path("id") id: String, @Query("timeframe") frame: String): JsonElement
    @GET("api/v1/markets/{id}/candles") suspend fun candles(@Path("id") id: String,
        @QueryMap query: Map<String, String>): CandlePage
    @GET("api/v1/markets/{id}/analysis/snapshots") suspend fun snapshots(@Path("id") id: String, @Query("timeframe") frame: String, @Query("limit") limit: Int = 20): JsonElement
    @GET("api/v1/markets/{id}/analysis") suspend fun analysis(@Path("id") id: String,
        @QueryMap query: Map<String, String>): JsonElement
    @GET("api/v1/watchlists") suspend fun watchlists(): List<Watchlist>
    @POST("api/v1/watchlists") suspend fun createWatchlist(@Body body: JsonElement): Watchlist
    @DELETE("api/v1/watchlists/{id}") suspend fun deleteWatchlist(@Path("id") id: String, @Query("expected_revision") revision: Int)
    @PATCH("api/v1/watchlists/{id}") suspend fun renameWatchlist(@Path("id") id: String,
        @Body body: JsonElement): Watchlist
    @PUT("api/v1/watchlists/{id}/markets/{market}") suspend fun addMember(@Path("id") id: String,
        @Path("market") market: String, @Body body: JsonElement): Watchlist
    @DELETE("api/v1/watchlists/{id}/markets/{market}") suspend fun removeMember(@Path("id") id: String,
        @Path("market") market: String, @Query("expected_revision") revision: Int): Watchlist
    @POST("api/v1/scans") suspend fun scan(@Body body: JsonElement): JsonElement
    @GET("api/v1/portfolios") suspend fun portfolios(): List<Portfolio>
    @POST("api/v1/portfolios") suspend fun createPortfolio(@Body body: JsonElement): Portfolio
    @POST("api/v1/portfolios/{id}/entries") suspend fun recordEntry(@Path("id") id: String,
        @Body body: JsonElement): JsonElement
    // Read-only advanced contracts are fixed by the caller's ScreenContract, never arbitrary URLs.
    @GET suspend fun document(@Url path: String, @QueryMap query: Map<String, String> = emptyMap()): JsonElement
}
