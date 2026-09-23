from pathlib import Path

p = Path('analysis/global_markets/universe.py')
text = p.read_text(encoding='utf-8')

old = '''    def _get_page(self, *, country: str, spec: ExchangeSpec, page: int, outputsize: int) -> dict:\n        common = {"page": page, "outputsize": outputsize, "format": "JSON", "type": "Common Stock"}\n        candidates: list[dict] = []\n\n        if spec.mic:\n            candidates.append(self._request({**common, "mic_code": spec.mic}))\n\n        country_name = get_country_pack(country).name\n        try:\n            candidates.append(self._request({**common, "country": country_name, "exchange": spec.label}))\n        except GlobalProviderError:\n            if not candidates:\n                raise\n\n        if not candidates:\n            raise GlobalProviderError(f"no reference-data lookup strategy for {country}/{spec.code}")\n        return max(candidates, key=self._payload_score)\n'''
new = '''    def _get_page(self, *, country: str, spec: ExchangeSpec, page: int, outputsize: int) -> dict:\n        common = {"page": page, "outputsize": outputsize, "format": "JSON", "type": "Common Stock"}\n\n        # A venue MIC is stronger identity evidence than a free-text exchange\n        # label. Never replace a valid MIC-scoped page merely because a broader\n        # country/exchange query happens to return more rows. Some vendor tiers\n        # ignore the exchange label and can otherwise contaminate one market\n        # with thousands of unrelated instruments.\n        if spec.mic:\n            try:\n                mic_payload = self._request({**common, "mic_code": spec.mic})\n                if self._payload_score(mic_payload)[0] > 0:\n                    return mic_payload\n            except GlobalProviderError:\n                pass\n\n        country_name = get_country_pack(country).name\n        try:\n            fallback = self._request({**common, "country": country_name, "exchange": spec.label})\n        except GlobalProviderError as exc:\n            raise GlobalProviderError(f"no reference-data lookup strategy for {country}/{spec.code}") from exc\n        return fallback\n'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit('get_page anchor not found')

old = '''        accepted_mics = set(spec.accepted_mics)\n        if accepted_mics and returned_mic and returned_mic not in accepted_mics:\n            return None\n'''
new = '''        accepted_mics = set(spec.accepted_mics)\n        # A configured exchange must be proven by MIC. Missing venue identity\n        # is not enough evidence for full-market ranking and is rejected.\n        if accepted_mics and not returned_mic:\n            return None\n        if accepted_mics and returned_mic not in accepted_mics:\n            return None\n'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit('MIC validation anchor not found')
p.write_text(text, encoding='utf-8')

p = Path('analysis/tests/test_global_universe_strict.py')
p.write_text('''from global_markets.country_packs import get_exchange\nfrom global_markets.universe import TwelveDataUniverseProvider\n\n\ndef test_configured_exchange_rejects_row_without_mic():\n    provider = TwelveDataUniverseProvider(api_key="demo")\n    item = provider._company_from_row(\n        country="IT",\n        spec=get_exchange("IT", "EURONEXT_MILAN"),\n        row={"symbol":"RACE","name":"Ferrari N.V.","type":"Common Stock","currency":"EUR","mic_code":""},\n    )\n    assert item is None\n\n\ndef test_mic_scoped_page_wins_over_larger_text_fallback():\n    provider = TwelveDataUniverseProvider(api_key="demo")\n    calls = []\n    def fake_request(params, endpoint="stocks"):\n        calls.append(dict(params))\n        if params.get("mic_code") == "XMIL":\n            return {"data":[{"symbol":"RACE","mic_code":"XMIL"}], "count":1}\n        return {"data":[{"symbol":f"X{i}"} for i in range(1000)], "count":1000}\n    provider._request = fake_request\n    payload = provider._get_page(country="IT", spec=get_exchange("IT","EURONEXT_MILAN"), page=1, outputsize=1000)\n    assert payload["count"] == 1\n    assert len(calls) == 1\n    assert calls[0].get("mic_code") == "XMIL"\n''', encoding='utf-8')
