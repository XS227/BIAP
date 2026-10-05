from pathlib import Path

p = Path("analysis/global_markets/esma_firds_universe.py")
text = p.read_text(encoding="utf-8")

old = '''    def _resolve(self, identities: list[dict], *, country: str, exchange: str, native_mic: str) -> tuple[dict[str, dict], dict[str, str], dict[str, list[str]], dict]:\n        resolved: dict[str, dict] = {}\n'''
new = '''    def _resolve(self, identities: list[dict], *, native_mic: str):\n        # Keep the historical internal signature so existing provider subclasses\n        # and tests remain compatible. Country/exchange are unambiguously inferred\n        # from the configured FIRDS native MIC.\n        pair = next((key for key, mic in _NATIVE_MIC.items() if mic.upper() == native_mic.upper()), None)\n        country, exchange = pair if pair else ("", "")\n        resolved: dict[str, dict] = {}\n'''
if old not in text:
    raise SystemExit("new FIRDS resolver signature anchor missing")
text = text.replace(old, new, 1)

old = '''        resolved, missing, ambiguous, resolver_metadata = self._resolve(identities, country=country, exchange=exchange, native_mic=native_mic)\n        official_count = len(identities)\n'''
new = '''        resolution = self._resolve(identities, native_mic=native_mic)\n        # Older/custom subclasses may still return the historical three-tuple.\n        if len(resolution) == 3:\n            resolved, missing, ambiguous = resolution\n            resolver_metadata = {}\n        else:\n            resolved, missing, ambiguous, resolver_metadata = resolution\n        official_count = len(identities)\n'''
if old not in text:
    raise SystemExit("FIRDS list resolution anchor missing")
text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

p = Path("analysis/tests/test_global_euronext_live.py")
text = p.read_text(encoding="utf-8")
old = '''    resolved, missing, ambiguous, meta = provider._resolve(\n        [{"isin": "NL0000852564"}],\n        country="NL", exchange="EURONEXT_AMSTERDAM", native_mic="XAMS",\n    )\n'''
new = '''    resolved, missing, ambiguous, meta = provider._resolve(\n        [{"isin": "NL0000852564"}], native_mic="XAMS",\n    )\n'''
if old not in text:
    raise SystemExit("Euronext test resolver call anchor missing")
text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")
