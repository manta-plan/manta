from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import HTTPException
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from typing_extensions import Doc


class BackendError(HTTPException):
    """
    Represents an error in a dependency / that isn't directly the user's fault.

    Resolves to a 500 error by default.
    """

    def __init__(
        self,
        status_code: Annotated[
            int,
            Doc("""
                    HTTP status code to send to the client.

                    Defaults to 500.
                    """),
        ] = HTTP_500_INTERNAL_SERVER_ERROR,
        detail: Annotated[
            Any,
            Doc("""
                    Any data to be sent to the client in the `detail` key of the JSON
                    response.

                    Read more about it in the
                    [FastAPI docs for Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/#use-httpexception)
                    """),
        ] = None,
        headers: Annotated[
            Mapping[str, str] | None,
            Doc("""
                    Any headers to send to the client in the response.

                    Read more about it in the
                    [FastAPI docs for Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/#add-custom-headers)

                    """),
        ] = None,
    ) -> None:
        super().__init__(status_code, detail, headers)
