import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import init_database
from controlserver.patch_utils import PatchUtils
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import NamedRedisConnection

"""
ARGUMENTS: <patch-script> [<additional-file> ...]
"""

if __name__ == "__main__":
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname("script-" + os.path.basename(__file__))
    init_database()
    # create ansible files
    p = PatchUtils(sys.argv[1], [Path(s) for s in sys.argv[2:]])
    tmpl = p.create_ansible_template()
    print("[*] Created ansible template:", tmpl)
    tmpl = p.create_ansible_hosts_template()
    print("[*] Created hosts template:  ", tmpl)
    print("    Use patch_publish.py when you're done editing.")
