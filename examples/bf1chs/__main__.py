import json
import os
import platform
import re
import textwrap
import webbrowser
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from api import (
    GiteeAPI,
    GithubAPI,
    ParaTranzAPI,
    ProxyError,
    RequestException,
    SourceAPI,
    URLlib3RequestError,
)
from conflict import Conflicts
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table
from rich.theme import Theme
from ttffont import TTFInfo

from flamethrower.localization import Histogram, StringsBinary

VERSION = "v0.5.1"
PROJECT_ID = 8862
REPO_NAME = "flamethrower"
REPO_OWNER_GITHUB = "zyf722"
REPO_OWNER_GITEE = "bf1-chs"
ASSET_NAME = "bf1chs.zip"

ARTIFACT_MANIFEST = {
    "strings-zht.csv.json": "静态本地化文件",
    "twinkle.json": "动态本地化文件",
    "bf2042.json": "额外动态本地化文件（战地风云 2042 相关）",
    "bfv.json": "额外动态本地化文件（战地风云 V 相关）",
    "codex.json": "额外动态本地化文件（百科）",
    "dogtags.json": "额外动态本地化文件（狗牌）",
    "generic.json": "额外动态本地化文件（通用）",
    "news.json": "额外动态本地化文件（新闻）",
    "store.json": "额外动态本地化文件（商店）",
    "video.json": "额外动态本地化文件（视频）",
    "eaplay.json": "额外动态本地化文件（EA Play）",
    "bf4.json": "额外动态本地化文件（战地风云 4 相关）",
    "bfhl.json": "额外动态本地化文件（战地风云：硬仗相关）",
}

os.chdir(os.path.dirname(os.path.abspath(__file__)))

console = Console(
    theme=Theme(
        {
            "dark-gray": "#5c6370",
            "light-blue": "#61afef",
            # Override rich's default theme
            "markdown.item.bullet": "yellow",
            "markdown.link_url": "#61afef",
            "markdown.code": "#e83e8c",
        }
    ),
    highlight=False,
)


