Refresh Token
--------------

If a refresh token has been saved then you can start with that

.. code-block:: python


    manager = CredentialManager(service_information)
    manager.init_with_token('my saved refreshed token')

    # Make authenticated request
    manager.post("https://api.endpoint.com", json={"hello": "world"})
