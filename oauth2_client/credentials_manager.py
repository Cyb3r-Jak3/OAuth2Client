import base64
import logging
from http import HTTPStatus
from threading import Event
from typing import Optional, Any, Callable, List
from urllib.parse import quote, urlparse

import requests

from oauth2_client.http_server import start_http_server, stop_http_server

_logger = logging.getLogger(__name__)


class OAuthError(Exception):
    def __init__(
        self,
        status_code: int,
        error: str,
        error_description: Optional[str] = None,
    ):
        super().__init__()
        self.status_code = status_code
        self.error = error
        self.error_description = error_description

    def __str__(self) -> str:
        return "%d  - %s : %s" % (
            self.status_code,
            self.error,
            self.error_description,
        )


class ServiceInformation:
    def __init__(
        self,
        authorize_service_url: Optional[str],
        token_service_url: Optional[str],
        client_id: str,
        client_secret: str,
        scopes: List[str],
        verify: bool = True,
    ):
        """
        Service Information contain all the information for a OAuth 2 Client

        :param authorize_service_url: Authorization grant URL for the service
        :type authorize_service_url: Optional[str]
        :param token_service_url: Token URL for the service
        :type token_service_url: Optional[str]
        :param client_id: Client ID of the application
        :type client_id: str
        :param client_secret: Client secret of the application
        :type client_secret: str
        :param scopes: Scopes that are used by the application
        :type scopes: List[str]
        :param verify: Verify the certificates (default True)
        :type verify: bool
        """
        self.authorize_service = authorize_service_url
        self.token_service = token_service_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes
        self.auth = base64.b64encode(
            bytes("%s:%s" % (self.client_id, self.client_secret), "UTF-8")
        ).decode("UTF-8")
        self.verify = verify


