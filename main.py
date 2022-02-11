"""
Copyright (c) 2022 - Charles `sparticvs` Timko

GPL v2.0 - See LICENSE file for details
"""
import subprocess
import argparse
import configparser
from github import Github
from pyrpm.spec import Spec
from pygit2 import (
        clone_repository, discover_repository, Repository, Keypair,
        RemoteCallbacks, Signature)

parser = argparse.ArgumentParser(
    description='Monitor Upstream for Changes to Trigger RPM SPEC Changes')
parser.add_argument('--dry', action='store_true', default=False,
    help='Don\'t actually commit or open the pull request.')
parser.add_argument('--config', nargs='?', default='soot.cfg', type=str,
    help='Change config file from default soot.cfg.')
args = parser.parse_args()

config = configparser.ConfigParser()
config.read(args.config)

GITHUB_UPSTREAM = config['upstream']['github']
GITHUB_SPEC_REPO = config['spec']['github']
GITHUB_ACCESS_TOKEN = config['github']['access_token']
UPSTREAM_SPEC_REPO = config['spec']['clone_url']
UPSTREAM_SPEC_BRANCH = config['spec']['branch']
UPSTREAM_SPEC_REMOTE = config['spec']['remote']
SPEC_FILE = config['spec']['file']
SRPM_TMP_REPO = config['default']['tmp_repo']
MAINTAINER_STR = f"{config['git-config']['name']} <{config['git-config']['email']}>"

def strip_version(vers):
    if vers[0] == "v":
        return vers[1:]
    return vers

spec_repo = None
spec_origin = None
repo_path = None
try: 
    repo_path = discover_repository(SRPM_TMP_REPO)
except KeyError:
    pass

key_pass = ""
if 'ssh_key_pass' in config['git-config']:
    key_pass = config['git-config']['ssh_key_pass']

keypair = Keypair(config['git-config']['ssh_user'],
                    config['git-config']['ssh_pub_key'],
                    config['git-config']['ssh_priv_key'],
                    key_pass)
callbacks = RemoteCallbacks(credentials=keypair)
if repo_path is None:
    try:
        spec_repo = clone_repository(UPSTREAM_SPEC_REPO, SRPM_TMP_REPO,
            checkout_branch=UPSTREAM_SPEC_BRANCH, callbacks=callbacks)
        spec_origin = spec_repo.remotes[UPSTREAM_SPEC_REMOTE]
        spec_origin.connect(callbacks=callbacks)
    except Exception as e:
        print("Unable to clone repository")
        print(e)
        exit()
else:
    spec_repo = Repository(repo_path)
    (spec_commit, spec_ref) = spec_repo.resolve_refish(UPSTREAM_SPEC_BRANCH)
    spec_repo.checkout(spec_ref)
    # Fetch latest head
    spec_origin = spec_repo.remotes[UPSTREAM_SPEC_REMOTE]
    spec_origin.connect(callbacks=callbacks)
    r = spec_origin.fetch()
    print(f'Fetch returned {r.total_deltas} deltas and {r.total_objects} objects')

if spec_repo is None or spec_origin is None:
    raise Exception('Something happened that wasn\'t caught!')

g = Github(GITHUB_ACCESS_TOKEN)
up_repo = g.get_repo(GITHUB_UPSTREAM)
latest_rel = up_repo.get_latest_release()
latest_ver = strip_version(latest_rel.tag_name)

spec = Spec.from_file(f'{SRPM_TMP_REPO}/{SPEC_FILE}')
if spec.version != latest_ver:
    print(f'Updating SPEC from {spec.version} to {latest_ver}')
    (spec_commit, spec_ref) = spec_repo.resolve_refish(UPSTREAM_SPEC_BRANCH)
    if spec_repo.branches.get(f'update/v{latest_ver}') is None:
        new_branch = spec_repo.branches.local.create(f'update/v{latest_ver}',
                spec_commit)
    (latest_commit, latest_ref) = spec_repo.resolve_refish(f'update/v{latest_ver}')
    spec_repo.checkout(latest_ref)
    rc = subprocess.run(["rpmdev-bumpspec", "-n", latest_ver,
                    f'--comment="Updating to v{latest_ver}"',
                    f'--userstring="{MAINTAINER_STR}"',
                    f'{SRPM_TMP_REPO}/{SPEC_FILE}'])
    print(f'Update bumpspec return code is {rc.returncode}')
    # Stage everything for the commit
    index = spec_repo.index
    index.add(SPEC_FILE)
    index.write()

    # Do the commit
    (commit, ref) = spec_repo.resolve_refish(f'update/v{latest_ver}')

    if args.dry:
        print(f'[DRY] Pushing Branch')
    else:
        message = f'Update spec from {spec.version} -> {latest_ver}'
        tree = index.write_tree()
        author = Signature(email=config['git-config']['email'], name=config['git-config']['name'])
        commiter = Signature(email=config['git-config']['email'], name=config['git-config']['name'])
        oid = spec_repo.create_commit(ref.name, author, commiter, message, tree, [commit.hex])
        
        # Push branch to remote
        r = spec_origin.push([ref.name], callbacks=callbacks)
        print(f'Push returned {r}')

    ## And open a Pull Request
    github_spec = g.get_repo(GITHUB_SPEC_REPO)
    title = f'Bump SPEC Version to {latest_rel}'
    body = f'''
    # Summary
    Bump SPEC Version to latest release (v{latest_ver}) from {GITHUB_UPSTREAM}
    '''
    if args.dry:
        print(f'[DRY] Create Pull Request\n{title}\n=======\n{body}')
    else:
        github_spec.create_pull(title=title,
            body=body, head=f'update/v{latest_ver}',
            base=UPSTREAM_SPEC_BRANCH)
else:
    print(f'SPEC is at {latest_ver} already')

