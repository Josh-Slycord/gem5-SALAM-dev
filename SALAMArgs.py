import argparse


def HWArgs():
    parser = argparse.ArgumentParser(
        description='Parse command line args for hardware generator'
    )
    parser.add_argument('-b', '--bench', type=str, required=True, help='Name of benchmark')
    parser.add_argument('-m', '--model', type=str, default='40nm_model', help='Hardware model name')
    parser.add_argument('-l', '--latency', type=str, default='5ns', help='Hardware latency/period')
    parser.add_argument('-p', '--profile', type=str, default='default_profile', help='Hardware profile name')
    return parser.parse_args()
