import os.path
import shutil
from typing import List, Tuple

from controlserver.models import Team
from saarctf_commons import config

ANSIBLE_TEMPLATE_1 = '''
---
- hosts: vulnboxes
  tasks:
'''
ANSIBLE_TEMPLATE_2 = '''
    - name: Copy <FNAME>
      copy: # more information on this module can be found here https://docs.ansible.com/ansible/latest/modules/copy_module.html
        # The src is the local filepath (relative from the playbook location)
        src: "<PATH1>"
        # dest is the remote path where the file should be stored
        dest: "/opt/<PATH2>"
        # content can be used instead of src to write directly into a new file. A local file can also be used as input by using functions from the templating engine (e.g. {{ lookup('file', '<local_file>') }})
        # content: "string"
        # owner: <user>
        # group: <group>
        mode: "<MODE>"
        # if a file is overwritten create a backup of the old one first
        # backup: yes
'''
ANSIBLE_TEMPLATE_3 = '''

    - name: Run a single command
      # Combining commands via pipe, etc. does not work, use the shell module for that instead: https://docs.ansible.com/ansible/latest/modules/shell_module.html#shell-module (see example below)
      # become: yes
      command: <COMMAND>
      # more information on this module can be found here https://docs.ansible.com/ansible/latest/modules/command_module.html
      # register the output of the command.
      register: var_name
      # indicate when the status should show 'changed'
      changed_when: "'DONE' not in var_name"
#    - name: Display the command output
#      # use one of the following
#      # .msg most of the time shows all outputs
#      debug: var=var_name.msg
#      debug: var=var_name.stdout
#      debug: var=var_name.stderr

     # shell module example:
#    - name: Remove low sized ssh moduli
#      shell: awk '$5 >= 4095' /etc/ssh/moduli > /etc/ssh/moduli.safe && mv /etc/ssh/moduli.safe /etc/ssh/moduli

#    - name: Manage some packages
#      # you can also write tasks as blocks in order to specify some general settings for all of them once or to make the playbook easier to read
#      # run all tasks in the block with sudo
#      become: yes
#      block:
#        - name: Install python3
#          apt: # more information on this module can be found here https://docs.ansible.com/ansible/latest/modules/apt_module.html
#            name: python3
#            # absent to uninstall a package
#            state: present
'''

ANSIBLE_HOSTS_TEMPLATE = '''
---
all:
  vars:
    ansible_user: root  # specify the username used by ansible to connect to remote hosts
    ansible_ssh_common_args: -o StrictHostKeyChecking=no
    ansible_ssh_private_key_file: ~/.ssh/vulnbox
  children:
    vulnboxes:
      hosts:
        # 10.[32:33].[0:255].2:
        # 127.0.0.1: {ansible_port: 22222}'''


class PatchUtils:
    def __init__(self, patchfile: str, additional_files: List[str] = None):
        self.patchfile = patchfile
        self.additional_files = additional_files or []
        if not os.path.exists(self.patchfile):
            self.patchfile = os.path.join(config.PATCHES_PATH, self.patchfile)
        for i in range(len(self.additional_files)):
            if not os.path.exists(self.additional_files[i]):
                self.additional_files[i] = os.path.join(config.PATCHES_PATH, self.additional_files[i])

    @staticmethod
    def ansible_base_template() -> str:
        return ANSIBLE_TEMPLATE_1 + ANSIBLE_TEMPLATE_2.replace('<FNAME>', 'your script') + ANSIBLE_TEMPLATE_3

    def ansible_filename(self) -> str:
        return os.path.join(os.path.dirname(self.patchfile), 'ansible-' + os.path.basename(self.patchfile) + '.yaml')

    def create_ansible_template(self) -> str:
        """
        Generate a playbook if it does not exist
        :return: Filename of the generated playbook
        """
        fname = self.ansible_filename()
        if not os.path.exists(fname):
            tmpl = ANSIBLE_TEMPLATE_1
            tmpl += ANSIBLE_TEMPLATE_2 \
                .replace('<PATH1>', os.path.abspath(self.patchfile)) \
                .replace('<PATH2>', os.path.basename(self.patchfile)) \
                .replace('<FNAME>', os.path.basename(self.patchfile)) \
                .replace('<MODE>', oct(os.stat(self.patchfile).st_mode & 0o777)[2:])
            for f in self.additional_files:
                tmpl += ANSIBLE_TEMPLATE_2 \
                    .replace('<PATH1>', os.path.abspath(f)) \
                    .replace('<PATH2>', os.path.basename(f)) \
                    .replace('<FNAME>', os.path.basename(f)) \
                    .replace('<MODE>', oct(os.stat(f).st_mode & 0o777)[2:])
            cmd = '/opt/' + os.path.basename(self.patchfile)
            if cmd.endswith('.sh'):
                cmd = 'bash ' + cmd
            if cmd.endswith('.py'):
                cmd = 'python3 ' + cmd
            tmpl += ANSIBLE_TEMPLATE_3.replace('<COMMAND>', cmd)
            with open(fname, 'w') as fh:
                fh.write(tmpl)
        return fname

    @staticmethod
    def get_ansible_hosts_templates() -> Tuple[str, str]:
        tmpl = ANSIBLE_HOSTS_TEMPLATE
        tmpl2 = ANSIBLE_HOSTS_TEMPLATE
        online_teams = Team.query.filter((Team.vpn_connected == True) | (Team.vpn2_connected == True)).order_by(Team.id).all()
        for team in online_teams:
            ip = config.team_id_to_vulnbox_ip(team.id)
            tmpl += f'\n        {ip}:  # {team.name}'
            if team.id == config.NOP_TEAM_ID:
                tmpl2 += f'\n        {ip}:  # {team.name}'
        return tmpl, tmpl2

    @classmethod
    def create_ansible_hosts_template(cls) -> str:
        """
        Generate fresh inventory files for all online vulnboxes
        :return: the filename of the primary inventory file
        """
        tmpl, tmpl2 = cls.get_ansible_hosts_templates()
        fname = os.path.join(config.PATCHES_PATH, 'hosts.yaml')
        with open(fname, 'w') as f:
            f.write(tmpl)
        with open(os.path.join(config.PATCHES_PATH, 'hosts_nop.yaml'), 'w') as f:
            f.write(tmpl2)
        return fname

    def publish_patch_files(self) -> List[str]:
        """

        :return: A list of download URLs, if configured
        """
        os.makedirs(config.PATCHES_PUBLIC_PATH, exist_ok=True)
        urls = []
        for fname in [self.patchfile] + self.additional_files:
            target = os.path.join(config.PATCHES_PUBLIC_PATH, os.path.basename(fname))
            if os.path.exists(target):
                os.remove(target)
            shutil.copy2(fname, target)
            urls.append((config.PATCHES_URL or '/patches/') + '/' + os.path.basename(fname))
        return urls
