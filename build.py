import sys
import subprocess
from pathlib import Path

#TODO Попробовать автоматически найти путь до блендера
#TODO Этот скрипт должен предложить пользователю сделать установку

def check(cond:bool, msg:str, code:int = 1):
    if not cond:
        print(msg)
        print_help()
        sys.exit(code)

def print_help():
    #TODO
    pass

def build_extension(blend_path:Path):
    cur_path = Path(__file__).parent
    addon_path = cur_path / "br2proj"
    check(addon_path.is_dir(), 'Path to the addon was not found')

    subprocess.run([blend_path, 
        '--command', 'extension', 'build',
        '--source-dir', addon_path,
        '--output-dir', cur_path
        ])

def main():
    check(len(sys.argv) == 2, 'Too many/few arguments passed')

    path = Path(sys.argv[1])
    check(path.is_file(), f'Path to the blender: "{path}" does not exist')

    build_extension(path)

if __name__ == '__main__':
    main()
