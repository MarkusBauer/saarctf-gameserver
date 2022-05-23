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
	tmpl = p.create_ansible_template()
	print('[*] Created ansible template:', tmpl)
	tmpl = p.create_ansible_hosts_template()
	print('[*] Created hosts template:  ', tmpl)
	print('    Use patch_publish.py when you\'re done editing.')

