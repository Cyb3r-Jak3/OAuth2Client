Using Client Authorization
---------------------------


.. code-block:: python

    from oauth2_client import ServiceInformation, CredentialManager
    scopes = ['scope_1', 'scope_2']

    service_information = ServiceInformation(
        'https://authorization-server/oauth/authorize',
        'https://token-server/oauth/token',
        'client_id',
        'client_secret',
        scopes
    )
    manager = CredentialManager(
        service_information,
        proxies={"http": 'http://localhost:3128', "https": 'http://localhost:3128'}
    )
    redirect_uri = 'http://localhost:8080/oauth/code'

    # Builds the authorization url and starts the local server according to the redirect_uri parameter
    url = manager.init_authorize_code_process(redirect_uri, 'state_test')
    print(f"Open {url} in your browser to complete the sign in process")

    code = manager.wait_and_terminate_authorize_code_process()
    # From this point the http server is opened on 8080 port and wait to receive a single GET request
    # All you need to do is open the url and the process will go on
    # (as long you put the host part of your redirect uri in your host file)
    # when the server gets the request with the code (or error) in its query parameters
    manager.init_with_authorize_code(redirect_uri, code)

    # Make authenticated request
    manager.post("https://api.endpoint.com", json={"hello": "world"})
