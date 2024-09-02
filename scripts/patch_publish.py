import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import init_database
from controlserver.patch_utils import PatchUtils
from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config

"""
ARGUMENTS: <patch-script> [<additional-file> ...]
"""

if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    init_database()
    # create ansible files
    p = PatchUtils(sys.argv[1], [Path(s) for s in sys.argv[2:]])
    tmpl = p.create_ansible_hosts_template()
    print('[*] Created hosts template:  ', tmpl)
    urls = p.publish_patch_files()
    print('[*] Published patch files. Download URLs:')
    for url in urls:
        print(f'- {url}')
    print('')
    # ansible guidelines
    print('To test this patch against NOP team:')
    print(f'>   cd "{os.path.dirname(p.ansible_filename())}"')
    print(f'>   ansible-playbook {os.path.basename(p.ansible_filename())} -i hosts_nop.yaml')
    print('')
    print('To deploy this patch:')
    print(f'>   cd "{os.path.dirname(p.ansible_filename())}"')
    print(f'>   ansible-playbook {os.path.basename(p.ansible_filename())} -i hosts.yaml')
