# Source - https://stackoverflow.com/a
# Posted by thinwybk, modified by community. See post 'Timeline' for change history
# Retrieved 2025-11-20, License - CC BY-SA 4.0

import shutil
import sys
from distutils.command.build_ext import build_ext
from distutils.errors import CCompilerError, DistutilsExecError, DistutilsPlatformError
from pathlib import Path

from setuptools import Distribution, Extension, setup


def build():
    ext_modules = [
        Extension(
            name="cligram.utils._device",
            sources=["src/cligram/utils/_device.c"],
        )
    ]

    distribution = Distribution({"ext_modules": ext_modules})
    cmd = build_ext(distribution)
    cmd.ensure_finalized()
    cmd.run()

    # Copy built extensions back to the project
    for output in cmd.get_outputs():
        output = Path(output)
        relative_extension = Path("src") / output.relative_to(cmd.build_lib)

        shutil.copyfile(output, relative_extension)


if __name__ == "__main__":
    build()
