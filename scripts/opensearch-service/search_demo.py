"""Serve the local movie-search page and proxy requests to the existing API."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


PAGE = Path(__file__).resolve().parents[2] / 'web/movie-search/index.html'


class SearchDemoHandler(BaseHTTPRequestHandler):
    def send_body(self, status, body, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A newer query may have cancelled the browser request.

    def send_error_json(self, status, code, message):
        self.send_body(status, json.dumps({
            'error': {'code': code, 'message': message},
        }).encode())

    def do_GET(self):
        request = urlsplit(self.path)
        if request.path in ('/', '/index.html'):
            self.send_body(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
        elif request.path == '/api/movies/search':
            upstream_url = self.server.search_url
            if request.query:
                upstream_url += '?' + request.query
            try:
                with urlopen(upstream_url, timeout=30) as response:
                    body = response.read()
                    self.send_body(response.status, body,
                                   response.headers.get('Content-Type', 'application/json'))
            except HTTPError as exc:
                with exc:
                    self.send_body(exc.code, exc.read(),
                                   exc.headers.get('Content-Type', 'application/json'))
            except TimeoutError:
                self.send_error_json(504, 'SEARCH_TIMEOUT', 'Search timed out. Please try again.')
            except URLError as exc:
                if isinstance(exc.reason, TimeoutError):
                    self.send_error_json(504, 'SEARCH_TIMEOUT', 'Search timed out. Please try again.')
                else:
                    self.send_error_json(503, 'SEARCH_UNAVAILABLE',
                                         'Could not reach movie search. Check that Floci is running.')
            except OSError:
                self.send_error_json(503, 'SEARCH_UNAVAILABLE',
                                     'Could not reach movie search. Please try again.')
        else:
            self.send_error_json(404, 'NOT_FOUND', 'Page not found.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Full /movies/search API endpoint (quote it)')
    parser.add_argument('--port', type=int, default=8000, help='Local port (default: 8000)')
    args = parser.parse_args()
    endpoint = urlsplit(args.url)
    if (endpoint.scheme not in ('http', 'https') or not endpoint.hostname
            or endpoint.query or endpoint.fragment or endpoint.username or endpoint.password):
        parser.error('--url must be an HTTP(S) endpoint without credentials, query parameters, or a fragment')
    try:
        endpoint.port
    except ValueError:
        parser.error('--url contains an invalid port')
    if any(part in ('None', 'null', 'undefined') for part in endpoint.path.split('/')):
        parser.error('--url contains a missing API ID; discover the deployed API first')
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    try:
        with ThreadingHTTPServer(('127.0.0.1', args.port), SearchDemoHandler) as server:
            server.search_url = args.url
            print(f'Movie Search: http://127.0.0.1:{args.port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print('\nStopped movie search.')
    except OSError as exc:
        parser.exit(1, f'Could not start the local server: {exc}\n')


if __name__ == '__main__':
    main()
