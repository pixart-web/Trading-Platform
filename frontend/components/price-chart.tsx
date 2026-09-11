"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart, CandlestickSeries, HistogramSeries, BaselineSeries, ColorType, CrosshairMode,
  type IChartApi, type UTCTimestamp,
} from "lightweight-charts";
import type { Candle } from "@/lib/market-data";
import { zoneTimes, type Zone } from "@/lib/zones";

const NO_ZONES: Zone[] = [];

export function PriceChart({ candles, zones = NO_ZONES }: { candles: Candle[]; zones?: Zone[] }) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [hovered, setHovered] = useState<Candle | null>(null);
  const current = hovered ?? candles[candles.length - 1];

  useEffect(() => {
    if (!container.current) return;
    const chart = createChart(container.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#101820" }, textColor: "#9aabb9", fontSize: 12 },
      grid: { vertLines: { color: "#1b2732" }, horzLines: { color: "#1b2732" } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#2a3742" },
      timeScale: { borderColor: "#2a3742", timeVisible: true, secondsVisible: false },
      localization: { locale: "pt-PT" },
    });
    chartRef.current = chart;
    const prices = chart.addSeries(CandlestickSeries, {
      upColor: "#6cceaf", downColor: "#ec8f8f", borderVisible: false,
      wickUpColor: "#6cceaf", wickDownColor: "#ec8f8f",
      priceFormat: { type: "custom", formatter: (price: number) =>
        price.toLocaleString("pt-PT", { maximumSignificantDigits: 10 }), minMove: 0.00000001 },
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "", lastValueVisible: false, priceLineVisible: false,
    }, 1);
    chart.panes()[0].setStretchFactor(4);
    chart.panes()[1].setStretchFactor(1);
    prices.setData(candles.map(c => ({
      time: Date.parse(c.open_time) / 1000 as UTCTimestamp,
      open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close),
    })));
    volume.setData(candles.map(c => ({
      time: Date.parse(c.open_time) / 1000 as UTCTimestamp, value: Number(c.volume),
      color: Number(c.close) >= Number(c.open) ? "#407b6c" : "#865457",
    })));
    for (const zone of zones) {
      const times = zoneTimes(zone, candles);
      if (!times) continue;
      const support = zone.role === "SUPPORT";
      const color = support ? "#6cceaf" : "#ec8f8f";
      const band = chart.addSeries(BaselineSeries, {
        baseValue: { type: "price", price: Number(zone.lower) },
        topLineColor: color, topFillColor1: support ? "#6cceaf22" : "#ec8f8f22",
        topFillColor2: support ? "#6cceaf22" : "#ec8f8f22",
        bottomLineColor: color, bottomFillColor1: "transparent", bottomFillColor2: "transparent",
        baseLineVisible: false, priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false, lineWidth: 1, autoscaleInfoProvider: () => null,
      });
      band.setData(times.map(time => ({ time: time as UTCTimestamp, value: Number(zone.upper) })));
    }
    const byTime = new Map(candles.map(c => [Date.parse(c.open_time) / 1000, c]));
    chart.subscribeCrosshairMove(param => {
      setHovered(typeof param.time === "number" ? byTime.get(param.time) ?? null : null);
    });
    chart.timeScale().fitContent();
    return () => { chartRef.current = null; chart.remove(); };
  }, [candles, zones]);

  function zoom(factor: number) {
    const scale = chartRef.current?.timeScale();
    const range = scale?.getVisibleLogicalRange();
    if (range) {
      const center = (range.from + range.to) / 2, half = (range.to - range.from) * factor / 2;
      scale?.setVisibleLogicalRange({ from: center - half, to: center + half });
    }
  }

  return <section aria-label="Gráfico de preço e volume">
    <div className="chart-legend">
      <span>{current ? new Date(current.open_time).toISOString().replace("T", " ").slice(0, 16) : "—"} UTC</span>
      {current && <><span>A <b>{current.open}</b></span><span>Máx <b>{current.high}</b></span>
        <span>Mín <b>{current.low}</b></span><span>F <b>{current.close}</b></span><span>Vol <b>{current.volume}</b></span></>}
    </div>
    <div ref={container} className="chart-canvas" data-testid="price-chart" />
    <div className="chart-footer"><span>Preço · Volume · UTC</span>
      <div className="chart-actions">
        <button onClick={() => zoom(0.75)} aria-label="Aproximar gráfico">+</button>
        <button onClick={() => zoom(1.3)} aria-label="Afastar gráfico">−</button>
        <button onClick={() => chartRef.current?.timeScale().fitContent()}>Ajustar</button>
      </div>
    </div>
  </section>;
}
