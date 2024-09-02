"""
Patch development and deployment
"""
import os.path
import re
import subprocess
import time

from flask import Blueprint, render_template, request, Response, redirect
from flask.typing import ResponseReturnValue
from werkzeug.utils import secure_filename

from controlserver.patch_utils import PatchUtils
from saarctf_commons.config import config

app = Blueprint('patches', __name__)

ANSIBLE_COMMAND = ['/usr/bin/python3', '/usr/bin/ansible-playbook']


@app.route('/patches/', methods=['GET', 'POST'])
def patches_index() -> ResponseReturnValue:
    if not config.PATCHES_PATH.exists():
        config.PATCHES_PATH.mkdir(exist_ok=True)
    if not config.PATCHES_PUBLIC_PATH.exists():
        config.PATCHES_PUBLIC_PATH.mkdir(exist_ok=True)
    files = os.listdir(config.PATCHES_PATH)
    files = [f for f in files if f != 'hosts.yaml' and f != 'hosts_nop.yaml']
    files.sort()
    public_files = os.listdir(config.PATCHES_PUBLIC_PATH)
    files_with_url: list[tuple[str, str | None]] = [(f, config.PATCHES_URL + '/' + f if config.PATCHES_URL and f in public_files else None)
                                                    for f in files]

    # run ansible playbook?
    if request.method == 'POST':
        # build command
        is_test = request.form['target'] == 'test'
        fname = request.form['filename']
        assert '..' not in fname
        assert '/' not in fname
        assert (config.PATCHES_PATH / fname).exists()
        command = ANSIBLE_COMMAND + [fname, '-i', 'hosts_nop.yaml' if is_test else 'hosts.yaml', '-f', '32']
        # build target files
        PatchUtils.create_ansible_hosts_template()
        # run!
        ts = time.time()
        try:
            output_raw = subprocess.check_output(command, stderr=subprocess.STDOUT, timeout=90, cwd=config.PATCHES_PATH)
            output = '> ' + ' '.join(command) + '\n' + output_raw.decode('utf-8', errors='ignore')
            success = True
        except subprocess.CalledProcessError as e:
            output = '> ' + ' '.join(command) + '\n' + e.output.decode('utf-8', errors='ignore') + '\nProcess failed with code ' + str(e.returncode)
            success = False
        except subprocess.TimeoutExpired as e:
            output = '> ' + ' '.join(command) + '\n' + e.output.decode('utf-8', errors='ignore') + '\nProcess timed out'
            success = False
        ts = time.time() - ts
        return render_template('patches.html', patches_path=config.PATCHES_PATH, patches_public_path=config.PATCHES_PUBLIC_PATH,
                               files=files_with_url, output=output, success=success, runtime=round(ts))

    return render_template('patches.html', patches_path=config.PATCHES_PATH, patches_public_path=config.PATCHES_PUBLIC_PATH, files=files_with_url)


@app.route('/patches/ansible/<fname>', methods=['GET'])
def patches_ansible_files(fname: str) -> ResponseReturnValue:
    if fname == 'hosts.yaml':
        tmpl, _ = PatchUtils.get_ansible_hosts_templates()
        return Response(tmpl, mimetype='text/vnd.yaml', headers={"Content-disposition": f"attachment; filename={fname}"})
    if fname == 'hosts_nop.yaml':
        _, tmpl = PatchUtils.get_ansible_hosts_templates()
        return Response(tmpl, mimetype='text/vnd.yaml', headers={"Content-disposition": f"attachment; filename={fname}"})
    if fname == 'ansible_template.yaml':
        tmpl = PatchUtils.ansible_base_template()
        return Response(tmpl, mimetype='text/vnd.yaml', headers={"Content-disposition": f"attachment; filename={fname}"})
    return 'Invalid filename', 404


BASH_DEFAULT_CONTENT = '''#!/usr/bin/env bash
set -e

# TODO code your patch

echo "DONE"
'''
PYTHON_DEFAULT_CONTENT = '''#!/usr/bin/env python3

def readfile(fname):
    with open(fname, 'r') as f:
        return f.read()
        
def writefile(fname, content):
    with open(fname, 'w') as f:
        f.write(fname, content)
        
# TODO code your patch

print('DONE')
'''


@app.route('/patches/create', methods=['POST'])
def patches_create() -> ResponseReturnValue:
    fname = request.form['filename']
    scripttype = request.form['type']
    if not re.match(r'^[A-Za-z0-9_.-]{3,}$', fname):
        return 'Invalid filename', 500
    if scripttype == 'bash':
        if not fname.endswith('.sh'):
            fname += '.sh'
        content = BASH_DEFAULT_CONTENT
    elif scripttype == 'python':
        if not fname.endswith('.py'):
            fname += '.py'
        content = PYTHON_DEFAULT_CONTENT
    else:
        return 'Invalid type', 500
    fname = os.path.join(config.PATCHES_PATH, fname)
    if not os.path.exists(fname):
        with open(fname, 'w') as f:
            f.write(content)
    p = PatchUtils(fname)
    p.create_ansible_template()
    p.create_ansible_hosts_template()
    return redirect('/patches')


@app.route('/patches/publish', methods=['POST'])
def patches_publish() -> ResponseReturnValue:
    fname = request.form['filename']
    assert '..' not in fname
    assert '/' not in fname
    p = PatchUtils(fname)
    p.publish_patch_files()
    return redirect('/patches')


@app.route('/patches/upload', methods=['POST'])
def patches_upload() -> ResponseReturnValue:
    if 'file' not in request.files or not request.files['file'].filename:
        return 'No filename', 400
    filename: str = request.files['file'].filename
    if '..' in filename or '/' in filename or len(filename) < 3:
        return 'Invalid filename', 400
    filename = secure_filename(filename)
    request.files['file'].save(os.path.join(config.PATCHES_PATH, filename))
    return redirect('/patches')


@app.route('/patches/hosts', methods=['POST'])
def patches_hosts() -> ResponseReturnValue:
    PatchUtils.create_ansible_hosts_template()
    return redirect('/patches')
