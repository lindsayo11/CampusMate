"""Print nonsensitive collection settings for the maintained, proven source catalog."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.public_source_catalog import allowed_hosts

print('PUBLIC_NOTICE_WATCH_ENABLED=true')
print('COLLECTOR_ENABLED=false')
print('COLLECTOR_ALLOWED_HOSTS='+','.join(allowed_hosts()))
