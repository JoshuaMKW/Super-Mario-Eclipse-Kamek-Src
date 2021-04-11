from __future__ import annotations

import argparse
import atexit
import json
import subprocess
import time
from fnmatch import fnmatch
from io import BytesIO
from pathlib import Path
from typing import Union

import oead
import psutil
from dolreader.dolfile import DolFile
from pyisotools.bnrparser import BNR
from pyisotools.iso import GamecubeISO

from compiler import Compiler, Define

TMPDIR = Path("tmp-compiler")


@atexit.register
def clean_resources():
    if TMPDIR.is_dir():
        pass  # shutil.rmtree(TMPDIR)


class FilePatcher(Compiler):
    class STATE:
        DEBUG = "DEBUG"
        RELEASE = "RELEASE"

    class BOOTTYPE:
        DOL = "DOL"
        ISO = "ISO"
        NONE = "NONE"

    def __init__(self, build: STATE, gameDir: str, projectDir: str = Path.cwd(), bootfrom: BOOTTYPE = BOOTTYPE.DOL, startAddr: int = 0x80000000, shines: int = 120):
        if isinstance(startAddr, str):
            startAddr = int(startAddr, 16)

        self.projectDir = Path(projectDir)
        self.gameDir = Path(gameDir)
        self.state = build
        self.maxShines = shines
        self.boottype = bootfrom
        self._fileTables = {}

        self._init_tables()

        super().__init__(Path("src/compiler"),
                         self._get_matching_filepath(
                             self.solutionDir / "main.dol"),
                         Path("src/linker/address.map"),
                         False,
                         startAddr)

        if self.is_release():
            self.defines = [
                Define("SME_MAX_SHINES", f"{self.maxShines}"), Define("SME_RELEASE")]
        elif self.is_debug():
            self.defines = [
                Define("SME_MAX_SHINES", f"{self.maxShines}"), Define("SME_DEBUG")]
        else:
            raise ValueError(f"Unknown patcher state {self.state}")

    @property
    def solutionDir(self) -> Path:
        if self.is_release():
            return self.projectDir / "bin" / "release"
        elif self.is_debug():
            return self.projectDir / "bin" / "debug"

    def is_release(self) -> bool:
        return self.state == FilePatcher.STATE.RELEASE

    def is_debug(self) -> bool:
        return self.state == FilePatcher.STATE.DEBUG

    def is_booting(self) -> bool:
        self.boottype != FilePatcher.BOOTTYPE.NONE

    def is_iso_boot(self) -> bool:
        self.boottype == FilePatcher.BOOTTYPE.ISO

    def is_dol_boot(self) -> bool:
        self.boottype == FilePatcher.BOOTTYPE.DOL

    def patch_game(self):
        with (self.solutionDir / ".config.json").open("r") as f:
            config = json.load(f)

        self._rename_files_from_config()
        self._replace_files(config)

        if self._patch_dol() and self.is_booting():
            for proc in psutil.process_iter():
                if proc.name() == "Dolphin.exe":
                    proc.kill()
                    while proc.is_running():
                        time.sleep(0.01)

            if self.is_release():
                options = ("-C Dolphin.General.DebugModeEnabled=True",
                           "-C Dolphin.General.OnScreenDisplayMessages=True",
                           "-C Dolphin.General.UsePanicHandlers=True",
                           "-C Dolphin.Core.CPUCore=1",
                           "-C Dolphin.Core.Fastmem=False",
                           "-C Dolphin.Core.CPUThread=False",
                           "-C Dolphin.Core.MMU=True",
                           "-C Logger.Logs.OSREPORT=True",
                           "-C Logger.Options.WriteToConsole=True",
                           "-C Logger.Options.WriteToWindow=True")
            else:
                options = ("-C Dolphin.General.ShowLag=True",
                           "-C Dolphin.General.ExtendedFPSInfo=True",
                           "-C Dolphin.General.DebugModeEnabled=True",
                           "-C Dolphin.General.OnScreenDisplayMessages=True",
                           "-C Dolphin.General.UsePanicHandlers=True",
                           "-C Dolphin.Core.CPUCore=1",
                           "-C Dolphin.Core.Fastmem=False",
                           "-C Dolphin.Core.CPUThread=False",
                           "-C Dolphin.Core.MMU=True",
                           "-C Logger.Logs.OSREPORT=True",
                           "-C Logger.Options.WriteToConsole=True",
                           "-C Logger.Options.WriteToWindow=True")

            dolphin = Path(config["dolphinpath"])

            if self.is_dol_boot():
                print(f"\nAttempting to boot Dolphin by DOL at {dolphin}...\n")
                subprocess.Popen(
                    f"\"{dolphin}\" -e \"{self.dest}\" " + " ".join(options), shell=True)
            elif self.is_iso_boot():
                print(f"\nAttempting to boot Dolphin by ISO at {dolphin}...\n")
                isoPath = self._build_iso(config)
                subprocess.Popen(
                    f"\"{dolphin}\" -e \"{isoPath}\" " + " ".join(options), shell=True)

    def _build_iso(self, config: dict) -> Path:
        print("")
        print("====== ISO BUILDING ======".center(128))
        print("-"*128)

        isoPath = Path(config["buildpath"])

        print(f"{self.dest.parent.parent} -> {isoPath}")

        iso = GamecubeISO.from_root(self.dest.parent.parent, True)
        iso.build(isoPath, preCalc=False)

        print("-"*128)
        return isoPath

    def _patch_dol(self) -> bool:
        from tools.pyiiasmh import pyiiasmh_cli
        dolPath = self.solutionDir / "system/main.dol"
        kernelPath = self.solutionDir / "kuribo/KuriboKernel.bin"

        if dolPath.exists():
            if self.is_release():
                print("")
                print("====== DOL PATCHING ======".center(128))
                print("-"*128)
                print(f"Generating {self.maxShines} shines RELEASE build")

            elif self.is_debug():
                print("")
                print("====== DOL PATCHING ======".center(128))
                print("-"*128)
                print(f"Generating {self.maxShines} shines DEBUG build")

            modules = self.run(Path("src/src-code"), dolPath)
            _doldata = DolFile(BytesIO(self.dest.read_bytes()))

            if isinstance(modules, list):
                size = 0
                for m in modules:
                    m.rename(self._get_translated_filepath(m.name))
                    size += m.stat().st_size
                self._alloc_from_heap(
                    _doldata, (kernelPath.stat().st_size() + size + 31) & -32)

                tmpbin = TMPDIR / "pyasm.bin"
                pyiiasmh_cli._ppc_exec([str(self.solutionDir / "kuribo/pre_patch.s"),
                                        "a",
                                        "--codetype", "C2D2",
                                        "--dest", tmpbin])

                data = BytesIO(tmpbin.read_bytes())
                injectaddr = (int.from_bytes(data.getvalue()[
                              :4], "big", signed=False) & 0x1FFFFFC) | 0x80000000
                codelen = int.from_bytes(
                    data.getvalue()[4:8], "big", signed=False) * 8
                blockstart = _doldata.seek_nearest_unmapped(
                    _doldata.bssAddress, codelen)

                _doldata.insert_branch(blockstart, injectaddr)
                _doldata.insert_branch(injectaddr + 4, blockstart + codelen)

                with self.dest.open("wb") as dest:
                    _doldata.save(dest)

            elif isinstance(modules, Path):
                modules.rename(self._get_translated_filepath(
                    modules.name).with_name("SME"))
                self._alloc_from_heap(
                    _doldata, (kernelPath.stat().st_size() + modules.stat().st_size + 31) & -32)

                tmpbin = TMPDIR / "pyasm.bin"
                pyiiasmh_cli._ppc_exec([str(self.solutionDir / "kuribo/pre_patch.s"),
                                        "a",
                                        "--codetype", "C2D2",
                                        "--dest", tmpbin])

                data = BytesIO(tmpbin.read_bytes())
                injectaddr = (int.from_bytes(data.getvalue()[
                              :4], "big", signed=False) & 0x1FFFFFC) | 0x80000000
                codelen = int.from_bytes(
                    data.getvalue()[4:8], "big", signed=False) * 8
                blockstart = _doldata.seek_nearest_unmapped(
                    _doldata.bssAddress, codelen)

                _doldata.insert_branch(blockstart, injectaddr)
                _doldata.insert_branch(injectaddr + 4, blockstart + codelen)

                with self.dest.open("wb") as dest:
                    _doldata.save(dest)

            print("-"*128)
            return True
        return False

    def _replace_files(self, config: dict):
        print("")
        print("====== REPLACING | COPYING ======".center(128))
        print("-"*128)

        bnrPath = (self.solutionDir / config["gamebanner"]).resolve()

        self._compile_bnr_to_game(bnrPath)
        destPath = self.gameDir / "opening.bnr"

        for f in self.solutionDir.rglob("*"):
            relativePath = f.relative_to(Path.cwd())

            if f.name.lower() == ".config.json":
                continue

            destPath = self._get_matching_filepath(f)

            if destPath is None:
                if f.is_file() and str(f.relative_to(Path.cwd(), "bin", "debug")) not in config["ignore"]:
                    print(f"{relativePath} -> No destination found")
                continue

            if not destPath.parent.exists():
                destPath.parent.mkdir(parents=True, exist_ok=True)

            if f.suffix.lower() in (".szs", ".arc"):
                destPath = destPath.with_suffix(".szs")
                with f.open("rb") as archive:
                    data = BytesIO(archive.read())

                data.seek(0)
                if data.read(4) != b"Yaz0":
                    data = oead.yaz0.compress(data.getvalue())
                    destPath.write_bytes(data)
                else:
                    destPath.write_bytes(f.read_bytes())
            else:
                print(destPath)
                print(f)
                destPath.write_bytes(f.read_bytes())

            print(f"{relativePath} -> {destPath}")

        print("-"*128)

    def _get_translated_filepath(self, relativePath: Union[str, Path]) -> Path:
        return self.gameDir / relativePath

    def _init_tables(self):
        for f in self.gameDir.rglob("*"):
            if f.is_file:
                self._fileTables.setdefault(f.suffix, []).append(f)

    def _get_matching_filepath(self, path: Path) -> Path:
        try:
            for f in self._fileTables[path.suffix]:
                if f.name == path.name:
                    return self.gameDir / f
        except KeyError:
            return self._get_path_from_config(path)
        else:
            return self._get_path_from_config(path)

    def _get_path_from_config(self, path: Path) -> Path:
        if self.is_release():
            parentGlob = "*/release/"
        elif self.is_debug():
            parentGlob = "*/debug/"
        else:
            raise ValueError("Invalid state!")

        with Path(self.solutionDir / ".config.json").open("r") as f:
            config = json.load(f)
            for _set in config["userfiles"]:
                glob = list(_set.keys())[0]
                if fnmatch(str(path).lower(), parentGlob + glob.strip().lower()):
                    if _set[glob]["rename"].strip() == "":
                        return self.gameDir / _set[glob]["destination"].strip() / path.name
                    else:
                        return self.gameDir / _set[glob]["destination"].strip() / _set[glob]["rename"].strip()

        return None

    def _rename_files_from_config(self):
        print("")
        print("====== RENAMING ======".center(128))
        print("-"*128)

        _renamed = []

        with Path(self.solutionDir / ".config.json").open("r") as f:
            config = json.load(f)
            for path in config["rename"]:
                rename = config["rename"][path]

                absPath = self.gameDir / path

                if absPath.exists() and absPath not in _renamed:
                    print(f"{absPath} -> {self.gameDir / absPath.parent / rename}")
                    absPath.rename(self.gameDir / absPath.parent / rename)
                    _renamed.append(absPath)

        print("-"*128)

    def _delete_files_from_config(self):
        with Path(self.solutionDir / ".config.json").open("r") as f:
            config = json.load(f)
            for path in config["delete"]:
                absPath = self.gameDir / path
                if absPath.exists():
                    print(f"{absPath} -> DELETED")
                    absPath.unlink()

    def _compile_bnr_to_game(self, path):
        bnr = BNR(path, BNR.Regions.AMERICA)
        bnr.save_bnr(self.gameDir / "opening.bnr")


