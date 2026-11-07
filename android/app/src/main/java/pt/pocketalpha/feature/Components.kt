package pt.pocketalpha.feature

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.*
import pt.pocketalpha.core.*
import java.time.Instant

@Composable fun ResourceStatus(resource: Resource?) {
    if (resource?.loading == true) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Accent)
    resource?.error?.let { Note(it, true) }
    resource?.cachedAt?.let { Note("OFFLINE / STALE · cached ${Instant.ofEpochMilli(it)} · read-only", true) }
}
@Composable fun Record(value: JsonElement?, depth: Int = 0) {
    when (value) {
        null, JsonNull -> Note("Unavailable")
        is JsonObject -> value.entries.forEach { (key, item) ->
            if (item is JsonPrimitive || item is JsonNull) {
                Column(Modifier.fillMaxWidth()) {
                    Text(key.replace('_', ' '), style = MaterialTheme.typography.labelMedium, color = Muted)
                    Text(if (item is JsonNull) "Unavailable" else item.jsonPrimitive.content,
                        style = MaterialTheme.typography.bodyMedium)
                }
            } else {
                var open by rememberSaveable(key, depth) { mutableStateOf(false) }
                TextButton(onClick = { open = !open }) { Text("${if (open) "−" else "+"} ${key.replace('_', ' ')}") }
                if (open && depth < 10) Column(Modifier.padding(start = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { Record(item, depth + 1) }
            }
        }
        is JsonArray -> {
            var limit by remember(value) { mutableIntStateOf(20) }
            if (value.isEmpty()) Note("No records")
            value.take(limit).forEachIndexed { index, item ->
                Text("${index + 1}", color = Accent, style = MaterialTheme.typography.labelMedium)
                Record(item, depth + 1)
                HorizontalDivider(color = Border)
            }
            if (value.size > limit) TextButton(onClick = { limit += 20 }) { Text("Show 20 more (${value.size - limit} remaining)") }
        }
        is JsonPrimitive -> Text(value.content)
    }
}
@Composable fun Score(value: JsonElement?) {
    val score = value.text("score")?.toBigDecimalOrNull()?.toFloat()?.takeIf { it in 0f..100f }
    Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
        Box(Modifier.size(112.dp)) {
            Canvas(Modifier.fillMaxSize().semantics { contentDescription = "Pocket Score ${score?.toInt() ?: "unavailable"}; score is not a probability" }) {
                drawArc(Border, 0f, 360f, false, style = Stroke(10.dp.toPx()))
                if (score != null) drawArc(Accent, -90f, score * 3.6f, false, style = Stroke(10.dp.toPx(), cap = StrokeCap.Round))
            }
            Text(score?.let { decimalLabel(it.toString(), 0) } ?: "—",
                Modifier.align(androidx.compose.ui.Alignment.Center), style = MaterialTheme.typography.headlineLarge)
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(value.text("status") ?: "Unavailable", color = if (score == null) Amber else Accent)
            Note("Coverage ${value.text("coverage") ?: "—"}")
            Note(value.text("score_version") ?: "No score version")
        }
    }
    Note("Setup quality · not a probability or permission to trade")
    Record(value.field("components"))
}
