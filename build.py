#Thanks to https://github.com/BradyAJohnston/MolecularNodes/blob/main/build.py
#for giving the idea of writing an build script
#This brought back memories of those long days I spent immersed in learning CMake

from urllib.request import urlretrieve
from tempfile import TemporaryDirectory
import zipfile

import subprocess
from pathlib import Path
from types import SimpleNamespace as Named

try:
    import bpy
except ImportError:
    print("ERROR: This script must be run inside Blender, click Scripting -> Text -> Open in Blender UI")
    raise

#Set True to generate a release instead of installing the addon.
#This is an alternative mode of using this script
GENERATE_RELEASE_MODE = False

CONFIG = Named(
    web=Named(
        url='https://github.com/PavelSharp/br2proj/archive/refs/heads/main.zip',
        prefix='br2proj-main/br2proj/'
    ),
    local=Named(
        dir='br2proj',
    ),
)

def download_zip(url:str, out_path:Path,*, prefix:str = None, allow_overwrite:bool = True):
    check(out_path.is_dir(), 'The output path must be a directory')
    tmp, _hdrs = urlretrieve(url)
    if prefix is None: prefix = ''
    with zipfile.ZipFile(tmp, 'r') as zip:
        for info in zip.infolist():
            if not info.is_dir() and info.filename.startswith(prefix):
                dest = out_path / info.filename[len(prefix):]
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not allow_overwrite and dest.exists(): 
                    raise FileExistsError(f"Some files already exist: {dest}")
                with zip.open(info) as src:
                    dest.write_bytes(src.read())

def check(cond:bool, msg:str):
    if not cond:
        raise Exception(msg)

#addon_path is 'root / br2proj'
#out_path can be directory path or file path 
def build(addon_path:Path,*, blend_path:Path = None, out_path:Path = None, repo:str = 'user_default'):
    check(addon_path.is_dir(), f'Path to the addon was not found, expected: {addon_path}')
    if blend_path is None: blend_path = Path(bpy.app.binary_path)

    out_arg = '--output-filepath'
    tmp_dir = None
    if out_path is None:
        tmp_dir = TemporaryDirectory()
        out_path = Path(tmp_dir.name) / 'built.zip'
    elif out_path.is_dir:
        out_arg = '--output-dir'

    res = subprocess.run([blend_path, 
        '--command', 'extension', 'build',
        '--source-dir', addon_path,
        out_arg, out_path,
    ])
    check(res.returncode==0, 'Something went wrong, click Window -> Toggle System Console for more details')

    if repo:
        check(out_path.is_file(), f'Path to the zip archive was not found, expected: {out_path}')
        bpy.ops.extensions.package_install_files(
            filepath=str(out_path),
            repo = repo, enable_on_install=True)
            #TODO Why package_install_files return FINISHED even if the path does not exist or the manifest does not exist in the archive? 
        
    if tmp_dir: tmp_dir.cleanup()

def web_install():
    web = CONFIG.web
    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        download_zip(web.url, tmp, prefix=web.prefix)
        build(tmp)

def get_run_path():
    name = bpy.context.space_data.text.name
    path = Path(bpy.data.texts[name].filepath)
    return path.parent if path.is_file() else None

def get_path_to_local():    
    run_path = get_run_path()
    if run_path and (addon:=(run_path / CONFIG.local.dir)).is_dir():
        return addon
    else:
        return None
    
#1. If the script does not have a save path -> then download(to a temporary directory) and install
#2. If the script is saved and there is a br2proj folder nearby -> then install from this folder

def auto_install():    
    if addon:=get_path_to_local():
        print('INFO: The local installation has been selected')
        build(addon)
    else:
        print('INFO: The web installation has been selected')
        web_install()

def generate_release():
    print('INFO: The release generation mode is selected')
    if addon:=get_path_to_local():
        build(addon, out_path=get_run_path(), repo=None)
    else:
        raise FileNotFoundError(f'This script should be saved near the folder: {CONFIG.local.dir}')

def main():
    if GENERATE_RELEASE_MODE:
        generate_release()
    else:
        auto_install()

if __name__ == '__main__':
    main()