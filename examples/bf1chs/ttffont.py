# Ported from PHP version, with streamlined features
# http://www.phpclasses.org/browse/package/2144.html

import struct


class TTFInfo:
    NAMES = {
        "COPYRIGHT": 0,
        "NAME": 1,
        "SUBFAMILY": 2,
        "SUBFAMILY_ID": 3,
        "FULL_NAME": 4,
        "VERSION": 5,
        "POSTSCRIPT_NAME": 6,
        "TRADEMARK": 7,
        "MANUFACTURER": 8,
        "DESIGNER": 9,
        "DESCRIPTION": 10,
        "VENDOR_URL": 11,
        "DESIGNER_URL": 12,
        "LICENSE": 13,
        "LICENSE_URL": 14,
        "PREFERRE_FAMILY": 16,
        "PREFERRE_SUBFAMILY": 17,
        "COMPAT_FULL_NAME": 18,
        "SAMPLE_TEXT": 19,
    }

    def __init__(self, filename):
        self.filename = filename
        self.text = None
        self.ntOffset = None
        self.info = self.getFontInfo()

    def getFontInfo(self):
        with open(self.filename, "rb") as f:
            self.text = f.read()

        number_of_tables = struct.unpack(">H", self.text[4:6])[0]

        for i in range(number_of_tables):
            tag = self.text[12 + i * 16 : 12 + i * 16 + 4].decode("utf-8")

            if tag == "name":
                self.ntOffset = struct.unpack(
                    ">L", self.text[12 + i * 16 + 8 : 12 + i * 16 + 12]
                )[0]
                offset_storage_dec = struct.unpack(
                    ">H", self.text[self.ntOffset + 4 : self.ntOffset + 6]
                )[0]
                number_name_records_dec = struct.unpack(
                    ">H", self.text[self.ntOffset + 2 : self.ntOffset + 4]
                )[0]

        storage_dec = offset_storage_dec + self.ntOffset

        assert self.ntOffset is not None

        font_tags = {}
        for j in range(number_name_records_dec):
            name_id_dec = struct.unpack(
                ">H",
                self.text[
                    self.ntOffset + 6 + j * 12 + 6 : self.ntOffset + 6 + j * 12 + 8
                ],
            )[0]
            string_length_dec = struct.unpack(
                ">H",
                self.text[
                    self.ntOffset + 6 + j * 12 + 8 : self.ntOffset + 6 + j * 12 + 10
                ],
            )[0]
            string_offset_dec = struct.unpack(
                ">H",
                self.text[
                    self.ntOffset + 6 + j * 12 + 10 : self.ntOffset + 6 + j * 12 + 12
                ],
            )[0]

            if name_id_dec and name_id_dec not in font_tags:
                font_tags[name_id_dec] = self.text[
                    storage_dec
                    + string_offset_dec : storage_dec
                    + string_offset_dec
                    + string_length_dec
                ].decode("utf-16-be")

        return font_tags

    def __getitem__(self, item: str):
        if item not in self.NAMES:
            raise AttributeError(f"Attribute {item} not found")
        return self.info[self.NAMES[item]]
