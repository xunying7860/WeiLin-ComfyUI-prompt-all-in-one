import os 
import sys
appendPath = os.path.join(os.path.dirname(__file__), "../")
sys.path.append(appendPath)

import launch

# [P0-2] 启动期只自动装 tqdm。其余包（openai/boto3/aliyun SDK/execjs/lxml/pathos 等）在插件里全部是
# 惰性 import（实测：chardet/openai/boto3 均在函数内导入，translators 包无人引用），
# 改由设置界面「安装」按钮按需安装（install_package 路由），不再启动时联网装大包。
packages = {
    "tqdm": "tqdm",
}

if __name__ == "__main__":
    for package_name in packages:
        package = packages[package_name]
        try:
            if not launch.is_installed(package_name):
                launch.run_pip(f"install {package}", f"sd-webui-prompt-all-in-one: {package_name}")
        except Exception as e:
            print(e)
            print(f'Warning: Failed to install {package}, some preprocessors may not work.')