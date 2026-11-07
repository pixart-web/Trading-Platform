package pt.pocketalpha

import android.graphics.Bitmap
import android.view.WindowManager
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.lifecycle.ViewModelProvider
import pt.pocketalpha.feature.WorkspaceViewModel
import pt.pocketalpha.core.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.MediaType.Companion.toMediaType
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/** Requires explicit disposable HTTPS server credentials; no production defaults or fixtures. */
class BackendWorkflowTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private fun waitText(text: String) {
        compose.waitUntil(30000) { compose.onAllNodesWithText(text, substring = true).fetchSemanticsNodes().isNotEmpty() }
    }
    @Test fun authenticatedWorkspaceUsesRealServerAndSurvivesRotation() {
        val arguments = InstrumentationRegistry.getArguments()
        val origin = arguments.getString("origin")
        assumeTrue("Disposable backend not configured", !origin.isNullOrEmpty())
        val username = requireNotNull(arguments.getString("username"))
        val password = requireNotNull(arguments.getString("password"))
        waitText("HTTPS server origin")
        compose.onNodeWithText("HTTPS server origin").performTextInput(requireNotNull(origin))
        compose.onNodeWithText("Operator login").performTextInput(username)
        compose.onNodeWithTag("login-list").performScrollToNode(hasText("Password"))
        compose.onNodeWithText("Password").performTextInput(password)
        compose.onNodeWithTag("login-list").performScrollToNode(hasText("Sign in securely"))
        compose.onNodeWithText("Sign in securely").performScrollTo().performClick()
        waitText("Market overview")
        waitText("SYNTHETIC-E2E ·")
        compose.onNodeWithTag("dashboard-grid").performScrollToIndex(3)
        waitText("Data quality: OK")
        compose.activity.runOnUiThread { compose.activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
        compose.waitForIdle()
        val output = File(compose.activity.getExternalFilesDir(null), "screenshots").apply { mkdirs() }
        val name = arguments.getString("screenshotName") ?: "standard"
        fun capture(suffix: String) {
            val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
            File(output, "$name-$suffix.png").outputStream().use { stream ->
                check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream))
            }
        }
        capture("dashboard")
        compose.onNodeWithTag("dashboard-grid").performScrollToIndex(0)
        compose.waitForIdle()
        val titleBounds = compose.onNodeWithText("Market overview").fetchSemanticsNode().boundsInRoot
        val subtitleBounds = compose.onNodeWithText("Intelligence, evidence and provenance from one shared backend").fetchSemanticsNode().boundsInRoot
        check(titleBounds.bottom <= subtitleBounds.top) { "Dashboard title overlaps its subtitle" }
        val searchBounds = compose.onNodeWithText("Search registered assets / markets").fetchSemanticsNode().boundsInRoot
        val searchButtonBounds = compose.onNodeWithText("Search").fetchSemanticsNode().boundsInRoot
        check(searchBounds.bottom <= searchButtonBounds.top) { "Market search controls overlap" }
        capture("overview")
        compose.onNodeWithText("Analyze", useUnmergedTree = false).performClick()
        waitText("Analyze")
        compose.onNodeWithText("Scanner", useUnmergedTree = false).performClick()
        waitText("Opportunity Scanner")
        compose.onNodeWithText("More", useUnmergedTree = false).performClick()
        compose.onAllNodesWithText("Watchlists").filter(hasAnyAncestor(hasTestTag("module-list"))).onFirst().performScrollTo().performClick()
        waitText("Create list")
        val listName = "Android E2E $name ${System.nanoTime()}"
        compose.onNodeWithText("List name").performTextInput(listName)
        compose.onNodeWithText("Create on server").performClick()
        compose.waitUntil(15000) { compose.onAllNodesWithText("Server confirmed the change.").fetchSemanticsNodes().isNotEmpty() }
        val workspace = ViewModelProvider(compose.activity)[WorkspaceViewModel::class.java]
        compose.waitUntil(15000) { workspace.resources.value["watchlists"]?.value.toString().contains(listName) }
        compose.onNodeWithTag("watchlists-list").performScrollToNode(hasText("$listName · revision 1"))
        waitText("$listName · revision 1")
        val list = workspace.resources.value["watchlists"]?.value.elements().first { it.text("name") == listName }
        val listId = requireNotNull(list.text("watchlist_id"))
        val cardTag = "watchlist:$listId"
        fun inCard(text: String) = hasText(text) and hasAnyAncestor(hasTestTag(cardTag))
        compose.onNode(inCard("Add SYNTHETIC-E2E")).performScrollTo().performClick()
        compose.waitUntil(15000) { workspace.resources.value["watchlists"]?.value.elements()
            .firstOrNull { it.text("watchlist_id") == listId }.field("members").elements().size == 1 }
        val renamed = "$listName renamed"
        compose.onNodeWithTag("watchlists-list").performScrollToNode(inCard("Rename list"))
        compose.onNode(inCard("Rename list")).performTextClearance()
        compose.onNode(inCard("Rename list")).performTextInput(renamed)
        compose.onNode(inCard("Save name")).performScrollTo().performClick()
        compose.waitUntil(15000) { workspace.resources.value["watchlists"]?.value.elements()
            .firstOrNull { it.text("watchlist_id") == listId }.text("name") == renamed }
        compose.onNodeWithTag("watchlists-list").performScrollToNode(inCard("Remove market"))
        compose.onNode(inCard("Remove market")).performClick()
        compose.waitUntil(15000) { workspace.resources.value["watchlists"]?.value.elements()
            .firstOrNull { it.text("watchlist_id") == listId }.field("members").elements().isEmpty() }
        compose.onNodeWithTag("watchlists-list").performScrollToNode(inCard("Delete list"))
        compose.onNode(inCard("Delete list")).performClick()
        compose.onNodeWithText("Delete", useUnmergedTree = false).performClick()
        compose.waitUntil(15000) { workspace.resources.value["watchlists"]?.value.elements()
            .none { it.text("watchlist_id") == listId } }
        compose.activityRule.scenario.recreate()
        waitText("POCKET ALPHA")
        workspace.document("revocation-sessions", "api/v1/auth/sessions")
        compose.waitUntil(15000) { workspace.resources.value["revocation-sessions"]?.value != null }
        val currentSession = workspace.resources.value["revocation-sessions"]?.value.elements()
            .first { it.text("current") == "true" }.text("session_id")!!
        val serializer = Json { ignoreUnknownKeys = true }
        fun client(token: String? = null): PocketApi {
            val http = OkHttpClient.Builder().retryOnConnectionFailure(false).addInterceptor { chain ->
                val request = chain.request().newBuilder()
                token?.let { request.header("Authorization", "Bearer $it") }
                chain.proceed(request.build())
            }.build()
            return Retrofit.Builder().baseUrl(requireNotNull(origin) + "/mobile/").client(http)
                .addConverterFactory(serializer.asConverterFactory("application/json".toMediaType()))
                .build().create(PocketApi::class.java)
        }
        runBlocking {
            val otherDevice = client().login(LoginRequest(username, password, "Disposable revocation device"))
            client(otherDevice.access_token).revoke(currentSession)
            client(otherDevice.access_token).revoke(otherDevice.session_id)
        }
        workspace.loadMarkets()
        waitText("HTTPS server origin")
        compose.onNodeWithText("Session expired or revoked. Sign in again.").assertExists()
    }
}