def main():
    parser = argparse.ArgumentParser(
        "SMS-Patcher", description="C++ Patcher for SMS NTSC-U, using Kamek by Treeki")

    parser.add_argument("gamefolder", help="root folder of GCR extracted ISO")
    parser.add_argument("-p", "--projectfolder",
                        help="project folder used to patch game", metavar="PATH")
    parser.add_argument("-s", "--startaddr", help="Starting address for the linker and code",
                        default="0x80000000", metavar="ADDR")
    parser.add_argument("-b", "--build", help="Build type",
                        choices=["R", "D"], default="D")
    parser.add_argument("--boot", help="What to boot from",
                        choices=["DOL", "ISO", "NONE"], default="NONE")
    parser.add_argument(
        "--shines", help="Max shines allowed", type=int, default=120)

    args = parser.parse_args()

    if args.shines < 0 or args.shines > 999:
        parser.error(
            f"Shine count is beyond the inclusive range (0 - 999): {args.shines}")

    if not args.projectfolder:
        args.projectfolder = Path.cwd()

    if not args.startaddr:
        args.startaddr = 0x80000000

    if args.build == "D":
        build = FilePatcher.STATE.DEBUG
    else:
        build = FilePatcher.STATE.RELEASE

    patcher = FilePatcher(build, args.gamefolder, args.projectfolder,
                          args.boot, args.startaddr, args.shines)

    if patcher.is_codewarrior():
        patcher.cxxOptions = ["-Cpp_exceptions off", "-gccinc", "-gccext on", "-enum int",
                              "-fp hard", "-use_lmw_stmw on", "-O4,p", "-c", "-rostr", "-sdata 0", "-sdata2 0"]
    elif patcher.is_clang():
        patcher.cxxOptions = ["--target=powerpc-gekko-ibm-kuribo-eabi", "-std=gnu++17", "-fno-exceptions", "-fno-rtti", "-fno-unwind-tables", "-ffast-math",
                              "-flto", "-nodefaultlibs", "-nostdlib", "-fno-use-init-array", "-fuse-ld=lld", "-fpermissive", "-Wall", "-O3", "-r", "-v"]
        patcher.cOptions = ["--target=powerpc-gekko-ibm-kuribo-eabi", "-fno-exceptions", "-fno-rtti", "-fno-unwind-tables", "-ffast-math", "-fdeclspec",
                            "-flto", "-nodefaultlibs", "-nostdlib", "-fno-use-init-array", "-fuse-ld=lld", "-fpermissive", "-Wall", "-O3", "-r", "-v"]
        patcher.sOptions = ["--target=powerpc-gekko-ibm-kuribo-eabi", "-fno-exceptions", "-fno-rtti", "-fno-unwind-tables",
                            "-flto", "-nodefaultlibs", "-nostdlib", "-fno-use-init-array", "-fuse-ld=lld", "-Wall", "-r", "-v"]
        patcher.linkOptions = ["--target=powerpc-gekko-ibm-kuribo-eabi", "-std=gnu++17", "-fno-exceptions", "-fno-rtti", "-fno-unwind-tables", "-ffast-math",
                               "-flto", "-nodefaultlibs", "-nostdlib", "-fno-use-init-array", "-fuse-ld=lld", "-fpermissive", "-Wall", "-O3", "-r", "-v"]
    elif patcher.is_gcc():
        patcher.cxxOptions = ["-nodefaultlibs", "-nostdlib", "-std=gnu++20",
                              "-fno-exceptions", "-fno-rtti", "-ffast-math", "-fpermissive", "-Wall", "-O3", "-r"]
        patcher.cOptions = ["-nodefaultlibs", "-nostdlib", "-fno-exceptions",
                            "-fno-rtti", "-ffast-math", "-fpermissive", "-Wall", "-O3", "-r"]
        patcher.sOptions = ["-nodefaultlibs", "-nostdlib",
                            "-fno-exceptions", "-fno-rtti", "-Wall", "-O3", "-r"]
        patcher.linkOptions = ["-nodefaultlibs", "-nostdlib", "-std=gnu++20",
                               "-fno-exceptions", "-fno-rtti", "-ffast-math", "-fpermissive", "-Wall", "-O3", "-r"]

    patcher.patch_game()


if __name__ == "__main__":
    main()
