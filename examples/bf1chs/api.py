import os
from abc import ABC
from datetime import datetime
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional, Union
from zipfile import ZipFile

from dateutil import tz
from requests import Response, Session
from requests.exceptions import ProxyError, RequestException, SSLError  # noqa: F401
from urllib3.exceptions import RequestError as URLlib3RequestError  # noqa: F401


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
        def wrapper(self: "BaseAPI", *args, **kwargs):
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


def from_utc_to_local(utc_datetime: datetime) -> datetime:
    """
    Convert datetime from UTC to local time.

    Args:
        utc_datetime (datetime): The datetime in UTC.

    Returns:
        datetime: The datetime in local time.
    """
    local_timezone = tz.tzlocal()
    utc_timezone = tz.tzutc()
    utc_datetime = utc_datetime.replace(tzinfo=utc_timezone)
    local_datetime = utc_datetime.astimezone(local_timezone)
    return local_datetime


class BaseAPI(ABC):
    """
    Base class for API.
    """

    def __init__(self) -> None:
        self.session = Session()
        self.base_url: str = ""

    def _set_url(self, endpoint: str) -> str:
        """
        Set the url for the request.

        Args:
            endpoint (str): The endpoint of the request. Should be in form of `/endpoint`.
        """
        return f"{self.base_url}{endpoint}"


class SourceAPI(BaseAPI, ABC):
    """
    Base class for update source API. Basically it should be a Github-like API.
    """

    def get_latest_asset(
        self, time_key: str, response: Optional[Response] = None, asset_name: str = ""
    ):
        """
        Get the latest release asset from the repo.
        """
        if response is None:
            raise ValueError("Response is None.")

        latest_asset_url = ""
        latest_published_time = None
        latest_version = ""
        latest_log = ""
        for release in response.json():
            if release["assets"]:
                for asset in release["assets"]:
                    if "name" in asset and asset_name in asset["name"]:
                        published_time = datetime.strptime(
                            release[time_key], "%Y-%m-%dT%H:%M:%S%z"
                        )
                        if (
                            latest_published_time is None
                            or published_time > latest_published_time
                        ):
                            latest_published_time = published_time
                            latest_asset_url = asset["browser_download_url"]
                            latest_version = release["name"].split(" ")[-1]
                            latest_log = release["body"]

        assert latest_published_time is not None
        return (latest_asset_url, latest_version, latest_published_time, latest_log)


class GithubAPI(SourceAPI):
    """
    Wrapper class to interact with Github API.
    """

    def __init__(self, owner: str, repo: str) -> None:
        super().__init__()
        self.owner = owner
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}"

    @api_call(endpoint="/releases", method="GET")
    def get_latest_asset(
        self, response: Optional[Response] = None, asset_name: str = ""
    ):
        """
        Get the latest release asset from the repo.
        """
        latest_asset_url, latest_version, latest_published_time, latest_log = (
            super().get_latest_asset("published_at", response, asset_name)
        )
        return (
            latest_asset_url,
            latest_version,
            from_utc_to_local(latest_published_time),
            latest_log,
        )


class GiteeAPI(SourceAPI):
    """
    Wrapper class to interact with Gitee API.
    """

    def __init__(self, owner: str, repo: str) -> None:
        super().__init__()
        self.owner = owner
        self.repo = repo
        self.base_url = f"https://gitee.com/api/v5/repos/{self.owner}/{self.repo}"

    @api_call(endpoint="/releases", method="GET")
    def get_latest_asset(
        self, response: Optional[Response] = None, asset_name: str = ""
    ):
        """
        Get the latest release asset from the repo.
        """
        return super().get_latest_asset("created_at", response, asset_name)


class ParaTranzAPI(BaseAPI):
    """
    Wrapper class to interact with ParaTranz OpenAPI.
    """

    def __init__(self, api_token: str, project_id: int) -> None:
        super().__init__()
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

    @api_call(endpoint="/artifacts/download", method="GET")
    def download_artifact(
        self,
        response: Optional[Response] = None,
        path: Union[str, Path] = Path("artifacts"),
        skip_predicate: Callable[[str], bool] = lambda x: False,
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
                if skip_predicate(file):
                    continue

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
        return from_utc_to_local(
            datetime.strptime(response.json()["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ")
        )

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
