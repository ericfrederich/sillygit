__author__ = 'Eric L. Frederich'

from subprocess import Popen, PIPE
import argparse
import time
import hashlib
import itertools
from datetime import datetime

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
    before = datetime.now()
    while not found:
        time_delta += 1
        content = TEMPLATE % {'TIME': start + time_delta}
        for n_padding_lines in range(5):
            for padding in itertools.product(*[range(80) for _ in range(n_padding_lines)]):
                tries += 1
                if tries % 100000 == 0:
                    print tries, 'tries'

                padding_str = ''
                for n in padding:
                    padding_str += '\n' + (' ' * n)

                padding_str += '\n'

                header = 'commit %d\0' % len(content + padding_str)
                store = header + content + padding_str
                h = hashlib.sha1()
                h.update(store)
                sha = h.hexdigest()
                # print 'would be', sha
                if sha.endswith(hsh):
                    found = True
                    break
            if found:
                break


    after = datetime.now()
    print '*' * 80
    print sha
    print repr(store)
    print '*' * 80
    print 'elapsed:', after - before
    print 'tries  :', tries
    print '%r tries per second' % (tries / (after - before).total_seconds())
    print 'had to increment commit time by', time_delta, 'seconds'

    out, err, ret = run_command(['git', '--git-dir', git_dir, 'hash-object', '-t', 'commit', '-w', '--stdin'], stdin=content + padding_str)
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
