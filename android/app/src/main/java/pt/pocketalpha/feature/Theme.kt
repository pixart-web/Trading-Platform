package pt.pocketalpha.feature

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

val Base = Color(0xFF050C14)
val Panel = Color(0xFF091621)
val Border = Color(0xFF213A4D)
val Accent = Color(0xFF2DD4A0)
val Muted = Color(0xFF8EA0B4)
val Negative = Color(0xFFFF4D67)
val Amber = Color(0xFFE8B84D)

@Composable fun PocketTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = darkColorScheme(primary = Accent, onPrimary = Base,
        secondary = Color(0xFF32C8DC), background = Base, surface = Panel,
        onBackground = Color(0xFFF0F5FA), onSurface = Color(0xFFF0F5FA),
        onSurfaceVariant = Muted, error = Negative, outline = Border,
        secondaryContainer = Color(0xFF0D2F49), onSecondaryContainer = Color(0xFFF0F5FA),
        primaryContainer = Color(0xFF0D2F49), surfaceTint = Color.Transparent,
        surfaceContainer = Panel, surfaceContainerHigh = Panel), content = content)
}
@Composable fun PocketCard(title: String, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp), color = Panel,
        border = BorderStroke(1.dp, Border)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}
@Composable fun Note(text: String, warning: Boolean = false) {
    Text(text, color = if (warning) Amber else Muted, style = MaterialTheme.typography.bodyMedium)
}
