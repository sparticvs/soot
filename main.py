import subprocess
import argparse
import configparser
from github import Github
from pyrpm.spec import Spec
from pygit2 import (
        clone_repository, discover_repository, Repository, Keypair,
        RemoteCallbacks)

parser = argparse.ArgumentParser(
    description='Monitor Upstream for Changes to Trigger RPM SPEC Changes')
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
MAINTAINER_STR = config['default']['maintainer']

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
keypair = Keypair('git', '/home/ctimko/.ssh/id_ed25519.pub',
        '/home/ctimko/.ssh/id_ed25519', '')
#keypair = Keypair('git', 'id_ed25519.pub',
#        'id_ed25519', '')
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
else:
    spec_repo = Repository(repo_path)
    (spec_commit, spec_ref) = spec_repo.resolve_refish(UPSTREAM_SPEC_BRANCH)
    spec_repo.checkout(spec_ref)
    # Fetch latest head
    spec_origin = spec_repo.remotes[UPSTREAM_SPEC_REMOTE]
    spec_origin.connect()
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
    # Update the working index
    index = spec_repo.index
    index.add(SPEC_FILE)
    index.write()
    # Push branch to remote
    (commit, ref) = spec_repo.resolve_refish(f'update/v{latest_ver}')
    r = spec_origin.push([f'update/v{latest_ver}'], callbacks=callbacks)
    print(f'Push returned {r}')
    ## And open a Merge Request
    github_spec = g.get_repo(GITHUB_SPEC)
    body = f'''
    # Summary
    Bump SPEC Version to latest release ({latest_rel}) from {GITHUB_UPSTREAM}
    '''
    github_spec.create_pull(title=f'Bump SPEC Version to {latest_rel}',
            body=body, head=f'update/v{latest_ver}',
            base=UPSTREAM_SPEC_BRANCH)
else:
    print(f'SPEC is at {latest_ver} already')

