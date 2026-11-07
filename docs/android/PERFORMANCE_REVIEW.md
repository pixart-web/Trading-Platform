# Android performance review

Implemented bounds: 500 candles per viewport request; market pages of 50 with at most 250 retained markets; four MiB per HTTP response; at most 64 Room snapshots, each stored only if no larger than one MiB; at most 24 dynamic ViewModel resources plus eight core resources. Chart drawing uses only visible bars; financial values use decimal strings/BigDecimal and convert to floating point only for rendering. Lists/grids are lazy; WorkManager requires connectivity and adequate battery and uses backoff.

Measured build evidence is in TEST_EVIDENCE.md. APK/AAB size is build-specific and is not a memory/startup/frame-rate benchmark. No cold-start percentile, frame-jank rate, battery consumption or production latency result has been measured. No invented performance score is provided.

Open acceptance work: Android Studio/Perfetto profiling on real hardware, large-report memory pressure, chart gesture stress and long sessions; Room/WAL disk-growth behavior; font-scale/tablet landscape; genuine process death and low-memory recovery. Native financial overlays and server job streams must be profiled once implemented. The current client is not performance-qualified for production.
