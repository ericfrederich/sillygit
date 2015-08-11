#!/usr/bin/env python

__author__ = 'Eric L. Frederich'

from subprocess import Popen, PIPE
import argparse
import time
import hashlib
import itertools
from datetime import datetime
import multiprocessing
import Queue

def finder(results_queue, stats_queue, stop_queue, start_time, time_delta, template, hsh):
    new_time = start_time - time_delta
    found = False
    tries = 0
    before = datetime.now()
    while not found:
        # drift time as needed
        # though this shouldn't happen too often since
        # the inner loop generates 41,478,481 tries
        new_time += time_delta
        content = template % {'TIME': new_time}

        print 'trying with time', new_time

        for padding in white_noise_generator():
            # keep track of and print tries
            tries += 1

            if tries % 10000 == 0:
                try:
                    stop_queue.get_nowait()
                except Queue.Empty:
                    pass
                else:
                    print 'got the stop signal'
                    stats_queue.put(tries)

            # if tries % 10000 == 0:
            #     print tries, 'tries', '(%d%%)' % int(100.0 * tries / 16**len(hsh))

            # calculate sha
            header = 'commit %d\0' % len(content + padding)
            store = header + content + padding
            h = hashlib.sha1()
            h.update(store)
            sha = h.hexdigest()

            # break if we found one that ends with the desired hash
            if sha.endswith(hsh):
                found = True
                break

    after = datetime.now()

    results_queue.put(( before, after, sha, store, new_time, content, padding ))
    stats_queue.put(tries)

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
    return out

def white_noise_generator(length=4, width=80):
    for n_padding_lines in range(length+1):
        for padding in itertools.product(*[range(width) for _ in range(n_padding_lines)]):
            ret = ''
            for n in padding:
                ret += '\n' + (' ' * n)
            ret += '\n'
            yield ret

def commit(git_dir, add, hsh, msg, n_procs):
    print 'creating commit for'
    print '  ', git_dir
    print '  ', hsh
    print '  ', msg

    git_cmd = ['git']
    if git_dir is not None:
        git_cmd.extend(['--git-dir', git_dir])

    username = run_command(git_cmd + ['config', 'user.name']).rstrip()
    email    = run_command(git_cmd + ['config', 'user.email']).rstrip()

    if add:
        run_command(git_cmd + ['add', '.'])

    tree_hash   = run_command(git_cmd + ['write-tree']).rstrip()
    # TODO: could we support amend by parsing 'HEAD^' instead of 'HEAD'?
    parent_hash = run_command(git_cmd + ['rev-parse', 'HEAD']).strip()

    print 'username   ', username
    print 'email      ', email
    print 'tree hash  ', tree_hash
    print 'parent hash', parent_hash

    template = '''\
tree %(TREE)s
parent %(PARENT)s
author %(USERNAME)s <%(EMAIL)s> %(TIME)s -0400
committer %(USERNAME)s <%(EMAIL)s> %(TIME)s -0400

%(MESSAGE)s
''' % {
        'TREE': tree_hash,
        'TIME': '%(TIME)s',
        'MESSAGE': msg,
        'PARENT': parent_hash,
        'USERNAME': username,
        'EMAIL': email,
    }

    start_time = int(time.time())

    # create some queues for communication
    results_queue = multiprocessing.Queue()
    stats_queue = multiprocessing.Queue()
    stop_queue = multiprocessing.Queue()

    # create all the processes using an offset for the start time so they're unique
    procs = []
    for i in range(n_procs):
        proc = multiprocessing.Process(target=finder, args=(results_queue, stats_queue, stop_queue, start_time + i, n_procs, template, hsh))
        procs.append(proc)

    # start all processes
    for proc in procs:
        proc.start()

    # first thing back on the results queue will alaways be the result
    before, after, sha, store, new_time, content, padding = results_queue.get()

    # signal all the other processes that we're done
    for i in range(n_procs):
        stop_queue.put(None)

    # now everything on the results queue is just the number of tries from each process
    # do a blocking call because we know how many processes there were
    tries = 0
    for i in range(n_procs):
        tries += stats_queue.get()

    # kill all the processes though they should be done already
    for proc in procs:
        proc.terminate()

    print '*' * 80
    print sha
    print repr(store)
    print '*' * 80
    print 'elapsed:', after - before
    print 'tries  :', tries
    print '%r tries per second' % (tries / (after - before).total_seconds())
    print 'had to increment commit time by', new_time - start_time, 'seconds'

    commit_hash = run_command(git_cmd + ['hash-object', '-t', 'commit', '-w', '--stdin'], stdin=content + padding).strip()
    if commit_hash == sha:
        print 'WOO HOO'
    else:
        raise RuntimeError('unexpected hash')

    run_command(git_cmd + ['update-ref', 'HEAD', sha])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--add', '-a', action='store_true')
    parser.add_argument('--message', '-m')
    parser.add_argument('--git-dir')
    parser.add_argument('--parallel', type=int, default=1)
    parser.add_argument('hash')
    args = parser.parse_args()
    # if len(args.hash) > 4:
    #     raise ValueError('hash too big, only 4 supported')
    try:
        int(args.hash, 16)
    except ValueError:
        raise ValueError('Invalid hex for hash')
    commit(args.git_dir, args.add, args.hash.lower(), args.message, args.parallel)

if __name__ == '__main__':
    main()
