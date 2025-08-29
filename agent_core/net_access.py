import requests
from bs4 import BeautifulSoup

def fetch_url(url):
    try:
        response = requests.get(url, timeout=10)
        return response.text
    except Exception as e:
        return f"[ERROR] {e}"

def scrape_text(url):
    html = fetch_url(url)
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text()

def simple_api_pull(url):
    try:
        response = requests.get(url, timeout=5)
        return response.json()
    except Exception as e:
        return f"[ERROR] {e}"

def post_data(url, payload):
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.json()
    except Exception as e:
        return f"[ERROR] {e}"
