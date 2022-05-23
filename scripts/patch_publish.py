import os
import sys
from typing import Optional

from controlserver.patch_utils import PatchUtils

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True

"""
ARGUMENTS: <patch-script> [<additional-file> ...]
"""

if __name__ == '__main__':
	# noinspection PyUnresolvedReferences
	from controlserver import app as app
	# create ansible files
	p = PatchUtils(sys.argv[1], sys.argv[2:])
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

