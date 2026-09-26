# B30-QH01 static diagnosis

Status: execution limit exhausted; no rerun was made.

The single attempt failed at `erp/test_bos3_fasteners_seed.py:29-33`, before the later database-path comparison. The class has `@override_settings(BOS_DATA_MODE='demo')`. Django's `override_settings.enable()` creates `UserSettingsHolder(settings._wrapped)`; `UserSettingsHolder.SETTINGS_MODULE` is explicitly `None`. Therefore the guard `getattr(settings, 'SETTINGS_MODULE', None) != 'verification_settings'` is true even with the process environment correctly set to `DJANGO_SETTINGS_MODULE=verification_settings`.

Evidence paths:
- `D:\3\BOSDev\qa-scratch\bos3-fixture-final-20260927\seed-attempt-3.raw.log`
- `D:\3\BOSDev\qa-scratch\bos3-fixture-final-20260927\seed-attempt-3.native-exit.json`

The existing `erp/test_initial_import.py:26-31` already documents this behavior and unwraps `settings._wrapped.default_settings` before inspecting `SETTINGS_MODULE`. No custom test runner is configured by `manage.py`, `verification_settings.py`, or `demo_settings.py`.

Seed business behavior is not verified: the runner reported `Ran 0 tests` and exit code 1.
