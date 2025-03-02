from prometheus_client import start_http_server, Counter, Gauge

REQUESTS_TOTAL = Counter('http_requests_total', 'Total number of HTTP requests')
CACHE_SIZE = Gauge('cache_size', 'Current size of the cache')

def start_metrics_server():
    start_http_server(8000)

def handle_request():
    REQUESTS_TOTAL.inc()

def update_cache_size(size):
    CACHE_SIZE.set(size)
