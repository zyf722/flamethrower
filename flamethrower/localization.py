import io
import struct
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from .hash import fnv1_32_hash as loc_id_hash


class ChunkData(ABC):
    """
    Base class for chunk data.
    """

    def __init__(self, file_path: Optional[str] = None) -> None:
        if file_path:
            self.load(file_path)

    @abstractmethod
    def load(self, file_path: str) -> None:
        """
        Load a chunk from a file.

        Args:
            file_path (str): The path to the file.
        """
        pass

    @abstractmethod
    def save(self, file_path: str) -> None:
        """
        Save the chunk to a file.

        Args:
            file_path (str): The path to the file.
        """
        pass

    @property
    @abstractmethod
    def chunk_size(self) -> int:
        """
        Get the size of the chunk.

        Returns:
            int: The size of the chunk.
        """
        pass

    @classmethod
    def _unpack_single(cls, format: str, reader: io.BufferedReader) -> Any:
        """
        Unpack single data from a buffer.

        Args:
            format (str): The format of the data.
            reader (io.BufferedReader): The buffer to read from.

        Returns:
            Any: The unpacked data.
        """
        return struct.unpack(format, reader.read(struct.calcsize(format)))[0]

    @classmethod
    def _unpack_multiple(
        cls, format: str, size: int, reader: io.BufferedReader
    ) -> List[Any]:
        """
        Unpack data from a buffer.

        Args:
            format (str): The format of the data.
            size (int): The amount of data to unpack in format.
            reader (io.BufferedReader): The buffer to read from.

        Returns:
            List: The unpacked data.
        """
        format *= size
        return list(struct.unpack(format, reader.read(struct.calcsize(format))))


