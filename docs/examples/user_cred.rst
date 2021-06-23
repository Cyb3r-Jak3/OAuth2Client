User Credentials
-----------------


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
    manager.init_with_user_credentials('login', 'password')
    # Here access and refresh token may be used
    manager.init_with_authorize_code(redirect_uri, code)

    # Make authenticated request
    manager.post("https://api.endpoint.com", json={"hello": "world"})
