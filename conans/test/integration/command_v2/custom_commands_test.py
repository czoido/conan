import os
import textwrap

from conans.test.utils.tools import TestClient


class TestCustomCommands:
    def test_simple_custom_command(self):
        mycommand = textwrap.dedent("""
            import json
            import os

            from conans.cli.output import cli_out_write
            from conans.cli.command import conan_command

            def output_mycommand_cli(info):
                cli_out_write(f"Conan cache folder is: {info.get('cache_folder')}")

            def output_mycommand_json(info):
                cli_out_write(json.dumps(info))

            @conan_command(group="custom commands",
                           formatters={"cli": output_mycommand_cli,
                                       "json": output_mycommand_json})
            def mycommand(conan_api, parser, *args, **kwargs):
                \"""
                this is my custom command, it will print the location of the cache folder
                \"""
                info = {"cache_folder": os.path.basename(conan_api.cache_folder)}
                return info
            """)

        client = TestClient()
        command_file_path = os.path.join(client.cache_folder, 'commands', 'cmd_mycommand.py')
        client.save({f"{command_file_path}": mycommand})
        client.run("mycommand")
        foldername = os.path.basename(client.cache_folder)
        assert f'Conan cache folder is: {foldername}' in client.out
        client.run("mycommand -f json")
        assert f'{{"cache_folder": "{foldername}"}}' in client.out

    def test_custom_command_with_subcommands(self):
        complex_command = textwrap.dedent("""
            import json

            from conans.cli.output import cli_out_write
            from conans.cli.command import conan_command, conan_subcommand

            def output_cli(info):
                cli_out_write(f"{info.get('argument1')}")

            def output_json(info):
                cli_out_write(json.dumps(info))

            @conan_subcommand(formatters={"cli": output_cli, "json": output_json})
            def complex_sub1(conan_api, parser, subparser, *args):
                \"""
                sub1 subcommand
                \"""
                subparser.add_argument("argument1", help="This is argument number 1")
                args = parser.parse_args(*args)
                info = {"argument1": args.argument1}
                return info

            @conan_command()
            def complex(conan_api, parser, *args, **kwargs):
                \"""
                this is a command with subcommands
                \"""
            """)

        client = TestClient()
        command_file_path = os.path.join(client.cache_folder, 'commands', 'cmd_complex.py')
        client.save({f"{command_file_path}": complex_command})
        client.run("complex sub1 myargument")
        assert "myargument" in client.out
        client.run("complex sub1 myargument -f json")
        assert f'{{"argument1": "myargument"}}' in client.out