class Histogram(ChunkData):
    """
    Class for histogram chunk.
    """

    def __init__(self, file_path: Optional[str] = None, magic: int = 0x39001) -> None:
        self.magic: int = magic
        self.fileSize: Optional[int] = None
        self.dataOffSize: Optional[int] = None
        self.section: Optional[List[str]] = None

        super().__init__(file_path)

    def load(self, file_path: str) -> None:
        """
        Load a histogram chunk from a file.

        Args:
            file_path (str): The path to the file.
        """

        with open(file_path, "rb") as file:
            if self._unpack_single("I", file) != self.magic:
                raise ValueError("Invalid histogram chunk.")

            self.fileSize = self._unpack_single("I", file)
            self.dataOffSize = self._unpack_single("I", file)

            assert self.fileSize is not None
            assert self.dataOffSize is not None

            self.section = []
            for char in self._unpack_multiple(
                format="H",
                size=(self.fileSize + 8 - file.tell()) // 2,
                reader=file,
            ):
                self.section.append(chr(char))

    def add_chars_from_strings(
        self, strings: Iterable[str], extra_chars: Optional[Iterable[str]] = None
    ) -> int:
        """
        Add chars to the histogram. Necessary shifts will be added automatically.

        Args:
            strings (Iterable[str]): The strings containing chars to add.
            extra_chars (Optional[Iterable[str]]): Extra chars to add. Each str should only be one char.

        Returns:
            int: The amount of chars added.
        """
        assert self.fileSize is not None
        assert self.dataOffSize is not None
        assert self.section is not None

        char_set: Set[str] = set()
        for value in strings:
            char_set.update(value)

        if extra_chars:
            char_set.update(extra_chars)

        chars = list(char_set.difference(self.section))

        # Calculate needed indices
        shift_nums_index = 0x40
        while shift_nums_index < 0xFF:
            if self.section[shift_nums_index] != "\x00":
                break
            shift_nums_index += 1

        inserted_start = self.dataOffSize - 1
        shift_nums = [
            chr(num) for num in range(2, ord(self.section[shift_nums_index]) + 1)
        ]
        shift_nums_count = len(shift_nums)

        def calculate_byte_positions(chars):
            return [
                inserted_start + shift_nums_count + (shift_nums_index - 0x80) + i
                for i in range(len(chars))
            ]

        def calculate_shift_nums_and_mappings(byte_positions):
            shift_nums_set: set = set()
            for char, byte in zip(chars, byte_positions):
                shift_num = chr(byte // 0x80)
                if ord(shift_num) >= 0x80:
                    raise ValueError("Too much characters")
                if shift_num not in shift_nums_set:
                    shift_nums_set.add(shift_num)
            return sorted(list(shift_nums_set), key=lambda x: ord(x))

        while True:
            new_shift_nums = calculate_shift_nums_and_mappings(
                calculate_byte_positions(chars)
            )
            # The number of shift_nums doesn't change - the algorithm ends
            if len(new_shift_nums) == shift_nums_count:
                shift_nums = new_shift_nums
                break
            # Otherwise, update the number of shift_nums and repeat
            shift_nums_count = len(new_shift_nums)

        # Update the section
        self.section = (
            self.section[:0x80]
            + shift_nums
            + self.section[shift_nums_index:inserted_start]
            + chars
            + self.section[inserted_start:]
        )
        self.dataOffSize += len(chars)

        return len(chars)

    def save(self, file_path: str) -> None:
        """
        Save the histogram to a file.

        Args:
            file_path (str): The path to the file.
        """
        assert self.fileSize is not None
        assert self.dataOffSize is not None
        assert self.section is not None

        with open(file_path, "wb") as file:
            file.write(struct.pack("III", self.magic, self.fileSize, self.dataOffSize))
            for char in self.section:
                char_code = ord(char)
                if char_code > 0xFFFF:
                    print(
                        f"Warning: Char {char} with code {hex(char_code)} out of range. Skippping."
                    )
                else:
                    file.write(struct.pack("H", char_code))

            # Update fileSize
            self.fileSize = file.tell() - 8
            file.seek(4)
            file.write(struct.pack("I", self.fileSize))

    @property
    def chunk_size(self) -> int:
        """
        Get the size of the chunk.

        Returns:
            int: The size of the chunk.
        """
        assert self.fileSize is not None
        return self.fileSize + 8

    @property
    def shifts(self) -> List[int]:
        """
        Get the shifts of the histogram.

        Returns:
            List[int]: The shifts of the histogram.
        """
        assert self.section is not None

        shifts = []
        for i in range(0x1FE, 0x80, -1):
            if ord(self.section[i]) < 0x80:
                shifts.append(i)
        return shifts


class StringsBinary(ChunkData):
    """
    Class for strings binary chunk.

    Hash indice are stored as integers. You may use `f"{index:#0{10}X}"[2:]` to have a more readable output.
    """

    def __init__(
        self,
        histogram: Histogram,
        file_path: Optional[str] = None,
        magic: int = 0x39000,
    ) -> None:
        self.histogram: Histogram = histogram
        self.buffer: Optional[io.BytesIO] = None

        self.magic: int = magic
        self.fileSize: Optional[int] = None
        self.listSize: Optional[int] = None
        self.dataOffset: Optional[int] = None
        self.stringsOffset: Optional[int] = None
        self.section: Optional[str] = None
        self.hashPairList: Optional[List[Tuple[int, int]]] = None
        self.stringList: Optional[Dict[int, str]] = None

        super().__init__(file_path)

    @classmethod
    def _unpack_null_term_string(
        cls, reader: io.BufferedReader, encoding: str = "utf-8"
    ) -> str:
        """
        Unpack a null-terminated string from a buffer.

        Args:
            reader (io.BufferedReader): The buffer to read from.
            encoding (str, optional): The encoding of the string. Defaults to "utf-8".

        Returns:
            str: The unpacked string.
        """
        string = ""
        while True:
            char = reader.read(1)
            if char == b"\x00":
                break
            string += char.decode(encoding)
        return string

    @classmethod
    def _unpack_null_term_string_bytes(cls, reader: io.BufferedReader) -> bytes:
        """
        Unpack a null-terminated string from a buffer.

        Args:
            reader (io.BufferedReader): The buffer to read from.

        Returns:
            bytes: The unpacked string.
        """
        string = b""
        while True:
            char = reader.read(1)
            if char == b"\x00":
                break
            string += char
        return string

    def _decode_string(self, bin_string: bytes) -> str:
        """
        Decode a binary string using the histogram.

        Args:
            bin_string (bytes): The string to decode.

        Returns:
            str: The decoded string.
        """
        assert self.histogram.section is not None

        index = 0
        string = ""
        while index < len(bin_string):
            byte = bin_string[index]
            if byte < 0x80:
                # ASCII
                string += chr(byte)
            else:
                # Not ASCII
                tmp = self.histogram.section[byte]
                if ord(tmp) >= 0x80:
                    string += tmp
                else:
                    index += 1
                    byte = bin_string[index]
                    if byte > 0x80:
                        string += self.histogram.section[byte - 0x80 + (ord(tmp) << 7)]
            index += 1
        return string

    def _encode_string(self, string: str, shifts: List[int]) -> bytes:
        """
        Encode a string using the histogram.

        Args:
            string (str): The string to encode.

        Returns:
            bytes: The encoded string.
        """
        assert self.histogram.section is not None

        bin_string = b""
        for char in string:
            check_shift = False
            ord_tmp = ord(char)
            if ord_tmp < 0x80:
                # ASCII
                bin_string += struct.pack("B", ord_tmp)
            else:
                # Not ASCII
                byte = self.histogram.section.index(char)

                if byte <= 0xFF:
                    bin_string += struct.pack("B", byte)
                else:
                    # Try to find a proper shift to fit the byte into range
                    for shift in shifts:
                        shift_byte = ord(self.histogram.section[shift]) << 7
                        byte_shifted = byte - shift_byte
                        if byte_shifted < 0x80 and byte_shifted >= 0:
                            bin_string += struct.pack("B", shift)
                            bin_string += struct.pack("B", (byte_shifted + 0x80))
                            check_shift = True
                            break

                    if not check_shift:
                        # If this happens, it means that there is no proper shift to fit the character into range.
                        # You may want to expand the shift range by calling `Histogram.expand_shift_range` method first.

                        raise ValueError(
                            f"Error: Unable to encode character {char} to bytes."
                        )

        bin_string += b"\x00"
        return bin_string

    def load(self, file_path: str) -> None:
        """
        Load a strings binary chunk from a file.

        Args:
            file_path (str): The path to the file.
        """

        with open(file_path, "rb") as file:
            # Header
            if self._unpack_single("I", file) != self.magic:
                raise ValueError("Invalid strings binary chunk.")

            self.fileSize = self._unpack_single("I", file)
            self.listSize = self._unpack_single("I", file)
            self.dataOffset = self._unpack_single("I", file)
            self.stringsOffset = self._unpack_single("I", file)

            assert self.fileSize is not None
            assert self.listSize is not None
            assert self.dataOffset is not None
            assert self.stringsOffset is not None

            self.section = self._unpack_null_term_string(file)

            # Read hash pairs in (hash, offset) format
            self.hashPairList = []
            file.seek(self.dataOffset + 8)
            while file.tell() != self.stringsOffset + 8:
                self.hashPairList.append(
                    (
                        self._unpack_single("I", file),
                        self._unpack_single("I", file),
                    )
                )

            # Read strings by locating offsets
            self.stringList = {}
            for hash_pair in self.hashPairList:
                file.seek(self.stringsOffset + hash_pair[1] + 8)
                bin_string = self._unpack_null_term_string_bytes(file)
                self.stringList[hash_pair[0]] = self._decode_string(bin_string)

    def update(self, histogram: Histogram) -> None:
        """
        Update header fields and hash pair offsets by simulating writing into a buffer.

        `fileSize`, `listSize`, `dataOffset`, `stringsOffset` and `hashPairList` will be updated.
        """
        assert self.fileSize is not None
        assert self.listSize is not None
        assert self.dataOffset is not None
        assert self.stringsOffset is not None
        assert self.section is not None
        assert self.hashPairList is not None
        assert self.stringList is not None

        self.buffer = io.BytesIO()
        self.histogram = histogram

        # Header
        self.listSize = len(self.stringList)
        self.dataOffset = 0x8C
        self.stringsOffset = 0x8C + self.listSize * 8
        self.buffer.write(
            struct.pack(
                "IIIII",
                self.magic,
                0,  # We skip `fileSize` first
                self.listSize,
                self.dataOffset,
                self.stringsOffset,
            )
        )
        self.buffer.write(self.section.encode())

        # Padding stuff
        while self.buffer.tell() < self.dataOffset + 8:
            self.buffer.write(b"\x00")

        # Update hash pair offsets
        shifts = self.histogram.shifts
        with io.BytesIO() as string_buffer:
            self.hashPairList = []
            for key, value in self.stringList.items():
                self.hashPairList.append((key, string_buffer.tell()))
                self.buffer.write(struct.pack("II", key, string_buffer.tell()))
                string_buffer.write(self._encode_string(value, shifts))
            string_buffer.seek(0)
            string_bytes = string_buffer.read()

        # Write strings
        self.buffer.write(string_bytes)

        # Update fileSize
        self.fileSize = self.buffer.tell() - 8
        self.buffer.seek(4)
        self.buffer.write(struct.pack("I", self.fileSize))

    def save(self, file_path: str) -> None:
        """
        Save the strings binary to a file using the buffer.

        Attention: Call `update()` before saving.

        Args:
            file_path (str): The path to the file.
            update (bool, optional): Whether to update the chunk before saving. Defaults to True.
        """
        assert self.buffer is not None

        with open(file_path, "wb") as file:
            file.write(self.buffer.getvalue())  # Directly write the buffer

    def import_strings(self, strings: Dict[Union[str, int], str]) -> None:
        """
        Import strings to the strings binary.

        Args:
            strings (Dict[Union[str, int], str]): The strings to import. For new strings, use a custom string as key - it will be automatically hashed.
        """
        assert self.stringList is not None

        for key, value in strings.items():
            if isinstance(key, str):
                hashed_key = loc_id_hash(key.encode())
            else:
                hashed_key = key
            self.stringList[hashed_key] = value

    @property
    def chunk_size(self) -> int:
        """
        Get the size of the chunk.

        Returns:
            int: The size of the chunk.
        """
        assert self.fileSize is not None
        return self.fileSize + 8
