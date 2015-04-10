"""
The RusTiny test runner.

Test layout:

    tests/
        compile-fail/   # Tests that shouldn't compile
            [category]/
                [test].rs
        run-pass/       # Tests that *should* compile
            [category]/
                [test].rs
        ir/             # Test for the intermediate representation
            [test].rs   # Input
            [test].ir   # Expected IR

`compile-fail` tests can tell the test runner which error they expect by
using special comments:

    //! ERROR([line]:[col]): [ERROR MESSAGE]
    //! ERROR: [ERROR MESSAGE]

"""

# FIXME: Detect panics and count as errors

from collections import namedtuple
from glob import glob
from pathlib import Path
import os
import subprocess
import sys
import re

from termcolor import cprint, colored


RUSTINY_DIR = Path(__file__).resolve().parents[1]
TEST_DIR = RUSTINY_DIR / 'tests'
COMPILER = RUSTINY_DIR / 'target' / 'debug' / 'rustiny'

if os.name == 'nt':
    import colorama
    colorama.init()

    COMPILER = COMPILER.with_suffix('.exe')


# --- HELPER CLASSES ----------------------------------------------------------

CompileResult = namedtuple('CompileResult', 'output exit_code')

FailedTest = namedtuple('FailedTest', 'path name unexpected missing output msg')


class CompilerError:
    def __init__(self, d: dict):
        self.error = d['error']
        self.line = int(d.get('line')) if 'line' in d else None
        self.col = int(d.get('col')) if 'col' in d else None

    def __repr__(self):
        if self.line and self.col:
            return 'Error in {}:{}: {}'.format(self.line, self.col, self.error)
        else:
            return 'Error: {}'.format(self.error)

    def __eq__(self, other):
        assert isinstance(other, CompilerError)
        return (self.error == other.error
                and self.line == other.line
                and self.col == other.col)

    def __hash__(self):
        return hash((self.error, self.line, self.col))


class Session:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []

    def start(self, name):
        print('Testing {} ...'.format(name), end='')

    def success(self):
        cprint('ok', 'green')

        self.passed += 1

    def failure(self, failure):
        cprint('failed', 'red')

        self.failures.append(failure)
        self.failed += 1

session = Session()


# --- Compile a file ----------------------------------------------------------