class AuthorizeResponseCallback(dict):
    """
    AuthorizeResponseCallback contains the OAuth call back information
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.response = Event()

    def wait(self, timeout: Optional[float] = None):
        """
        Wait for a response

        :param timeout: How long to wait for the response event
        :type timeout: Optional[float]
        :return:
        """
        self.response.wait(timeout)

    def register_parameters(self, parameters: dict):
        """
        This is call once there has been an OAuth response. It updates the class with the response information

        :param parameters: Response parameters
        :type parameters: dict
        """
        self.update(parameters)
        self.response.set()


class AuthorizationContext:
    def __init__(self, state: str, port: int, host: str):
        self.state = state
        self.results = AuthorizeResponseCallback()
        self.server = start_http_server(port, host, self.results.register_parameters)


class CredentialManager:
    def __init__(
        self, service_information: ServiceInformation, proxies: Optional[dict] = None, save: bool = True
    ):
        """
        CredentialManager handles the login process and will start a local http server to complete that authentication

        :param service_information: Service information for the OAuth application
        :type service_information: ServiceInformation
        :param proxies: Proxies to pass the request session
        :type proxies: dict
        :param save: Save the access information locally
        :type save: bool
        """
        self.service_information = service_information
        self.proxies = proxies if proxies is not None else {"http": "", "https": ""}
        self.authorization_code_context = None
        self.refresh_token = None
        self._session = None
        self.save = save
        if not service_information.verify:
            from requests.packages.urllib3.exceptions import InsecureRequestWarning
            import warnings

            warnings.filterwarnings(
                "ignore",
                "Unverified HTTPS request is being made.*",
                InsecureRequestWarning,
            )

    @staticmethod
    def _handle_bad_response(response: requests.Response):
        """
        Handle a bad response

        :param response: Response that threw the error
        :type response: requests.Response
        """
        try:
            error = response.json()
            raise OAuthError(
                HTTPStatus(response.status_code),
                error.get("error"),
                error.get("error_description"),
            )
        except BaseException as ex:
            if isinstance(ex, OAuthError):
                _logger.exception(
                    "_handle_bad_response - error while getting error as json - %s - %s"
                    % (type(ex), str(ex))
                )
                raise OAuthError(
                    response.status_code, "unknown_error", response.text
                ) from ex
            raise

    def generate_authorize_url(self, redirect_uri: str, state: str, **kwargs) -> str:
        """
        Generates the url for the authorization request

        :param redirect_uri: Redirect URL
        :param state: State for OAuth request
        :type state: str
        :param kwargs: Keyword arguments
        :return: URL to open to start the authorization process
        :rtype: str
        """
        parameters = {
            "client_id": self.service_information.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.service_information.scopes),
            "state": state,
            **kwargs,
        }
        return "%s?%s" % (
            self.service_information.authorize_service,
            "&".join(
                "%s=%s" % (k, quote(v, safe="~()*!.'")) for k, v in parameters.items()
            ),
        )

    def init_authorize_code_process(self, redirect_uri: str, state: str = "") -> str:
        """
        Starts the OAuth authorization process

        :param redirect_uri: Redirect URL for once the login is complete
        :type redirect_uri: str
        :param state: OAuth state default ''
        :type state: str
        :return: URL to open to start the authorization process
        :rtype: str
        """
        uri_parsed = urlparse(redirect_uri)
        if uri_parsed.scheme == "https":
            raise NotImplementedError("Redirect uri cannot be secured")
        if uri_parsed.port == "":
            _logger.warning("You should use a port above 1024 for redirect uri server")
            port = 80
        else:
            port = int(uri_parsed.port)
        if uri_parsed.hostname not in ["localhost", "127.0.0.1"]:
            _logger.warning(
                "Remember to put %s in your hosts config to point to loop back address"
                % uri_parsed.hostname
            )
        self.authorization_code_context = AuthorizationContext(
            state, port, uri_parsed.hostname
        )
        return self.generate_authorize_url(redirect_uri, state)

    def wait_and_terminate_authorize_code_process(
        self, timeout: Optional[float] = None
    ) -> str:
        """
        Starts the HTTP server to listen for a response code

        :param timeout: Time to wait before closing the server
        :type timeout: Optional[float]
        :return: The authorization code to get a token with
        :rtype: str
        """
        if self.authorization_code_context is None:
            raise Exception("Authorization code not started")
        try:
            self.authorization_code_context.results.wait(timeout)
            error = self.authorization_code_context.results.get("error", None)
            error_description = self.authorization_code_context.results.get(
                "error_description", ""
            )
            code = self.authorization_code_context.results.get("code", None)
            state = self.authorization_code_context.results.get("state", None)
            if error is not None:
                raise OAuthError(HTTPStatus.UNAUTHORIZED, error, error_description)
            if state != self.authorization_code_context.state:
                _logger.warning("State received does not match the one that was sent")
                raise OAuthError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "invalid_state",
                    "Sate returned does not match: Sent(%s) <> Got(%s)"
                    % (self.authorization_code_context.state, state),
                )
            if code is None:
                raise OAuthError(
                    HTTPStatus.INTERNAL_SERVER_ERROR, "no_code", "No code returned"
                )
            return code
        finally:
            stop_http_server(self.authorization_code_context.server)
            self.authorization_code_context = None

    def init_with_authorize_code(self, redirect_uri: str, code: str):
        """
        OAuth applications using the authorization code grant

        :param redirect_uri: Redirect URL
        :param code: The authorization code from the authorization process
        """
        self._token_request(self._grant_code_request(code, redirect_uri), True)

    def init_with_user_credentials(self, login: str, password: str):
        """
        OAuth applications using Resource Owner Password grant

        :param login: Username to login in with
        :type login: str
        :param password: Password to login with
        :type password: str
        """
        self._token_request(self._grant_password_request(login, password), True)

    def init_with_client_credentials(self):
        """
        OAuth process for Client Credentials flow
        """
        self._token_request(self._grant_client_credentials_request(), False)

    def init_with_token(self, refresh_token: str):
        """
        OAuth process for refresh token

        :param refresh_token: Refresh token to use
        :type refresh_token: str
        """
        self._token_request(self._grant_refresh_token_request(refresh_token), False)
        if self.refresh_token is None:
            self.refresh_token = refresh_token

    def _grant_code_request(self, code: str, redirect_uri: str) -> dict:
        """
        Generates request body for code request

        :param code: Access code from authorization request
        :type code: str
        :param redirect_uri: Redirect URL
        :type redirect_uri: str
        :return: Data to send in token request
        :rtype: dict
        """
        return {
            "grant_type": "authorization_code",
            "code": code,
            "scope": " ".join(self.service_information.scopes),
            "redirect_uri": redirect_uri,
        }

    def _grant_password_request(self, login: str, password: str) -> dict:
        """
        Generate request body for password request

        :param login: Username to login with
        :type login: str
        :param password: Password to login in with
        :type password: str
        :return: Data to send in token request
        :rtype: dict
        """
        return {
            "grant_type": "password",
            "username": login,
            "scope": " ".join(self.service_information.scopes),
            "password": password,
        }

    def _grant_client_credentials_request(self) -> dict:
        """
        Generate request body for client credentials request
        :return: Data to send in token request
        :rtype: dict
        """
        return {
            "grant_type": "client_credentials",
            "scope": " ".join(self.service_information.scopes),
        }

    def _grant_refresh_token_request(self, refresh_token: str) -> dict:
        """
        Generate request body for refresh token request

        :param refresh_token: Refresh token to use
        :return: Data to send in token request
        :rtype: dict
        """
        return {
            "grant_type": "refresh_token",
            "scope": " ".join(self.service_information.scopes),
            "refresh_token": refresh_token,
        }

    def _refresh_token(self):
        """
        Attempt to refresh an expired token
        """
        payload = self._grant_refresh_token_request(self.refresh_token)
        try:
            self._token_request(payload, False)
        except OAuthError as err:
            if err.status_code == HTTPStatus.UNAUTHORIZED:
                _logger.debug("refresh_token - unauthorized - cleaning token")
                self._session = None
                self.refresh_token = None
            raise err

    def _token_request(self, request_parameters: dict, refresh_token_mandatory: bool):
        """
        Make a request to the token endpoint to complete the auth process

        :param request_parameters: Generated request parameters
        :type request_parameters: dict
        :param refresh_token_mandatory: Refresh token required from the response
        :type refresh_token_mandatory: bool
        """
        headers = {
            "grant_type": request_parameters["grant_type"],
            "Authorization": f"Basic {self.service_information.auth}"
        }
        response = requests.post(
            self.service_information.token_service,
            data=request_parameters,
            headers=headers,
            proxies=self.proxies,
            verify=self.service_information.verify,
        )
        if response.status_code != HTTPStatus.OK:
            CredentialManager._handle_bad_response(response)
        else:
            _logger.debug(response.text)
            self._process_token_response(response.json(), refresh_token_mandatory)

    def _process_token_response(
        self, token_response: dict, refresh_token_mandatory: bool
    ):
        """
        Handles token response from OAuth endpoint

        :param token_response: JSON body of the response from the token request
        :type token_response: dict
        :param refresh_token_mandatory: Refresh token required in the response
        :type refresh_token_mandatory: bool
        """
        self.refresh_token = (
            token_response["refresh_token"]
            if refresh_token_mandatory
            else token_response.get("refresh_token")
        )
        self._access_token = token_response["access_token"]

    @property
    def _access_token(self) -> Optional[str]:
        """
        OAuth token that is used

        :return: OAuth Token. Returns none if empty
        :rtype: Optional[str]
        """
        authorization_header = (
            self._session.headers.get("Authorization")
            if self._session is not None
            else None
        )
        if authorization_header is not None:
            return authorization_header[len("Bearer "):]
        return None

    @_access_token.setter
    def _access_token(self, access_token: str = None):
        if self._session is None:
            self._session = requests.Session()
            self._session.proxies = self.proxies
            self._session.verify = self.service_information.verify
            self._session.trust_env = False
        if len(access_token) > 0:
            self._session.headers["Authorization"] = f"Bearer {access_token}"

    def get(self, url: str, params: Optional[dict] = None, **kwargs) -> requests.Response:
        """
        Authenticated GET request. Operates a request.get() method

        :param url: URL to make the request to
        :type url: str
        :param params: URL parameters to pass
        :type params: Optional[dict]
        :param kwargs: Keyword arguments to pass to request.get()
        :return: Response Object
        :rtype: requests.Response
        """
        kwargs["params"] = params
        return self._bearer_request(method="GET", url=url, **kwargs)

    def post(
        self, url: str, data: Optional[Any] = None, json: Optional[dict] = None, **kwargs: Optional[Any]
    ) -> requests.Response:
        """
        Authenticated POST request. Operates a request.post() method

        :param url: URL to make the request to
        :type url: str
        :param data: Body data to post
        :type data: dict
        :param json: JSON to post
        :type json: dict
        :param kwargs: Keyword arguments to pass to request.post()
        :return: Response Object
        :rtype: requests.Response
        """
        kwargs["data"] = data
        kwargs["json"] = json
        return self._bearer_request(method="POST", url=url, **kwargs)

    def put(
        self, url: str, data: Optional[Any] = None, json: Optional[Any] = None, **kwargs
    ) -> requests.Response:
        """
        Authenticated PUT request. Operates a request.put() method

        :param url: URL to make the request to
        :type url: str
        :param data: Body data for the request
        :type data: dict
        :param json: JSON data for the request
        :type json: dict
        :param kwargs: Keyword arguments to pass to request.put()
        :return: Response Object
        :rtype: requests.Response
        """
        kwargs["data"] = data
        kwargs["json"] = json
        return self._bearer_request(method="PUT", url=url, **kwargs)

    def patch(
        self, url: str, data: Optional[Any] = None, json: Optional[Any] = None, **kwargs
    ) -> requests.Response:
        """
        Authenticated PATCH request. Operates a request.PATCH() method

        :param url: URL to make the request to
        :type url: str
        :param data: Body data for the request
        :type data: dict
        :param json: JSON data for the request
        :type json: dict
        :param kwargs: Keyword arguments to pass to request.PATCH()
        :return: Response Object
        :rtype: requests.Response
        """
        kwargs["data"] = data
        kwargs["json"] = json
        return self._bearer_request(method="PATCH", url=url, **kwargs)

    def delete(self, url: str, **kwargs) -> requests.Response:
        """
        Authenticated DELETE request. Operates a request.delete() method

        :param url: URL to make the request to
        :type url: str
        :param kwargs: Keyword arguments to pass to request.delete()
        :return: Response Object
        :rtype: requests.Response
        """
        return self._bearer_request("DELETE", url, **kwargs)

    def _get_session(self) -> requests.Session:
        """
        Returns the authenticated session
        :return: Authenticated session
        :rtype: requests.Session
        """
        if self._session is None:
            raise OAuthError(HTTPStatus.UNAUTHORIZED, "no_token", "no token provided")
        return self._session

    def _bearer_request(
        self, method: str, url: str, **kwargs
    ) -> requests.Response:
        """
        Make a request with the authorization token set

        :param method: HTTP method to use
        :type method: str
        :param url: URL to make the request to
        :type str:
        :param kwargs: Keyword arguments to pass to the method call
        :return: Response object
        :rtype: requests.Response
        """
        headers = kwargs.get("headers", None)
        if headers is None:
            kwargs["headers"] = {}
        _logger.debug("_bearer_request on %s - %s" % (method, url))
        response = self._session.request(method=method, url=url, **kwargs)
        if self.refresh_token is not None and self._is_token_expired(response):
            self._refresh_token()
            return self._session.request(method=method, url=url, **kwargs)
        return response

    @staticmethod
    def _is_token_expired(response: requests.Response) -> bool:
        """
        Check if the OAuth token has expired

        :param response: Response to check
        :type response: requests.Response
        :return: Token is expired
        :rtype: bool
        """
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            try:
                json_data = response.json()
                return json_data.get("error") == "invalid_token"
            except ValueError:
                return False
        else:
            return False
