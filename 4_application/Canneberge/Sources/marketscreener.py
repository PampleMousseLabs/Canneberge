import requests
from bs4 import BeautifulSoup
import re


class MarketScreenerClient:
    def resolve_slug(self, ticker):
        url = "https://www.marketscreener.com/async/search/quick"
        body = f"search={ticker}&search-type=1"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Origin': 'https://www.marketscreener.com',
            'Referer': 'https://www.marketscreener.com/'
        }
        response = requests.post(url, data=body, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if 'data' not in data:
            return None

        soup = BeautifulSoup(data['data'], 'html.parser')
        rows = soup.find_all('tr', attrs={'data-href': True})
        for row in rows:
            href = row.get('data-href', '')
            if '/quote/stock/' in href:
                slug = href.split('/quote/stock/')[1].rstrip('/')
                return slug
        return None

    def get_finance_html(self, slug):
        url = f"https://www.marketscreener.com/quote/stock/{slug}/finances/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.marketscreener.com/'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text

    def get_all_year_headers(self, html):
        ebitda_pos = html.upper().find('EBITDA')
        if ebitda_pos == -1:
            return []
        search_start = max(0, ebitda_pos - 12000)
        header_search = html[search_start:ebitda_pos]
        pattern = r'20[0-9]{2}'
        matches = re.findall(pattern, header_search)
        years = []
        seen = set()
        for match in matches:
            year = int(match)
            if 2015 <= year <= 2030 and year not in seen:
                years.append(str(year))
                seen.add(year)
        return years

    def get_row_values(self, html, label, expected_count):
        label_pos = html.upper().find(label.upper())
        if label_pos == -1:
            return []
        next_row_pos = html.find('bg-grey-light', label_pos + len(label))
        if next_row_pos == -1:
            next_row_pos = min(label_pos + 60000, len(html))
        row_segment = html[label_pos:next_row_pos]
        cleaned = re.sub(r'<sup[^>]*>.*?</sup>', '', row_segment, flags=re.DOTALL)
        pattern = r'>[\s]*(\-?[0-9][0-9,\.]*|\-)[\s]*<'
        matches = re.findall(pattern, cleaned)
        values = []
        for match in matches:
            values.append(match)
            if len(values) >= expected_count:
                break
        return values

    def get_row_values_ebit(self, html, expected_count):
        search_pos = 0
        ebit_pos = -1
        while True:
            pos = html.upper().find('EBIT', search_pos)
            if pos == -1:
                break
            if html[pos:pos+6].upper() != 'EBITDA':
                ebit_pos = pos
                break
            search_pos = pos + 1
        if ebit_pos == -1:
            return []
        next_row_pos = html.find('bg-grey-light', ebit_pos + 4)
        if next_row_pos == -1:
            next_row_pos = min(ebit_pos + 60000, len(html))
        row_segment = html[ebit_pos:next_row_pos]
        cleaned = re.sub(r'<sup[^>]*>.*?</sup>', '', row_segment, flags=re.DOTALL)
        pattern = r'>[\s]*(\-?[0-9][0-9,\.]*|\-)[\s]*<'
        matches = re.findall(pattern, cleaned)
        values = []
        for match in matches:
            values.append(match)
            if len(values) >= expected_count:
                break
        return values