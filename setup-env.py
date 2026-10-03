"""Generate an isolated local configuration for local development."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'scripts'))
from local_env import prepare

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-port',type=int,default=8000)
    parser.add_argument('--web-port',type=int,default=3000)
    parser.add_argument('--force',action='store_true',help='覆盖已有环境文件；默认保留')
    args=parser.parse_args()
    if not all(1024<=p<=65535 for p in [args.api_port,args.web_port]) or args.api_port==args.web_port:
        parser.error('请使用两个不同的 1024–65535 端口')
    env=prepare(args.api_port,args.web_port,args.force)
    print('本地配置已准备。已有环境文件默认保留；原始公开数据快照不会被修改。')
    print('数据库：'+env['DATABASE_URL'])
    print('安装依赖并构建前端后，运行 Python scripts/start_local.py')
    return 0

if __name__=='__main__':sys.exit(main())
