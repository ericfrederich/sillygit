__author__ = 'Eric L. Frederich'

from subprocess import Popen, PIPE
import argparse
import time
import hashlib
import itertools

def run_command(cmd, stdin=None, allowed_exit_codes=[0]):
    """
    wrapper around subprocess.Popen
    returns stdout, stderr and the return code
    """
    if stdin:
        p = Popen(cmd, stdout=PIPE, stderr=PIPE, stdin=PIPE)
        p.stdin.write(stdin)
    else:
        p = Popen(cmd, stdout=PIPE, stderr=PIPE)

    out, err = p.communicate()
    ret = p.wait()
    if allowed_exit_codes is not None and ret not in allowed_exit_codes:
        print '--- return code:', ret
        for line in out.splitlines():
            print '--- out:', line
        for line in err.splitlines():
            print '--- err:', line
        raise RuntimeError('Error running command %r' % cmd)
    return out, err, ret

def commit(git_dir, hsh, msg):
    print 'creating commit for'
    print '  ', git_dir
    print '  ', hsh
    print '  ', msg

    out, err, ret = run_command(['git', '--git-dir', git_dir, 'write-tree'])
    tree_hash = out.strip()
    print 'commit hash is', tree_hash

    out, err, ret = run_command(['git', '--git-dir', git_dir, 'rev-parse', 'HEAD'])
    parent_hash = out.strip()
    print 'parent hash is', parent_hash

    TEMPLATE='''\
tree %(TREE)s
parent %(PARENT)s
author Eric L Frederich <eric.frederich@gmail.com> %(TIME)s -0400
committer Eric L Frederich <eric.frederich@gmail.com> %(TIME)s -0400

%(MESSAGE)s
''' % {
        'TREE': tree_hash,
        'TIME': '%(TIME)s',
        'MESSAGE': msg,
        'PARENT': parent_hash,
    }

    start = int(time.time())
    time_delta = -1
    found = False
    tries = 0
    while not found:
        time_delta += 1
        for padding in itertools.product(range(80), range(80), range(80)):
            tries += 1
            if tries % 100000 == 0:
                print tries, 'tries'
            content = TEMPLATE % {'TIME': start + time_delta}

            for n in padding:
                content += '\n' + (' ' * n)

            content += '\n'

            header = 'commit %d\0' % len(content)
            store = header + content
            h = hashlib.sha1()
            h.update(store)
            sha = h.hexdigest()
            # print 'would be', sha
            if sha.endswith(hsh):
                found = True
                break

    print 'after', tries, 'tries'
    print 'had to increment time by', time_delta, 'seconds or', time_delta / 60.0, 'minutes'
    print 'sha...', sha
    print repr(store)
    print repr(content)

    out, err, ret = run_command(['git', '--git-dir', git_dir, 'hash-object', '-t', 'commit', '-w', '--stdin'], stdin=content)
    commit_hash = out.strip()
    if commit_hash == sha:
        print 'WOO HOO'
    else:
        raise RuntimeError('unexpected hash')

    run_command(['git', '--git-dir', git_dir, 'update-ref', 'HEAD', sha])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--message', '-m')
    parser.add_argument('--git-dir')
    parser.add_argument('hash')
    args = parser.parse_args()
    # if len(args.hash) > 4:
    #     raise ValueError('hash too big, only 4 supported')
    commit(args.git_dir, args.hash, args.message)

if __name__ == '__main__':
    main()
