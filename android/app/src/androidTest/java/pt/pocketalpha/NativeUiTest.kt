package pt.pocketalpha

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import org.junit.Rule
import org.junit.Test

class NativeUiTest {
    @get:Rule val compose = createAndroidComposeRule<LegacyClientActivity>()
    @Test fun secureLoginIsNativeAndAccessible() {
        compose.waitUntil(15000) { compose.onAllNodesWithText("Sign in securely").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("HTTPS server origin").assertExists().performTextInput("https://example.test")
        compose.onNodeWithText("Operator login").performTextInput("operator")
        compose.onNodeWithText("Password").performTextInput("test-only-password")
        compose.onNodeWithText("Sign in securely").assertIsEnabled()
        compose.onNodeWithText("Private operator access · TLS verification enabled\nReal-money trading is not authorized.").assertExists()
    }
}
