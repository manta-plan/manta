import secrets

# TODO: Read from environment/files
# see: python-configuration


class MantaAuthConfig:
    """
    Configuration for Manta Authentication system
    """

    def __init__(self, api_signing_key: bytes):
        self._api_signing_key = api_signing_key

    @property
    def api_signing_key(self) -> bytes:
        """
        Signing secret for Bearer authentication tokens
        """
        return self._api_signing_key


def get_auth_config() -> MantaAuthConfig:
    """Generate a new MantaAuthConfig with a random API signing key"""
    return MantaAuthConfig(secrets.token_bytes(32))