class BF1ChsToolbox:
    """
    Main class of the toolbox.
    """

    class ExitException(Exception):
        pass

    class IncompatibleConfigException(Exception):
        pass

    class Config:
        """
        Config class to store and validate config.
        """

        # (default, description, validator, hint_message)

        class Validator:
            none_validator = ((lambda x: True), None)

            @staticmethod
            def filename_validator(ext: str):
                return (
                    (
                        lambda x: bool(re.match(r'^[^<>:"/\\|?*]+\Z', x))
                        and len(x) <= 255
                        and x.endswith(ext)
                    ),
                    f'文件名不应包含特殊字符（< > : " / \\ | ? *），文件名长度不应超过 255 个字符且应以 {ext} 结尾。',
                )

            positive_integer_validator = (
                lambda x: isinstance(x, int) and x > 0,
                "应为正整数。",
            )

        schema: Dict[str, Tuple[Any, str, Callable[[Any], bool], Optional[str]]] = {
            "bf1chs.version": (
                VERSION,
                "当前配置文件版本，用于校验。[bold dark_red]不应手动修改。",
                lambda x: all(
                    [
                        x == y
                        for x, y in zip(x.split(".")[:-1], VERSION.split(".")[:-1])
                    ]  # Skip the last version number
                ),
                "配置文件版本不匹配，可能是由于配置文件版本过旧或者版本不兼容导致。",
            ),
            "paratranz.token": (
                "",
                "ParaTranz API Token，可在 [link=https://paratranz.cn/users/my]https://paratranz.cn/users/my[/link] 获取。",
                lambda x: len(x) == 32 and ParaTranzAPI.test_api(x, PROJECT_ID),
                "请检查 API Token 是否正确、ParaTranz 账户是否已经加入[link=https://paratranz.cn/projects/8862]汉化项目[/link]、网络连接是否正常。\n如果问题仍然存在，可能由于短时间内请求过多导致，请两分钟后重试。",
            ),
            "paratranz.artifactPath": (
                "artifact",
                "下载的汉化文件存放路径，可为相对路径。",
                *Validator.none_validator,
            ),
            "paratranz.processedPath": (
                "artifact/processed",
                "转换后的汉化文件存放路径，可为相对路径。",
                *Validator.none_validator,
            ),
            "paratranz.conflictReport.filename": (
                "conflict.md",
                "译文不一致检测生成的冲突报告文件名，需以 .md 结尾。",
                *Validator.filename_validator(".md"),
            ),
            "paratranz.conflictReport.headerLevel": (
                2,
                "冲突报告的标题级别。",
                *Validator.positive_integer_validator,
            ),
            "localization.histogramPath": (
                "localization/histogram",
                "码表文件存放路径，可为相对路径。",
                *Validator.none_validator,
            ),
            "localization.stringsPath": (
                "localization/strings",
                "静态本地化文件存放路径，可为相对路径。",
                *Validator.none_validator,
            ),
            "localization.twinklePath": (
                "localization/twinkle",
                "动态本地化文件存放路径，可为相对路径。",
                *Validator.none_validator,
            ),
            "localization.twinkleFilename": (
                "BF1CHS_twinkle_extra.json",
                "默认动态本地化文件名，需以 .json 结尾。",
                *Validator.filename_validator(".json"),
            ),
            "font.path": (
                "font",
                "字体文件存放路径，可为相对路径。",
                *Validator.none_validator,
            ),
            "ui.maxItems": (
                10,
                "本程序界面中最多显示的项目数，当项目数超过此值时会自动截断。对表格、列表等生效。",
                *Validator.positive_integer_validator,
            ),
            "meta.autoUpdate": (
                True,
                "是否在启动时自动检查更新。",
                lambda x: isinstance(x, bool),
                "应为布尔值。",
            ),
            "meta.autoUpdate.source": (
                "github",
                "自动检查更新时使用的源。可选值：github / gitee。",
                lambda x: x in ("github", "gitee"),
                "应为 'github' 或 'gitee'。",
            ),
        }

        def __init__(self) -> None:
            self._config_dict = {}
            for key, value in self.schema.items():
                self._config_dict[key] = value[0]

        @classmethod
        def load(cls, config_dict: Dict = {}) -> "BF1ChsToolbox.Config":
            config = cls()

            config._config_dict = {}
            for key, value in config_dict.items():
                if key in cls.schema:
                    if not isinstance(value, type(cls.schema[key][0])):
                        raise TypeError(key, cls.schema[key][3])
                    if not cls.schema[key][2](value):
                        if key == "bf1chs.version":
                            raise BF1ChsToolbox.IncompatibleConfigException
                        else:
                            raise ValueError(key, cls.schema[key][3])
                    config._config_dict[key] = value

            return config

        def __getitem__(self, key: str) -> Any:
            return self._config_dict[key]

        def update(self, config_dict: Dict) -> None:
            """
            This method should only be used when updating old config files.
            """
            for key, value in config_dict.items():
                if key in self.schema:
                    if not isinstance(value, type(self.schema[key][0])):
                        raise TypeError(key, self.schema[key][3])
                    if key != "bf1chs.version":
                        if not self.schema[key][2](value):
                            raise ValueError(key, self.schema[key][3])
                        self._config_dict[key] = value
                else:
                    console.print(f"[yellow]无效配置项 {key}，已忽略。")

        def show(self):
            console.print("[underline yellow]当前配置")
            for key, value in self._config_dict.items():
                if key == "paratranz.token" and value != "":
                    value = value[0:4] + "*" * 24 + value[-4:]
                console.print(
                    f"{key}: [light-blue]{value}[/]  [dark-gray]# {self.schema[key][1]}[/]"
                )
            console.print()

    class SelectAction:
        """
        Helper class to create a select action.
        """

        def __init__(
            self,
            title: str,
            desc: str,
            choices: Dict[
                str, Dict[str, Union[str, Callable, "BF1ChsToolbox.SelectAction", None]]
            ],
            is_main: bool = False,
        ) -> None:
            self.title = title
            self.desc = desc
            self.choices = choices
            self.back_choice: List[Union[Separator, Choice]] = [
                Separator(),
                Choice(
                    value="back",
                    name="退出程序" if is_main else "返回上一级",
                ),
            ]
            self.is_main = is_main

        @staticmethod
        def _choice_helper(choices: List[Choice]) -> str:
            console.print("[dark-gray]（使用方向键上下移动 / 回车键确认）")
            action = inquirer.select(
                message="选择一项操作",
                choices=choices,
            ).execute()
            console.print()
            return action

        def run(self):
            while True:
                console.print(f"[underline yellow]{self.title}[/]\n{self.desc}\n")

                if not self.is_main:
                    for value in self.choices.values():
                        desc_str = f"- [bold]{value['name']}[/]："

                        if value["actor"] is None:
                            desc_str += "[dark-gray]本功能暂未实现。"
                        elif "desc" not in value:
                            desc_str += "[dark-gray]暂无描述。"
                        else:
                            assert isinstance(value["desc"], str)
                            desc_str += value["desc"]
                        console.print(desc_str)
                    console.print()

                action = self._choice_helper(
                    [
                        Choice(value=key, name=value["name"])  # type: ignore
                        for key, value in self.choices.items()
                    ]
                    + self.back_choice  # type: ignore
                )

                if action == "back":
                    break

                try:
                    if self.choices[action]["actor"] is None:
                        # This is a placeholder
                        console.print("[dark-gray]本功能暂未实现。\n\n按回车键以继续。")
                        input()
                    elif isinstance(
                        self.choices[action]["actor"], BF1ChsToolbox.SelectAction
                    ):
                        # This is a SelectAction representing a submenu
                        self.choices[action]["actor"].run()  # type: ignore
                    elif callable(self.choices[action]["actor"]):
                        # This is a function that actually do things
                        self.choices[action]["actor"]()  # type: ignore
                        console.print("[dark-gray]按回车键以继续。")
                        input()
                except BF1ChsToolbox.ExitException:
                    raise BF1ChsToolbox.ExitException
                except ProxyError:
                    console.print("[bold red]代理错误。请检查代理设置是否正确。\n")
                except (RequestException, URLlib3RequestError) as e:
                    console.print(
                        f"[bold red]未知网络错误 ({e.__class__.__name__})。请尝试使用代理连接。\n"
                    )
                except Exception as e:
                    console.print(f"[bold red]未知错误 ({e.__class__.__name__}): {e}\n")

    def _rich_truncate(
        self, container: Union[list, tuple, dict], max_items: Optional[int] = None
    ) -> str:
        """
        Helper function to truncate container in rich format.
        """
        trunc_container: Union[list, tuple, dict]

        if max_items is None:
            max_items = self.config["ui.maxItems"]

        if len(container) <= max_items:
            return str(container)
        elif isinstance(container, (list, tuple)):
            trunc_container = container[:max_items]
        elif isinstance(container, dict):
            trunc_container = dict(list(container.items())[:max_items])
        else:
            raise TypeError(f"Type {type(container)} is not supported.")

        return f"[light-blue]{trunc_container} ... [/](共 [light-blue]{len(container)}[/] 项)"

    def _rich_show_object(self, object: Any, max_items: Optional[int] = None):
        """
        Helper function to show object in rich format.
        """
        console.print(f"[underline yellow]{object.__class__.__name__} 对象[/]")
        for key, value in vars(object).items():
            console.print(
                f"{key} [yellow]({type(value).__name__})[/]: ",
                end="",
            )

            if isinstance(value, (list, tuple, dict)):
                console.print(f"{self._rich_truncate(value, max_items)}")
            else:
                console.print(f"[light-blue]{value}")
        console.print()

    @staticmethod
    def _rich_indeterminate_progress(
        task_name: str, short_name: str, actor: Callable, *args, **kwargs
    ):
        """
        Helper function to show indeterminate progress in rich format.
        """
        try:
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}")
            ) as progress:
                progress.add_task(f"[yellow]正在{task_name}...")
                result = actor(*args, **kwargs)
            console.print(f"[bold green]{short_name}成功。\n")
            return result
        except Exception as e:
            console.print(f"[bold red]{short_name}失败：{e}\n")
            return None

    @staticmethod
    def _rich_progress(
        task_name: str, short_name: str, actor: Callable, total: int, *args, **kwargs
    ):
        """
        Helper function to show progress in rich format.
        """
        try:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                MofNCompleteColumn(),
            ) as progress:
                task = progress.add_task(f"[yellow]正在{task_name}", total=total)
                result = actor(progress, task, *args, **kwargs)
            console.print(f"[bold green]{short_name}成功。\n")
            return result
        except Exception as e:
            console.print(f"[bold red]{short_name}失败：{e}\n")
            return None

    @staticmethod
    def _rich_confirm(message: str, default=True, desc: Optional[str] = None, **kwargs):
        """
        Helper function to show confirm in rich format.
        """
        console.print("[dark-gray]（输入 y/n 或者回车键直接确认）")
        if desc is not None:
            console.print(f"[dark-gray]（{desc}）")
        return inquirer.confirm(
            message=message,
            default=default,
            confirm_letter="y",
            reject_letter="n",
            transformer=lambda result: "是" if result else "否",
            **kwargs,
        ).execute()

    @staticmethod
    def _rich_integer(
        message: str, default: int = 0, desc: Optional[str] = None, **kwargs
    ):
        """
        Helper function to show integer in rich format.
        """
        console.print("[dark-gray]（使用方向键上下增减 / 数字键输入数字 / 回车键确认）")
        if desc is not None:
            console.print(f"[dark-gray]（{desc}）")
        result = inquirer.number(
            message=message,
            default=default,
            **kwargs,
        ).execute()
        console.print()
        return int(result)

    @staticmethod
    def _rich_text(
        message: str, default: str = "", desc: Optional[str] = None, **kwargs
    ):
        """
        Helper function to show text in rich format.
        """
        console.print("[dark-gray]（输入文本 / 回车键确认）")
        if desc is not None:
            console.print(f"[dark-gray]（{desc}）")
        result = inquirer.text(
            message=message,
            default=default,
            **kwargs,
        ).execute()
        console.print()
        return result

    @staticmethod
    def _rich_fuzzy_select_file(
        directory: str,
        types: Union[str, List[str]],
        message: str = "选择文件",
        desc: Optional[str] = None,
        **kwargs,
    ):
        """
        Helper function to show fuzzy select file in rich format.
        """

        def validator(types: Union[str, List[str]], file: str):
            if isinstance(types, str):
                return file.endswith(types)
            elif isinstance(types, list):
                return any(file.endswith(type) for type in types)
            else:
                raise TypeError(f"Type {type(types)} is not supported.")

        choices = [file for file in os.listdir(directory) if validator(types, file)]
        types_repr = types if isinstance(types, str) else " / ".join(types)
        if len(choices) == 0:
            console.print(f"[yellow]路径 {directory} 下无可用文件。")
            console.print(f"[yellow]支持文件类型：[/]{types_repr}\n")
            return None

        console.print(
            "[dark-gray]（使用方向键上下移动 / 回车键确认 / 输入关键词进行模糊搜索）"
        )
        if desc is not None:
            console.print(f"[dark-gray]（{desc}）")
        result = inquirer.fuzzy(
            message=f"{message} ({types_repr})",
            choices=choices,
            filter=lambda result: os.path.join(directory, result),
            **kwargs,
        ).execute()
        console.print()
        return result

    @staticmethod
    def _rich_multiline_string(string: str) -> str:
        """
        Helper function to wrap multiline string correctly.
        """
        return textwrap.dedent(string)[:-1]

    def __init__(self) -> None:
        console.print(
            "[bold gold3]"
            + self._rich_multiline_string(
                """
                ██████╗ ███████╗ ██╗ ██████╗██╗  ██╗███████╗
                ██╔══██╗██╔════╝███║██╔════╝██║  ██║██╔════╝
                ██████╔╝█████╗  ╚██║██║     ███████║███████╗
                ██╔══██╗██╔══╝   ██║██║     ██╔══██║╚════██║
                ██████╔╝██║      ██║╚██████╗██║  ██║███████║
                ╚═════╝ ╚═╝      ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝
                """
            )
        )

        # Load config
        try:
            config_loaded = False
            try:
                with open("config.json", "r", encoding="utf-8") as f:
                    self.config = BF1ChsToolbox.Config.load(json.load(f))
                    config_loaded = True

            except BF1ChsToolbox.IncompatibleConfigException:
                console.print("[yellow]配置文件 config.json 版本不兼容。\n")
                if self._rich_confirm(message="是否尝试升级？"):
                    with open("config.json", "r", encoding="utf-8") as f:
                        config_dict = json.load(f)
                    self.config = BF1ChsToolbox.Config()

                    try:
                        self.config.update(config_dict)
                    except Exception as e:
                        console.print("[bold red]配置文件升级失败。\n")
                        raise e

                    with open("config.json", "w", encoding="utf-8") as f:
                        json.dump(
                            self.config._config_dict, f, indent=4, ensure_ascii=False
                        )

                    console.print("[bold green]配置文件升级成功。\n")
                    config_loaded = True

            finally:
                if config_loaded:
                    self.config.show()
                    self.paratranz_api = ParaTranzAPI(
                        self.config["paratranz.token"], PROJECT_ID
                    )

        except FileNotFoundError:
            self.config = BF1ChsToolbox.Config()
            console.print("[yellow]配置文件 config.json 不存在，使用默认配置初始化。\n")
            self.config.show()

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config._config_dict, f, indent=4, ensure_ascii=False)

            console.print("[yellow]请修改配置文件 config.json 后重新运行。")

            if self._rich_confirm(message="是否立刻打开配置文件？"):
                if platform.system() == "Windows":
                    os.startfile("config.json")
                elif platform.system() == "Darwin":
                    os.system("open ./config.json")
                elif platform.system() == "Linux":
                    os.system("xdg-open ./config.json")

            raise BF1ChsToolbox.ExitException

        except (RequestException, URLlib3RequestError):
            console.print("[bold red]网络错误。请检查网络连接是否正常。\n")
            input()
            raise BF1ChsToolbox.ExitException

        except (TypeError, ValueError) as e:
            console.print(
                f"[bold red]配置文件 config.json 格式错误：键 {e.args[0]} 值不合法。"
            )
            if e.args[1] is not None:
                console.print(f"[bold red]提示：{e.args[1]}")
            input()
            raise BF1ChsToolbox.ExitException

        except Exception as e:
            console.print(f"[bold red]配置文件 config.json 读取失败：{e}")
            input()
            raise BF1ChsToolbox.ExitException

        # Check for updates
        self.source_api: SourceAPI
        if self.config["meta.autoUpdate.source"] == "github":
            self.source_api = GithubAPI(REPO_OWNER_GITHUB, REPO_NAME)
        else:
            self.source_api = GiteeAPI(REPO_OWNER_GITEE, REPO_NAME)

        if self.config["meta.autoUpdate"]:
            # try:
            #     self._check_update()
            # except Exception as e:
            #     console.print(f"[bold red]检查更新失败: {e}\n")
            self._check_update()

    def _check_manifest(self) -> bool:
        """
        Check if all necessary files are present.
        """
        if not os.path.exists(self.config["paratranz.artifactPath"]):
            console.print(
                f"[bold red]下载路径 {os.path.abspath(self.config['paratranz.artifactPath'])} 不存在。"
            )
            return False

        checked = True
        artifact_directory = os.listdir(self.config["paratranz.artifactPath"])
        for file in ARTIFACT_MANIFEST.keys():
            if file not in artifact_directory:
                console.print(f"[bold red]缺失{ARTIFACT_MANIFEST[file]} {file}。")
                checked = False

        return checked

    def _download(self):
        """
        Download the artifact from ParaTranz.
        """
        artifact_datetime = self._rich_indeterminate_progress(
            task_name="从 ParaTranz 获取构建信息",
            short_name="获取构建信息",
            actor=self.paratranz_api.get_artifact_datetime,
        )
        if artifact_datetime is None:
            return

        console.print(
            f"最后构建于：[bold green]{artifact_datetime.strftime('%Y年%m月%d日 %H:%M:%S')}\n"
        )

        if os.path.exists(self.config["paratranz.artifactPath"]):
            console.print(
                f"[yellow]下载路径 {os.path.abspath(self.config['paratranz.artifactPath'])} 已存在。"
            )
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        console.print(
            f"[yellow]下载路径：{os.path.abspath(self.config['paratranz.artifactPath'])}\n"
        )

        def _skip_predicate(file: str) -> bool:
            return (file.startswith("utf8/") and not file.endswith(".json")) or (
                file.startswith("raw") and file.endswith(".json.json")
            )

        self._rich_indeterminate_progress(
            task_name="从 ParaTranz 下载",
            short_name="下载",
            actor=self.paratranz_api.download_artifact,
            path=self.config["paratranz.artifactPath"],
            skip_predicate=_skip_predicate,
        )

    def _replace(self):
        """
        Replace the localization files.
        """
        artifact_path = os.path.abspath(self.config["paratranz.artifactPath"])
        if not os.path.exists(artifact_path):
            console.print(
                f"[bold red]下载路径 {artifact_path} 不存在，请先下载汉化文件。"
            )
            return

        if not self._check_manifest():
            console.print("[bold red]汉化文件不完整，请重新下载汉化文件。")
            return

        processed_path = os.path.abspath(self.config["paratranz.processedPath"])
        if not os.path.exists(processed_path):
            os.makedirs(processed_path)
        else:
            console.print(f"[yellow]处理后文件目录 {processed_path} 已存在。")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        def _replace_runner(
            progress: Progress,
            task: TaskID,
            data: List[Dict[str, Union[str, int, List[str]]]],
            save_name: str,
        ):
            data_processed = {}

            for i in range(len(data)):
                item = data[i]
                assert isinstance(item["translation"], str)
                assert isinstance(item["original"], str)

                # Deal with newlines
                item["translation"] = item["translation"].replace("\\n", "\n")
                item["original"] = item["original"].replace("\\n", "\n")

                # Stage code: https://paratranz.cn/docs
                if item["stage"] in (0, 1, 2):
                    for term in terms:
                        item["translation"] = item["translation"].replace(
                            term, terms[term]
                        )

                data[i] = item
                data_processed[item["key"]] = item["translation"]
                progress.advance(task)

            with open(
                os.path.join(artifact_path, save_name),
                "w",
                encoding="utf-8",
            ) as new_file:
                json.dump(data, new_file, indent=4, ensure_ascii=False)

            with open(
                os.path.join(processed_path, save_name),
                "w",
                encoding="utf-8",
            ) as new_file:
                json.dump(data_processed, new_file, indent=4, ensure_ascii=False)
            progress.advance(task)

        terms: Dict = self._rich_indeterminate_progress(
            task_name="从 ParaTranz 获取术语表",
            short_name="获取术语表",
            actor=self.paratranz_api.get_terms,
        )
        if terms is None:
            return
        console.print(f"[underline yellow]术语表（共 {len(terms)} 项）")

        terms_table = Table(
            show_header=True,
            header_style="bold green",
            box=box.SQUARE_DOUBLE_HEAD,
        )
        terms_table.add_column("原文", justify="center")
        terms_table.add_column("替换为", justify="center")
        for i, item in enumerate(terms.items()):
            key, value = item
            if i == self.config["ui.maxItems"]:
                terms_table.add_row("...", "...")
                break
            terms_table.add_row(key, value)
        console.print(terms_table)
        console.print()

        for file, desc in ARTIFACT_MANIFEST.items():
            with open(os.path.join(artifact_path, file), "r", encoding="utf-8") as f:
                data = json.load(f)

            self._rich_progress(
                task_name=f"替换并处理{desc}",
                short_name=f"替换并处理 {file} ",
                actor=_replace_runner,
                total=len(data) + 1,
                data=data,
                save_name=file,
            )

    def _update_strings(self):
        """
        Update the strings chunk file.
        """
        histogram_path = os.path.abspath(self.config["localization.histogramPath"])
        if not os.path.exists(histogram_path):
            console.print(f"[yellow]码表路径 {histogram_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(histogram_path)
                console.print(
                    f"[yellow]请将导出后的码表文件放入路径 {histogram_path} 后重新选择本项。\n"
                )
            return

        strings_path = os.path.abspath(self.config["localization.stringsPath"])
        if not os.path.exists(strings_path):
            console.print(f"[yellow]本地化文件路径 {strings_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(strings_path)
                console.print(
                    f"[yellow]请将导出后的本地化文件放入路径 {strings_path} 后重新选择本项。\n"
                )
            return

        processed_path = os.path.abspath(self.config["paratranz.processedPath"])
        if not os.path.exists(processed_path):
            console.print(
                f"[bold red]处理后文件目录 {processed_path} 不存在，请先替换汉化文件。"
            )
            return

        original_histogram_path = self._rich_fuzzy_select_file(
            directory=histogram_path,
            types=[".chunk", ".bin"],
            message="选择 Frosty Editor 导出的原始码表文件",
        )
        if original_histogram_path is None:
            return

        original_strings_path = self._rich_fuzzy_select_file(
            directory=strings_path,
            types=[".chunk", ".bin"],
            message="选择 Frosty Editor 导出的原始本地化文件",
        )
        if original_strings_path is None:
            return

        histogram = Histogram(original_histogram_path)

        console.print("[bold green]已读取原始码表文件。\n")
        self._rich_show_object(histogram)

        def _create_strings_binary_runner(
            original_histogram_path: str, original_strings_path: str
        ) -> StringsBinary:
            return StringsBinary(
                Histogram(original_histogram_path), original_strings_path
            )

        strings_binary: StringsBinary = self._rich_indeterminate_progress(
            task_name="读取本地化文件",
            short_name="读取",
            actor=_create_strings_binary_runner,
            original_histogram_path=original_histogram_path,
            original_strings_path=original_strings_path,
        )
        if strings_binary is None:
            return

        self._rich_show_object(strings_binary)

        debug_mode = self._rich_confirm(
            message="是否启用调试模式？",
            default=False,
            desc="调试模式下，所有词条前将被添加对应键作为注释。",
        )
        console.print()

        # Load new strings json file
        with open(
            os.path.join(processed_path, "strings-zht.csv.json"),
            "r",
            encoding="utf-8",
        ) as new_file:
            new_dict: Dict[int, str] = {
                int(key, 16): value for key, value in json.load(new_file).items()
            }

        added = histogram.add_chars_from_strings(new_dict.values())
        console.print(f"[bold green]已自动添加 {added} 个字符至码表。\n")

        new_histogram_path = self._rich_text(
            message="输入新的码表文件名",
            default=f"new-{os.path.basename(original_histogram_path).rsplit('.', 1)[0]}.chunk",
            filter=lambda x: os.path.join(histogram_path, x),
        )
        if os.path.exists(new_histogram_path):
            console.print(f"[yellow]码表文件 {new_histogram_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        histogram.save(new_histogram_path)

        histogram = Histogram(new_histogram_path)
        self._rich_show_object(histogram)
        console.print(
            f"[bold green]已完成码表更新。导入 Chunk 时请一并修改 HistogramChunkSize 为 [underline]{histogram.chunk_size}[/] 。\n"
        )

        def _import_strings_wrapper():
            if debug_mode:
                for key, value in new_dict.items():
                    new_dict[key] = f"{key:08X} {value}"
            strings_binary.import_strings(new_dict)  # type: ignore
            return True

        if (
            self._rich_indeterminate_progress(
                task_name="导入汉化至本地化文件",
                short_name="导入",
                actor=_import_strings_wrapper,
            )
            is None
        ):
            return

        new_strings_path = self._rich_text(
            message="输入新的本地化文件名",
            default=f"new-{os.path.basename(original_strings_path).rsplit('.', 1)[0]}.chunk",
            filter=lambda x: os.path.join(strings_path, x),
        )
        if os.path.exists(new_strings_path):
            console.print(f"[yellow]本地化文件 {new_strings_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        def _save_strings_binary_runner(file_path: str):
            strings_binary.update(histogram)
            strings_binary.save(file_path)
            return True

        if (
            self._rich_indeterminate_progress(
                task_name="保存本地化文件",
                short_name="保存",
                actor=_save_strings_binary_runner,
                file_path=new_strings_path,
            )
            is None
        ):
            return

        self._rich_show_object(strings_binary)
        console.print(
            f"[bold green]已完成本地化文件更新。导入 Chunk 时请一并修改 BinaryChunkSize 为 [underline]{strings_binary.chunk_size}[/] 。\n"
        )

    def _update_histogram(self):
        """
        Update the histogram chunk file only.
        """
        histogram_path = os.path.abspath(self.config["localization.histogramPath"])
        if not os.path.exists(histogram_path):
            console.print(f"[yellow]码表路径 {histogram_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(histogram_path)
                console.print(
                    f"[yellow]请将导出后的码表文件放入路径 {histogram_path} 后重新选择本项。\n"
                )
            return

        strings_path = os.path.abspath(self.config["localization.stringsPath"])
        if not os.path.exists(strings_path):
            console.print(f"[yellow]本地化文件路径 {strings_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(strings_path)
                console.print(
                    f"[yellow]请将导出后的本地化文件放入路径 {strings_path} 后重新选择本项。\n"
                )
            return

        original_histogram_path = self._rich_fuzzy_select_file(
            directory=histogram_path,
            types=[".chunk", ".bin"],
            message="选择需要更新的原始码表文件",
        )
        if original_histogram_path is None:
            return

        extra_chars_path = self._rich_fuzzy_select_file(
            directory=histogram_path,
            types=[".txt"],
            message="选择额外字符列表文件",
        )
        if extra_chars_path is None:
            return

        original_strings_path = self._rich_fuzzy_select_file(
            directory=strings_path,
            types=[".chunk", ".bin"],
            message="选择需要更新的原始本地化文件",
        )
        if original_strings_path is None:
            return

        histogram = Histogram(original_histogram_path)

        console.print("[bold green]已读取原始码表文件。\n")
        self._rich_show_object(histogram)

        def _create_strings_binary_runner(
            original_histogram_path: str, original_strings_path: str
        ) -> StringsBinary:
            return StringsBinary(
                Histogram(original_histogram_path), original_strings_path
            )

        strings_binary: StringsBinary = self._rich_indeterminate_progress(
            task_name="读取本地化文件",
            short_name="读取",
            actor=_create_strings_binary_runner,
            original_histogram_path=original_histogram_path,
            original_strings_path=original_strings_path,
        )
        if strings_binary is None:
            return

        self._rich_show_object(strings_binary)

        # Load new chars file
        with open(extra_chars_path, "r", encoding="utf-8") as f:
            extra_chars = f.read().splitlines()

        added = histogram.add_chars_from_strings([], extra_chars)
        console.print(f"[bold green]已添加 {added} 个字符至码表。\n")

        new_histogram_path = self._rich_text(
            message="输入新的码表文件名",
            default=f"new-{os.path.basename(original_histogram_path).rsplit('.', 1)[0]}.chunk",
            filter=lambda x: os.path.join(histogram_path, x),
        )
        if os.path.exists(new_histogram_path):
            console.print(f"[yellow]码表文件 {new_histogram_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        histogram.save(new_histogram_path)

        histogram = Histogram(new_histogram_path)
        self._rich_show_object(histogram)
        console.print(
            f"[bold green]已完成码表更新。导入 Chunk 时请一并修改 HistogramChunkSize 为 [underline]{histogram.chunk_size}[/] 。\n"
        )

        new_strings_path = self._rich_text(
            message="输入新的本地化文件名",
            default=f"new-{os.path.basename(original_strings_path).rsplit('.', 1)[0]}.chunk",
            filter=lambda x: os.path.join(strings_path, x),
        )
        if os.path.exists(new_strings_path):
            console.print(f"[yellow]本地化文件 {new_strings_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        def _save_strings_binary_runner(file_path: str):
            strings_binary.update(histogram)
            strings_binary.save(file_path)
            return True

        if (
            self._rich_indeterminate_progress(
                task_name="保存本地化文件",
                short_name="保存",
                actor=_save_strings_binary_runner,
                file_path=new_strings_path,
            )
            is None
        ):
            return

        self._rich_show_object(strings_binary)
        console.print(
            f"[bold green]已完成本地化文件更新。导入 Chunk 时请一并修改 BinaryChunkSize 为 [underline]{strings_binary.chunk_size}[/] 。\n"
        )

    def _update_twinkle(self):
        """
        Generate twinkle dynamic files.
        """
        artifact_path = os.path.abspath(self.config["paratranz.artifactPath"])
        if not os.path.exists(artifact_path):
            console.print(
                f"[bold red]下载路径 {artifact_path} 不存在，请先下载汉化文件。"
            )
            return

        if not self._check_manifest():
            console.print("[bold red]汉化文件不完整，请重新下载汉化文件。")
            return

        twinkle_path = os.path.abspath(self.config["localization.twinklePath"])
        if not os.path.exists(twinkle_path):
            os.makedirs(twinkle_path)

        entries = []
        entry_dict = {}
        for file, desc in ARTIFACT_MANIFEST.items():
            with open(os.path.join(artifact_path, file), "r", encoding="utf-8") as f:
                entries.extend(json.load(f))

        twinkle_file_name = self._rich_text(
            message="输入新的本地化文件名",
            default=self.config["localization.twinkleFilename"],
        )
        twinkle_file_path = os.path.join(twinkle_path, twinkle_file_name)
        if os.path.exists(twinkle_file_path):
            console.print(f"[yellow]本地化文件 {twinkle_file_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        debug_mode = self._rich_confirm(
            message="是否启用调试模式？",
            default=False,
            desc="调试模式下，所有词条前将被添加对应键作为注释。",
        )
        console.print()

        def _twinkle_runner(
            progress: Progress,
            task: TaskID,
            entries: List[Dict[str, Union[str, int, List[str]]]],
        ):
            conflict_count = 0
            for item in entries:
                if item["original"] not in entry_dict:
                    entry_dict[item["original"]] = item["translation"]
                elif entry_dict[item["original"]] != item["translation"]:
                    conflict_count += 1

                if debug_mode:
                    entry_dict[item["original"]] = (
                        f"{item['key']} {item['translation']}"
                    )

                progress.advance(task)

            with open(
                twinkle_file_path,
                "w",
                encoding="utf-8",
            ) as new_file:
                json.dump(entry_dict, new_file, indent=4, ensure_ascii=False)
            progress.advance(task)

            return conflict_count

        conflict_count = self._rich_progress(
            task_name="导出动态本地化文件",
            short_name="导出动态本地化",
            actor=_twinkle_runner,
            total=len(entries) + 1,
            entries=entries,
        )

        if conflict_count is None:
            return
        elif conflict_count > 0:
            console.print(
                f"[bold red]导出时发现 {conflict_count} 个译文不一致冲突，请手动检测冲突查看。\n"
            )

        if platform.system() == "Windows":
            if self._rich_confirm(message="是否复制到 twinkle/assets 文件夹？"):
                # Code from https://stackoverflow.com/questions/6227590/finding-the-users-my-documents-path/30924555

                import ctypes.wintypes

                buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
                asset_path = os.path.join(
                    buf.value, "Battlefield 1", "twinkle", "assets"
                )

                if not os.path.exists(asset_path):
                    console.print(
                        f"[yellow]twinkle/assets 文件夹 {asset_path} 不存在。"
                    )
                else:
                    if os.path.exists(os.path.join(asset_path, twinkle_file_name)):
                        console.print(f"[yellow]文件 {twinkle_file_name} 已存在。\n")
                        if not self._rich_confirm(message="是否覆盖？"):
                            return
                        console.print()

                    import shutil

                    try:
                        shutil.copy(twinkle_file_path, asset_path)
                        console.print(
                            f"[bold green]已复制文件 {twinkle_file_name} 至 {asset_path}。\n"
                        )
                    except Exception as e:
                        console.print(f"[bold red]复制失败：{e}\n")

    def _res2ttf(self):
        """
        Convert .res to .ttf.
        """
        font_path = os.path.abspath(self.config["font.path"])
        if not os.path.exists(font_path):
            console.print(f"[yellow]字体文件路径 {font_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(font_path)
                console.print(
                    f"[yellow]请将导出后的资源文件放入路径 {font_path} 后重新选择本项。\n"
                )
            return

        original_res_path = self._rich_fuzzy_select_file(
            directory=font_path,
            types=".res",
            message="选择 Frosty Editor 导出的原始资源文件",
        )
        if original_res_path is None:
            return

        new_ttf_path = self._rich_text(
            message="输入新的字体文件名",
            default=f"new-{os.path.basename(original_res_path).replace('.res', '.ttf')}",
            filter=lambda x: os.path.join(font_path, x),
        )
        if os.path.exists(new_ttf_path):
            console.print(f"[yellow]字体文件 {new_ttf_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        def _convert_runner(original_res_path: str, new_ttf_path: str):
            with open(original_res_path, "rb") as original_res:
                with open(new_ttf_path, "wb") as new_ttf:
                    # Skip the first 16 bytes
                    original_res.seek(16)
                    new_ttf.write(original_res.read())

        self._rich_indeterminate_progress(
            task_name="转换字体文件",
            short_name="转换",
            actor=_convert_runner,
            original_res_path=original_res_path,
            new_ttf_path=new_ttf_path,
        )

    def _ttf2res(self):
        """
        Convert .ttf to .res.
        """
        font_path = os.path.abspath(self.config["font.path"])
        if not os.path.exists(font_path):
            console.print(f"[yellow]字体文件路径 {font_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(font_path)
                console.print(
                    f"[yellow]请将导出后的字体文件放入路径 {font_path} 后重新选择本项。\n"
                )
            return

        original_ttf_path = self._rich_fuzzy_select_file(
            directory=font_path,
            types=".ttf",
            message="选择需要导入的字体文件",
        )
        if original_ttf_path is None:
            return

        new_res_path = self._rich_text(
            message="输入新的字体资源文件名",
            default=f"new-{os.path.basename(original_ttf_path).replace('.ttf', '.res')}",
            filter=lambda x: os.path.join(font_path, x),
        )
        if os.path.exists(new_res_path):
            console.print(f"[yellow]字体资源文件 {new_res_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        def _convert_runner(original_ttf_path: str, new_res_path: str):
            with open(original_ttf_path, "rb") as original_ttf:
                with open(new_res_path, "wb") as new_res:
                    # Write the first 16 bytes
                    new_res.write(b"\x00" * 16)
                    new_res.write(original_ttf.read())

            try:
                ttf_obj = TTFInfo(original_ttf_path)
                return ttf_obj["NAME"]
            except Exception:
                return False

        font_family = self._rich_indeterminate_progress(
            task_name="转换字体资源文件",
            short_name="转换",
            actor=_convert_runner,
            original_ttf_path=original_ttf_path,
            new_res_path=new_res_path,
        )

        if font_family:
            console.print(
                f"[bold green]已完成字体转换。导入字体资源时请一并修改 FontFamily 为 [underline]{font_family}[/] 。\n"
            )
        elif font_family is False:
            # If font_family is False, it means no exception was raised before obtaining the font family.
            console.print(
                "[yellow]已完成字体转换，但字体信息获取失败。请手动获取 FontFamily。\n"
            )

    def _check_update(self):
        """
        Check for updates.
        """
        console.print("[yellow]正在检查更新...")
        try:
            (latest_asset_url, latest_version, latest_published_time, latest_log) = (
                self.source_api.get_latest_asset(ASSET_NAME)
            )
        except ProxyError as e:
            console.print("[bold red]代理错误。请检查代理设置是否正确。\n")
            raise e
        except (RequestException, URLlib3RequestError) as e:
            console.print(
                f"[bold red]未知网络错误 ({e.__class__.__name__})。请尝试使用代理连接。\n"
            )
            raise e

        if latest_version == VERSION:
            console.print("[bold green]当前版本已是最新。\n")
        else:
            console.print(
                f"[yellow]发现新版本 {latest_version}，发布于 {latest_published_time.strftime('%Y年%m月%d日 %H:%M:%S')}。\n"
            )
            console.print("[underline yellow]更新日志：")
            console.print(Markdown(latest_log))
            console.print()
            if self._rich_confirm(message="是否立即下载？"):
                webbrowser.open(latest_asset_url)
                raise BF1ChsToolbox.ExitException
            else:
                console.print("[yellow]当前版本已过时，请及时更新。\n")

    def _check_conflict(self):
        """
        Check for conflicts.
        """
        artifact_path = os.path.abspath(self.config["paratranz.artifactPath"])
        if not os.path.exists(artifact_path):
            console.print(
                f"[bold red]下载路径 {artifact_path} 不存在，请先下载汉化文件。"
            )
            return

        report_path = os.path.join(
            artifact_path, self.config["paratranz.conflictReport.filename"]
        )
        if os.path.exists(report_path):
            console.print(f"[yellow]冲突报告文件 {report_path} 已存在。")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        conflicts = Conflicts(PROJECT_ID)

        def _conflicts_runner(
            progress: Progress, task: TaskID, data: List[Any], file_name: str
        ):
            for obj in data:
                if "original" in obj and isinstance(obj["original"], str):
                    conflicts.add(
                        obj["original"],
                        file_name,
                        obj["key"],
                        obj["translation"],
                    )
                    progress.advance(task)
            return True

        for file in ARTIFACT_MANIFEST:
            with open(os.path.join(artifact_path, file), "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    console.print(f"[bold red]{file} 文件格式错误，跳过。")
                    continue

                if (
                    self._rich_progress(
                        task_name=f"检测{ARTIFACT_MANIFEST[file]}",
                        short_name=f"检测 {file} ",
                        actor=_conflicts_runner,
                        total=len(data),
                        data=data,
                        file_name=file,
                    )
                    is None
                ):
                    return

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(
                conflicts.to_markdown(
                    self.config["paratranz.conflictReport.headerLevel"]
                )
            )

        console.print(
            f"[bold green]已完成词条冲突检测。冲突报告已保存至 {report_path} 。\n"
        )

    def run(self):
        # Run main menu
        BF1ChsToolbox.SelectAction(
            title="工具箱主菜单",
            desc=f"当前版本：[light-blue]{VERSION}[/]",
            choices={
                "localization": {
                    "name": "本地化相关",
                    "actor": BF1ChsToolbox.SelectAction(
                        title="本地化相关",
                        desc="此部分包含与 ParaTranz 交互、生成 Frosty Editor 可用文件等相关功能。",
                        choices={
                            "download": {
                                "name": "从 ParaTranz 下载最新汉化文件",
                                "desc": "从 ParaTranz 项目导出处下载最新汉化压缩包，解压到指定路径。",
                                "actor": self._download,
                            },
                            "replace": {
                                "name": "使用 ParaTranz 术语库替换汉化文件",
                                "desc": "使用 ParaTranz 术语库对汉化文件进行就地替换，并额外生成工具箱能够处理的 .json 文件。",
                                "actor": self._replace,
                            },
                            "check_conflict": {
                                "name": "检测 ParaTranz 词条冲突",
                                "desc": "检测汉化文件中的译文不一致冲突，并输出为 .md 文件。",
                                "actor": self._check_conflict,
                            },
                            "strings": {
                                "name": "生成 Frosty Editor 码表并更新静态本地化 chunk 文件",
                                "desc": "根据替换后的 .json 汉化文件生成码表、更新导出的原始本地化文件，并生成新的本地化文件。",
                                "actor": self._update_strings,
                            },
                            "update-histogram": {
                                "name": "生成 Frosty Editor 码表并更新静态本地化 chunk 文件（仅插入新字符）",
                                "desc": "将给定的字符列表文件中的字符序列加入码表、更新导出的原始本地化文件，并生成新的本地化文件。本功能仅基于输入的字符列表文件，不会对原有的码表和本地化文件进行修改。",
                                "actor": self._update_histogram,
                            },
                            "twinkle": {
                                "name": "更新 Frosty Editor 动态本地化 chunk 文件",
                                "desc": "根据替换后的 .json 汉化文件生成可读取的动态本地化文件。",
                                "actor": self._update_twinkle,
                            },
                        },
                    ),
                },
                "font": {
                    "name": "字体替换相关",
                    "actor": BF1ChsToolbox.SelectAction(
                        title="字体替换相关",
                        desc="此部分包含字体替换相关功能。",
                        choices={
                            "res2ttf": {
                                "name": "资源文件 (.res) -> 字体文件 (.ttf)",
                                "desc": "将 Frosty Editor 导出的字体资源文件转换为 .ttf 字体文件。",
                                "actor": self._res2ttf,
                            },
                            "ttf2res": {
                                "name": "字体文件 (.ttf) -> 资源文件 (.res)",
                                "desc": "将 .ttf 字体文件转换为 Frosty Editor 可用的资源文件。",
                                "actor": self._ttf2res,
                            },
                        },
                    ),
                },
                "update": {
                    "name": "检查程序更新",
                    "actor": self._check_update,
                },
            },
            is_main=True,
        ).run()


if __name__ == "__main__":
    try:
        BF1ChsToolbox().run()
    except BF1ChsToolbox.ExitException:
        pass
    except BF1ChsToolbox.ExitException:
        pass
