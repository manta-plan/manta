from pathlib import Path

import httpx2
import pytest


def test_hit_homepage(frontend_files: Path, app_server: str) -> None:
    # Given
    index_page = None
    try:
        index_page = open(frontend_files / "index.html", "rb")  # noqa: SIM115
        homepage_contents = index_page.read()
    except OSError as err:
        pytest.fail(f"could not load index page: {err}")
    finally:
        if index_page is not None:
            index_page.close()

    # When
    response = httpx2.get(f"{app_server}/")

    # Then
    assert response.status_code == 200
    assert homepage_contents == response.read()
