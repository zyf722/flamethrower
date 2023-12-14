import os
from datetime import datetime
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import Optional, Union
from zipfile import ZipFile

from requests import Response, Session


# Decorator to wrap API.
def api_call(endpoint: str, method: str, params: Optional[dict] = None):
    """
    Decorator to wrap API calls.

    Args:
        endpoint (str): The endpoint of the request. Should be in form of `/endpoint`.
        method (str): The method of the request. Should be in form of `GET`, `POST`, etc.
        params (Optional[dict], optional): The parameters of the request. Defaults to None.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self: "ParaTranzAPI", *args, **kwargs):
            url = self._set_url(endpoint)
            response = self.session.request(method, url, params)
            if response.status_code == 200:
                return func(self, response, *args, **kwargs)
            else:
                raise Exception(
                    f"Response Error: {response.status_code} {response.reason}"
                )

        return wrapper

    return decorator


class ParaTranzAPI:
    """
    Wrapper class to interact with ParaTranz OpenAPI.
    """

    def __init__(self, api_token: str, project_id: int) -> None:
        self.session = Session()
        self.session.headers.update({"Authorization": f"{api_token}"})
        self.project_id = project_id
        self.base_url = f"https://paratranz.cn/api/projects/{self.project_id}"

    @staticmethod
    def test_api(api_token: str, project_id: int) -> bool:
        """
        Test if the API is valid.

        Args:
            api_token (str): The API token of the project.
            project_id (int): The project id of the project.

        Returns:
            bool: If the API is valid.
        """
        session = Session()
        session.headers.update({"Authorization": f"{api_token}"})
        response = session.get(f"https://paratranz.cn/api/projects/{project_id}/files")
        return response.status_code == 200

    def _set_url(self, endpoint: str) -> str:
        """
        Set the url for the request.

        Args:
            endpoint (str): The endpoint of the request. Should be in form of `/endpoint`.
        """
        return f"{self.base_url}{endpoint}"

    @api_call(endpoint="/artifacts/download", method="GET")
    def download_artifact(
        self,
        response: Optional[Response] = None,
        path: Union[str, Path] = Path("artifacts"),
    ) -> None:
        """
        Download the artifact from the project.
        """
        if response is None:
            raise ValueError("Response is None.")

        # Extract the artifact
        if isinstance(path, Path):
            path = str(path)

        os.makedirs(path, exist_ok=True)
        with ZipFile(BytesIO(response.content)) as artifact:
            for file in artifact.namelist():
                dest = os.path.join(path, os.path.basename(file))
                with open(dest, "wb") as f:
                    f.write(artifact.read(file))

    @api_call(endpoint="/artifacts", method="GET")
    def get_artifact_datetime(self, response: Optional[Response] = None) -> datetime:
        """
        Get the artifact info from the project.
        """
        if response is None:
            raise ValueError("Response is None.")
        return datetime.strptime(response.json()["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ")

    @api_call(endpoint="/terms", method="GET", params={"page": 1, "pageSize": 800})
    def get_terms(self, response: Optional[Response] = None) -> dict:
        """
        Get the terms from the project.
        """
        if response is None:
            raise ValueError("Response is None.")

        terms = {}
        for term in response.json()["results"]:
            terms[term["term"]] = term["translation"]

        return terms
