import json
import os
import re
import textwrap
import webbrowser
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from api import GithubAPI, ParaTranzAPI, ProxyError, RequestException
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from rich import box
from rich.console import Console
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

from flamethrower.localization import Histogram, StringsBinary

VERSION = "v0.2.0"
PROJECT_ID = 8862
REPO_NAME = "flamethrower"
REPO_OWNER = "zyf722"
ASSET_NAME = "bf1chs.zip"

os.chdir(os.path.dirname(os.path.abspath(__file__)))

console = Console(
    theme=Theme({"dark-gray": "#5c6370", "light-blue": "#61afef"}),
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
        none_validator = ((lambda x: True), None)
        json_validator = (
            (
                lambda x: bool(re.match(r'^[^<>:"/\\|?*]+\Z', x))
                and len(x) <= 255
                and x.endswith(".json")
            ),
            '文件名不应包含特殊字符（< > : " / \\ | ? *），文件名长度不应超过 255 个字符且应以 .json 结尾。',
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
                "汉化文件存放路径，可为相对路径。下载与替换操作均在此路径下进行。",
                *none_validator,
            ),
            "paratranz.newStringsBinaryFilename": (
                "new-strings.json",
                "替换术语后新生成的静态本地化文件名，需以 .json 结尾。",
                *json_validator,
            ),
            "paratranz.newTwinkleFilename": (
                "new-twinkle.json",
                "替换术语后新生成的动态本地化文件名，需以 .json 结尾。",
                *json_validator,
            ),
            "localization.histogramPath": (
                "localization/histogram",
                "码表文件存放路径，可为相对路径。",
                *none_validator,
            ),
            "localization.stringsPath": (
                "localization/strings",
                "本地化文件存放路径，可为相对路径。",
                *none_validator,
            ),
            "font.path": (
                "font",
                "字体文件存放路径，可为相对路径。",
                *none_validator,
            ),
            "ui.maxItems": (
                10,
                "本程序界面中最多显示的项目数，当项目数超过此值时会自动截断。对表格、列表等生效。",
                lambda x: isinstance(x, int) and x > 0,
                "应为正整数。",
            ),
            "meta.autoUpdate": (
                True,
                "是否在启动时自动检查更新。",
                lambda x: isinstance(x, bool),
                "应为布尔值。",
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
                except RequestException as e:
                    console.print(f"[bold red]未知网络错误 ({e.__class__.__name__}): {e}\n")
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
    def _rich_confirm(message: str, default=True, **kwargs):
        """
        Helper function to show confirm in rich format.
        """
        console.print("[dark-gray]（输入 y/n 或者回车键直接确认）")
        return inquirer.confirm(
            message=message,
            default=default,
            confirm_letter="y",
            reject_letter="n",
            transformer=lambda result: "是" if result else "否",
            **kwargs,
        ).execute()

    @staticmethod
    def _rich_integer(message: str, default: int = 0, **kwargs):
        """
        Helper function to show integer in rich format.
        """
        console.print("[dark-gray]（使用方向键上下增减 / 数字键输入数字 / 回车键确认）")
        result = inquirer.number(
            message=message,
            default=default,
            **kwargs,
        ).execute()
        console.print()
        return int(result)

    @staticmethod
    def _rich_text(message: str, default: str = "", **kwargs):
        """
        Helper function to show text in rich format.
        """
        console.print("[dark-gray]（输入文本 / 回车键确认）")
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

        console.print("[dark-gray]（使用方向键上下移动 / 回车键确认 / 输入关键词进行模糊搜索）")
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
            try:
                with open("config.json", "r", encoding="utf-8") as f:
                    self.config = BF1ChsToolbox.Config.load(json.load(f))
                self.config.show()
                self.paratranz_api = ParaTranzAPI(
                    self.config["paratranz.token"], PROJECT_ID
                )

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

        except FileNotFoundError:
            self.config = BF1ChsToolbox.Config()
            console.print("[yellow]配置文件 config.json 不存在，使用默认配置初始化。\n")
            self.config.show()

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config._config_dict, f, indent=4, ensure_ascii=False)

            console.print("[yellow]请修改配置文件 config.json 后重新运行。")

            if self._rich_confirm(message="是否立刻打开配置文件？"):
                import platform

                if platform.system() == "Windows":
                    os.startfile("config.json")
                elif platform.system() == "Darwin":
                    os.system("open ./config.json")
                elif platform.system() == "Linux":
                    os.system("xdg-open ./config.json")

            raise BF1ChsToolbox.ExitException

        except (TypeError, ValueError) as e:
            console.print(f"[bold red]配置文件 config.json 格式错误：键 {e.args[0]} 值不合法。")
            if e.args[1] is not None:
                console.print(f"[bold red]提示：{e.args[1]}")
            input()
            raise BF1ChsToolbox.ExitException

        except Exception as e:
            console.print(f"[bold red]配置文件 config.json 读取失败：{e}")
            input()
            raise BF1ChsToolbox.ExitException

        # Check for updates
        self.github_api = GithubAPI(REPO_OWNER, REPO_NAME)
        if self.config["meta.autoUpdate"]:
            try:
                self._check_update()
            except Exception:
                console.print("[bold red]自动更新失败。\n")

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

        self._rich_indeterminate_progress(
            task_name="从 ParaTranz 下载",
            short_name="下载",
            actor=self.paratranz_api.download_artifact,
            path=self.config["paratranz.artifactPath"],
        )

    def _replace(self):
        """
        Replace the localization files.
        """

        def _replace_runner(
            progress: Progress, task: TaskID, new_dict: Dict, save_name: str
        ):
            for key in new_dict:
                assert isinstance(new_dict[key], tuple)

                # Stage code: https://paratranz.cn/docs
                if new_dict[key][1] in (0, 1, 2):
                    raw_string = new_dict[key][0]
                    for term in terms:
                        raw_string = raw_string.replace(term, terms[term])
                    new_dict[key] = raw_string
                else:
                    new_dict[key] = new_dict[key][0]
                progress.advance(task)

            with open(
                os.path.join(artifact_path, save_name),
                "w",
                encoding="utf-8",
            ) as new_file:
                json.dump(new_dict, new_file, indent=4, ensure_ascii=False)
            progress.advance(task)

        def _load_raw_json(path: str) -> Dict:
            original_json = open(
                os.path.join(artifact_path, path),
                "r",
                encoding="utf-8",
            )
            return {
                item["key"]: (item["translation"], item["stage"])
                for item in json.load(original_json)
            }

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

        artifact_path = os.path.abspath(self.config["paratranz.artifactPath"])
        if not os.path.exists(artifact_path):
            console.print(f"[bold red]下载路径 {artifact_path} 不存在，请先下载汉化文件。")
            return

        # For strings-zht.csv
        if os.path.exists(
            os.path.join(
                artifact_path, self.config["paratranz.newStringsBinaryFilename"]
            )
        ):
            console.print(
                f"[yellow]静态本地化文件 {self.config['paratranz.newStringsBinaryFilename']} 已存在。"
            )
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        # NOTE: stop using csv
        # original_csv = open(
        #     os.path.join(artifact_path, "strings-zht.csv"),
        #     "r",
        #     encoding="utf-8-sig",  # However \ufeff still appears, why?
        # )
        # new_dict = {}
        # for row in csv.reader(original_csv):
        #     if row[0].startswith("\ufeff"):
        #         row[0] = row[0][1:]
        #     new_dict[row[0]] = row[2] if len(row) == 3 else row[1]

        new_dict = _load_raw_json("strings-zht.csv.json")
        self._rich_progress(
            task_name="替换静态本地化文件",
            short_name="替换静态本地化",
            actor=_replace_runner,
            total=len(new_dict) + 1,
            new_dict=new_dict,
            save_name=self.config["paratranz.newStringsBinaryFilename"],
        )

        # For twinkle.json
        if os.path.exists(
            os.path.join(artifact_path, self.config["paratranz.newTwinkleFilename"])
        ):
            console.print(
                f"[yellow]动态本地化文件 {self.config['paratranz.newTwinkleFilename']} 已存在。"
            )
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        new_dict = _load_raw_json("twinkle.json")
        self._rich_progress(
            task_name="替换动态本地化文件",
            short_name="替换动态本地化",
            actor=_replace_runner,
            total=len(new_dict) + 1,
            new_dict=new_dict,
            save_name=self.config["paratranz.newTwinkleFilename"],
        )

    def _update_histogram(self):
        """
        Update the histogram chunk file.
        """
        histogram_path = os.path.abspath(self.config["localization.histogramPath"])
        if not os.path.exists(histogram_path):
            console.print(f"[yellow]码表路径 {histogram_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(histogram_path)
                console.print(f"[yellow]请将导出后的码表文件放入路径 {histogram_path} 后重新选择本项。\n")
            return

        original_histogram_path = self._rich_fuzzy_select_file(
            directory=histogram_path,
            types=[".chunk", ".bin"],
            message="选择 Frosty Editor 导出的原始码表文件",
        )
        if original_histogram_path is None:
            return

        histogram = Histogram(original_histogram_path)

        console.print("[bold green]已读取原始码表文件。\n")
        self._rich_show_object(histogram)

        char_list_path = self._rich_fuzzy_select_file(
            directory=histogram_path,
            types=".txt",
            message="选择新增字符列表文件",
        )
        if char_list_path is None:
            return

        added = histogram.add_chars_from_file(char_list_path)
        console.print(f"[bold green]已添加 {added} 个字符。\n")

        expand_shifts = self._rich_integer(
            message="输入码表位移量个数的扩展量（扩展此值能够使码表支持更多字符）",
            default=48,
            min_allowed=0,
        )
        if expand_shifts is None:
            return

        histogram.expand_shift_range(expand_shifts)

        new_histogram_path = self._rich_text(
            message="输入新的码表文件名",
            default=f"new-{os.path.basename(original_histogram_path)}",
            filter=lambda x: os.path.join(histogram_path, x),
        )
        if os.path.exists(new_histogram_path):
            console.print(f"[yellow]码表文件 {new_histogram_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        histogram.save(new_histogram_path)

        self._rich_show_object(histogram)
        console.print(
            f"[bold green]已完成码表更新。导入 Chunk 时请一并修改 HistogramChunkSize 为 [underline]{histogram.chunk_size}[/] 。\n"
        )

    def _update_strings(self):
        """
        Update the strings chunk file.
        """
        strings_path = os.path.abspath(self.config["localization.stringsPath"])
        if not os.path.exists(strings_path):
            console.print(f"[yellow]本地化文件路径 {strings_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(strings_path)
                console.print(f"[yellow]请将导出后的本地化文件放入路径 {strings_path} 后重新选择本项。\n")
            return

        original_strings_path = self._rich_fuzzy_select_file(
            directory=strings_path,
            types=[".chunk", ".bin"],
            message="选择 Frosty Editor 导出的原始本地化文件",
        )
        if original_strings_path is None:
            return

        histogram_path = os.path.abspath(self.config["localization.histogramPath"])
        if not os.path.exists(histogram_path):
            console.print(f"[yellow]码表路径 {histogram_path} 不存在，请先更新码表。")
            return

        original_histogram_path = self._rich_fuzzy_select_file(
            directory=histogram_path,
            types=[".chunk", ".bin"],
            message="选择 Frosty Editor 导出的原始码表文件",
        )
        if original_histogram_path is None:
            return

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

        self._rich_show_object(strings_binary)

        # Load new strings json file
        artifact_path = os.path.abspath(self.config["paratranz.artifactPath"])
        if not os.path.exists(artifact_path):
            console.print(f"[bold red]下载路径 {artifact_path} 不存在，请先下载汉化文件。")
            return

        with open(
            os.path.join(
                artifact_path, self.config["paratranz.newStringsBinaryFilename"]
            ),
            "r",
            encoding="utf-8",
        ) as new_file:
            new_dict = {
                int(key, 16): value for key, value in json.load(new_file).items()
            }

        self._rich_indeterminate_progress(
            task_name="导入汉化至本地化文件",
            short_name="导入",
            actor=strings_binary.import_strings,
            strings=new_dict,
        )

        new_histogram_path = self._rich_fuzzy_select_file(
            directory=histogram_path,
            types=[".chunk", ".bin"],
            message="选择更新后的码表文件",
        )
        if new_histogram_path is None:
            return

        new_strings_path = self._rich_text(
            message="输入新的本地化文件名",
            default=f"new-{os.path.basename(original_strings_path)}",
            filter=lambda x: os.path.join(strings_path, x),
        )
        if os.path.exists(new_strings_path):
            console.print(f"[yellow]本地化文件 {new_strings_path} 已存在。\n")
            if not self._rich_confirm(message="是否覆盖？"):
                return
            console.print()

        def _save_strings_binary_runner(histogram: Histogram, file_path: str):
            strings_binary.update(histogram)
            strings_binary.save(file_path)

        self._rich_indeterminate_progress(
            task_name="保存本地化文件",
            short_name="保存",
            actor=_save_strings_binary_runner,
            histogram=Histogram(new_histogram_path),
            file_path=new_strings_path,
        )

        self._rich_show_object(strings_binary)
        console.print(
            f"[bold green]已完成本地化文件更新。导入 Chunk 时请一并修改 BinaryChunkSize 为 [underline]{strings_binary.chunk_size}[/] 。\n"
        )

    def _res2ttf(self):
        """
        Convert .res to .ttf.
        """
        font_path = os.path.abspath(self.config["font.path"])
        if not os.path.exists(font_path):
            console.print(f"[yellow]字体文件路径 {font_path} 不存在。")
            if self._rich_confirm(message="是否创建？"):
                os.makedirs(font_path)
                console.print(f"[yellow]请将导出后的资源文件放入路径 {font_path} 后重新选择本项。\n")
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
                console.print(f"[yellow]请将导出后的字体文件放入路径 {font_path} 后重新选择本项。\n")
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

        self._rich_indeterminate_progress(
            task_name="转换字体资源文件",
            short_name="转换",
            actor=_convert_runner,
            original_ttf_path=original_ttf_path,
            new_res_path=new_res_path,
        )

    def _check_update(self):
        """
        Check for updates.
        """
        console.print("[yellow]正在检查更新...")
        try:
            (
                latest_asset_url,
                latest_version,
                latest_published_time,
            ) = self.github_api.get_latest_asset(ASSET_NAME)
        except ProxyError as e:
            console.print("[bold red]代理错误。请检查代理设置是否正确。\n")
            raise e
        except RequestException as e:
            console.print(f"[bold red]未知网络错误 ({e.__class__.__name__}): {e}\n")
            raise e

        if latest_version == VERSION:
            console.print("[bold green]当前版本已是最新。\n")
        else:
            console.print(
                f"[yellow]发现新版本 {latest_version}，发布于 {latest_published_time.strftime('%Y年%m月%d日 %H:%M:%S')}。\n"
            )
            if self._rich_confirm(message="是否立即下载？"):
                webbrowser.open(latest_asset_url)
                raise BF1ChsToolbox.ExitException
            else:
                console.print("[yellow]当前版本已过时，请及时更新。\n")

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
                                "desc": "使用 ParaTranz 术语库对汉化文件进行替换，生成能够导入的 .json 文件。",
                                "actor": self._replace,
                            },
                            "histogram": {
                                "name": "更新 Frosty Editor 码表 chunk 文件",
                                "desc": "向导出的原始码表文件增加新的字符，并生成新的码表文件。",
                                "actor": self._update_histogram,
                            },
                            "strings": {
                                "name": "更新 Frosty Editor 静态本地化 chunk 文件",
                                "desc": "用替换后的 .json 汉化文件更新导出的原始本地化文件，并生成新的本地化文件。",
                                "actor": self._update_strings,
                            },
                            "twinkle": {
                                "name": "更新 Frosty Editor 动态本地化 chunk 文件",
                                "actor": None,
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
