# Mobile Step Sensor Integration (Android-first)

This backend now supports a mobile sensor-ingestion flow with priority:

1. `STEP_COUNTER` (hardware counter, recommended)
2. `STEP_DETECTOR`
3. `ACCELEROMETER` (fallback)

## Endpoint

`POST /device/steps/sync` (JWT required)

## Request payload

```json
{
  "device_id": "android-primary",
  "sensor_type": "STEP_COUNTER",
  "timezone": "Africa/Lagos",
  "event_time": "2026-02-24T12:15:30Z",
  "boot_id": "boot-2026-02-24-1",
  "total_steps_since_boot": 12345,
  "detected_steps_delta": 20,
  "step_delta": 20,
  "activity_minutes_delta": 5,
  "algorithm_version": "accel-v1",
  "confidence": 0.91,
  "record_date": "2026-02-24"
}
```

Notes:
- For `STEP_COUNTER`, send `total_steps_since_boot`.
- For `STEP_DETECTOR`/`ACCELEROMETER`, send `detected_steps_delta`.
- `step_delta` is a legacy fallback.
- Backend handles:
  - daily baseline reset,
  - device reboot/counter reset detection,
  - per-device state tracking.

## Response payload

```json
{
  "user_id": 2,
  "tenant_id": 1,
  "device_id": "android-primary",
  "sensor_type": "STEP_COUNTER",
  "processing_mode": "hardware_step_counter",
  "record_date": "2026-02-24",
  "accepted_step_delta": 42,
  "daily_steps_from_sensor": 5092,
  "total_steps": 5092,
  "total_activity_minutes": 28,
  "warning": "Daily baseline reset at midnight"
}
```

## Android mapping

- Sensor availability order:
  - `TYPE_STEP_COUNTER`
  - `TYPE_STEP_DETECTOR`
  - `TYPE_ACCELEROMETER`
- Suggested payload mapping:
  - `TYPE_STEP_COUNTER` -> `sensor_type=STEP_COUNTER`, `total_steps_since_boot`, `boot_id`
  - `TYPE_STEP_DETECTOR` -> `sensor_type=STEP_DETECTOR`, `detected_steps_delta`
  - accelerometer algorithm -> `sensor_type=ACCELEROMETER`, `detected_steps_delta`, `algorithm_version`, `confidence`

