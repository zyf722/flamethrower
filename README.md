# flamethrower
> 🔥 ***Flamethrower***, where ❄️ ***Frostbite*** meets the dance of inferno.

`flamethrower` is a Python package designed to provide a simple interface for modders to interact with the original Frostbite engine binaries. 

## Installation
This package is managed by [Poetry](https://python-poetry.org/).

**Currently, the package is in its early stages of development and is not yet ready for public use.** However, if you are interested, you can install the package by cloning the repository and running the following command:

```bash
poetry install
```

Then you can use the package in the virtual environment created by Poetry.

## Usage
The package only supports the following features now:

- `flamethrower.hash`: Hash functions used by the Frostbite engine. Currently, only `FNV` series hash functions are supported.
- `flamethrower.localization`: Interface for `Histogram` and `LocalizationBinary` files.

Examples of how to use the package are available in the `examples` directory. There is only one example now, which is an interactive toolbox for Chinese localization of Battlefield 1 (with UI in Chinese). More examples are welcomed.

## Contributing
Though the package is still in its early stages of development, [Pull Requests](https://github.com/zyf722/flamethrower/pulls) are welcome.

You can setup your own copy of the source code with Git and [Poetry](https://python-poetry.org/):

```shell
# Git
git clone https://github.com/zyf722/flamethrower.git
cd flamethrower/

# Poetry
poetry lock
poetry install
poetry shell
```

It is strongly recommended to follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification when writing commit messages and creating pull requests.

## License
[GPL-3.0](/LICENSE)