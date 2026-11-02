import subprocess


def bounded(command, *, cwd, env, timeout, events, cleanup_timeout=3):
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    event = {'pid': process.pid, 'command': command, 'timeoutSeconds': timeout, 'cleanupTimeoutSeconds': cleanup_timeout}
    events.append(event)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        event['timedOut'] = True
        try:
            killed = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, text=True, timeout=cleanup_timeout)
            event['treeCleanup'] = {'exit': killed.returncode, 'stdout': killed.stdout, 'stderr': killed.stderr}
        except (subprocess.TimeoutExpired, OSError) as error:
            event['treeCleanupFailure'] = repr(error)
        try:
            stdout, stderr = process.communicate(timeout=cleanup_timeout)
        except subprocess.TimeoutExpired:
            event['pipeCleanupTimedOut'] = True
            process.kill()
            try:
                stdout, stderr = process.communicate(timeout=cleanup_timeout)
            except subprocess.TimeoutExpired:
                event['cleanupIncomplete'] = True
                stdout = expired.stdout or b''
                stderr = expired.stderr or b''
                stdout = stdout.decode(errors='replace') if isinstance(stdout, bytes) else stdout
                stderr = stderr.decode(errors='replace') if isinstance(stderr, bytes) else stderr
                event['pipeReadersPendingAtJobExit'] = True
    event['exit'] = process.poll()
    event['processEnded'] = event['exit'] is not None
    return subprocess.CompletedProcess(command, 124 if event.get('timedOut') else process.returncode, stdout, stderr)