def compile_file(filename: Path, args=[]) -> CompileResult:
    proc = subprocess.Popen([str(COMPILER)] + args + [str(filename)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            cwd=str(TEST_DIR))
    output = proc.communicate()[0].decode("utf-8")
    exit_code = proc.returncode

    return CompileResult(output, exit_code)


# --- Error and expectatino handling ------------------------------------------

def parse_errors(output: str):
    errors = []
    stderr = []

    for line in output.splitlines():
        match = re.match('Error in line (?P<line>\d+):(?P<col>\d+): ?'
                         '(?P<error>.*)', line)
        if match is not None:
            errors.append(CompilerError(match.groupdict()))
            continue

        match = re.match('Error: (?P<error>.*)', line)
        if match is not None:
            errors.append(CompilerError(match.groupdict()))
            continue

        stderr.append(line)

    return errors, stderr


def parse_expectations(filename: Path):
    expectations = []

    with filename.open(encoding='utf-8') as f:
        for line in f.readlines():
            match = re.match('.*//! ERROR\((?P<line>\d+):(?P<col>\d+)\): ?'
                             '(?P<error>.*)', line)
            if match is not None:
                expectations.append(CompilerError(match.groupdict()))
                continue

            match = re.match('.*//! ERROR: (?P<error>.*)', line)
            if match is not None:
                expectations.append(CompilerError(match.groupdict()))
                continue

    return expectations


# --- Compile a file ----------------------------------------------------------

def collect_categorized_tests(name):
    for cat in (TEST_DIR / name).iterdir():
        for test in sorted(list((TEST_DIR / cat).iterdir())):
            yield cat.name, test


def tests_compiler():
    try:
        subprocess.check_call(['cargo', 'test'], cwd=str(RUSTINY_DIR))
    except subprocess.CalledProcessError:
        cprint('Compiler unit tests failed!', 'red')
        sys.exit(1)


def tests_compile_fail():
    cprint('Running compile-fail tests...', 'blue')

    for category, test in collect_categorized_tests('compile-fail'):
        test_name = test.name
        print('Testing {}/{} ... '.format(category, test_name), end='')

        expectations = parse_expectations(test)
        cresult = compile_file(test)

        if cresult.exit_code == 0:
            session.failure(FailedTest(test, test_name, None, None, cresult.output,
                                       'compiling succeeded'))
        else:
            # Verify errors
            errors, stderr = parse_errors(cresult.output)
            unexpected_errors = set(errors) - set(expectations)
            missing_errors = set(expectations) - set(errors)

            if not unexpected_errors and not missing_errors:
                session.success()
            else:
                session.failure(FailedTest(test, test_name,
                                           unexpected_errors,
                                           missing_errors,
                                           '\n'.join(stderr),
                                           None))


def tests_run_pass():
    cprint('Running run-pass tests...', 'blue')

    for category, test in collect_categorized_tests('run-pass'):
        test_name = test.parts[-1]
        print('Testing {}/{} ... '.format(category, test_name), end='')

        cresult = compile_file(test)

        # Verify errors
        errors, stderr = parse_errors(cresult.output)

        if not errors and cresult.exit_code == 0:
            session.success()
        else:
            session.failure(FailedTest(test, test_name, errors, None,
                                       '\n'.join(stderr), None))


def tests_ir():
    cprint('Running IR tests...', 'blue')

    tests = [name for name in sorted(list((TEST_DIR / 'ir').iterdir()))
             if name.suffix == '.rs']

    for test in tests:
        test_name = test.parts[-1]
        print('Testing {} ... '.format(test_name), end='')

        # Get generated IR
        cresult = compile_file(test, ['--ir'])

        if cresult.exit_code != 0:
            session.failure(FailedTest(test, test_name, None, None, cresult.output,
                                       'compiling failed'))
            continue

        generated_ir = cresult.output.strip()

        # Get expceted IR
        with (TEST_DIR / 'ir' / (test.stem + '.ir')).open() as f:
            expected_ir = f.read().strip()

        if generated_ir == expected_ir:
            session.success()
        else:
            session.failure(FailedTest(test, test_name, None, None,
                            None, '\n   {}\n{}\n\n   {}\n{}'.format(colored('Expected IR:', 'cyan'), expected_ir, colored('Generated IR:', 'cyan'), generated_ir)))


def print_results():
    print()

    if session.failed > 0:
        cprint('{} tests failed; '.format(session.failed), 'red', end='')
        print('{} tests passed'.format(session.passed))

        for failure in session.failures:
            print()
            print('--- Test {}: {}'.format(failure.path, failure.msg or ''))

            if failure.unexpected:
                print('Unexpected errors:')
                for unexpected in failure.unexpected:
                    print('   ' + str(unexpected))


            if failure.missing:
                print('Missing errors:')
                for missing in failure.missing:
                    print('   ' + str(missing))


            if failure.output:
                print('Compiler output:')
                print('   ' + '\n   '.join(failure.output.splitlines()))

    else:
        print('{}'.format(
            colored('{} tests passed'.format(session.passed), 'green'),
            session.passed, session.failed))


def refresh_compiler():
    try:
        subprocess.check_call(['cargo', 'build'], cwd=str(RUSTINY_DIR))
    except subprocess.CalledProcessError:
        cprint('Compiling the compiler failed!', 'red')
        sys.exit(1)



if __name__ == '__main__':
    cprint('Refreshing the compiler...', 'blue')
    refresh_compiler()

    cprint('Running compiler unit tests...', 'blue')
    tests_compiler()

    tests_compile_fail()
    print()
    tests_run_pass()
    print()
    tests_ir()

    print_results()

    if session.failed > 0:
        sys.exit(1)
