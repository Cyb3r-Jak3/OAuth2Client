Client Credentials
-------------------


.. code-block:: python

    manager = CredentialManager(
        service_information,
        proxies={"http": 'http://localhost:3128', "https": 'http://localhost:3128'}
    )
    manager.init_with_client_credentials()

    # Make authenticated request
    manager.post("https://api.endpoint.com", json={"hello": "world"})
