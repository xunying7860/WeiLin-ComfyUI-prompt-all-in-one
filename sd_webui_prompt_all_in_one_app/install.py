import sys
import os

# [P0-2] 原先用相对路径，依赖 CWD=插件目录；从 ComfyUI 根目录启动时该路径并不存在（误打误撞跳过安装）。
# 现改为基于 __file__，路径真实可靠，并由 .installed 标记保证只跑一次。
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
AIO_PATH = os.path.join(_APP_DIR, "sd_webui_prompt_all_in_one")
sys.path.append(AIO_PATH)

from . import launch

def run_install():
    # [P0-2] 装成功后写 .installed 标记，之后每次启动直接 return，
    # 不再为 10 个包新起一个 Python 解释器逐个检查（方案A1：启动慢的头号嫌疑）
    flag = os.path.join(_APP_DIR, ".installed")
    if os.path.exists(flag):
        return
    install_path = os.path.join(AIO_PATH, 'install.py')
    if os.path.exists(install_path):
        print(f"== WeiLin prompt-all-in-one == Running install.py...")
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{_APP_DIR}{os.pathsep}{env.get('PYTHONPATH', '')}"

        stdout = launch.run(f'"{sys.executable}" "{install_path}"', errdesc=f"Error running install.py", custom_env=env).strip()
        if stdout:
            print(stdout)

        with open(flag, "w") as f:   # run() 非零退出会抛异常，走到这里才算成功
            f.write("1")
        print(f"Finished running install.py.")
