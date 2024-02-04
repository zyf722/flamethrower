from typing import Dict, Set


class Conflicts:
    class Entry:
        def __init__(self, file_name: str, original: str, key: str, value: str) -> None:
            self.file_name = file_name
            self.original = original
            self.key = key
            self.value = value

        def __eq__(self, __value: object) -> bool:
            return (
                isinstance(__value, Conflicts.Entry)
                and self.original == __value.original
                and self.value == __value.value
            )

        def __hash__(self) -> int:
            return hash((self.original, self.value))

    conflict_dict: Dict[str, Set[Entry]]

    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        self.conflict_dict = {}

    def add(self, original: str, file_name: str, key: str, value: str) -> None:
        if original not in self.conflict_dict:
            self.conflict_dict[original] = set()
        self.conflict_dict[original].add(
            Conflicts.Entry(file_name, original, key, value)
        )

    def to_markdown(self, header_level: int = 2) -> str:
        markdown = ""
        count = 0
        for key, entries in self.conflict_dict.items():
            if len(entries) == 1:
                continue

            count += 1

            markdown += "#" * header_level + f" {count}. {key}\n\n"
            for entry in entries:
                markdown += f"- ([文件 `{entry.file_name}` 中的 `{entry.key}`](https://paratranz.cn/projects/{self.project_id}/strings?key={entry.key})): `{entry.value}`\n"
            markdown += "\n"
        return markdown
