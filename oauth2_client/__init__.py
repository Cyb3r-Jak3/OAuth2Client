# -*- coding: utf-8 -*-
"""
OAuth2 client is python client that handles oauth logging in make request making in accordance with rfc6749
"""
from oauth2_client.credentials_manager import (
    ServiceInformation,
    OAuthError,
    CredentialManager,
)

__version__ = "1.2.1"

__all__ = ["ServiceInformation", "__version__", "OAuthError", "CredentialManager"]
