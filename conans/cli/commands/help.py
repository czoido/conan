import textwrap

from conans.cli.output import CliOutput
from conans.client.output import Color
from conans.errors import ConanException
from conans.cli.command import conan_command


def output_help_cli(out, commands, groups):
    """
    Prints a summary of all commands.
    """
    max_len = max((len(c) for c in commands)) + 1
    fmt = '  %-{}s'.format(max_len)

    for group_name, comm_names in groups.items():
        out.info(group_name, Color.BRIGHT_MAGENTA)
        for name in comm_names:
            # future-proof way to ensure tabular formatting
            out.info(fmt % name, Color.GREEN)

            # Help will be all the lines up to the first empty one
            docstring_lines = commands[name].doc.split('\n')
            start = False
            data = []
            for line in docstring_lines:
                line = line.strip()
                if not line:
                    if start:
                        break
                    start = True
                    continue
                data.append(line)

            txt = textwrap.fill(' '.join(data), 80, subsequent_indent=" " * (max_len + 2))
            out.info(txt)

    out.info("")
    out.info('Conan commands. Type "conan <command> -h" for help', Color.BRIGHT_YELLOW)


@conan_command(group="Misc", formatters={"cli": output_help_cli})
def help(conan_api, parser, *args, commands, groups, **kwargs):
    """
    Shows help for a specific command.
    """

    parser.add_argument("command", help='command', nargs="?")
    args = parser.parse_args(*args)
    if not args.command:
        output_help_cli(conan_api.out, commands, groups)
        return None
    try:
        commands[args.command].run(conan_api, CliOutput(), commands[args.command].parser, ["--help"])
    except KeyError:
        raise ConanException("Unknown command '%s'" % args.command)
