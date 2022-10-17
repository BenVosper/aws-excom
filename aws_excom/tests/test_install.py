from os.path import abspath, join, dirname

here = abspath(__file__)
package_path = join(dirname(here), "..", "..")


def test_install(virtualenv):
    virtualenv.run(f"pip install {package_path}")
    assert "aws-excom" in virtualenv.installed_packages()

    script_path = virtualenv.run("which aws-excom", capture=True)
    assert script_path.endswith("aws-excom\n")

    help_output = virtualenv.run("aws-excom --help", capture=True)
    assert "Interactive script to call 'aws ecs execute-command'" in help_output
