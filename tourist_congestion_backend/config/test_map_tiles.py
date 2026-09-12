from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, RequestFactory
from config.map_tiles import vworld_tile

class VWorldTileTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/')

    @patch.dict('os.environ', {'VWORLD_API_KEY': 'test-private-key'})
    @patch('config.map_tiles.requests.get')
    def test_only_png_bytes_are_returned(self, get):
        upstream = MagicMock(status_code=200)
        upstream.iter_content.return_value = [b'\x89PNG\r\n\x1a\nimage']
        get.return_value.__enter__.return_value = upstream
        response = vworld_tile(self.request, 13, 6985, 3172)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'test-private-key', response.content)
        self.assertNotIn('Location', response)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertFalse(get.call_args.kwargs['allow_redirects'])

    @patch.dict('os.environ', {'VWORLD_API_KEY': 'test-private-key'})
    @patch('config.map_tiles.requests.get')
    def test_provider_errors_never_expose_credentials(self, get):
        get.side_effect = RuntimeError('https://provider/test-private-key')
        response = vworld_tile(self.request, 13, 6985, 3172)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(b'test-private-key', response.content)

    @patch.dict('os.environ', {'VWORLD_API_KEY': 'test-private-key'})
    @patch('config.map_tiles.requests.get')
    def test_error_body_not_forwarded(self, get):
        upstream = MagicMock(status_code=200)
        upstream.iter_content.return_value = [b'<error>test-private-key</error>']
        get.return_value.__enter__.return_value = upstream
        self.assertEqual(vworld_tile(self.request, 13, 6985, 3172).status_code, 502)

    @patch('config.map_tiles.requests.get')
    def test_invalid_coordinates_do_not_call_provider(self, get):
        self.assertEqual(vworld_tile(self.request, 99, 1, 1).status_code, 404)
        self.assertEqual(vworld_tile(self.request, 3, 8, 1).status_code, 404)
        get.assert_not_called()
