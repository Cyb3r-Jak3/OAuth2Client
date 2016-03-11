import urllib
import base64
import logging
import httplib
from threading import Event
from urlparse import urlparse

import requests

from oauth2_client.http_server import start_http_server, stop_http_server


requests.packages.urllib3.disable_warnings()

_logger = logging.getLogger(__name__)


class OAuthError(BaseException):
    def __init__(self, status_code, response_text, error=None):
        self.status_code = status_code
        self.response_text = response_text
        self.error = error

    def __str__(self):
        return '%d  - %s : %s' % (self.status_code, self.error['error'], self.error['error_description']) \
            if self.error is not None else '%d  - %s' % (self.status_code, self.response_text)


class ServiceInformation(object):
    def __init__(self, authorize_service, token_service, client_id, client_secret, scopes):
        self.authorize_service = authorize_service
        self.token_service = token_service
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = ' '.join(scopes)
        self.auth = base64.b64encode('%s:%s' % (self.client_id, self.client_secret))


class AuthorizeResponseCallback(dict):
    def __init__(self, *args, **kwargs):
        super(AuthorizeResponseCallback, self).__init__(*args, **kwargs)
        self.response = Event()

    def update(self, other, **kwargs):
        super(AuthorizeResponseCallback, self).update(other, **kwargs)
        self.response.set()

    def wait(self, timeout=None):
        self.response.wait(timeout)


class AuthorizationContext(object):
    def __init__(self, state, port, host):
        self.state = state
        self.results = AuthorizeResponseCallback()
        self.server = start_http_server(port, host, self.results.update)


class CredentialManager(object):
    def __init__(self, service_information, proxies=dict(http='', https='')):
        self.service_information = service_information
        self.proxies = proxies
        self.authorization_code_context = None
        self.access_token = None
        self.refresh_token = None

    @staticmethod
    def _handle_bad_response(response):
        try:
            raise OAuthError(response.status_code, response.text, response.json())
        except:
            raise OAuthError(response.status_code, response.text)

    def init_authorize_code_process(self, redirect_uri, state=''):
        uri_parsed = urlparse(redirect_uri)
        if uri_parsed.scheme == 'https':
            raise NotImplementedError("Redirect uri cannot be secured")
        elif uri_parsed.port == '' or uri_parsed.port is None:
            _logger.warn('You should use a port above 1024 for redirect uri server')
            port = 80
        else:
            port = int(uri_parsed.port)
        if uri_parsed.hostname != 'localhost' and uri_parsed.hostname != '127.0.0.1':
            _logger.warn('Remember to put %s in your hosts config to point to loop back address' % uri_parsed.hostname)
        self.authorization_code_context = AuthorizationContext(state, port, uri_parsed.hostname)
        parameters = dict(client_id=self.service_information.client_id, redirect_uri=redirect_uri,
                          response_type='code', scope=self.service_information.scopes, state=state)

        url = '%s?%s' % (self.service_information.authorize_service,
                         '&'.join('%s=%s' % (k, urllib.quote(v, safe='~()*!.\'')) for k, v in parameters.items()))
        return url

    def wait_and_terminate_authorize_code_process(self, timeout=None):
        if self.authorization_code_context is None:
            raise Exception('Authorization code not started')
        else:
            try:
                self.authorization_code_context.results.wait(timeout)
                error = self.authorization_code_context.results.get('error', None)
                error_description = self.authorization_code_context.results.get('error_description', '')
                code = self.authorization_code_context.results.get('code', None)
                state = self.authorization_code_context.results.get('state', None)
                if error is not None:
                    raise OAuthError(httplib.UNAUTHORIZED, error_description,
                                     dict(error=error, error_description=error_description))
                elif state != self.authorization_code_context.state:
                    _logger.warn('State received does not match the one that was sent')
                    raise OAuthError(httplib.INTERNAL_SERVER_ERROR,
                                     'Sate returned does not match: Sent(%s) <> Got(%s)'
                                     % (self.authorization_code_context.state, state))
                elif code is None:
                    raise OAuthError(httplib.INTERNAL_SERVER_ERROR, 'No code returned')
                else:
                    return code
            finally:
                stop_http_server(self.authorization_code_context.server)
                self.authorization_code_context = None

    def init_with_authorize_code(self, redirect_uri, code):
        request_parameters = dict(code=code, grant_type="authorization_code", scope=self.service_information.scopes,
                                  redirect_uri=redirect_uri)
        self._token_request(request_parameters)

    def init_with_credentials(self, login, password):
        request_parameters = dict(username=login, grant_type="password", scope=self.service_information.scopes,
                                  password=password)
        self._token_request(request_parameters)

    def init_with_token(self, refresh_token):
        request_parameters = dict(grant_type="refresh_token", scope=self.service_information.scopes,
                                  refresh_token=refresh_token)
        self._token_request(request_parameters)

    def _refresh_token(self):
        request_parameters = dict(grant_type="refresh_token", scope=self.service_information.scopes,
                                  refresh_token=self.refresh_token)
        try:
            self._token_request(request_parameters)
        except OAuthError, err:
            if err.status_code == httplib.UNAUTHORIZED:
                _logger.debug('refresh_token - unauthorized - cleaning token')
                self.access_token = None
                self.refresh_token = None
            raise err

    def _token_request(self, request_parameters):
        response = requests.post('%s%s' % self.service_information.token_service,
                                 data=request_parameters,
                                 headers=dict(Authorization='Basic %s' % self.service_information.auth),
                                 proxies=self.proxies)
        if response.status_code != httplib.OK:
            CredentialManager._handle_bad_response(response)
        else:
            response_tokens = response.json()
            _logger.debug(response.text)
            self.access_token = response_tokens['access_token']
            self.refresh_token = response_tokens['refresh_token']

    def get(self, url, params=None, **kwargs):
        kwargs['params'] = params
        return self._bearer_request(requests.get, url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        kwargs['data'] = data
        kwargs['json'] = json
        return self._bearer_request(requests.post, url, **kwargs)

    def put(self, url, data=None, json=None, **kwargs):
        kwargs['data'] = data
        kwargs['json'] = json
        return self._bearer_request(requests.put, url, **kwargs)

    def patch(self, url, data=None, json=None, **kwargs):
        kwargs['data'] = data
        kwargs['json'] = json
        return self._bearer_request(requests.patch, url, **kwargs)

    def delete(self, url, **kwargs):
        return self._bearer_request(requests.delete, url, **kwargs)

    def _bearer_request(self, method, url, **kwargs):
        if self.access_token is None:
            raise OAuthError(httplib.UNAUTHORIZED, 'not_authenticated')
        headers = kwargs.get('headers', None)
        if headers is None:
            headers = dict()
            kwargs['headers'] = headers
        headers['Authorization'] = 'Bearer %s' % self.access_token
        response = method(url, **kwargs)
        if CredentialManager._is_token_expired(response):
            self._refresh_token()
            headers['Authorization'] = 'Bearer %s' % self.access_token
            return method(url, **kwargs)
        else:
            return response

    @staticmethod
    def _is_token_expired(response):
        if response.status_code == httplib.UNAUTHORIZED:
            try:
                json_data = response.json()
                return json_data.get('error', '') == 'invalid_token'
            except:
                return False
        else:
            return False