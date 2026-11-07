package pt.pocketalpha.feature

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import pt.pocketalpha.core.Candle
import pt.pocketalpha.core.priceLabel
import pt.pocketalpha.core.axisPriceLabel
import java.math.BigDecimal
import kotlin.math.*

/** Rendering only: all indicators and analytical overlays must originate on the server. */
@Composable fun FinancialChart(candles: List<Candle>, modifier: Modifier = Modifier) {
    if (candles.isEmpty()) { Note("No candles stored for this market and interval."); return }
    var count by remember(candles) { mutableFloatStateOf(minOf(80, candles.size).toFloat()) }
    var offset by remember(candles) { mutableFloatStateOf(0f) }
    var verticalScale by remember(candles) { mutableFloatStateOf(1f) }
    var crosshair by remember(candles) { mutableIntStateOf(candles.lastIndex) }
    val shown = count.toInt().coerceIn(1, candles.size)
    val last = (candles.lastIndex - offset.toInt()).coerceIn(shown - 1, candles.lastIndex)
    val first = (last - shown + 1).coerceAtLeast(0)
    val visible = candles.subList(first, last + 1)
    val active = candles[crosshair.coerceIn(candles.indices)]
    Text("${active.open_time} UTC", style = MaterialTheme.typography.labelMedium, color = Muted)
    Text("O ${priceLabel(active.open)}  H ${priceLabel(active.high)}\nL ${priceLabel(active.low)}  C ${priceLabel(active.close)}  V ${priceLabel(active.volume)}",
        style = MaterialTheme.typography.bodySmall)
    Canvas(modifier.fillMaxWidth().height(280.dp)
        .semantics { contentDescription = "Candlestick chart, ${candles.size} stored bars. Selected candle close ${active.close}, time ${active.open_time}. Use previous and next buttons for accessible selection." }
        .pointerInput(candles) {
            detectTransformGestures { _, pan, zoom, _ ->
                count = (count / zoom).coerceIn(minOf(12, candles.size).toFloat(), candles.size.toFloat())
                offset = (offset + pan.x / 8).coerceIn(0f, (candles.size - count.toInt()).coerceAtLeast(0).toFloat())
                verticalScale = (verticalScale + pan.y / 500).coerceIn(0.5f, 3f)
            }
        }.pointerInput(first, last) {
            detectTapGestures(onTap = { crosshair = (first + (it.x / size.width * shown).toInt()).coerceIn(first, last) },
                onLongPress = { crosshair = (first + (it.x / size.width * shown).toInt()).coerceIn(first, last) })
        }) {
        val top = visible.maxOf { BigDecimal(it.high) }
        val bottom = visible.minOf { BigDecimal(it.low) }
        val range = (top - bottom).takeIf { it.signum() > 0 } ?: BigDecimal.ONE
        val middle = (top + bottom) / BigDecimal(2)
        val span = range.toDouble() * verticalScale
        val chartBottom = size.height * 0.72f
        val right = size.width - 62.dp.toPx()
        val step = right / visible.size
        fun y(value: String): Float = (chartBottom / 2 - ((BigDecimal(value) - middle).toDouble() / span * chartBottom * 0.85)).toFloat()
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.rgb(142, 160, 180); textSize = 10.dp.toPx() }
        repeat(5) { index ->
            val line = chartBottom * index / 4
            drawLine(Border, Offset(0f, line), Offset(size.width, line), 1f)
            val price = middle.toDouble() + (chartBottom / 2 - line) / chartBottom / 0.85 * span
            drawIntoCanvas { it.nativeCanvas.drawText(axisPriceLabel(price.toString()), right + 4, line + paint.textSize, paint) }
        }
        val maxVolume = visible.maxOf { BigDecimal(it.volume) }.takeIf { it.signum() > 0 } ?: BigDecimal.ONE
        visible.forEachIndexed { index, candle ->
            val x = (index + 0.5f) * step
            val color = if (BigDecimal(candle.close) >= BigDecimal(candle.open)) Accent else Negative
            drawLine(color, Offset(x, y(candle.high)), Offset(x, y(candle.low)), 1.dp.toPx())
            drawLine(color, Offset(x, y(candle.open)), Offset(x, y(candle.close) + 1), (step * 0.65f).coerceAtLeast(1f))
            val volumeHeight = (BigDecimal(candle.volume).divide(maxVolume, 12, java.math.RoundingMode.HALF_EVEN).toFloat() * size.height * 0.18f)
            drawLine(color.copy(alpha = 0.45f), Offset(x, size.height - 20.dp.toPx()),
                Offset(x, size.height - 20.dp.toPx() - volumeHeight), (step * 0.65f).coerceAtLeast(1f))
        }
        if (crosshair in first..last) {
            val x = (crosshair - first + 0.5f) * step
            drawLine(Muted, Offset(x, 0f), Offset(x, chartBottom), 1f)
            drawLine(Muted, Offset(0f, y(active.close)), Offset(right, y(active.close)), 1f)
        }
        drawIntoCanvas {
            it.nativeCanvas.drawText(visible.first().open_time.take(16), 0f, size.height, paint)
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = { crosshair = (crosshair - 1).coerceAtLeast(0) }, enabled = crosshair > 0) { Text("Previous bar") }
        OutlinedButton(onClick = { crosshair = (crosshair + 1).coerceAtMost(candles.lastIndex) }, enabled = crosshair < candles.lastIndex) { Text("Next bar") }
    }
    Note("Pinch to zoom · drag to pan/scale · tap for crosshair. Green: close ≥ open; red: close < open.")
    Note("Source: ${active.source} · received ${active.received_at}. ${if (active.source.contains("synthetic", true) || active.source.contains("fixture", true)) "SYNTHETIC RESEARCH DATA" else "Stored provider observation"}")
}
