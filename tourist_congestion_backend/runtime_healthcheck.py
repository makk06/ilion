"""Container probe: no third-party calls and no application credentials."""
import os
import urllib.request

with urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/healthz', timeout=4) as response:
    if response.status != 200:
        raise SystemExit(1)
