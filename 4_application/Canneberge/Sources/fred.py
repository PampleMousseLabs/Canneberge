import requests


class FREDClient:
    def __init__(self, api_key: str, label_map: dict = None):
        self.api_key = api_key
        self.label_map = label_map or {}

    def fetch_series(self, series_id: str):
        url = (
            f"https://api.stlouisfed.org/fred/series/observations?"
            f"series_id={series_id}&api_key={self.api_key}"
            f"&sort_order=desc&limit=1&file_type=json"
        )
        headers = {'Accept': 'application/json'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if 'error_code' in data:
            return None

        observations = data.get('observations', [])
        if not observations:
            return None

        latest = observations[0]
        return {
            'SeriesID': series_id,
            'DisplayLabel': self.label_map.get(series_id, series_id),
            'AsOfDate': latest.get('date'),
            'LatestValue': latest.get('value')
        }

    def fetch_all(self, series_ids: list) -> list:
        results = []
        for sid in series_ids:
            result = self.fetch_series(sid)
            if result:
                results.append(result)
        return results