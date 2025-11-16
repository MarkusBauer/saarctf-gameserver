import os
import sys


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import config, load_default_config
from controlserver.models import init_database
from controlserver.service_mgr import ServiceRepoManager

"""
Clone/update service repositories and update metadata in database.
Does not update existing checker scripts, tries to preserve manual changes.
ARGUMENTS: none
"""

if __name__ == "__main__":
    load_default_config()
    config.set_script()
    init_database()

    mgr = ServiceRepoManager()
    mgr.update_all_services()
    print("[OK] Service update complete")
    print("     You might want to update the checker scripts in UI.")
