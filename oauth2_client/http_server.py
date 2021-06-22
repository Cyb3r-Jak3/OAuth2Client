"""Local HTTP server used to handle responses"""
import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer
from typing import Callable, Type, Optional
from urllib.parse import unquote

_logger = logging.getLogger(__name__)


class _ReuseAddressTcpServer(TCPServer):
    def __init__(
        self, host: str, port: int, handler_class: Type[BaseHTTPRequestHandler]
    ):
        self.allow_reuse_address = True
        TCPServer.__init__(self, (host, port), handler_class)


def read_request_parameters(path: str) -> dict:
    """Read the request parameters

    :param path: URL path to read
    :type path: str
    :return: Dict of parameters
    :rtype: dict
    """

    params_received = {}
    idx = path.find("?")
    if 0 <= idx < (len(path) - 1):
        for params in path[idx + 1 :].split("&"):
            param_split = params.split("=")
            if len(param_split) == 2:
                params_received[param_split[0]] = unquote(param_split[1])
    return params_received


def start_http_server(
    port: int, host: str = "", callback: Optional[Callable[[dict], None]] = None
) -> TCPServer:
    """
    Create and start a local http server to handle the Authorization response

    :param port: Local port to listen on. **Highly recommended** to use above 1024
    :type port: int
    :param host:
    :type host:
    :param callback:
    :return: HTTP server to handle local request
    :rtype: TCPServer
    """

    class Handler(BaseHTTPRequestHandler):
        """
        Handle HTTP request
        """

        def do_GET(self):  # pylint: disable=invalid-name
            """
            Handles the GET request
            """
            _logger.debug("GET - %s", self.path)
            params_received = read_request_parameters(self.path)
            response = (
                "Response received"
                f"{json.dumps(params_received)}."
                "Result was transmitted to the original thread. You can close this window."
            )
            self.send_response(HTTPStatus.OK, "OK")
            self.send_header("Content-type", "text/plain")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            try:
                self.wfile.write(bytes(response, "UTF-8"))
            finally:
                if callback is not None:
                    callback(params_received)
                self.wfile.flush()

    _logger.debug(
        'start_http_server - instantiating server to listen on "%s:%d"', host, port
    )
    httpd = _ReuseAddressTcpServer(host, port, Handler)

    def serve():
        _logger.debug("server daemon - starting server")
        httpd.serve_forever()
        _logger.debug("server daemon - server stopped")

    thread_type = threading.Thread(target=serve)
    thread_type.start()
    return httpd


def stop_http_server(httpd: TCPServer):
    """
    Stop the local server
    :param httpd: The local server
    :type httpd: TCPServer
    """

    _logger.debug("stop_http_server - stopping server")
    httpd.shutdown()
